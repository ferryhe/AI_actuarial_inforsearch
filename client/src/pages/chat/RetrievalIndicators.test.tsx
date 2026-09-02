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

function render(values: Omit<Parameters<typeof RetrievalIndicators>[0], "t">): string {
  return renderToStaticMarkup(<RetrievalIndicators {...values} t={t} />);
}

function assertLabels(
  values: Omit<Parameters<typeof RetrievalIndicators>[0], "t">,
  expectedLabels: string[],
): void {
  const markup = render(values);
  const labels = Array.from(markup.matchAll(/aria-label="([^"]+)"/g), (match) => match[1]);
  assert.deepEqual(labels, expectedLabels);
  assert.equal((markup.match(/whitespace-nowrap/g) || []).length, expectedLabels.length);
  assert.match(markup, /class="flex flex-wrap items-center gap-2"/);
}

const keywordMethods = [
  ["summaries", "Summaries"],
  ["titles", "Titles"],
  ["sections", "Sections"],
  ["relations", "Relations"],
  ["formulas", "Formulas"],
  ["tables", "Tables"],
  ["calculation_terms", "Calculation terms"],
] as const;

for (const [method, methodLabel] of keywordMethods) {
  assertLabels(
    { keywordRelevance100: 31, retrievalMethod: method },
    ["Keyword relevance: 31/100", `Retrieval method: ${methodLabel}`],
  );
}

assertLabels(
  { semanticRelevance100: 83, retrievalMethod: "vector" },
  ["Semantic relevance: 83/100", "Retrieval method: Semantic retrieval"],
);
assertLabels(
  { semanticRelevance100: 0, retrievalMethod: "vector" },
  ["Semantic relevance: 0/100", "Retrieval method: Semantic retrieval"],
);
assertLabels(
  { keywordRelevance100: 100, retrievalMethod: "tables" },
  ["Keyword relevance: 100/100", "Retrieval method: Tables"],
);

assertLabels(
  {
    semanticRelevance100: 83,
    keywordRelevance100: 50,
    retrievalMethod: "formulas",
  },
  [
    "Semantic relevance: 83/100",
    "Keyword relevance: 50/100",
    "Retrieval method: Formulas",
  ],
);
assertLabels(
  {
    semanticRelevance100: 83,
    keywordRelevance100: 50,
    retrievalMethod: "vector",
  },
  [
    "Semantic relevance: 83/100",
    "Keyword relevance: 50/100",
    "Retrieval method: Semantic retrieval",
  ],
);

const invalidApplicableScores = [
  undefined,
  null,
  Number.NaN,
  Number.POSITIVE_INFINITY,
  10.5,
  -1,
  101,
];

for (const score of invalidApplicableScores) {
  assertLabels(
    { semanticRelevance100: score, retrievalMethod: "vector" },
    ["Semantic relevance: —", "Retrieval method: Semantic retrieval"],
  );
  assertLabels(
    { keywordRelevance100: score, retrievalMethod: "titles" },
    ["Keyword relevance: —", "Retrieval method: Titles"],
  );
}

assertLabels(
  { retrievalMethod: "titles" },
  ["Keyword relevance: —", "Retrieval method: Titles"],
);
assertLabels(
  { retrievalMethod: "vector" },
  ["Semantic relevance: —", "Retrieval method: Semantic retrieval"],
);

assertLabels(
  { retrievalMethod: "  future_method  " },
  ["Retrieval method: Other"],
);
assertLabels(
  { semanticRelevance100: 72, retrievalMethod: "future_method" },
  ["Semantic relevance: 72/100", "Retrieval method: Other"],
);
assertLabels(
  { keywordRelevance100: 48, retrievalMethod: "future_method" },
  ["Keyword relevance: 48/100", "Retrieval method: Other"],
);
assertLabels(
  {
    semanticRelevance100: 72,
    keywordRelevance100: 48,
    retrievalMethod: "future_method",
  },
  [
    "Semantic relevance: 72/100",
    "Keyword relevance: 48/100",
    "Retrieval method: Other",
  ],
);
assertLabels(
  {
    semanticRelevance100: Number.NaN,
    keywordRelevance100: 10.5,
    retrievalMethod: "future_method",
  },
  ["Retrieval method: Other"],
);
assertLabels({}, ["Retrieval method: Other"]);

const componentSource = readFileSync(new URL("./RetrievalIndicators.tsx", import.meta.url), "utf8");
assert.match(componentSource, /flex flex-wrap items-center gap-2/);
assert.match(componentSource, /whitespace-nowrap/);
console.log("chat retrieval indicator component assertions passed");
