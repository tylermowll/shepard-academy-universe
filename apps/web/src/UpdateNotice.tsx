import { useEffect, useState } from "react";
export function UpdateNotice({
  deferRefresh = false,
}: {
  deferRefresh?: boolean;
}) {
  const [waiting, setWaiting] = useState<ServiceWorker | null>(null);
  useEffect(() => {
    if (!("serviceWorker" in navigator) || !import.meta.env.PROD) return;
    let disposed = false;
    void navigator.serviceWorker
      .register("/sw.js")
      .then((registration) => {
        if (disposed) return;
        if (registration.waiting) setWaiting(registration.waiting);
        registration.addEventListener("updatefound", () => {
          const worker = registration.installing;
          worker?.addEventListener("statechange", () => {
            if (
              !disposed &&
              worker.state === "installed" &&
              navigator.serviceWorker.controller
            )
              setWaiting(worker);
          });
        });
      })
      .catch(() => {
        /* Installation is optional; normal online practice still works. */
      });
    return () => {
      disposed = true;
    };
  }, []);
  if (!waiting) return null;
  if (deferRefresh)
    return (
      <aside className="notice" role="status">
        An update is ready. Finish creating your administrator account before
        refreshing.
      </aside>
    );
  return (
    <aside className="notice" role="status">
      An update is ready. Save your current work before refreshing.{" "}
      <button
        onClick={() => {
          if (
            window.confirm(
              "Refresh now? Saved work will remain; unsent text and photographs will be lost.",
            )
          ) {
            navigator.serviceWorker.addEventListener(
              "controllerchange",
              () => window.location.reload(),
              { once: true },
            );
            waiting.postMessage("ACTIVATE_UPDATE");
          }
        }}
      >
        Refresh when ready
      </button>
    </aside>
  );
}
