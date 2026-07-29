import { describe, expect, it } from "vitest";
import { renderMarkdown } from "./markdown";

describe("renderMarkdown", () => {
  it("renders headings, emphasis, code and lists", () => {
    const html = renderMarkdown("# Title\n\nSome **bold** and `code`.\n\n- one\n- two");
    expect(html).toContain("<h1");
    expect(html).toContain("<strong>bold</strong>");
    expect(html).toContain("<code");
    expect(html).toContain("<li>one</li>");
    expect(html).toContain("<li>two</li>");
  });

  it("links only http(s) targets", () => {
    const html = renderMarkdown("[docs](https://example.com/x)");
    expect(html).toContain('href="https://example.com/x"');
    expect(html).toContain('rel="noreferrer noopener"');
  });

  it("escapes HTML in the source so it can never become live markup", () => {
    const html = renderMarkdown('<script>alert("xss")</script>');
    expect(html).not.toContain("<script>");
    expect(html).toContain("&lt;script&gt;");
  });

  it("neutralises an inline event handler dressed up as markup", () => {
    const html = renderMarkdown('<img src=x onerror="alert(1)">');
    expect(html).not.toContain("<img");
    expect(html).toContain("&lt;img");
  });

  it("does not turn a javascript: link into an anchor", () => {
    // The link pattern only accepts http(s), so this stays literal text.
    const html = renderMarkdown("[click](javascript:alert(1))");
    expect(html).not.toContain("<a ");
    expect(html).toContain("javascript:alert(1)");
  });

  it("keeps code-block contents intact, including an unterminated fence", () => {
    expect(renderMarkdown("```\nconst a = 1;\n```")).toContain("const a = 1;");
    expect(renderMarkdown("```\nstill shown")).toContain("still shown");
  });

  it("treats blank lines as paragraph breaks", () => {
    const html = renderMarkdown("first para\n\nsecond para");
    expect(html.match(/<p>/g)).toHaveLength(2);
  });
});
