import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { App } from "../src/App";

describe("development preview", () => {
  it("renders the welcome screen and clearly labels unavailable practice", () => {
    render(<App />);

    expect(screen.getByRole("main")).toBeVisible();
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Make room for a little math.",
    );
    const availability = screen.getByRole("complementary", {
      name: "Preview availability",
    });
    expect(
      within(availability).getByText(/Practice sessions are not available yet/),
    ).toBeVisible();
  });
});
