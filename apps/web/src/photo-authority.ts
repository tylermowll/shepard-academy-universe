// Capture before rendering or handling in-app navigation: fragment secrets must
// stay in memory, never in server URLs, browser storage, or subsequent links.
export function capturePhotoToken(): string | null {
  const token = new URLSearchParams(window.location.hash.slice(1)).get(
    "capture",
  );
  if (token !== null)
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search + "#capture",
    );
  return token;
}
