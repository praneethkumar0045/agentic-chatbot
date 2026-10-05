import { NextRequest } from "next/server";
import { login } from "@/lib/server/auth-proxy";

export const dynamic = "force-dynamic";

export function POST(request: NextRequest) {
  return login(request);
}
