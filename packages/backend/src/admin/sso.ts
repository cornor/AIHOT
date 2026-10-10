import { randomBytes } from "node:crypto";
import { z } from "zod";
import { config } from "../config.ts";
import { sql } from "../db.ts";
import { sha256 } from "../lib/ids.ts";
import { audit } from "../audit.ts";

export const SSO_COOKIE = "gamehot_session";
export const SSO_STATE_COOKIE = "gamehot_sso_state";
export const SSO_SESSION_SECONDS = 8 * 3600;
export const SSO_LOGIN_URL = "https://account.xmpaoyou.com/sso";
export const SSO_CHECK_URL = "https://account.xmpaoyou.com/api/sso/check-token";
export const ssoEnabled = () => process.env.SSO_ENABLED === "true";
export class SsoRejected extends Error {}

export function safeSiteReturn(input: string): string {
  try {
    const decoded = decodeURIComponent(input);
    if (!decoded.startsWith("/") || decoded.startsWith("//") || /[\\\x00-\x20\x7f]/.test(decoded)) return "/";
    const url = new URL(input, "https://local.invalid");
    const path = decodeURIComponent(url.pathname);
    if (url.origin !== "https://local.invalid" || path.startsWith("//") || /^\/(api\/auth|sso|(?:admin\/)?login(?:\.data)?)(\/|$)/.test(path)) return "/";
    return url.pathname + url.search;
  } catch { return "/"; }
}

export async function startSso(returnTo: string) {
  if (!ssoEnabled() || (config.environmentName === "production" && !config.siteUrl.startsWith("https://"))) throw new SsoRejected("公司登录尚未启用");
  const state = randomBytes(32).toString("base64url");
  const browser = randomBytes(32).toString("base64url");
  await sql`DELETE FROM sso_login_requests WHERE expires_at < now()`;
  await sql`DELETE FROM sso_sessions WHERE expires_at < now()`;
  await sql`INSERT INTO sso_login_requests(state_hash,browser_hash,return_to,expires_at)
    VALUES(${sha256(state)},${sha256(browser)},${safeSiteReturn(returnTo)},now()+interval '10 minutes')`;
  const callback = new URL("/sso/callback", config.siteUrl);
  callback.searchParams.set("state", state);
  return { browser, url: `${SSO_LOGIN_URL}?${new URLSearchParams({ url: callback.href })}` };
}

const Identity = z.object({ account: z.string().min(1).max(160).regex(/^[^\s\x00-\x1f\x7f]+$/), name: z.string().max(200).optional().default("") });
export async function verifySsoToken(token: string) {
  const response = await fetch(SSO_CHECK_URL, { method: "POST", redirect: "error",
    headers: { "content-type": "application/x-www-form-urlencoded" }, body: new URLSearchParams({ token }), signal: AbortSignal.timeout(15_000) });
  if (!response.ok) throw new SsoRejected("公司登录校验暂不可用，请重新登录");
  const value = await response.json() as { code?: number; data?: unknown };
  if (value.code !== 0) throw new SsoRejected("公司登录凭据无效或已过期，请重新登录");
  const parsed = Identity.safeParse(value.data);
  if (!parsed.success) throw new SsoRejected("公司登录返回的账号信息不完整");
  return parsed.data;
}

