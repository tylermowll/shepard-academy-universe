import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Research from "../src/Research";
import type { ResearchEngine, ResearchLibrary } from "../src/research-runtime";

const { loadLibrary } = vi.hoisted(() => ({ loadLibrary: vi.fn() }));
vi.mock("../src/research-runtime", () => ({
  loadResearchLibrary: loadLibrary,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

const modelResponse = {
  choices: [{ message: { content: "Synthetic response" } }],
};
function engine() {
  return {
    interruptGenerate: vi.fn(),
    unload: vi.fn().mockResolvedValue(undefined),
    chat: { completions: { create: vi.fn().mockResolvedValue(modelResponse) } },
  };
}
const createEngine = vi.fn<ResearchLibrary["CreateWebWorkerMLCEngine"]>();
const deleteCache = vi.fn<ResearchLibrary["deleteModelAllInfoInCache"]>();
const library: ResearchLibrary = {
  CreateWebWorkerMLCEngine: createEngine,
  deleteModelAllInfoInCache: deleteCache,
};
const terminate = vi.fn();
const WorkerMock = vi.fn(
  class {
    terminate = terminate;
  },
);

beforeEach(() => {
  vi.clearAllMocks();
  loadLibrary.mockResolvedValue(library);
  createEngine.mockResolvedValue(engine());
  deleteCache.mockResolvedValue(undefined);
  vi.stubGlobal("Worker", WorkerMock);
  vi.stubGlobal("navigator", {
    gpu: {},
    userAgent: "Synthetic browser",
    storage: { estimate: vi.fn().mockResolvedValue({ usage: 0 }) },
  });
});
afterEach(() => vi.unstubAllGlobals());

function download() {
  fireEvent.click(screen.getByRole("checkbox"));
  fireEvent.click(
    screen.getByRole("button", { name: "Download and load experiment" }),
  );
}

it.each(["cancel", "unmount", "withdraw consent"])(
  "prevents delayed runtime loading after %s",
  async (action) => {
    const delayedLibrary = deferred<ResearchLibrary>();
    loadLibrary.mockReturnValueOnce(delayedLibrary.promise);
    const view = render(<Research />);
    expect(
      screen.getByRole("button", { name: "Download and load experiment" }),
    ).toBeDisabled();
    download();
    if (action === "unmount") view.unmount();
    else if (action === "cancel")
      fireEvent.click(
        screen.getByRole("button", { name: "Cancel and unload" }),
      );
    else fireEvent.click(screen.getByRole("checkbox"));
    await act(async () => {
      delayedLibrary.resolve(library);
      await delayedLibrary.promise;
    });
    expect(WorkerMock).not.toHaveBeenCalled();
    expect(createEngine).not.toHaveBeenCalled();
  },
);

it("ignores a canceled engine's completion and progress while a new load runs", async () => {
  const first = deferred<ResearchEngine>();
  const second = deferred<ResearchEngine>();
  createEngine
    .mockReturnValueOnce(first.promise)
    .mockReturnValueOnce(second.promise);
  render(<Research />);
  download();
  await vi.waitFor(() => expect(createEngine).toHaveBeenCalledTimes(1));
  const oldProgress = createEngine.mock.calls[0]![2].initProgressCallback;
  fireEvent.click(screen.getByRole("button", { name: "Cancel and unload" }));
  expect(terminate).toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "Download and load experiment" }),
  );
  await vi.waitFor(() => expect(createEngine).toHaveBeenCalledTimes(2));
  await act(async () => {
    oldProgress({ text: "Stale progress" });
    first.resolve(engine());
    await first.promise;
  });
  expect(screen.getByRole("status")).not.toHaveTextContent("Stale progress");
  expect(
    screen.getByRole("button", { name: "Run three synthetic questions" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Download and load experiment" }),
  ).toBeDisabled();
  await act(async () => {
    second.resolve(engine());
    await second.promise;
  });
  expect(
    screen.getByRole("button", { name: "Run three synthetic questions" }),
  ).toBeEnabled();
});

it("stops synthetic evaluation after cancellation even if its result arrives later", async () => {
  const delayedAnswer = deferred<typeof modelResponse>();
  const loaded = engine();
  vi.mocked(loaded.chat.completions.create).mockReturnValueOnce(
    delayedAnswer.promise,
  );
  createEngine.mockResolvedValueOnce(loaded);
  render(<Research />);
  download();
  await vi.waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Run three synthetic questions" }),
    ).toBeEnabled(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Run three synthetic questions" }),
  );
  fireEvent.click(screen.getByRole("button", { name: "Cancel and unload" }));
  await act(async () => {
    delayedAnswer.resolve(modelResponse);
    await delayedAnswer.promise;
  });
  expect(loaded.chat.completions.create).toHaveBeenCalledTimes(1);
  expect(
    screen.queryByLabelText("Synthetic measurement report"),
  ).not.toBeInTheDocument();
  expect(screen.getByRole("status")).toHaveTextContent("Canceled and unloaded");
});

it("loads with consent, records synthetic results, and serializes cache deletion", async () => {
  const deleting = deferred<void>();
  deleteCache.mockReturnValueOnce(deleting.promise);
  const loaded = engine();
  createEngine.mockResolvedValueOnce(loaded);
  render(<Research />);
  download();
  await vi.waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Run three synthetic questions" }),
    ).toBeEnabled(),
  );
  fireEvent.click(
    screen.getByRole("button", { name: "Run three synthetic questions" }),
  );
  await vi.waitFor(() =>
    expect(
      screen.getByLabelText<HTMLTextAreaElement>("Synthetic measurement report")
        .value,
    ).toContain("Synthetic response"),
  );
  expect(loaded.chat.completions.create).toHaveBeenCalledTimes(3);
  fireEvent.click(screen.getByRole("button", { name: "Remove model cache" }));
  await vi.waitFor(() => expect(deleteCache).toHaveBeenCalledTimes(1));
  expect(terminate).toHaveBeenCalled();
  expect(
    screen.getByRole("button", { name: "Download and load experiment" }),
  ).toBeDisabled();
  expect(
    screen.getByRole("button", { name: "Cancel and unload" }),
  ).toBeDisabled();
  await act(async () => {
    deleting.resolve();
    await deleting.promise;
  });
  expect(screen.getByRole("status")).toHaveTextContent("Model cache removed.");
  expect(
    screen.getByRole("button", { name: "Download and load experiment" }),
  ).toBeEnabled();
});
