import { useEffect, useRef, useState } from "react";
import { loadResearchLibrary, type ResearchEngine } from "./research-runtime";
import manifest from "./research-manifest.json";

export default function Research() {
  const worker = useRef<Worker | null>(null);
  const engine = useRef<ResearchEngine | null>(null);
  const generation = useRef(0);
  const [consent, setConsent] = useState(false);
  const [status, setStatus] = useState("No model downloaded.");
  const [ready, setReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [removingCache, setRemovingCache] = useState(false);
  const [report, setReport] = useState("");
  useEffect(
    () => () => {
      generation.current += 1;
      worker.current?.terminate();
    },
    [],
  );
  const bytes = Object.values(manifest.files).reduce(
    (sum, file) => sum + file.size,
    0,
  );
  function cancel() {
    generation.current += 1;
    worker.current?.terminate();
    worker.current = null;
    engine.current = null;
    setReady(false);
    setBusy(false);
    setStatus("Canceled and unloaded. Downloaded model cache may remain.");
  }
  async function load() {
    if (!consent) return;
    const operation = ++generation.current;
    setBusy(true);
    try {
      if (!("gpu" in navigator))
        throw new Error("WebGPU is unavailable on this browser.");
      const start = performance.now();
      const { CreateWebWorkerMLCEngine } = await loadResearchLibrary();
      if (operation !== generation.current) return;
      const loadingWorker = new Worker(
        new URL("./research.worker.ts", import.meta.url),
        { type: "module" },
      );
      worker.current = loadingWorker;
      const loadedEngine = await CreateWebWorkerMLCEngine(
        loadingWorker,
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
          initProgressCallback: (progress) => {
            if (operation === generation.current) setStatus(progress.text);
          },
        },
      );
      if (operation !== generation.current) {
        loadingWorker.terminate();
        return;
      }
      engine.current = loadedEngine;
      setReady(true);
      setStatus(
        `Loaded in ${((performance.now() - start) / 1000).toFixed(1)} seconds. Text-only research; no learner data is used.`,
      );
    } catch (cause) {
      if (operation !== generation.current) return;
      worker.current?.terminate();
      worker.current = null;
      engine.current = null;
      setStatus(
        cause instanceof Error
          ? cause.message
          : "Research runtime unavailable.",
      );
    } finally {
      if (operation === generation.current) setBusy(false);
    }
  }
  async function evaluate() {
    const evaluatingEngine = engine.current;
    if (!evaluatingEngine) return;
    const operation = ++generation.current;
    setBusy(true);
    try {
      const results = [];
      for (const question of [
        "What is 1/2 + 1/3? Give only the fraction.",
        "Solve 2x + 3 = 11. Give x only.",
        "Explain briefly why 2/4 equals 1/2.",
      ]) {
        const start = performance.now();
        const response = await evaluatingEngine.chat.completions.create({
          messages: [{ role: "user", content: question }],
          max_tokens: 128,
          temperature: 0,
        });
        if (operation !== generation.current) return;
        results.push({
          question,
          response: response.choices[0]?.message.content,
          latency_ms: Math.round(performance.now() - start),
          usage: response.usage,
        });
      }
      const storage = await navigator.storage.estimate();
      if (operation !== generation.current) return;
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
      if (operation !== generation.current) return;
      setStatus(
        cause instanceof Error ? cause.message : "Research run failed.",
      );
    } finally {
      if (operation === generation.current) setBusy(false);
    }
  }
  async function removeCache() {
    cancel();
    const operation = generation.current;
    setBusy(true);
    setRemovingCache(true);
    try {
      const { deleteModelAllInfoInCache } = await loadResearchLibrary();
      if (operation !== generation.current) return;
      await deleteModelAllInfoInCache(manifest.model_id, {
        model_list: [
          {
            model_id: manifest.model_id,
            model: manifest.model_base,
            model_lib: manifest.model_lib,
          },
        ],
      });
      if (operation === generation.current) setStatus("Model cache removed.");
    } catch {
      if (operation === generation.current)
        setStatus("Cache removal failed. Use browser site-storage controls.");
    } finally {
      if (operation === generation.current) {
        setBusy(false);
        setRemovingCache(false);
      }
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
          disabled={removingCache}
          onChange={(e) => {
            setConsent(e.target.checked);
            if (!e.target.checked) cancel();
          }}
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
        <button disabled={removingCache} onClick={cancel}>
          Cancel and unload
        </button>
        <button disabled={busy} onClick={() => void removeCache()}>
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
