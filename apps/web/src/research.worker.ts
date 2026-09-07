import runtimeURL from "@mlc-ai/web-llm/lib/index.js?url";
import manifest from "./research-manifest.json";
const originalFetch = globalThis.fetch.bind(globalThis);
const files: Record<string, { algorithm: string; hash: string; size: number }> =
  manifest.files;
globalThis.fetch = async (input: RequestInfo | URL, init?: RequestInit) => {
  const url =
    typeof input === "string"
      ? input
      : input instanceof URL
        ? input.href
        : input.url;
  const entry = files[url];
  if (!entry)
    throw new Error(
      "Research download is outside the pinned artifact manifest.",
    );
  const response = await originalFetch(input, {
    ...init,
    credentials: "omit",
    referrerPolicy: "no-referrer",
  });
  if (!response.ok) throw new Error("Research artifact unavailable.");
  const buffer = await response.arrayBuffer();
  if (buffer.byteLength !== entry.size)
    throw new Error("Research artifact size mismatch.");
  const content = new Uint8Array(buffer);
  const header =
    entry.algorithm === "git-SHA-1"
      ? new TextEncoder().encode(`blob ${content.length}\0`)
      : new Uint8Array();
  const checked = new Uint8Array(header.length + content.length);
  checked.set(header);
  checked.set(content, header.length);
  const hash = Array.from(
    new Uint8Array(
      await crypto.subtle.digest(
        entry.algorithm === "git-SHA-1" ? "SHA-1" : "SHA-256",
        checked,
      ),
    ),
    (b) => b.toString(16).padStart(2, "0"),
  ).join("");
  if (hash !== entry.hash)
    throw new Error("Research artifact checksum mismatch.");
  return new Response(buffer, {
    status: response.status,
    headers: response.headers,
  });
};
const library: unknown = await import(/* @vite-ignore */ runtimeURL);
if (
  !library ||
  typeof library !== "object" ||
  !("WebWorkerMLCEngineHandler" in library) ||
  typeof library.WebWorkerMLCEngineHandler !== "function"
)
  throw new Error("Unsupported research worker runtime.");
const Handler = library.WebWorkerMLCEngineHandler as new () => {
  onmessage(event: MessageEvent): void;
};
const handler = new Handler();
self.onmessage = (event: MessageEvent) => handler.onmessage(event);
