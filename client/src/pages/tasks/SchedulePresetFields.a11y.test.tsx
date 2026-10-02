import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { SchedulePresetFields } from "./SchedulePresetFields";

it("labels schedule controls and has no axe violations", async () => {
  const { container } = render(<SchedulePresetFields value={{ frequency: "daily", quantity: "1", time: "08:30", timezone: "UTC" }} onChange={() => undefined} taskType="catalog" testIdPrefix="a11y" />);
  expect(screen.getByLabelText("tasks.sched.frequency")).toBeInTheDocument();
  expect(screen.getByLabelText("tasks.sched.run_time")).toBeInTheDocument();
  expect(screen.getByLabelText("tasks.sched.timezone")).toBeInTheDocument();
  expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});
