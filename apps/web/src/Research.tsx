import { useEffect, useRef, useState } from "react";
import { loadResearchLibrary, type ResearchEngine } from "./research-runtime";
import manifest from "./research-manifest.json";

export default function Research() {
  const worker = useRef<Worker | null>(null);
  const engine = useRef<ResearchEngine | null>(null);
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState("No model downloaded.");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [report, setReport] = useState("");
  useEffect(
    () => () => {
      worker.current?.terminate();
    },
    [],
  );
  const bytes = Object.values(manifest.files).reduce(
    (sum, file) => sum + file.size,
    0,
  );
  async function load() {
    setBusy(true);
    try {
      if (!("gpu" in navigator))
        throw new Error("WebGPU is unavailable on this browser.");
      const start = performance.now();
      const { CreateWebWorkerMLCEngine } = await loadResearchLibrary();
      worker.current = new Worker(
        new URL("./research.worker.ts", import.meta.url),
        { type: "module" },
      );
      engine.current = await CreateWebWorkerMLCEngine(
        worker.current,
        manifest.model_id,
        {
          appConfig: {
            model_list: [
              {
                model_id: manifest.model_id,
                model: manifest.model_base,
                model_lib: manifest.model_lib,
                required_features: ["shader-f16"],
                overrides: { context_window_size: 1024 },
              },
            ],
          },
          initProgressCallback: (progress) => setStatus(progress.text),
        },
      );
      setReady(true);
      setStatus(
        `Loaded in ${((performance.now() - start) / 1000).toFixed(1)} seconds. Text-only research; no learner data is used.`,
      );
    } catch (cause) {
      setStatus(
        cause instanceof Error
          ? cause.message
          : "Research runtime unavailable.",
      );
    } finally {
      setBusy(false);
    }
  }
  async function evaluate() {
    if (!engine.current) return;
    setBusy(true);
    try {
      const results = [];
      for (const question of [
        "What is 1/2 + 1/3? Give only the fraction.",
        "Solve 2x + 3 = 11. Give x only.",
        "Explain briefly why 2/4 equals 1/2.",
      ]) {
        const start = performance.now();
        const response = await engine.current.chat.completions.create({
          messages: [{ role: "user", content: question }],
          max_tokens: 128,
          temperature: 0,
        });
        results.push({
          question,
          response: response.choices[0]?.message.content,
          latency_ms: Math.round(performance.now() - start),
          usage: response.usage,
        });
      }
      const storage = await navigator.storage.estimate();
      setReport(
        JSON.stringify(
          {
            model: manifest.model_id,
            revision: manifest.model_revision,
            browser: navigator.userAgent,
            artifact_bytes: bytes,
            storage_usage: storage.usage,
            results,
            manual_fields: {
              device: "pending",
              memory: "pending",
              battery_thermal: "pending",
              eviction: "pending",
              human_accuracy_review: "pending",
            },
          },
          null,
          2,
        ),
      );
    } catch (cause) {
      setStatus(
        cause instanceof Error ? cause.message : "Research run failed.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="card">
      <h2>Browser model research</h2>
      <p>
        This separate text-only experiment uses synthetic questions and never
        changes server practice results. No device has been certified.
        Small-model output can be wrong.
      </p>
      <p>
        {manifest.model_id}; approximately {Math.ceil(bytes / 1024 / 1024)} MiB
        of pinned artifacts. The publisher estimates about 360 MB of GPU memory;
        actual device use still needs measurement.
      </p>
      <p>
        Downloads contact Hugging Face and GitHub. Content hashes are checked.
        Model licensing is separate from this app’s MIT license; review the
        model repository before accepting.
      </p>
      <label className="check">
        <input
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
        />
        I am the adult operator, reviewed the model license, and authorize these
        downloads on this device.
      </label>
      <div className="actions">
        <button
          disabled={!consent || busy || ready}
          onClick={() => void load()}
        >
          Download and load experiment
        </button>
        <button disabled={!ready || busy} onClick={() => void evaluate()}>
          Run three synthetic questions
        </button>
        <button
          onClick={() => {
            engine.current?.interruptGenerate();
            worker.current?.terminate();
            worker.current = null;
            engine.current = null;
            setReady(false);
            setBusy(false);
            setStatus(
              "Canceled and unloaded. Downloaded model cache may remain.",
            );
          }}
        >
          Cancel and unload
        </button>
        <button
          onClick={() => {
            void (async () => {
              const { deleteModelAllInfoInCache } = await loadResearchLibrary();
              await engine.current?.unload();
              worker.current?.terminate();
              engine.current = null;
              setReady(false);
              await deleteModelAllInfoInCache(manifest.model_id, {
                model_list: [
                  {
                    model_id: manifest.model_id,
                    model: manifest.model_base,
                    model_lib: manifest.model_lib,
                  },
                ],
              });
              setStatus("Model cache removed.");
            })().catch(() =>
              setStatus(
                "Cache removal failed. Use browser site-storage controls.",
              ),
            );
          }}
        >
          Remove model cache
        </button>
      </div>
      <p role="status">{status}</p>
      {report && (
        <>
          <label>
            Synthetic measurement report
            <textarea readOnly rows={12} value={report} />
          </label>
          <button
            onClick={() => {
              const url = URL.createObjectURL(
                new Blob([report], { type: "application/json" }),
              );
              const a = document.createElement("a");
              a.href = url;
              a.download = "browser-research.json";
              a.click();
              setTimeout(() => URL.revokeObjectURL(url), 1000);
            }}
          >
            Download report
          </button>
        </>
      )}
    </section>
  );
}
