import { memo, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkBreaks from "remark-breaks";
import remarkGfm from "remark-gfm";
import { sanitizeReturnPath } from "@/lib/navigation";
import { cn } from "@/lib/utils";

export interface MarkdownContentProps {
  content: string;
  className?: string;
}

const REMARK_PLUGINS = [remarkGfm, remarkBreaks];
const DISALLOWED_ELEMENTS = ["img"];

function isWellFormedMarkdownUrl(url: string): boolean {
  if (/[\\\u0000-\u001f\u007f]/u.test(url)) return false;
  try {
    decodeURI(url);
    return true;
  } catch {
    return false;
  }
}

export function transformMarkdownUrl(url: string, key: string): string | undefined {
  if (key !== "href" || !url || url !== url.trim() || !isWellFormedMarkdownUrl(url)) {
    return undefined;
  }

  if (sanitizeReturnPath(url) === url) return url;
  if (!/^https?:\/\//iu.test(url)) return undefined;

  try {
    const parsed = new URL(url);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return undefined;
    if (parsed.username || parsed.password) return undefined;
    return url;
  } catch {
    return undefined;
  }
}

function MarkdownLink({ href, children }: { href?: string; children?: ReactNode }) {
  if (!href || transformMarkdownUrl(href, "href") !== href) return <>{children}</>;

  const className = "break-words text-primary underline-offset-2 hover:underline [overflow-wrap:anywhere]";
  if (sanitizeReturnPath(href) === href) {
    return <a href={href} className={className}>{children}</a>;
  }
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className={className}>
      {children}
    </a>
  );
}

const MARKDOWN_COMPONENTS: Components = {
  a: ({ href, children }) => <MarkdownLink href={href}>{children}</MarkdownLink>,
  h1: ({ children }) => <h1 className="mb-2 mt-4 text-xl font-semibold first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2 mt-4 text-lg font-semibold first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 mt-3 text-base font-semibold first:mt-0">{children}</h3>,
  h4: ({ children }) => <h4 className="mb-2 mt-3 text-sm font-semibold first:mt-0">{children}</h4>,
  h5: ({ children }) => <h5 className="mb-2 mt-3 text-sm font-medium first:mt-0">{children}</h5>,
  h6: ({ children }) => <h6 className="mb-2 mt-3 text-xs font-medium uppercase first:mt-0">{children}</h6>,
  p: ({ children }) => <p className="my-2 leading-relaxed first:mt-0 last:mb-0">{children}</p>,
  ul: ({ children }) => <ul className="my-2 list-disc space-y-1 pl-5">{children}</ul>,
  ol: ({ children }) => <ol className="my-2 list-decimal space-y-1 pl-5">{children}</ol>,
  li: ({ children }) => <li className="pl-0.5">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-primary/40 pl-3 text-muted-foreground">{children}</blockquote>
  ),
  code: ({ children }) => {
    const text = String(children);
    const isBlock = text.endsWith("\n");
    return (
      <code className={isBlock ? "font-mono" : "rounded bg-muted px-1 py-0.5 font-mono text-[0.9em]"}>
        {children}
      </code>
    );
  },
  pre: ({ children }) => (
    <pre className="my-3 max-w-full overflow-x-auto rounded-lg border border-border bg-muted/60 p-3 text-xs leading-relaxed">
      {children}
    </pre>
  ),
  table: ({ children }) => (
    <div className="my-3 max-w-full overflow-x-auto">
      <table className="min-w-max border-collapse text-left text-sm">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead className="bg-muted/70">{children}</thead>,
  th: ({ children }) => <th className="border border-border px-3 py-2 font-semibold">{children}</th>,
  td: ({ children }) => <td className="border border-border px-3 py-2 align-top">{children}</td>,
  hr: () => <hr className="my-4 border-border" />,
  input: ({ type, checked }) => type === "checkbox"
    ? <input type="checkbox" checked={Boolean(checked)} disabled className="mr-1.5 align-middle" />
    : null,
};

function MarkdownContentImpl({ content, className }: MarkdownContentProps) {
  return (
    <div className={cn("min-w-0 max-w-full break-words text-sm leading-relaxed [overflow-wrap:anywhere]", className)}>
      <ReactMarkdown
        remarkPlugins={REMARK_PLUGINS}
        components={MARKDOWN_COMPONENTS}
        disallowedElements={DISALLOWED_ELEMENTS}
        skipHtml
        urlTransform={transformMarkdownUrl}
      >
        {content}
      </ReactMarkdown>
    </div>
  );
}

export const MarkdownContent = memo(MarkdownContentImpl);
