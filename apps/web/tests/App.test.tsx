import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../src/App";
import { OfflinePractice } from "../src/OfflinePractice";
import { checkOffline } from "../src/offline-math";
import { SafeText } from "../src/SafeText";

beforeEach(() =>
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          authenticated: false,
          csrf_token: "synthetic-csrf",
        }),
        { headers: { "Content-Type": "application/json" } },
      ),
    ),
  ),
);
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
describe("entry and offline practice", () => {
  it("offers real sign-in and pairing with an authenticated CSRF bootstrap", async () => {
    render(<App />);
    expect(screen.getByRole("main")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Make room for a little math.",
    );
    await vi.waitFor(() =>
      expect(screen.getByRole("button", { name: "Sign in" })).toBeEnabled(),
    );
    expect(screen.getByLabelText("Password")).toHaveAttribute(
      "type",
      "password",
    );
    expect(
      screen.getByRole("button", { name: "Pair this device" }),
    ).toBeEnabled();
  });
  it("uses exact bounded client arithmetic and labels its result", () => {
    expect(checkOffline("10/12", 5n, 6n)).toMatch("Correct value");
    expect(checkOffline("1/0", 5n, 6n)).toMatch("cannot be zero");
    expect(checkOffline("1+1", 2n, 1n)).toMatch("Use an integer");
    expect(checkOffline("999999999/999999998", 999999999n, 999999998n)).toMatch(
      "Correct value",
    );
    render(<OfflinePractice />);
    fireEvent.click(screen.getByText("Public offline practice pack"));
    fireEvent.change(screen.getByLabelText("Offline answer"), {
      target: { value: "5/6" },
    });
    fireEvent.click(
      screen.getByRole("button", { name: "Check on this device" }),
    );
    expect(screen.getByRole("status")).toHaveTextContent(
      "checked on this device",
    );
  });
  it("renders untrusted output without HTML, external images, or links", () => {
    const { container } = render(
      <SafeText
        text={
          '<img src="https://evil.invalid/x"> **Hint** [click](javascript:alert(1)) $\\frac{1}{2}$'
        }
      />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(screen.getByText("Hint").tagName).toBe("STRONG");
    expect(container.querySelector("math")).not.toBeNull();
  });
});
