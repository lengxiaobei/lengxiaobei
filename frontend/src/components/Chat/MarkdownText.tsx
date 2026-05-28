import { useMemo, useEffect, useRef, useCallback } from "react";

const CODE_COLLAPSE_LINES = 15;

/** Lightweight Markdown renderer — no external deps.
 *  Supports: **bold**, *italic*, `inline code`, ```code blocks```,
 *  - lists, [links](url), and paragraph breaks.
 */
export function MarkdownText({ text }: { text: string }) {
  const html = useMemo(() => renderMarkdown(text), [text]);
  const containerRef = useRef<HTMLDivElement>(null);

  const wrapLongCodeBlocks = useCallback(() => {
    const container = containerRef.current;
    if (!container) return;

    const pres = container.querySelectorAll<HTMLPreElement>(".code-block:not(.code-wrapped)");

    pres.forEach((pre, idx) => {
      const lineCount = (pre.textContent || "").split("\n").length;
      if (lineCount <= CODE_COLLAPSE_LINES) {
        pre.classList.add("code-wrapped");
        return;
      }

      pre.classList.add("code-wrapped", "code-collapsible");

      // Wrap in collapsible container
      const wrapper = document.createElement("div");
      wrapper.className = "code-collapse-wrapper";

      const btn = document.createElement("button");
      btn.className = "code-collapse-btn";
      btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg> 展开代码块 (${lineCount} 行)`;
      btn.setAttribute("data-code-idx", String(idx));

      btn.addEventListener("click", () => {
        const isCollapsed = wrapper.classList.toggle("code-expanded");
        const chevron = btn.querySelector("svg")!;
        if (isCollapsed) {
          btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="18 15 12 9 6 15"></polyline></svg> 收起代码块`;
        } else {
          btn.innerHTML = `<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polyline points="6 9 12 15 18 9"></polyline></svg> 展开代码块 (${lineCount} 行)`;
        }
      });

      pre.parentNode?.insertBefore(wrapper, pre);
      wrapper.appendChild(btn);
      wrapper.appendChild(pre);
    });
  }, []);

  useEffect(() => {
    // Small delay to let the DOM settle
    const timer = setTimeout(wrapLongCodeBlocks, 0);
    return () => clearTimeout(timer);
  }, [html, wrapLongCodeBlocks]);

  return <div className="markdown-body" ref={containerRef} dangerouslySetInnerHTML={{ __html: html }} />;
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
