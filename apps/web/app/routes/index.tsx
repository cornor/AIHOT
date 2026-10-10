import { redirect } from "react-router";
import type { Route } from "./+types/index";

export function loader({ request }: Route.LoaderArgs) {
  return redirect(`/all${new URL(request.url).search}`, {
    status: 302,
    headers: { "Cache-Control": "no-store" },
  });
}
