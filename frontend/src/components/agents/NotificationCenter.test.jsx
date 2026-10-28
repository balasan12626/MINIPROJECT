import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import NotificationCenter from "./NotificationCenter.jsx";

const msg = (id, severity, title) => ({
  id,
  severity,
  title,
  text: `${title} text`,
  at: "2026-10-08T10:00:00Z",
  from_name: "Manager Agent",
  to_names: ["Ambulance Agent"],
});

describe("notification centre", () => {
  it("counts unread, colours the bell by the worst one, and filters by severity", () => {
    const messages = [msg(3, "red", "ALL ON FIELD"), msg(2, "yellow", "Unit dispatched"), msg(1, "green", "Safe at shelter")];
    render(<NotificationCenter messages={messages} runId="t1" />);
    const bell = screen.getByRole("button", { name: /Notifications, 3 unread/ });
    expect(bell.className).toContain("sev-red");
    fireEvent.click(bell);
    expect(screen.getByText("Safe at shelter")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /🔴 1/ }));
    expect(screen.queryByText("Safe at shelter")).toBeNull();
    expect(screen.getByText("ALL ON FIELD")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Mark all read" }));
    expect(screen.getByRole("button", { name: /Notifications, 0 unread/ })).toBeTruthy();
  });

  it("pops up only new yellow / red notifications, not the backlog", () => {
    const { rerender } = render(<NotificationCenter messages={[msg(1, "red", "Old alert")]} runId="t2" />);
    expect(document.querySelector(".notif-toast")).toBeNull();
    rerender(<NotificationCenter messages={[msg(3, "green", "Safe"), msg(2, "red", "Sudden rise"), msg(1, "red", "Old alert")]} runId="t2" />);
    const toasts = [...document.querySelectorAll(".notif-toast")].map((t) => t.textContent);
    expect(toasts).toHaveLength(1);
    expect(toasts[0]).toContain("Sudden rise");
  });
});
