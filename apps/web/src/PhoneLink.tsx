import { QRCodeSVG } from "qrcode.react";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, newKey, type Schema } from "./client";

type Props = {
  problem: string;
  version: number;
  disabled: boolean;
  act: (action: () => Promise<void>) => Promise<void>;
};

export function PhoneLink({ problem, version, disabled, act }: Props) {
  const [link, setLink] = useState<Schema<"PhoneUploadLink"> | null>(null);
  const [busy, setBusy] = useState(false);
  const [expired, setExpired] = useState(false);
  const requestKey = useRef<string | null>(null);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  useEffect(() => {
    if (!link) return;
    const timer = window.setTimeout(
      () => setExpired(true),
      Math.max(0, Date.parse(link.expires_at) - Date.now()),
    );
    return () => window.clearTimeout(timer);
  }, [link]);
  const loopback = ["127.0.0.1", "localhost", "[::1]"].includes(
    window.location.hostname,
  );
  return (
    <section className="phone-link" aria-label="Phone photograph">
      <button
        disabled={disabled || busy}
        onClick={() =>
          void act(async () => {
            setBusy(true);
            requestKey.current ??= newKey();
            try {
              const created = await api<Schema<"PhoneUploadLink">>(
                `/problems/${problem}/phone-uploads`,
                "POST",
                { version },
                requestKey.current,
              );
              requestKey.current = null;
              if (mounted.current) {
                setLink(created);
                setExpired(false);
              }
            } catch (cause) {
              if (
                cause instanceof ApiError &&
                cause.status < 500 &&
                cause.status !== 408
              )
                requestKey.current = null;
              throw cause;
            } finally {
              setBusy(false);
            }
          })
        }
      >
        {busy
          ? "Preparing photo link…"
          : link
            ? "Create a new phone link"
            : "Take photo with phone"}
      </button>
      {link && !disabled && !expired && (
        <div className="phone-link-details">
          <h4>Scan with your iPhone camera</h4>
          <QRCodeSVG
            value={link.url}
            size={256}
            marginSize={4}
            level="M"
            title="Scan to photograph your work"
          />
          <p>
            Open the link, take a photo, and send it. Its reading will appear in
            your learning conversation below.
          </p>
          <p className="fine">
            One upload; expires at{" "}
            {new Date(link.expires_at).toLocaleTimeString()}. Anyone with this
            link can send that photo—keep it private.
          </p>
          {loopback && (
            <p className="notice">
              This computer is using a localhost address, which your iPhone
              cannot reach. Open the app at its configured HTTPS network address
              first; see the phone setup guide.
            </p>
          )}
          <div className="actions">
            <a href={link.url} target="_blank" rel="noreferrer">
              Open photo page
            </a>
            <button
              disabled={busy}
              onClick={() =>
                void act(async () => {
                  await api(`/phone-uploads/${link.id}`, "DELETE");
                  setLink(null);
                })
              }
            >
              Cancel phone link
            </button>
          </div>
        </div>
      )}
      {link && expired && !disabled && (
        <p role="status">
          The phone link expired. Create a new link to take your photo.
        </p>
      )}
    </section>
  );
}
