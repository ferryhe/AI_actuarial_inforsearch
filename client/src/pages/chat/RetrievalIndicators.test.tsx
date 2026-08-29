import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { RetrievalIndicators } from "./RetrievalIndicators";

const translations: Record<string, string> = {
  "chat.relevance.semantic": "Semantic relevance",
  "chat.relevance.keyword": "Keyword relevance",
  "chat.relevance.method": "Retrieval method",
  "chat.retrieval_method.vector": "Semantic retrieval",
  "chat.retrieval_method.summaries": "Summaries",
  "chat.retrieval_method.titles": "Titles",
  "chat.retrieval_method.sections": "Sections",
  "chat.retrieval_method.relations": "Relations",
  "chat.retrieval_method.formulas": "Formulas",
  "chat.retrieval_method.tables": "Tables",
  "chat.retrieval_method.calculation_terms": "Calculation terms",
  "chat.retrieval_method.other": "Other",
};
const t = (key: string) => translations[key] || key;

function render(values: Parameters<typeof RetrievalIndicators>[0]): string {
  return renderToStaticMarkup(<RetrievalIndicators {...values} />);
}

const full = render({
  semanticRelevance100: 83,
  keywordRelevance100: 50,
  retrievalMethod: "formulas",
  t,
});
assert.match(full, /Semantic relevance: 83\/100/);
assert.match(full, /Keyword relevance: 50\/100/);
assert.match(full, /Retrieval method: Formulas/);
assert.equal((full.match(/whitespace-nowrap/g) || []).length, 3);

const single = render({ keywordRelevance100: 72, t });
assert.match(single, /Semantic relevance: —/);
assert.match(single, /Keyword relevance: 72\/100/);
assert.match(single, /Retrieval method: Other/);

const missing = render({ t });
assert.match(missing, /Semantic relevance: —/);
assert.match(missing, /Keyword relevance: —/);
assert.match(missing, /Retrieval method: Other/);

const unknown = render({ retrievalMethod: "future_method", t });
assert.match(unknown, /Retrieval method: Other/);
assert.match(unknown, /aria-label="Retrieval method: Other"/);

const componentSource = readFileSync(new URL("./RetrievalIndicators.tsx", import.meta.url), "utf8");
assert.match(componentSource, /flex flex-wrap items-center gap-2/);
assert.match(componentSource, /whitespace-nowrap/);
console.log("chat retrieval indicator component assertions passed");
