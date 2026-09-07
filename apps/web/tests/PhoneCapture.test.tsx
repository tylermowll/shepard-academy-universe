import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PhoneCapture } from "../src/PhoneCapture";
import { PhoneLink } from "../src/PhoneLink";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("phone camera permission", () => {
  it("opens a capture screen without logging in or placing its secret in an API URL", async () => {
    const fetcher = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          received: false,
          problem_text: "1/2 + 1/3",
          processing: "Read on your computer.",
          expires_at: new Date(Date.now() + 300_000).toISOString(),
        }),
      ),
    );
    vi.stubGlobal("fetch", fetcher);
    render(<PhoneCapture token={"a".repeat(64)} />);
    expect(await screen.findByText("1/2 + 1/3")).toBeVisible();
    expect(screen.getByLabelText("Take or choose a photo")).toHaveAttribute(
      "capture",
      "environment",
    );
    expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
    expect(fetcher).toHaveBeenCalledWith("/api/v1/phone-upload", {
      headers: { "X-Photo-Token": "a".repeat(64) },
      credentials: "omit",
      cache: "no-store",
    });
    expect(localStorage.length).toBe(0);
  });

  it("shows only a receipt when the link already received its photo", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            received: true,
            problem_text: "",
            processing: "",
            expires_at: new Date().toISOString(),
          }),
        ),
      ),
    );
    render(<PhoneCapture token={"b".repeat(64)} />);
    expect(
      await screen.findByText("Photo sent to your computer."),
    ).toBeVisible();
    expect(
      screen.queryByLabelText("Take or choose a photo"),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByText("Confirm this interpretation"),
    ).not.toBeInTheDocument();
  });

  it("explains expiry without offering another upload", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            detail:
              "This photo link ended. Create a new link on your computer.",
          }),
          { status: 410 },
        ),
      ),
    );
    render(<PhoneCapture token={"c".repeat(64)} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "This photo link ended",
    );
    expect(
      screen.queryByLabelText("Take or choose a photo"),
    ).not.toBeInTheDocument();
  });

  it("creates a locally rendered QR and cancels its server permission", async () => {
    const link = {
      id: "synthetic-link",
      url: "https://tutor.invalid/#capture=synthetic",
      expires_at: new Date(Date.now() + 300_000).toISOString(),
    };
    const fetcher = vi
      .fn()
      .mockImplementation(() =>
        Promise.resolve(new Response(JSON.stringify(link))),
      );
    vi.stubGlobal("fetch", fetcher);
    render(
      <PhoneLink
        problem="synthetic-problem"
        version={2}
        disabled={false}
        act={async (action) => action()}
      />,
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Take photo with phone" }),
    );
    expect(
      await screen.findByText("Scan with your iPhone camera"),
    ).toBeVisible();
    expect(
      screen.getByRole("link", { name: "Open photo page" }),
    ).toHaveAttribute("href", link.url);
    expect(document.querySelector(".phone-link svg")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Cancel phone link" }));
    await vi.waitFor(() =>
      expect(
        screen.queryByText("Scan with your iPhone camera"),
      ).not.toBeInTheDocument(),
    );
    expect(fetcher.mock.calls[1]?.[0]).toBe(
      "/api/v1/phone-uploads/synthetic-link",
    );
    expect(fetcher.mock.calls[1]?.[1]).toMatchObject({ method: "DELETE" });
  });
});
