import { useState } from "react";
import type { Route } from "./+types/users";
import { adminGet } from "../../lib/admin.server";
import { useAdminAction } from "../../features/admin/action";
import { AdminPage, Button, Card, Input } from "../../features/admin/ui";

type User = { account: string; display_name: string; role: "reader" | "admin"; enabled: boolean; last_login_at: string | null };
export async function loader({ request }: Route.LoaderArgs) {
  return adminGet<{ rows: User[]; allowAll: boolean; ssoEnabled: boolean }>(request, "/api/admin/users");
}
export default function Users({ loaderData: data }: Route.ComponentProps) {
  const [account, setAccount] = useState("");
  const [role, setRole] = useState<"reader" | "admin">("reader");
  const [enabled, setEnabled] = useState(true);
  const [reason, setReason] = useState("");
  const { run, busy } = useAdminAction();
  return <AdminPage title="账号与权限" subtitle="读者可浏览资讯；管理员可管理站点和访问 WeRSS。权限调整立即使该账号的已有会话失效。">
    <div className="space-y-5">
      <Card title="公司登录">
        <p className="text-sm text-ink-3">{data.ssoEnabled ? "已启用" : "未启用"} · {data.allowAll ? "新公司账号自动开通读者权限" : "新公司账号需要管理员开通"}</p>
      </Card>
      <Card title="开通或调整账号">
        <form className="grid max-w-xl gap-4" onSubmit={async e => {
          e.preventDefault();
          const result = await run("POST", "/api/admin/users", { account: account.trim(), role, enabled, reason }, { success: "权限已保存，该账号需要重新登录" });
          if (result) setReason("");
        }}>
          <label className="text-sm">公司 account<Input required maxLength={160} value={account} onChange={e => setAccount(e.target.value)} placeholder="填写公司 SSO 返回的准确账号" /></label>
          <label className="text-sm">权限<select className="ml-3 rounded border border-line bg-surface p-2" value={role} onChange={e => setRole(e.target.value as "reader" | "admin")}><option value="reader">读者</option><option value="admin">管理员</option></select></label>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />允许访问本站</label>
          <label className="text-sm">调整原因<Input required maxLength={500} value={reason} onChange={e => setReason(e.target.value)} /></label>
          <Button type="submit" tone="primary" disabled={busy}>保存权限</Button>
        </form>
      </Card>
      <Card title="公司账号（最多显示最近 1000 个）">
        <div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead><tr><th className="p-2">账号 / 姓名</th><th>权限</th><th>状态</th><th>操作</th></tr></thead><tbody>
          {data.rows.map(user => <tr key={user.account} className="border-t border-line"><td className="p-2">{user.account}<div className="text-xs text-ink-4">{user.display_name}</div></td><td>{user.role === "admin" ? "管理员" : "读者"}</td><td>{user.enabled ? "已开通" : "未开通 / 已停用"}</td><td><Button size="sm" onClick={() => { setAccount(user.account); setRole(user.role); setEnabled(user.enabled); setReason(""); window.scrollTo({ top: 0, behavior: "smooth" }); }}>调整</Button></td></tr>)}
          {!data.rows.length && <tr><td colSpan={4} className="p-4 text-ink-4">暂无账号。可提前填写准确的 account 开通，或等待员工首次公司登录后在这里开通。</td></tr>}
        </tbody></table></div>
      </Card>
    </div>
  </AdminPage>;
}
