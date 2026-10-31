import { renderMarkdownHtml } from "@/components/MarkdownContent";

export interface ArticleInterpretation {
  interpretation_id: string;
  title_zh: string;
  body_markdown_zh: string;
  generated_at: string;
  file_url: string;
  raw_sha256: string;
  markdown_sha256: string;
  china_article_url: string;
  references?: { published_time?: string; original_title?: string; author?: string | string[]; authors?: string | string[]; source?: { name_zh?: string; name_en?: string } };
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[char]!);
}

export function interpretationAuthors(item: ArticleInterpretation): string[] {
  const values = [item.references?.author, item.references?.authors].flatMap((value) => Array.isArray(value) ? value : [value]);
  return [...new Set(values.filter((value): value is string => typeof value === "string" && !!value.trim()).map((value) => value.trim()))];
}

export function interpretationBody(item: ArticleInterpretation): string {
  const matches = [...item.body_markdown_zh.matchAll(/(?:^|\r?\n)## 原文出处与阅读[ \t]*\r?\n/g)];
  const marker = matches.at(-1);
  if (!marker || marker.index === undefined) return item.body_markdown_zh;
  const start = marker.index + (marker[0].startsWith("\r\n") ? 2 : marker[0].startsWith("\n") ? 1 : 0);
  const footer = item.body_markdown_zh.slice(start);
  const normalizedFooter = footer.replace(/\r\n/g, "\n").trimEnd();
  const lines = normalizedFooter.split("\n");
  const exactCitationLine = `[原文](${item.file_url}) · [国内阅读](${item.china_article_url})`;
  let cursor = 5;
  if (lines[cursor] === "" && /^规范来源：[^\r\n]+。$/.test(lines[cursor + 1] || "")) cursor += 2;
  if (lines[cursor] === "" && /^未覆盖章节：[^\r\n]+$/.test(lines[cursor + 1] || "")) cursor += 2;
  if (
    lines[0] !== "## 原文出处与阅读"
    || lines[1] !== ""
    || !/^原文日期：.+。$/.test(lines[2] || "")
    || lines[3] !== ""
    || lines[4] !== exactCitationLine
    || cursor !== lines.length
  ) return item.body_markdown_zh;
  return item.body_markdown_zh.slice(0, start).trimEnd();
}

export function buildInterpretationMarkdown(item: ArticleInterpretation, fileTitle: string): string {
  const authors = interpretationAuthors(item);
  const title = item.references?.original_title ?? fileTitle;
  const body = interpretationBody(item);
  const published = item.references?.published_time && item.references.published_time !== "日期不明" ? ` · 发表日期：${item.references.published_time}` : "";
  const source = item.references?.source?.name_zh ? ` · ${item.references.source.name_zh}` : "";
  const author = authors.length ? `\n\n作者：${authors.join("、")}` : "";
  return `# ${item.title_zh}\n\n${body}\n\n---\n\n原文：${title}${source}${published}${author}\n\n[原文](${item.file_url})\n\n[在国内站阅读原文](${item.china_article_url})`;
}

export function buildInterpretationHtml(item: ArticleInterpretation, fileTitle: string): string {
  const title = item.references?.original_title ?? fileTitle;
  const body = interpretationBody(item);
  const authors = interpretationAuthors(item);
  const published = item.references?.published_time && item.references.published_time !== "日期不明" ? item.references.published_time : "";
  const attribution = `<p>原文：${escapeHtml(title)}</p>${item.references?.source?.name_zh ? `<p>机构：${escapeHtml(item.references.source.name_zh)}</p>` : ""}${authors.length ? `<p>作者：${escapeHtml(authors.join("、"))}</p>` : ""}${published ? `<p>发表日期：${escapeHtml(published)}</p>` : ""}`;
  return `<!doctype html><html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${escapeHtml(item.title_zh)}</title></head><body style="margin:0;padding:20px;font:16px/1.8 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#222;overflow-wrap:anywhere"><article style="box-sizing:border-box;width:100%;max-width:720px;margin:0 auto"><h1 style="font-size:1.8em;line-height:1.35;overflow-wrap:anywhere">${escapeHtml(item.title_zh)}</h1>${renderMarkdownHtml(body)}<hr style="margin:1.5em 0;border:0;border-top:1px solid #ddd">${attribution}<p><a href="${escapeHtml(item.file_url)}" style="color:#1457a6;overflow-wrap:anywhere">原文</a></p><p><a href="${escapeHtml(item.china_article_url)}" style="color:#1457a6;overflow-wrap:anywhere">在国内站阅读原文</a></p></article></body></html>`;
}
