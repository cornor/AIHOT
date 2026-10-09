import "./setup.ts";
import assert from "node:assert/strict";
import { after, beforeEach, test } from "node:test";
import Fastify from "fastify";
import { randomBytes } from "node:crypto";
import { config } from "@aihot/backend/config";
import { sql, closeDb } from "@aihot/backend/db";
import { sha256 } from "@aihot/backend/lib/ids";
import { safeSiteReturn, startSso, completeSso, setSsoAccess, ssoPrincipal, SSO_COOKIE, SSO_STATE_COOKIE, SSO_CHECK_URL } from "@aihot/backend/admin/sso";
import { registerSsoAuth } from "../apps/api/src/routes/sso-auth.ts";
import { registerAdminAuth } from "../apps/api/src/routes/admin-auth.ts";
import { isApiOwned } from "@aihot/contracts/http-policy";
import { tag } from "./setup.ts";

const T = `sso-${tag()}`;
const saved = { site: config.siteUrl, environment: config.environmentName, dev: config.devAdmin, enabled: process.env.SSO_ENABLED, allow: process.env.SSO_ALLOW_ALL };
const realFetch = globalThis.fetch;
let account = `${T}-reader`, response: unknown, providerHits = 0;
const states: string[] = [];
globalThis.fetch = (async (input: string | URL | Request, init?: RequestInit) => {
  assert.equal(String(input), SSO_CHECK_URL, "SSO tests cannot access any network service");
  assert.equal(init?.method, "POST"); assert.equal(init?.redirect, "error");
  assert.equal(new Headers(init?.headers).get("content-type"), "application/x-www-form-urlencoded");
  assert.equal(new URLSearchParams(String(init?.body)).get("token"), "synthetic-company-token");
  providerHits++;
  if (response instanceof Error) throw response;
  return new Response(JSON.stringify(response ?? { code: 0, data: { account, name: "测试员工" } }), { status: 200 });
}) as typeof fetch;
const app = Fastify({ logger: false });
registerAdminAuth(app); registerSsoAuth(app);
const headersFor = (token: string) => ({ cookie: `${SSO_COOKIE}=${token}` });
async function requestState(returnTo = "/all?category=tech") {
  const request = await startSso(returnTo);
  const callback = new URL(new URL(request.url).searchParams.get("url")!);
  assert.equal(callback.origin, config.siteUrl);
  assert.equal(callback.pathname, "/sso/callback");
  const state = callback.searchParams.get("state")!; states.push(sha256(state));
  return { state, browser: request.browser };
}
async function login(returnTo?: string) {
  const { state, browser } = await requestState(returnTo);
  return completeSso("synthetic-company-token", state, browser);
}
async function allow(role: "reader" | "admin" = "reader", enabled = true) {
  return setSsoAccess({ account, role, enabled, reason: "synthetic test" }, T);
}
beforeEach(() => {
  config.siteUrl = "https://gamehot.example.test";
  config.environmentName = "production"; config.devAdmin = null;
  process.env.SSO_ENABLED = "true"; process.env.SSO_ALLOW_ALL = "false";
  response = undefined;
});
after(async () => {
  globalThis.fetch = realFetch;
  await app.close();
  await sql`DELETE FROM sso_login_requests WHERE state_hash=ANY(${states})`;
  await sql`DELETE FROM sso_users WHERE account LIKE ${T + '%'}`;
  await sql`DELETE FROM admin_users WHERE sso_account LIKE ${T + '%'}`;
  await sql`DELETE FROM audit_log WHERE actor=${T} OR actor LIKE ${'sso:' + T + '%'}`;
  config.siteUrl = saved.site; config.environmentName = saved.environment; config.devAdmin = saved.dev;
  for (const [key, value] of [["SSO_ENABLED", saved.enabled], ["SSO_ALLOW_ALL", saved.allow]]) {
    if (value === undefined) delete process.env[key!]; else process.env[key!] = value;
  }
  await closeDb();
});

