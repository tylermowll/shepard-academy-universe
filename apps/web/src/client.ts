import type { components } from "./generated/api";
export type Schema<K extends keyof components["schemas"]> =
  components["schemas"][K];
let csrf = "";
let generation = 0;

export function setIdentity(token: string) {
  csrf = token;
  generation += 1;
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
  if (current !== generation)
    throw new Error("Session changed. Reload your current session.");
  if (!response.ok) {
    const error: unknown = await response.json().catch(() => null);
    throw new Error(
      error &&
        typeof error === "object" &&
        "detail" in error &&
        typeof error.detail === "string"
        ? error.detail
        : "Request failed. Your saved work is available in session history.",
    );
  }
  return response.json() as Promise<T>;
}
export async function imageRequest(
  path: string,
  blob: Blob,
  key?: string,
): Promise<Response> {
  const current = generation;
  const headers: Record<string, string> = {
    "X-CSRF-Token": csrf,
    "Content-Type": "application/octet-stream",
  };
  if (key) headers["Idempotency-Key"] = key;
  const response = await fetch(`/api/v1${path}`, {
    method: "POST",
    headers,
    body: blob,
    credentials: "same-origin",
    cache: "no-store",
  });
  if (current !== generation)
    throw new Error("Session changed. Reload your current session.");
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    throw new Error(
      data &&
        typeof data === "object" &&
        "detail" in data &&
        typeof data.detail === "string"
        ? data.detail
        : "Photo could not be submitted. Try typed input.",
    );
  }
  return response;
}
export const newKey = () => crypto.randomUUID();
