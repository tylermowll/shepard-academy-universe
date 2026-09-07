/** Narrow runtime-checked boundary for WebLLM's self-contained ESM distribution.
 * Upstream declarations import unpublished development runtimes and extension-only
 * globals. Keep those outside the application rather than skipping type checks.
 */
import runtimeURL from "@mlc-ai/web-llm/lib/index.js?url";
export { runtimeURL };
export type ResearchEngine = {
  interruptGenerate(): void;
  unload(): Promise<void>;
  chat: {
    completions: {
      create(input: {
        messages: { role: "user"; content: string }[];
        max_tokens: number;
        temperature: number;
      }): Promise<{
        choices: { message: { content: string | null } }[];
        usage?: unknown;
      }>;
    };
  };
};
type ModelRecord = {
  model_id: string;
  model: string;
  model_lib: string;
  required_features?: string[];
  overrides?: { context_window_size: number };
};
type AppConfig = { model_list: ModelRecord[] };
export type ResearchLibrary = {
  CreateWebWorkerMLCEngine(
    this: void,
    worker: Worker,
    model: string,
    options: {
      appConfig: AppConfig;
      initProgressCallback: (report: { text: string }) => void;
    },
  ): Promise<ResearchEngine>;
  deleteModelAllInfoInCache(
    this: void,
    model: string,
    config: AppConfig,
  ): Promise<void>;
};
export async function loadResearchLibrary(): Promise<ResearchLibrary> {
  const library: unknown = await import(/* @vite-ignore */ runtimeURL);
  if (
    typeof library !== "object" ||
    library === null ||
    !("CreateWebWorkerMLCEngine" in library) ||
    typeof library.CreateWebWorkerMLCEngine !== "function" ||
    !("deleteModelAllInfoInCache" in library) ||
    typeof library.deleteModelAllInfoInCache !== "function"
  )
    throw new Error("Unsupported browser research runtime.");
  return library as ResearchLibrary;
}