test("return URLs stay on this site and never restart authentication", () => {
  for (const url of ["//evil.test", "https://evil.test", "/\\evil", "/%2fexample.test", "/%5cevil", "/a/../../..//evil", "/api/auth/logout", "/sso/callback?token=x", "/admin/login", "/a%0ab", "%bad"]) assert.equal(safeSiteReturn(url), "/", url);
  assert.equal(safeSiteReturn("/all?q=game#top"), "/all?q=game");
  assert.equal(isApiOwned("/sso/callback"), true);
});

test("unknown employees are recorded pending, without any site/admin session", async () => {
  await assert.rejects(login(), /尚未开通/);
  const [row] = await sql`SELECT role,enabled FROM sso_users WHERE account=${account}`;
  assert.equal(row!.enabled, false); assert.equal(row!.role, "reader");
  assert.equal((await sql`SELECT 1 FROM sso_sessions WHERE account=${account}`).length, 0);
});

test("reader can enter the site, cannot read or write admin endpoints or WeRSS auth", async () => {
  await allow();
  const result = await login("/werss/"); assert.equal(result.returnTo, "/");
  const headers = headersFor(result.token);
  assert.equal((await app.inject({ url: "/api/auth/site-check", headers })).statusCode, 204);
  assert.equal((await app.inject({ url: "/api/auth/me", headers })).json().account, account);
  for (const url of ["/api/auth/check", "/api/admin/me", "/api/admin/users"]) assert.equal((await app.inject({ url, headers })).statusCode, 403);
  assert.equal((await app.inject({ method: "POST", url: "/api/admin/users", headers, payload: { account, role: "admin", enabled: true, reason: "attack" } })).statusCode, 403);
  const [session] = await sql`SELECT * FROM sso_sessions WHERE account=${account}`;
  assert.equal(session!.id_hash, sha256(result.token));
  assert.ok(!JSON.stringify(session).includes(result.token));
  assert.ok(!JSON.stringify(session).includes("synthetic-company-token"));
  assert.ok(Math.abs(new Date(session!.expires_at).getTime() - Date.now() - 8 * 3600_000) < 5000);
});

test("admin mutations require CSRF and revocation removes existing sessions", async () => {
  account = `${T}-admin`; await allow("admin");
  const result = await login("/admin/users"); assert.equal(result.returnTo, "/admin/users");
  const headers = headersFor(result.token);
  assert.equal((await app.inject({ url: "/api/auth/check", headers })).statusCode, 204);
  const me = (await app.inject({ url: "/api/admin/me", headers })).json();
  const payload = { account, enabled: true, role: "reader", reason: "remove admin role" };
  assert.equal((await app.inject({ method: "POST", url: "/api/admin/users", headers, payload })).statusCode, 403);
  assert.equal((await app.inject({ method: "POST", url: "/api/admin/users", headers: { ...headers, "x-csrf-token": me.csrf }, payload })).statusCode, 200);
  assert.equal(await ssoPrincipal(result.token), null);
  assert.equal((await app.inject({ url: "/api/auth/site-check", headers })).statusCode, 401);
  const reader = await login(); await allow("reader", false);
  assert.equal(await ssoPrincipal(reader.token), null);
  await assert.rejects(login(), /尚未开通/);
  assert.ok((await sql`SELECT 1 FROM audit_log WHERE actor LIKE 'admin:%' AND action='sso.access' AND subject=${account}`).length);
});

test("state is browser-bound, expires, and is consumed once before contacting SSO", async () => {
  account = `${T}-reader`; await allow();
  const { state, browser } = await requestState(); const hits = providerHits;
  await assert.rejects(completeSso("synthetic-company-token", state, randomBytes(32).toString("base64url")), /已失效/);
  assert.equal(providerHits, hits);
  await completeSso("synthetic-company-token", state, browser);
  await assert.rejects(completeSso("synthetic-company-token", state, browser), /已失效/);
  assert.equal(providerHits, hits + 1);
  const expired = await requestState();
  await sql`UPDATE sso_login_requests SET expires_at=now()-interval '1 second' WHERE state_hash=${sha256(expired.state)}`;
  await assert.rejects(completeSso("synthetic-company-token", expired.state, expired.browser), /已失效/);
});

