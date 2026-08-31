import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { MarkdownContent, transformMarkdownUrl } from "./MarkdownContent";

function render(content: string): string {
  return renderToStaticMarkup(<MarkdownContent content={content} />);
}

assert.equal(transformMarkdownUrl("/chat?kb_id=one#answer", "href"), "/chat?kb_id=one#answer");
assert.equal(transformMarkdownUrl("https://example.test/report?q=1", "href"), "https://example.test/report?q=1");
assert.equal(transformMarkdownUrl("http://example.test/report", "href"), "http://example.test/report");
for (const unsafeUrl of [
  "//evil.example/path",
  "javascript:alert(1)",
  "data:text/html,unsafe",
  "file:///tmp/unsafe",
  "vbscript:msgbox(1)",
  "mailto:person@example.test",
  "relative/path",
  "https://exa mple.test",
  "https://example.test/%ZZ",
  "https://example.test\\@evil.example",
  "https://user:password@example.test/report",
  " https://example.test",
]) {
  assert.equal(transformMarkdownUrl(unsafeUrl, "href"), undefined, unsafeUrl);
}
assert.equal(transformMarkdownUrl("https://example.test/image.png", "src"), undefined);

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
assert.match(gfm, /<code/);
assert.match(gfm, /&lt;safe&gt;/);
assert.doesNotMatch(gfm, /language-ts/);

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
