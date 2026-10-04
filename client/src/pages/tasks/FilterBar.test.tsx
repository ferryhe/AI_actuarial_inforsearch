import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { test } from "vitest";
import { FilterBar } from "./FilterBar";

test("task filters use shared enum labels while preserving API filter values", () => {
  const markup = renderToStaticMarkup(<FilterBar searchQuery="" onSearchChange={() => {}} statusFilter="" onStatusChange={() => {}} typeFilter="" onTypeChange={() => {}} />);
  assert.match(markup, /<option value="" selected="">tasks\.filter\.all_status<\/option>/);
  assert.match(markup, /<option value="running">enum\.status\.running<\/option>/);
  assert.match(markup, /<option value="completed">enum\.status\.completed<\/option>/);
  assert.match(markup, /<option value="scheduled">tasks\.type\.scheduled<\/option>/);
  assert.match(markup, /<option value="quick_check">tasks\.type\.web_crawl<\/option>/);
  assert.match(markup, /<option value="embedding_generation">tasks\.type\.chunk<\/option>/);
  assert.match(markup, /<option value="ready_data_build">tasks\.type\.ready_data_build<\/option>/);
});
