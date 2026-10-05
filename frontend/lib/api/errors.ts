export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export async function apiErrorFromResponse(response: Response): Promise<ApiError> {
  let message = `Request failed (${response.status}).`;

  try {
    const payload: unknown = await response.json();
    if (payload && typeof payload === "object" && "detail" in payload) {
      const detail = payload.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (Array.isArray(detail)) {
        const messages = detail
          .map((item) =>
            item && typeof item === "object" && "msg" in item && typeof item.msg === "string"
              ? item.msg
              : "",
          )
          .filter(Boolean);
        if (messages.length) message = messages.join(" ");
      }
    }
  } catch {
    // Keep the status-based error when the server response isn't JSON.
  }

  return new ApiError(message, response.status);
}
