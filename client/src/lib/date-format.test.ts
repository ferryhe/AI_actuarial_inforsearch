import { expect, it } from "vitest";
import { formatDateTime, formatUtcIso } from "./date-format";

it("formats valid instants in the app locale and safely falls back for invalid values", () => {
  expect(formatDateTime("2026-03-08T07:30:00Z", "en", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" })).toContain("3:30");
  expect(formatDateTime("2026-03-08T07:30:00Z", "zh", { timeZone: "America/New_York", hour: "2-digit", minute: "2-digit" })).toContain("3:30");
  expect(formatDateTime("not-a-date", "en")).toBe("—");
  expect(formatDateTime(null, "zh")).toBe("—");
  expect(formatUtcIso("not-a-date")).toBeNull();
});

it("keeps UTC calendar boundaries distinct from browser-local dates", () => {
  const instant = "2026-03-08T00:30:00Z";
  expect(formatDateTime(instant, "en", { timeZone: "UTC", year: "numeric", month: "short", day: "numeric" })).toContain("Mar 8");
  expect(formatDateTime(instant, "en", { timeZone: "America/New_York", year: "numeric", month: "short", day: "numeric" })).toContain("Mar 7");
  expect(formatUtcIso(instant)).toBe("2026-03-08T00:30:00.000Z");
  expect(formatDateTime("2026-01-01T00:30:00Z", "en", { timeZone: "Asia/Shanghai", year: "numeric", month: "short", day: "numeric" })).toContain("Jan 1");
});
