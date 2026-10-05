import { NextRequest, NextResponse } from "next/server";

const refreshCookieName = "medha_refresh";
const refreshCookiePath = "/api/auth";

type BackendTokenResponse = {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
};

function backendUrl(path: string) {
  const baseUrl =
    process.env.AUTH_API_URL?.trim() ||
    process.env.NEXT_PUBLIC_API_URL?.trim() ||
    "http://localhost:8000/api/v1";
  return `${baseUrl.replace(/\/+$/, "")}${path}`;
}

function relay(response: Response) {
  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      "Cache-Control": "no-store",
      "Content-Type": response.headers.get("content-type") ?? "application/json",
    },
  });
}

function noContent() {
  return new NextResponse(null, {
    status: 204,
    headers: { "Cache-Control": "no-store" },
  });
}

function unavailable() {
  return NextResponse.json(
    { detail: "The authentication service is unavailable. Please try again." },
    { status: 502, headers: { "Cache-Control": "no-store" } },
  );
}

async function callBackend(path: string, body: string) {
  try {
    return await fetch(backendUrl(path), {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body,
      cache: "no-store",
    });
  } catch {
    return null;
  }
}

function setRefreshCookie(response: NextResponse, refreshToken: string) {
  const configuredDays = Number(process.env.AUTH_REFRESH_TOKEN_EXPIRE_DAYS ?? "30");
  const maxAgeDays =
    Number.isSafeInteger(configuredDays) && configuredDays > 0 ? configuredDays : 30;
  response.cookies.set(refreshCookieName, refreshToken, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: refreshCookiePath,
    maxAge: maxAgeDays * 24 * 60 * 60,
  });
}

function clearRefreshCookie(response: NextResponse) {
  response.cookies.set(refreshCookieName, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "strict",
    path: refreshCookiePath,
    maxAge: 0,
  });
}

async function tokenResponse(upstream: Response) {
  if (!upstream.ok) return relay(upstream);

  let tokens: BackendTokenResponse;
  try {
    tokens = (await upstream.json()) as BackendTokenResponse;
  } catch {
    return unavailable();
  }
  if (
    typeof tokens.access_token !== "string" ||
    typeof tokens.refresh_token !== "string" ||
    typeof tokens.expires_in !== "number"
  ) {
    return unavailable();
  }

  const response = NextResponse.json(
    {
      access_token: tokens.access_token,
      token_type: tokens.token_type,
      expires_in: tokens.expires_in,
    },
    { headers: { "Cache-Control": "no-store" } },
  );
  setRefreshCookie(response, tokens.refresh_token);
  return response;
}

export async function register(request: NextRequest) {
  let body: string;
  try {
    body = await request.text();
  } catch {
    return NextResponse.json({ detail: "Invalid request body." }, { status: 400 });
  }
  const upstream = await callBackend("/auth/register", body);
  return upstream ? relay(upstream) : unavailable();
}

export async function login(request: NextRequest) {
  let body: string;
  try {
    body = await request.text();
  } catch {
    return NextResponse.json({ detail: "Invalid request body." }, { status: 400 });
  }
  const upstream = await callBackend("/auth/login", body);
  return upstream ? tokenResponse(upstream) : unavailable();
}

export async function refresh(request: NextRequest) {
  const refreshToken = request.cookies.get(refreshCookieName)?.value;
  if (!refreshToken) {
    return NextResponse.json(
      { detail: "Your session has expired. Please sign in again." },
      { status: 401, headers: { "Cache-Control": "no-store" } },
    );
  }

  const upstream = await callBackend(
    "/auth/refresh",
    JSON.stringify({ refresh_token: refreshToken }),
  );
  if (!upstream) return unavailable();
  const response = await tokenResponse(upstream);
  if (upstream.status === 401) clearRefreshCookie(response);
  return response;
}

export async function logout(request: NextRequest) {
  const refreshToken = request.cookies.get(refreshCookieName)?.value;
  if (!refreshToken) {
    return noContent();
  }

  const upstream = await callBackend(
    "/auth/logout",
    JSON.stringify({ refresh_token: refreshToken }),
  );
  const response = !upstream
    ? unavailable()
    : upstream.status === 401
      ? noContent()
      : relay(upstream);
  clearRefreshCookie(response);
  return response;
}
