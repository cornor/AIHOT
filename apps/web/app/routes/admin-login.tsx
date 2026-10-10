// Keep old bookmarks working without treating ordinary readers as administrators.
import { redirect } from "react-router";
import type { Route } from "./+types/admin-login";

export function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  return redirect(`/login${url.search}`, {
    status: 302,
    headers: { "Cache-Control": "no-store", "X-Robots-Tag": "noindex, nofollow" },
  });
}
