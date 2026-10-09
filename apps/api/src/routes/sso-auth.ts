import type { FastifyInstance } from "fastify";
import { config } from "@aihot/backend/config";
import { completeSso, endSsoSession, startSso, ssoPrincipal, ssoEnabled, SsoRejected, SSO_COOKIE, SSO_STATE_COOKIE, SSO_SESSION_SECONDS, listSsoUsers, setSsoAccess } from "@aihot/backend/admin/sso";
import { parseCookies, cookie, SESSION_COOKIE, sessionPrincipal, endSession, actorOf } from "@aihot/backend/admin/auth";
import { adminHandler } from "./admin-auth.ts";

export function registerSsoAuth(app: FastifyInstance) {
  const secure = () => config.siteUrl.startsWith("https://");
  const headers = { "Cache-Control": "no-store", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow" };
  const attempts = new Map<string, { count: number; reset: number }>();
  app.get("/api/auth/sso/start", async (req, reply) => {
    reply.headers(headers);
    const now = Date.now();
    if (attempts.size > 5000) attempts.clear();
    const keys = [req.ip, "all"];
    let limited = false;
    for (const key of keys) {
      const prior = attempts.get(key);
      const row = prior && prior.reset > now ? prior : { count: 0, reset: now + 15 * 60_000 };
      row.count++; attempts.set(key, row);
      if (row.count > (key === "all" ? 500 : 30)) limited = true;
    }
    if (limited) return reply.code(429).send({ message: "登录尝试过多，请稍后再试" });
    try {
      const result = await startSso(String((req.query as Record<string, string>).return ?? "/"));
      return reply.header("Set-Cookie", cookie(SSO_STATE_COOKIE, result.browser, 600, secure())).redirect(result.url, 302);
    } catch { return reply.code(503).send({ message: "公司登录暂不可用" }); }
  });
  // A standalone callback avoids analytics, shared page loaders, and third-party resources.
  app.get("/sso/callback", async (_req, reply) => reply.headers(headers)
    .header("Content-Security-Policy", "default-src 'none'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
    .type("text/html; charset=utf-8").send('<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>公司账号登录</title><p id="status">正在验证登录…</p><a href="/admin/login">返回登录</a><script src="/api/auth/sso/callback.js"></script></html>'));
  app.get("/api/auth/sso/callback.js", async (_req, reply) => reply.headers(headers).type("text/javascript; charset=utf-8").send(`
(async () => {
  const params = new URLSearchParams(location.search);
  const token = params.get('token'), state = params.get('state');
  history.replaceState(null, '', '/sso/callback');
  try {
    if (!token || !state) throw new Error('缺少登录凭据，请重新登录');
    const response = await fetch('/api/auth/sso/callback', {method:'POST', credentials:'same-origin', headers:{'content-type':'application/json'}, body:JSON.stringify({token,state})});
    const result = await response.json();
    if (!response.ok) throw new Error(result.message || '登录失败，请重新登录');
    location.replace(result.returnTo);
  } catch (error) { document.getElementById('status').textContent = error.message || '登录失败，请重新登录'; }
})();`));
  app.post("/api/auth/sso/callback", { bodyLimit: 16 * 1024,
    errorHandler: (_error, _req, reply) => reply.code(400).headers(headers).send({ message: "登录请求无效，请重新登录" }),
  }, async (req, reply) => {
    reply.headers(headers);
    if (req.headers.origin !== new URL(config.siteUrl).origin) return reply.code(403).send({ message: "登录请求来源无效" });
    const b = (req.body ?? {}) as Record<string, unknown>;
    const cookies = parseCookies(req.headers.cookie);
    try {
      const result = await completeSso(typeof b.token === "string" ? b.token : "", typeof b.state === "string" ? b.state : "", cookies[SSO_STATE_COOKIE]);
      await endSession(req.headers.cookie);
      await endSsoSession(cookies[SSO_COOKIE]);
      return reply.header("Set-Cookie", [cookie(SSO_COOKIE, result.token, SSO_SESSION_SECONDS, secure()), cookie(SSO_STATE_COOKIE, "", 0, secure()), cookie(SESSION_COOKIE, "", 0, secure())]).send({ returnTo: result.returnTo });
    } catch (error) {
      // Never log the callback body, provider payload, or token-bearing exceptions.
      return reply.code(error instanceof SsoRejected ? 403 : 503).header("Set-Cookie", cookie(SSO_STATE_COOKIE, "", 0, secure()))
        .send({ message: error instanceof SsoRejected ? error.message : "公司登录暂不可用，请稍后重新登录" });
    }
  });
  app.get("/api/auth/site-check", async (req, reply) => {
    reply.headers(headers);
    const company = await ssoPrincipal(parseCookies(req.headers.cookie)[SSO_COOKIE]);
    const admin = company ? null : await sessionPrincipal(req.headers.cookie);
    return reply.code(company || (admin && !admin.dev) ? 204 : 401).send();
  });
  app.get("/api/auth/me", async (req, reply) => {
    reply.headers(headers);
    const company = await ssoPrincipal(parseCookies(req.headers.cookie)[SSO_COOKIE]);
    if (company) return { name: company.name, account: company.account, role: company.role };
    const admin = await sessionPrincipal(req.headers.cookie);
    return admin ? { name: admin.name, account: "", role: "admin" } : reply.code(401).send({ message: "请先登录" });
  });
  app.get("/api/admin/users", adminHandler(async () => ({ rows: await listSsoUsers(), allowAll: process.env.SSO_ALLOW_ALL === "true", ssoEnabled: ssoEnabled() })));
  app.post("/api/admin/users", adminHandler(async (req, _reply, admin) => setSsoAccess(req.body, actorOf(admin))));
}