export async function completeSso(token: string, state: string, browser: string | undefined) {
  if (!ssoEnabled() || !browser || !/^[\w-]{43}$/.test(state) || !/^[\w-]{43}$/.test(browser) || !token || token.length > 8192 || /[\x00-\x20\x7f]/.test(token)) throw new SsoRejected("登录请求已失效，请重新登录");
  const [request] = await sql<{ return_to: string }[]>`DELETE FROM sso_login_requests
    WHERE state_hash=${sha256(state)} AND browser_hash=${sha256(browser)} AND expires_at>now() RETURNING return_to`;
  if (!request) throw new SsoRejected("登录请求已失效，请重新登录");
  const identity = await verifySsoToken(token);
  const session = randomBytes(32).toString("base64url");
  const user = await sql.begin(async tx => {
    await tx`INSERT INTO sso_users(account,display_name,enabled) VALUES(${identity.account},${identity.name || identity.account},${process.env.SSO_ALLOW_ALL === "true"})
      ON CONFLICT(account) DO NOTHING`;
    const [row] = await tx<{ role: "reader" | "admin"; enabled: boolean }[]>`SELECT role,enabled FROM sso_users WHERE account=${identity.account} FOR UPDATE`;
    await tx`UPDATE sso_users SET display_name=${identity.name || identity.account},last_login_at=now() WHERE account=${identity.account}`;
    if (!row!.enabled) return null;
    await tx`INSERT INTO sso_sessions(id_hash,account,csrf_token,expires_at)
      VALUES(${sha256(session)},${identity.account},${randomBytes(18).toString("base64url")},now()+interval '8 hours')`;
    return row!;
  });
  if (!user) throw new SsoRejected("此账号尚未开通本站权限，请联系管理员");
  await audit(`sso:${identity.account}`, "auth.sso.login", null, null, null, { account: identity.account });
  const restricted = /^\/(admin|werss)(\/|\?|$)/.test(request.return_to);
  return { token: session, returnTo: restricted && user.role !== "admin" ? "/" : safeSiteReturn(request.return_to) };
}

export interface SsoPrincipal { account: string; name: string; role: "reader" | "admin"; admin_user_id: number | null; csrf: string }
export async function ssoPrincipal(token: string | undefined): Promise<SsoPrincipal | null> {
  if (!ssoEnabled() || !token || !/^[\w-]{43}$/.test(token)) return null;
  const [row] = await sql<SsoPrincipal[]>`SELECT u.account,u.display_name AS name,u.role,u.admin_user_id,s.csrf_token AS csrf
    FROM sso_sessions s JOIN sso_users u USING(account) WHERE s.id_hash=${sha256(token)} AND s.expires_at>now() AND u.enabled`;
  return row ?? null;
}
export async function endSsoSession(token: string | undefined) {
  if (token) await sql`DELETE FROM sso_sessions WHERE id_hash=${sha256(token)}`;
}
export async function listSsoUsers() {
  return sql`SELECT account,display_name,role,enabled,last_login_at FROM sso_users ORDER BY created_at DESC LIMIT 1000`;
}
const Access = z.object({ account: Identity.shape.account, role: z.enum(["reader", "admin"]), enabled: z.boolean(), reason: z.string().trim().min(1).max(500) });
export async function setSsoAccess(input: unknown, actor: string) {
  const value = Access.parse(input);
  return sql.begin(async tx => {
    await tx`SELECT pg_advisory_xact_lock(hashtext('sso-user:' || ${value.account}))`;
    const [before] = await tx`SELECT account,role,enabled FROM sso_users WHERE account=${value.account} FOR UPDATE`;
    let adminId: number | null = null;
    if (value.role === "admin") {
      const [admin] = await tx`INSERT INTO admin_users(sso_account,display_name) VALUES(${value.account},${value.account})
        ON CONFLICT(sso_account) DO UPDATE SET sso_account=EXCLUDED.sso_account RETURNING id`;
      adminId = Number(admin!.id);
    }
    await tx`INSERT INTO sso_users(account,display_name,role,enabled,admin_user_id)
      VALUES(${value.account},${value.account},${value.role},${value.enabled},${adminId})
      ON CONFLICT(account) DO UPDATE SET role=EXCLUDED.role,enabled=EXCLUDED.enabled,admin_user_id=EXCLUDED.admin_user_id`;
    await tx`DELETE FROM sso_sessions WHERE account=${value.account}`;
    await audit(actor, "sso.access", value.account, value.reason, before, { role: value.role, enabled: value.enabled }, { db: tx });
    return { account: value.account, role: value.role, enabled: value.enabled };
  });
}
