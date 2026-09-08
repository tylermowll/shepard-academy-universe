import { useLayoutEffect, useState } from "react";
import { App } from "./App";
import { PhoneCapture } from "./PhoneCapture";
import { capturePhotoToken } from "./photo-authority";
import type { SetupAuthority } from "./setup-authority";

export function Entry({
  photoToken,
  setupAuthority,
}: {
  photoToken: string | null;
  setupAuthority: SetupAuthority;
}) {
  const [token, setToken] = useState(photoToken);
  useLayoutEffect(() => {
    const changed = () => {
      const next = capturePhotoToken();
      // The browser can deliver popstate and hashchange for one navigation.
      // The second event sees the scrubbed marker; retain the in-memory token.
      setToken((current) => (next === "" ? (current ?? "") : next));
    };
    // Install before the app's navigation effects so they only see the marker.
    window.addEventListener("hashchange", changed);
    window.addEventListener("popstate", changed);
    return () => {
      window.removeEventListener("hashchange", changed);
      window.removeEventListener("popstate", changed);
    };
  }, []);

  return token === null ? (
    <App setupAuthority={setupAuthority} />
  ) : (
    <PhoneCapture key={token} token={token} />
  );
}
