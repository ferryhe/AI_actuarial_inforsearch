import axe from "axe-core";
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { FilterBar } from "@/pages/tasks/FilterBar";

it("labels task filters, gives them mobile-size targets, and has no axe violations", async () => {
  const { container } = render(<FilterBar searchQuery="" onSearchChange={() => {}} statusFilter="" onStatusChange={() => {}} typeFilter="" onTypeChange={() => {}} />);
  for (const [id, name] of [["input-task-filter-search", "Search tasks"], ["select-task-filter-status", "Status"], ["select-task-filter-type", "Type"]]) {
    expect(screen.getByLabelText(name)).toHaveAttribute("id", id);
    expect(screen.getByLabelText(name)).toHaveClass("min-h-[44px]");
  }
  expect((await axe.run(container, { rules: { "color-contrast": { enabled: false } } })).violations).toEqual([]);
});
