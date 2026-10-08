import { render, screen, fireEvent } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ErrorBoundary from "./ErrorBoundary.jsx";

let shouldThrow = true;
function Boom() {
  if (shouldThrow) throw new Error("kaboom");
  return <p>recovered</p>;
}

describe("ErrorBoundary", () => {
  it("contains a render error, logs it, and recovers on retry", () => {
    const spy = vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <div>
        <p>sibling stays</p>
        <ErrorBoundary name="Test section">
          <Boom />
        </ErrorBoundary>
      </div>
    );
    expect(screen.getByText("sibling stays")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("kaboom");
    expect(spy.mock.calls.some((c) => String(c[0]).includes('"Test section" crashed'))).toBe(true);

    shouldThrow = false;
    fireEvent.click(screen.getByText("Retry this section"));
    expect(screen.getByText("recovered")).toBeTruthy();
    spy.mockRestore();
  });
});
