import { NextRequest } from "next/server";
import { logout } from "@/lib/server/auth-proxy";

export const dynamic = "force-dynamic";

export function POST(request: NextRequest) {
  return logout(request);
}
