// Tiny markdown renderer for the side panel + welcome card. Handles only
// what one-page docs typically use: headings (# / ## / ###), bold, italic,
// inline code, paragraphs, and unordered/ordered lists. No nested lists,
// no tables, no links — keep the surface small and the output safe.
//
// Output is HTML. All raw input is HTML-escaped first, then a small set
// of explicit transformations are applied. This is fine for content
// admin-edited; we don't render arbitrary participant input through here.

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function inline(s: string): string {
  // Order matters: code first so its contents aren't bolded.
  return s
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*]+)\*([^*]|$)/g, "$1<em>$2</em>$3")
    .replace(/_([^_]+)_/g, "<em>$1</em>");
}

export function renderMarkdown(source: string): string {
  const escaped = escapeHtml(source).replace(/\r\n?/g, "\n");
  const lines = escaped.split("\n");
  const out: string[] = [];

  let i = 0;
  while (i < lines.length) {
    const line = lines[i];

    // Heading.
    const h = /^(#{1,6})\s+(.+?)\s*$/.exec(line);
    if (h) {
      const level = h[1].length;
      out.push(`<h${level}>${inline(h[2])}</h${level}>`);
      i += 1;
      continue;
    }

    // Unordered list.
    if (/^[-*]\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^[-*]\s+/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^[-*]\s+/, ""))}</li>`);
        i += 1;
      }
      out.push(`<ul>${items.join("")}</ul>`);
      continue;
    }

    // Ordered list.
    if (/^\d+\.\s+/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s+/.test(lines[i])) {
        items.push(`<li>${inline(lines[i].replace(/^\d+\.\s+/, ""))}</li>`);
        i += 1;
      }
      out.push(`<ol>${items.join("")}</ol>`);
      continue;
    }

    // Blank line — paragraph break.
    if (!line.trim()) {
      i += 1;
      continue;
    }

    // Paragraph (gather consecutive non-empty non-special lines).
    const para: string[] = [];
    while (
      i < lines.length &&
      lines[i].trim() &&
      !/^(#{1,6})\s+/.test(lines[i]) &&
      !/^[-*]\s+/.test(lines[i]) &&
      !/^\d+\.\s+/.test(lines[i])
    ) {
      para.push(lines[i]);
      i += 1;
    }
    out.push(`<p>${inline(para.join(" "))}</p>`);
  }

  return out.join("\n");
}
