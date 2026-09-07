import { useEffect, useState } from "react";
import { imageRequest, newKey } from "./client";

type Props = {
  problem: string;
  version: number;
  onSaved: () => Promise<void>;
  act: (a: () => Promise<void>) => Promise<void>;
};
export function PhotoInput({ problem, version, onSaved, act }: Props) {
  const [blob, setBlob] = useState<Blob | null>(null);
  const [url, setUrl] = useState("");
  const [rotation, setRotation] = useState(0);
  const [crop, setCrop] = useState(0);
  const [kind, setKind] = useState("answer");
  const [key, setKey] = useState(newKey);
  useEffect(
    () => () => {
      if (url) URL.revokeObjectURL(url);
    },
    [url],
  );
  async function transform(): Promise<Blob> {
    if (!blob) throw new Error("Choose a photograph first.");
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
        "image/png",
      ),
    );
  }
  return (
    <details>
      <summary>Submit a photograph</summary>
      <p>
        Photograph your work on this problem. You will confirm the transcription
        before it is checked. Typed answers remain available if camera access is
        denied.
      </p>
      <label>
        Take or choose a photo
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp,image/heic,image/heif"
          capture="environment"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file)
              void act(async () => {
                if (file.size > 8388608)
                  throw new Error("Choose a photograph under 8 MiB.");
                const response = await imageRequest("/images/preview", file);
                const normalized = await response.blob();
                setBlob(normalized);
                setUrl(URL.createObjectURL(normalized));
                setRotation(0);
                setCrop(0);
                setKey(newKey());
              });
          }}
        />
      </label>
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
          <label>
            Purpose
            <select value={kind} onChange={(e) => setKind(e.target.value)}>
              <option value="answer">Check my final answer</option>
              <option value="question">Ask about my work</option>
            </select>
          </label>
          <button
            onClick={() =>
              void act(async () => {
                await imageRequest(
                  `/problems/${problem}/photos?version=${version}&kind=${kind}`,
                  await transform(),
                  key,
                );
                setBlob(null);
                setUrl("");
                setKey(newKey());
                await onSaved();
              })
            }
          >
            Submit this photograph
          </button>
        </>
      )}
    </details>
  );
}
