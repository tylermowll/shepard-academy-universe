import { useEffect, useRef, useState } from "react";
import { ApiError, imageRequest, newKey } from "./client";
import { BusyStatus } from "./BusyStatus";

type Props = {
  problem: string;
  version: number;
  disabled: boolean;
  onPendingChange: (pending: boolean) => void;
  onDraftChange?: (draft: boolean) => void;
  onSaved: () => Promise<void>;
  act: (a: () => Promise<void>) => Promise<void>;
  companionToken?: string;
  reference?: boolean;
};
type PendingPhoto = {
  path: string;
  blob: Blob;
  key: string;
  ambiguous: boolean;
};
export function PhotoInput({
  problem,
  version,
  disabled,
  onPendingChange,
  onDraftChange,
  onSaved,
  act,
  companionToken,
  reference = false,
}: Props) {
  const [blob, setBlob] = useState<Blob | null>(null);
  const [url, setUrl] = useState("");
  const [rotation, setRotation] = useState(0);
  const [crop, setCrop] = useState(0);
  const [pending, setPending] = useState<PendingPhoto | null>(null);
  const [working, setWorking] = useState(false);
  const [dragging, setDragging] = useState(false);
  const uploading = useRef(false);
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
      onPendingChange(false);
    };
  }, [onPendingChange]);
  useEffect(() => {
    onDraftChange?.(Boolean(blob || pending || working));
  }, [blob, pending, working, onDraftChange]);
  useEffect(() => () => onDraftChange?.(false), [onDraftChange]);
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  async function transform(): Promise<Blob> {
    if (!blob) throw new Error("Choose a photograph first.");
    if (!rotation && !crop) return blob;
    const image = await createImageBitmap(blob);
    const edge = crop / 100;
    const width = Math.round(image.width * (1 - edge * 2));
    const height = Math.round(image.height * (1 - edge * 2));
    const canvas = document.createElement("canvas");
    canvas.width = rotation % 180 === 0 ? width : height;
    canvas.height = rotation % 180 === 0 ? height : width;
    const context = canvas.getContext("2d");
    if (!context)
      throw new Error("Image editing is unavailable. Use typed input.");
    context.translate(canvas.width / 2, canvas.height / 2);
    context.rotate((rotation * Math.PI) / 180);
    context.drawImage(
      image,
      Math.round(image.width * edge),
      Math.round(image.height * edge),
      width,
      height,
      -width / 2,
      -height / 2,
      width,
      height,
    );
    image.close();
    return new Promise((resolve, reject) =>
      canvas.toBlob(
        (result) =>
          result
            ? resolve(result)
            : reject(new Error("Could not prepare photograph.")),
        "image/jpeg",
        0.9,
      ),
    );
  }
  async function sendPhoto(request: PendingPhoto) {
    setWorking(true);
    try {
      try {
        await imageRequest(
          request.path,
          request.blob,
          request.key,
          companionToken,
        );
      } catch (cause) {
        if (
          !request.ambiguous &&
          cause instanceof ApiError &&
          cause.status < 500 &&
          cause.status !== 408
        ) {
          setPending(null);
          onPendingChange(false);
        } else request.ambiguous = true;
        throw cause;
      }
      setPending(null);
      onPendingChange(false);
      setBlob(null);
      setUrl("");
      await onSaved();
    } finally {
      setWorking(false);
    }
  }
  async function preparePhoto(files: File[]) {
    if (disabled || working || pending || uploading.current || !files.length)
      return;
    if (files.length !== 1) throw new Error("Choose one photograph at a time.");
    const file = files[0]!;
    if (file.size > 8388608)
      throw new Error("Choose a photograph under 8 MiB.");
    uploading.current = true;
    setWorking(true);
    try {
      const response = await imageRequest(
        companionToken ? "/phone-upload/preview" : "/images/preview",
        file,
        undefined,
        companionToken,
      );
      const normalized = await response.blob();
      if (!mounted.current) return;
      setBlob(normalized);
      setUrl(URL.createObjectURL(normalized));
      setRotation(0);
      setCrop(0);
    } finally {
      uploading.current = false;
      setWorking(false);
    }
  }
  return (
    <details
      open={companionToken ? true : undefined}
      hidden={disabled && !pending && !blob && !working}
    >
      <summary>Upload a photo</summary>
      <p>
        {reference
          ? "Photograph the reference material. The tutor will create related practice and will not solve the original assignment."
          : "Include the whole page, use good lighting, and keep your writing in focus. You will see the photo reading before the feedback."}{" "}
        {companionToken
          ? "If camera access is unavailable, return to your computer to enter an answer."
          : "Typed answers remain available if camera access is denied."}
      </p>
      <fieldset disabled={disabled || working || pending !== null}>
        <div
          role="group"
          aria-label="Photo upload"
          className={`photo-dropzone${dragging ? " dragging" : ""}`}
          onDragOver={(event) => {
            event.preventDefault();
            const available = !disabled && !working && !pending;
            event.dataTransfer.dropEffect = available ? "copy" : "none";
            setDragging(available);
          }}
          onDragLeave={(event) => {
            if (
              !event.currentTarget.contains(event.relatedTarget as Node | null)
            )
              setDragging(false);
          }}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            const files = Array.from(event.dataTransfer.files);
            void act(() => preparePhoto(files));
          }}
        >
          <label>
            Take or choose a photo
            <input
              type="file"
              accept="image/jpeg,image/png,image/webp,image/heic,image/heif,.jpg,.jpeg,.png,.webp,.heic,.heif"
              capture="environment"
              onChange={(e) => {
                const files = Array.from(e.target.files ?? []);
                e.target.value = "";
                void act(() => preparePhoto(files));
              }}
            />
          </label>
          <p className="hint">
            Or drop one photo here. JPG, PNG, WebP, HEIC or HEIF · up to 8 MiB.
          </p>
        </div>
        {blob && (
          <>
            <div className="photo-preview">
              {url && (
                <img
                  src={url}
                  alt="Your photograph before submission"
                  style={{
                    transform: `rotate(${rotation}deg)`,
                    clipPath: `inset(${crop}%)`,
                  }}
                />
              )}
            </div>
            <div className="actions">
              <button
                type="button"
                onClick={() => setRotation((rotation + 90) % 360)}
              >
                Rotate 90°
              </button>
              <label>
                Crop equally from edges ({crop}%)
                <input
                  type="range"
                  min={0}
                  max={35}
                  value={crop}
                  onChange={(e) => setCrop(Number(e.target.value))}
                />
              </label>
            </div>
            <button
              onClick={() =>
                void act(async () => {
                  if (uploading.current || pending) return;
                  uploading.current = true;
                  setWorking(true);
                  onPendingChange(true);
                  let request: PendingPhoto | undefined;
                  try {
                    request = {
                      path: companionToken
                        ? "/phone-upload/photos"
                        : `/problems/${problem}/photos?version=${version}&kind=answer`,
                      blob: await transform(),
                      key: newKey(),
                      ambiguous: false,
                    };
                    if (!mounted.current) return;
                    setPending(request);
                    await sendPhoto(request);
                  } finally {
                    if (!request) onPendingChange(false);
                    uploading.current = false;
                    setWorking(false);
                  }
                })
              }
            >
              {companionToken ? "Send to computer" : "Submit this photograph"}
            </button>
          </>
        )}
      </fieldset>
      {working && (
        <BusyStatus
          message={
            pending ? "Sending your photograph…" : "Preparing your photograph…"
          }
        />
      )}
      {blob && !pending && (
        <button
          type="button"
          disabled={working}
          onClick={() => {
            setBlob(null);
            setUrl("");
          }}
        >
          Remove photo
        </button>
      )}
      {pending && !working && (
        <div role="status" className="notice">
          <p>
            The server has not acknowledged your photograph. Retry the saved
            photograph to recover its submission.
          </p>
          <button
            onClick={() => void act(() => sendPhoto(pending))}
            disabled={!navigator.onLine}
          >
            Retry saved photograph
          </button>
        </div>
      )}
    </details>
  );
}
