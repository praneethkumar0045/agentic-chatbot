import { NextRequest } from "next/server";
import { refresh } from "@/lib/server/auth-proxy";

export const dynamic = "force-dynamic";

export function POST(request: NextRequest) {
  return refresh(request);
}
