import { redirect } from "react-router";
import type { Route } from "./+types/index";

export function loader({ request }: Route.LoaderArgs) {
  const url = new URL(request.url);
  const path = url.searchParams.get("q")?.trim() ? "/all" : "/selected";
  return redirect(`${path}${url.search}`, {
    status: 302,
    headers: { "Cache-Control": "no-store" },
  });
}
