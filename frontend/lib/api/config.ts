const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL?.trim();

export const API_BASE_URL = (
  configuredApiUrl || "http://localhost:8000/api/v1"
).replace(/\/+$/, "");
