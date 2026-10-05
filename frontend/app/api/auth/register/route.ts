import { NextRequest } from "next/server";
import { register } from "@/lib/server/auth-proxy";

export const dynamic = "force-dynamic";

export function POST(request: NextRequest) {
  return register(request);
}