test("upstream failures and malformed identities fail closed without echoing provider data", async () => {
  for (const value of [{ code: 1, message: "secret-provider-value" }, { code: 0, data: {} }, { code: 0, data: { account: " " } }, { code: 0, data: { account: 123 } }, new Error("secret-provider-value")]) {
    response = value;
    const { state, browser } = await requestState();
    const result = await app.inject({ method: "POST", url: "/api/auth/sso/callback", headers: { origin: config.siteUrl, cookie: `${SSO_STATE_COOKIE}=${browser}` }, payload: { state, token: "synthetic-company-token" } });
    assert.ok([403, 503].includes(result.statusCode));
    assert.ok(!result.body.includes("secret-provider-value"));
    assert.ok(!result.body.includes("synthetic-company-token"));
    assert.ok(!JSON.stringify(result.headers['set-cookie']).includes(`${SSO_COOKIE}=`));
  }
});

test("callback enforces origin and sets Secure HttpOnly sessions; logout/expiry revoke them", async () => {
  await allow(); const { state, browser } = await requestState("/all");
  const input = { method: "POST" as const, url: "/api/auth/sso/callback", headers: { origin: "https://evil.test", cookie: `${SSO_STATE_COOKIE}=${browser}` }, payload: { state, token: "synthetic-company-token" } };
  assert.equal((await app.inject(input)).statusCode, 403);
  const result = await app.inject({ ...input, headers: { ...input.headers, origin: config.siteUrl } });
  assert.equal(result.statusCode, 200); assert.equal(result.json().returnTo, "/all");
  const cookies = result.headers["set-cookie"] as string[];
  const session = cookies.find(c => c.startsWith(`${SSO_COOKIE}=`))!;
  assert.match(session, /HttpOnly/); assert.match(session, /Secure/); assert.match(session, /SameSite=Lax/);
  const token = session.split(";")[0]!.split("=")[1]!;
  assert.ok(await ssoPrincipal(token));
  assert.equal((await app.inject({ method: "POST", url: "/api/auth/logout", headers: { ...headersFor(token), origin: config.siteUrl } })).statusCode, 303);
  assert.equal(await ssoPrincipal(token), null);
  const expired = await login();
  await sql`UPDATE sso_sessions SET expires_at=now()-interval '1 second' WHERE id_hash=${sha256(expired.token)}`;
  assert.equal(await ssoPrincipal(expired.token), null);
});

test("callback contains no provider data or shared page resources and is never cached", async () => {
  const page = await app.inject({ url: "/sso/callback?token=synthetic-company-token" });
  assert.equal(page.statusCode, 200); assert.equal(page.headers["referrer-policy"], "no-referrer");
  assert.equal(page.headers["cache-control"], "no-store");
  assert.match(String(page.headers["content-security-policy"]), /default-src 'none'/);
  assert.ok(!page.body.includes("synthetic-company-token"));
  const script = await app.inject({ url: "/api/auth/sso/callback.js" });
  assert.ok(script.body.indexOf("history.replaceState") < script.body.indexOf("await fetch"));
  assert.ok(!script.body.includes("localStorage"));
  const bad = await app.inject({ method: "POST", url: "/api/auth/sso/callback", headers: { "content-type": "application/json", origin: config.siteUrl }, payload: '{"token":"synthetic-company-token"' });
  assert.equal(bad.statusCode, 400); assert.ok(!bad.body.includes("synthetic-company-token"));
});

test("SSO disabled and non-HTTPS production refuse starting a login", async () => {
  process.env.SSO_ENABLED = "false"; await assert.rejects(startSso("/"));
  process.env.SSO_ENABLED = "true"; config.siteUrl = "http://example.test"; await assert.rejects(startSso("/"));
});

test("allow-all is explicitly opt-in and never upgrades readers to administrators", async () => {
  account = `${T}-auto`; process.env.SSO_ALLOW_ALL = "true";
  const result = await login(); assert.equal((await ssoPrincipal(result.token))!.role, "reader");
  await allow("reader", false);
  await assert.rejects(login(), /尚未开通/, "explicitly disabled accounts stay disabled even in allow-all mode");
});
