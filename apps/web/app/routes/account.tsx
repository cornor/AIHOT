import type { Route } from "./+types/account";
import { adminGet } from "../lib/admin.server";
import { buttonClass } from "../components/ui/Controls";

export async function loader({ request }: Route.LoaderArgs) {
  return adminGet<{ name: string; account: string; role: "reader" | "admin" }>(request, "/api/auth/me");
}
export const headers = () => ({ "Cache-Control": "private, no-store" });
export const meta = () => [{ title: "我的账号" }, { name: "robots", content: "noindex, nofollow" }];
export default function Account({ loaderData: me }: Route.ComponentProps) {
  return <div className="mx-auto max-w-xl py-6">
    <h1 className="mb-5 text-2xl font-bold">我的账号</h1>
    <div className="card space-y-4 p-6">
      <p className="text-lg font-medium">{me.name}</p>
      {me.account && <p className="text-sm text-ink-3">公司账号：{me.account}</p>}
      <p className="text-sm text-ink-3">本站权限：{me.role === "admin" ? "管理员" : "读者"}</p>
      {me.role === "admin" && <div className="flex gap-4 text-accent"><a href="/admin">管理后台</a><a href="/werss/">WeRSS</a></div>}
      <form method="post" action="/api/auth/logout"><button className={buttonClass("secondary", "lg")}>退出本站</button></form>
      <p className="text-xs text-ink-4">退出本站不会退出公司的其他系统。公司登录的本站会话最长保留 8 小时。</p>
    </div>
  </div>;
}
