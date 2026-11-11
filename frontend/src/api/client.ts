export interface ApiFieldError {
  loc?: Array<string | number>;
  msg?: string;
  type?: string;
  field?: string;
  message?: string;
}

export class ApiClientError extends Error {
  public readonly status: number;
  public readonly code: string;
  public readonly requestId?: string;
  public readonly fieldErrors?: ApiFieldError[];

  constructor(
    status: number,
    code: string,
    message: string,
    requestId?: string,
    fieldErrors?: ApiFieldError[],
  ) {
    super(message);
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.requestId = requestId;
    this.fieldErrors = fieldErrors;
  }
}

export interface ApiFetchOptions extends RequestInit {
  baseUrl?: string;
}

function getDefaultBaseUrl(): string {
  if (typeof window === "undefined") {
    const maybeProcess = (
      globalThis as { process?: { env?: Record<string, string | undefined> } }
    ).process;
    return maybeProcess?.env?.BACKEND_ORIGIN || "http://127.0.0.1:8000";
  }
  return "";
}

interface RawErrorPayload {
  code?: unknown;
  message?: unknown;
  detail?: unknown;
  request_id?: unknown;
  field_errors?: unknown;
}

function parseErrorPayload(raw: unknown, fallbackStatus: number): {
  code: string;
  message: string;
  requestId?: string;
  fieldErrors?: ApiFieldError[];
} {
  if (!raw || typeof raw !== "object") {
    return {
      code: `HTTP_${fallbackStatus}`,
      message: `Request failed with status ${fallbackStatus}`,
    };
  }
  const obj = raw as RawErrorPayload;
  const code = typeof obj.code === "string" ? obj.code : `HTTP_${fallbackStatus}`;
  const requestId = typeof obj.request_id === "string" ? obj.request_id : undefined;

  let message = `Request failed with status ${fallbackStatus}`;
  if (typeof obj.message === "string" && obj.message.trim().length > 0) {
    message = obj.message;
  } else if (typeof obj.detail === "string" && obj.detail.trim().length > 0) {
    message = obj.detail;
  } else if (Array.isArray(obj.detail)) {
    const first = obj.detail[0] as { msg?: unknown } | undefined;
    if (first && typeof first.msg === "string") {
      message = first.msg;
    }
  }

  let fieldErrors: ApiFieldError[] | undefined;
  if (Array.isArray(obj.field_errors)) {
    fieldErrors = obj.field_errors as ApiFieldError[];
  } else if (Array.isArray(obj.detail)) {
    fieldErrors = obj.detail as ApiFieldError[];
  }

  return { code, message, requestId, fieldErrors };
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
): Promise<T> {
  const { baseUrl, headers, ...init } = options;
  const origin = baseUrl ?? getDefaultBaseUrl();
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const url = `${origin}${normalizedPath}`;

  const mergedHeaders = new Headers(headers);
  if (!mergedHeaders.has("Accept")) {
    mergedHeaders.set("Accept", "application/json");
  }
  if (init.body && typeof init.body === "string" && !mergedHeaders.has("Content-Type")) {
    mergedHeaders.set("Content-Type", "application/json");
  }

  const method = (init.method ?? "GET").toUpperCase();
  if (
    typeof document !== "undefined" &&
    (method === "POST" || method === "PUT" || method === "PATCH" || method === "DELETE") &&
    !mergedHeaders.has("X-CSRF-Token")
  ) {
    const csrfCookie = document.cookie
      .split("; ")
      .find((entry) => entry.startsWith("clps_csrf="));
    if (csrfCookie) {
      const csrfValue = decodeURIComponent(csrfCookie.slice("clps_csrf=".length));
      if (csrfValue) {
        mergedHeaders.set("X-CSRF-Token", csrfValue);
      }
    }
  }

  const response = await fetch(url, {
    ...init,
    headers: mergedHeaders,
    credentials: init.credentials ?? "include",
  });

  const text = await response.text();
  let parsed: unknown = null;
  if (text.length > 0) {
    try {
      parsed = JSON.parse(text) as unknown;
    } catch {
      parsed = null;
    }
  }

  if (!response.ok) {
    const info = parseErrorPayload(parsed, response.status);
    throw new ApiClientError(
      response.status,
      info.code,
      info.message,
      info.requestId,
      info.fieldErrors,
    );
  }

  return parsed as T;
}
