// This holder belongs to one page load, not browser storage or a module singleton.
// Clearing it also releases the copy passed to the React root on first render.
export type SetupAuthority = { token: string };

export function captureSetupAuthority(): SetupAuthority {
  const token = new URLSearchParams(window.location.hash.slice(1)).get("setup");
  if (token !== null)
    window.history.replaceState(
      null,
      "",
      window.location.pathname + window.location.search,
    );
  return { token: token ?? "" };
}
