import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { PiiBadge, PiiSummary, describeFlags } from "./pii-flags";
import type { ApiDocument } from "@/lib/api/types";

function doc(pii_flags: Record<string, number> | null, id = "d1"): ApiDocument {
  return {
    id,
    knowledge_base_id: "kb1",
    source_type: "file",
    filename: "policy.pdf",
    mime_type: "application/pdf",
    size_bytes: 100,
    source_url: null,
    status: "ready",
    error_message: null,
    chunk_count: 3,
    pii_flags,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };
}

describe("describeFlags", () => {
  it("pluralises per kind", () => {
    expect(describeFlags({ email: 1 })).toBe("1 email address");
    expect(describeFlags({ email: 2, phone: 1 })).toBe("2 email addresses, 1 phone number");
  });

  it("drops zero counts and names unknown kinds rather than hiding them", () => {
    expect(describeFlags({ email: 0, phone: 1 })).toBe("1 phone number");
    expect(describeFlags({ passport: 1 })).toBe("1 passport");
  });
});

describe("PiiBadge", () => {
  it("warns with the categories found", () => {
    render(<PiiBadge flags={{ email: 2, phone: 1 }} />);
    expect(screen.getByText("2 email addresses, 1 phone number")).toBeInTheDocument();
  });

  it("renders nothing for a clean document", () => {
    const { container } = render(<PiiBadge flags={{}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing when the document was never scanned", () => {
    // Silence, not a clean bill of health — the document predates the scan.
    const { container } = render(<PiiBadge flags={null} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("PiiSummary", () => {
  it("states affirmatively when nothing was found", () => {
    // A silent absence reads as "not implemented", which is what an operator must not
    // conclude about a safety check.
    render(<PiiSummary documents={[doc({}), doc({}, "d2")]} />);
    expect(screen.getByText(/No contact details or secrets found in 2 documents/)).toBeInTheDocument();
  });

  it("counts only the flagged documents", () => {
    render(<PiiSummary documents={[doc({ email: 1 }), doc({}, "d2"), doc({ phone: 2 }, "d3")]} />);
    expect(screen.getByText(/2 documents contain/)).toBeInTheDocument();
  });

  it("separates never-scanned documents from clean ones", () => {
    render(<PiiSummary documents={[doc({}), doc(null, "d2")]} />);
    expect(screen.getByText(/No contact details or secrets found in 1 document/)).toBeInTheDocument();
    expect(screen.getByText(/1 added before scanning existed/)).toBeInTheDocument();
  });

  it("renders nothing when no document has been scanned at all", () => {
    const { container } = render(<PiiSummary documents={[doc(null), doc(null, "d2")]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
