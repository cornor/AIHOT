// Company sign-in is the only entry offered on the site's login page.
import { useLoaderData } from "react-router";
import type { Route } from "./+types/login";
import { SITE } from "@aihot/industry/site";
import { apiGet } from "../lib/api.server";
import { Wordmark } from "../components/Logo";
import { buttonClass } from "../components/ui/Controls";

export async function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const returnTo = url.searchParams.get("return") ?? "/";
  const options = await apiGet<{ sso: boolean }>("/api/auth/options", { signal: request.signal }).catch(() => ({ sso: false }));
  return { returnTo: returnTo.startsWith("/") && !returnTo.startsWith("//") && !/[\\\x00-\x20]/.test(returnTo) ? returnTo : "/", sso: options.sso };
}

export const meta: Route.MetaFunction = () => [{ title: `登录 · ${SITE.name}` }, { name: "robots", content: "noindex, nofollow" }];

export const headers: Route.HeadersFunction = () => ({ "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow" });

export default function Login() {
  const { returnTo, sso } = useLoaderData<typeof loader>();
  return (
    <div className="flex min-h-dvh items-center justify-center bg-bg px-4">
      <div className="w-full max-w-[360px]">
        <div className="flex items-center justify-center gap-2">
          <Wordmark size={26} className="text-ink" />
          <span className="text-[15px] font-semibold text-ink-3">内部资讯</span>
        </div>
        {sso && <div className="card mt-8 p-6">
          <p className="mb-4 text-sm text-ink-3">使用公司账号访问游戏行业资讯。</p>
          <a href={`/api/auth/sso/start?${new URLSearchParams({ return: returnTo })}`} className={`${buttonClass("primary", "lg")} w-full`}>公司账号登录</a>
        </div>}
        {!sso && <p role="alert" className="mt-8 text-center text-sm text-ink-3">公司账号登录暂不可用，请稍后重试。</p>}
        <p className="mt-6 text-center text-[12px] text-ink-4">
          <a href="/" className="hover:text-ink-2">
            回到 {SITE.name}
          </a>
        </p>
      </div>
    </div>
  );
}
