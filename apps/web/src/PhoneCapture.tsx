import { useCallback, useEffect, useState } from "react";
import { ApiError, type Schema } from "./client";
import { PhotoInput } from "./PhotoInput";

async function phoneInfo(token: string): Promise<Schema<"PhoneUploadInfo">> {
  const response = await fetch("/api/v1/phone-upload", {
    headers: { "X-Photo-Token": token },
    credentials: "omit",
    cache: "no-store",
  });
  if (!response.ok) {
    const data: unknown = await response.json().catch(() => null);
    throw new ApiError(
      data &&
        typeof data === "object" &&
        "detail" in data &&
        typeof data.detail === "string"
        ? data.detail
        : "The photo link is unavailable. Open a new link from your computer.",
      response.status,
    );
  }
  return (await response.json()) as Schema<"PhoneUploadInfo">;
}

export function PhoneCapture({ token }: { token: string }) {
  const [info, setInfo] = useState<Schema<"PhoneUploadInfo"> | null>(null);
  const [error, setError] = useState("");
  const [connectionError, setConnectionError] = useState("");
  const [ended, setEnded] = useState(false);
  const [offline, setOffline] = useState(!navigator.onLine);
  const [pending, setPending] = useState(false);
  const [sent, setSent] = useState(false);
  const act = useCallback(async (action: () => Promise<void>) => {
    setError("");
    try {
      await action();
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "Connection lost. Keep this screen open and retry.",
      );
      if (
        cause instanceof ApiError &&
        [401, 403, 404, 410].includes(cause.status)
      )
        setEnded(true);
    }
  }, []);
  useEffect(() => {
    let canceled = false;
    const refresh = () => {
      setOffline(!navigator.onLine);
      if (!navigator.onLine || document.visibilityState !== "visible") return;
      void phoneInfo(token)
        .then((result) => {
          if (!canceled) {
            setInfo(result);
            setEnded(false);
            setConnectionError("");
          }
        })
        .catch((cause: unknown) => {
          if (canceled) return;
          setConnectionError(
            cause instanceof Error
              ? cause.message
              : "Reconnect to your computer.",
          );
          if (
            cause instanceof ApiError &&
            [401, 403, 404, 409, 410, 422].includes(cause.status)
          )
            setEnded(true);
        });
    };
    refresh();
    const timer = window.setInterval(refresh, 5000);
    window.addEventListener("online", refresh);
    window.addEventListener("offline", refresh);
    document.addEventListener("visibilitychange", refresh);
    return () => {
      canceled = true;
      window.clearInterval(timer);
      window.removeEventListener("online", refresh);
      window.removeEventListener("offline", refresh);
      document.removeEventListener("visibilitychange", refresh);
    };
  }, [token]);
  const received = sent || info?.received;
  return (
    <main className="phone-capture">
      <p className="eyebrow">Shepard Academy Universe · Phone camera</p>
      <h1>
        {received ? "Photo sent to your computer." : "Photograph your work."}
      </h1>
      {received ? (
        <p role="status">
          Return to your computer for the reading and guidance. If the writing
          is unclear, the tutor will ask for a clearer photo. You can close this
          screen.
        </p>
      ) : (
        <>
          <p>
            One photo for the activity below. No sign-in is needed on this
            phone.
          </p>
          {info && (
            <>
              <h2 className="math-problem">{info.problem_text}</h2>
              <p>{info.processing}</p>
              <p className="fine">
                This link expires at{" "}
                {new Date(info.expires_at).toLocaleTimeString()}. Keep this
                screen open until the photo is sent.
              </p>
            </>
          )}
          {offline && (
            <p role="status">
              Reconnect to the network that can reach your computer, then retry.
            </p>
          )}
          {error && (
            <p role="alert" className="error">
              {error}
            </p>
          )}
          {connectionError && (
            <p role="alert" className="error">
              {connectionError}
            </p>
          )}
          {ended ? (
            <p>Create a new photo link on your computer and scan it again.</p>
          ) : info ? (
            <PhotoInput
              problem=""
              version={1}
              companionToken={token}
              disabled={offline}
              act={act}
              onPendingChange={setPending}
              onSaved={() => {
                setSent(true);
                return Promise.resolve();
              }}
            />
          ) : (
            !error &&
            !connectionError &&
            !offline && <p role="status">Connecting to your computer…</p>
          )}
          {pending && (
            <p className="notice">
              Your photo is held on this screen while sending. Please do not
              reload or close it.
            </p>
          )}
        </>
      )}
    </main>
  );
}
