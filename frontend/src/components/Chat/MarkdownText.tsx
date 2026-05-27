import { useMemo } from "react";

/** Lightweight Markdown renderer — no external deps.
 *  Supports: **bold**, *italic*, `inline code`, ```code blocks```,
 *  - lists, [links](url), and paragraph breaks.
 */
export function MarkdownText({ text }: { text: string }) {
  const html = useMemo(() => renderMarkdown(text), [text]);
  return <div className="markdown-body" dangerouslySetInnerHTML={{ __html: html }} />;
}

function renderMarkdown(src: string): string {
  if (!src) return "";

  // Normalize line endings
  let text = src.replace(/\r\n/g, "\n");

  // Code blocks (``` ... ```)
  text = text.replace(/```(\w*)\n([\s\S]*?)```/g, (_match, lang, code) => {
    const escaped = escapeHtml(code.trimEnd());
    const langClass = lang ? ` class="language-${lang}"` : "";
    return `<pre class="code-block"><code${langClass}>${escaped}</code></pre>`;
  });

  // Inline code
  text = text.replace(/`([^`\n]+)`/g, '<code class="inline-code">$1</code>');

  // Bold
  text = text.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");

  // Italic
  text = text.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, "<em>$1</em>");

  // Links
  text = text.replace(
    /\[([^\]]+)\]\(([^)]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>'
  );

  // Unordered list items
  text = text.replace(/^[*-]\s+(.+)$/gm, "<li>$1</li>");
  text = text.replace(/(<li>.*<\/li>\n?)+/g, (match) => `<ul>${match}</ul>`);

  // Numbered list items
  text = text.replace(/^\d+\.\s+(.+)$/gm, "<li>$1</li>");
  // Wrap consecutive <li> not already in <ul> (from numbered lists)
  text = text.replace(/(?<!<\/ul>)(<li>.*<\/li>\n?)+/g, (match) => {
    if (match.includes("<ul>")) return match;
    return `<ol>${match}</ol>`;
  });

  // Headings (### / ## / #)
  text = text.replace(/^### (.+)$/gm, "<h4>$1</h4>");
  text = text.replace(/^## (.+)$/gm, "<h3>$1</h3>");
  text = text.replace(/^# (.+)$/gm, "<h2>$1</h2>");

  // Horizontal rules
  text = text.replace(/^---+$/gm, "<hr />");

  // Paragraphs: double newlines
  text = text.replace(/\n\n+/g, "</p><p>");
  // Single newlines to <br> (except inside pre/code blocks)
  text = text.replace(/(?<!<\/pre>)\n(?![\s]*<)/g, "<br />");

  return `<p>${text}</p>`;
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
