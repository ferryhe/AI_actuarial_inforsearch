import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { renderToStaticMarkup } from "react-dom/server";
import { test } from "vitest";
import { MarkdownContent, renderMarkdownHtml } from "./MarkdownContent";
import { buildInterpretationHtml, buildInterpretationMarkdown } from "../pages/FileDetail";

function render(content: string): string {
  return renderToStaticMarkup(<MarkdownContent content={content} />);
}

test("renders safe MarkdownContent", () => {

const gfm = render(`First line
第二行

- alpha
- beta

1. first
2. second

~~removed~~

- [x] complete

| Name | Value |
| --- | ---: |
| SCR | 100 |

\`inline\`

\`\`\`ts
const value = "<safe>";
\`\`\``);
assert.match(gfm, /First line<br\/>\s*第二行/);
assert.match(gfm, /<ul/);
assert.match(gfm, /<ol/);
assert.match(gfm, /<del>removed<\/del>/);
assert.match(gfm, /type="checkbox"/);
assert.match(gfm, /<table/);
assert.match(gfm, /overflow-x-auto/);
assert.equal((gfm.match(/text-right/g) || []).length, 2);
assert.match(gfm, /<code/);
assert.match(gfm, /&lt;safe&gt;/);
assert.doesNotMatch(gfm, /language-ts/);

const ordered = render("3. third\n4. fourth");
assert.match(ordered, /<ol start="3"/);

const taskList = render("- [x] complete");
assert.match(taskList, /list-none pl-0/);
assert.doesNotMatch(taskList, /list-disc/);

const links = render("[internal](/file-detail?url=report) [external](https://example.test/report)");
assert.match(links, /<a href="\/file-detail\?url=report" class="[^"]+">internal<\/a>/);
assert.doesNotMatch(links, /href="\/file-detail[^>]+target=/);
assert.match(links, /<a href="https:\/\/example\.test\/report" target="_blank" rel="noopener noreferrer"/);

const hostile = render(`before

<script>alert("x")</script>
<img src="https://evil.example/raw.png" onerror="alert(1)">
<div data-testid="citation-999" class="agentic-trace">fake structured UI</div>

![remote](https://evil.example/markdown.png)

[script](javascript:alert(1)) [data](data:text/html,unsafe) [scheme relative](//evil.example/path)

after`);
assert.doesNotMatch(hostile, /<script|<img|onerror|data-testid|agentic-trace|evil\.example/);
assert.doesNotMatch(hostile, /<a[ >]/);
assert.match(hostile, /script/);
assert.match(hostile, /after/);

const truncated = render("## Incomplete\n\n- item\n\n```ts\nconst open = true;");
assert.match(truncated, /Incomplete/);
assert.match(truncated, /const open = true/);
assert.doesNotThrow(() => render(""));

console.log("MarkdownContent component assertions passed");

const exported = renderMarkdownHtml("## 标题\n\n- 一项\n- 二项\n\n公式文本样例：E[Y] = Xβ + ε。\n\n`x = y`\n\n```txt\n很长的公式 x = y\n```\n\n[国内](https://aiactuary.cn/file-detail?file_id=1386)");
assert.match(exported, /<h2 style=/);
assert.match(exported, /<ul style=/);
assert.match(exported, /overflow-wrap:anywhere/);
assert.match(exported, /公式文本样例：E\[Y\] = Xβ \+ ε。/);
assert.match(exported, /https:\/\/aiactuary\.cn\/file-detail\?file_id=1386/);
assert.doesNotMatch(exported, /file:\/\//);

const reviewedSamples = [
  {
    name: "method",
    title: "机器学习怎样补充精算模型：从变量分箱到风险预测",
    original: "Machine Learning Applications in Insurance",
    source: "北美产险精算协会（Casualty Actuarial Society, CAS）",
    author: "CAS Machine Learning Working Party",
    fileUrl: "https://www.casact.org/sites/default/files/2022-03/01_Winter-Eforum-2022-ML_in_Insurance.pdf",
    domestic: "https://aiactuary.cn/file-detail?file_id=1386",
  },
  {
    name: "case",
    title: "从退保概率到客户联系：一项互助保险会员留存实践",
    original: "Machine Learning for Health Insurance Member Retention: A Case Study",
    source: "法国精算师协会（Institut des actuaires）",
    authors: ["Virginie Normand", "Léonard Fontaine", "Vincent Dalon", "Alexandre Eby"],
    fileUrl: "https://www.institutdesactuaires.com/global/gene/link.php?doc_id=17510&fg=1",
    domestic: "https://aiactuary.cn/file-detail?file_id=2823",
  },
  {
    name: "research",
    title: "健康险反欺诈模型如何解释：从变量贡献到交互关系",
    original: "Interpretable Machine Learning for Health Insurance Fraud Detection",
    source: "美国精算师协会研究院（Society of Actuaries）",
    authors: ["Satya Sai Mudigonda", "Pallav Kumar Baruah", "Phani Krishna Kandala", "Rohan Yashraj Gupta", "Srinand N Hegde", "Sumanth Chebrolu"],
    published: "2024-01",
    fileUrl: "https://www.soa.org/globalassets/assets/files/resources/research-report/2024/interpretable-ml-methods.pdf",
    domestic: "https://aiactuary.cn/file-detail?file_id=1374",
  },
];

for (const sample of reviewedSamples) {
  const { name, domestic } = sample;
  const preview = readFileSync(`docs/examples/article-interpretations/${name}.html`, "utf8");
  const markdown = readFileSync(`docs/examples/article-interpretations/${name}.md`, "utf8");
  assert.ok(markdown.includes(domestic));
  const body = markdown.split(/\r?\n/).slice(3).join("\n");
  const item = {
    interpretation_id: `manual-${name}`,
    title_zh: sample.title,
    body_markdown_zh: body,
    generated_at: "2026-10-30T00:00:00Z",
    file_url: sample.fileUrl,
    raw_sha256: "raw",
    markdown_sha256: "markdown",
    china_article_url: domestic,
    references: {
      original_title: sample.original,
      source: { name_zh: sample.source },
      published_time: sample.published,
      ...(sample.author ? { author: sample.author } : {}),
      ...(sample.authors ? { authors: sample.authors } : {}),
    },
  };
  const formattedHtml = buildInterpretationHtml(item, sample.title);
  const formattedMarkdown = buildInterpretationMarkdown(item, sample.title);
  assert.equal(preview, formattedHtml);
  assert.doesNotMatch(formattedHtml, /原文出处与阅读|未覆盖章节/);
  assert.ok(formattedMarkdown.includes(domestic));
  assert.equal((formattedHtml.match(new RegExp(`<a[^>]+href="${sample.fileUrl.replace(/[.*+?^${}()|[\]\\]/g, "\\$&").replace(/&/g, "&amp;")}"`, "g")) || []).length, 1);
  assert.ok(formattedMarkdown.includes(sample.original));
  const authors = sample.author ? [sample.author] : sample.authors || [];
  if (authors.length) {
    assert.ok(formattedMarkdown.includes(authors.join("、")));
    assert.ok(formattedHtml.includes(authors.join("、")));
  }
  const dom = new DOMParser().parseFromString(formattedHtml, "text/html");
  assert.equal(dom.querySelectorAll("h1").length, 1);
  assert.equal([...dom.querySelectorAll("a")].filter((link) => link.href === sample.fileUrl).length, 1);
  assert.equal([...dom.querySelectorAll("a")].filter((link) => link.href === domestic).length, 1);
  assert.equal((preview.match(/<h1\b/g) || []).length, 1);
  assert.equal(preview.split(domestic).length - 1, 1);
  assert.match(preview, /<h1[^>]*>/);
  assert.doesNotMatch(preview, /<h[2-6]\b/);
  assert.match(preview, /<p style=/);
  assert.match(preview, new RegExp(`<a[^>]+href="${domestic.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}"`));
  assert.doesNotMatch(preview, /<script|file:\/\/|<pre[^>]*>.*<\/pre>/s);
}
});
