import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import RescueStepper, { minutesBetween, stepIndex } from "./RescueStepper.jsx";

describe("rescue stepper", () => {
  it("splits 'assigned' into request-sent and driver-accepted", () => {
    expect(stepIndex({ stage: "queued" })).toBe(0);
    expect(stepIndex({ stage: "assigned", accepted: false })).toBe(1);
    expect(stepIndex({ stage: "assigned", accepted: true })).toBe(2);
    expect(stepIndex({ stage: "en_route" })).toBe(3);
    expect(stepIndex({ stage: "to_shelter" })).toBe(4);
    expect(stepIndex({ stage: "rescued" })).toBe(5);
  });

  it("measures minutes between backend stamps and refuses missing ones", () => {
    expect(minutesBetween("2026-10-08T10:00:00Z", "2026-10-08T10:03:30Z")).toBeCloseTo(3.5);
    expect(minutesBetween("2026-10-08T10:00:00Z", null)).toBeNull();
  });

  it("shows the backend timestamp of each completed step", () => {
    render(
      <RescueStepper
        p={{
          name: "Priya",
          stage: "en_route",
          accepted: true,
          timestamps: { queued: "2026-10-08T10:00:00Z", assigned: "2026-10-08T10:00:03Z", accepted: "2026-10-08T10:00:05Z" },
        }}
      />
    );
    expect(screen.getByText("Driver accepted")).toBeTruthy();
    expect(screen.getByText("15:30:05 IST")).toBeTruthy();
    expect(screen.getByText("in progress")).toBeTruthy();
  });
});
