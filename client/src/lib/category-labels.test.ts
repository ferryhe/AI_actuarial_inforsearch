import assert from "node:assert/strict";
import { test } from "vitest";
import { categoryDisplayName } from "./category-labels";

test("formats category display labels", () => {
assert.equal(categoryDisplayName(null, "en"), "-");
assert.equal(categoryDisplayName(undefined, "zh"), "-");
assert.equal(categoryDisplayName("Pricing", "en"), "Pricing");
assert.equal(categoryDisplayName("Pricing", "zh"), "定价");
assert.equal(
  categoryDisplayName(
    { name: "Custom", label: "Default label", labels: { zh: "本地化标签" } },
    "zh",
  ),
  "本地化标签",
);
assert.equal(
  categoryDisplayName({ name: "Custom", label: "Default label" }, "en"),
  "Default label",
);
});
