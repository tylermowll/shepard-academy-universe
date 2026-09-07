import type { components } from "./generated/api";
export type Schema<K extends keyof components["schemas"]> =
  components["schemas"][K];
let csrf = "";
let generation = 0;
let authenticated = false;
const authenticationLost = new Set<() => void>();

export function setIdentity(token: string, signedIn = false) {
  csrf = token;
  authenticated = signedIn;
  generation += 1;
}
export function onAuthenticationLost(listener: () => void) {
  authenticationLost.add(listener);
  return () => {
    authenticationLost.delete(listener);
  };
}
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}
function checkSession(current: number, response: Response, path: string) {
  if (current !== generation)
    throw new Error("Session changed. Reload your current session.");
  if (response.status === 401 && authenticated && path !== "/auth/login") {
    setIdentity("");
    for (const listener of authenticationLost) listener();
    throw new ApiError(
      "Your session ended. Sign in or pair this device again.",
      401,
    );
  }
}
export async function api<T>(
  path: string,
  method = "GET",
  body?: unknown,
  key?: string,
): Promise<T> {
  const current = generation;
  const headers: Record<string, string> = { "X-CSRF-Token": csrf };
  if (key) headers["Idempotency-Key"] = key;
  const options: RequestInit = {
    method,
    headers,
    credentials: "same-origin",
    cache: "no-store",
  };
  if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(body);
  }
  const response = await fetch(`/api/v1${path}`, options);
  checkSession(current, response, path);
  if (!response.ok) {
    const error: unknown = await response.json().catch(() => null);
    checkSession(current, response, path);
    throw new ApiError(
      error &&
        typeof error === "object" &&
        "detail" in error &&
        typeof error.detail === "string"
        ? error.detail
        : "Request failed. Your saved work is available in session history.",
      response.status,
    );
  }
  const result = (await response.json()) as T;
  checkSession(current, response, path);
  return result;
}
export async function imageRequest(
  path: string,
  blob: Blob,
  key?: string,
  photoToken?: string,
): Promise<Response> {
  const current = generation;
  const headers: Record<string, string> = {
    "X-CSRF-Token": csrf,
    "Content-Type": "application/octet-stream",
  };
  if (key) headers["Idempotency-Key"] = key;
  if (photoToken) headers["X-Photo-Token"] = photoToken;
  const response = await fetch(`/api/v1${path}`, {
    method: "POST",
    headers,
    body: blob,
    credentials: photoToken ? "omit" : "same-origin",
    cache: "no-store",
  });
  checkSession(current, response, path);
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    checkSession(current, response, path);
    throw new ApiError(
      data &&
        typeof data === "object" &&
        "detail" in data &&
        typeof data.detail === "string"
        ? data.detail
        : "Photo could not be submitted. Try typed input.",
      response.status,
    );
  }
  return response;
}
export const newKey = () => crypto.randomUUID();
