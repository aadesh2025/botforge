import type { DocStatus } from "./types";

export type DocType = "pdf" | "docx" | "txt" | "csv" | "md" | "url";

export interface KbDocument {
  id: string;
  name: string;
  type: DocType;
  status: DocStatus;
  chunks: number;
  sizeKb: number;
  progress: number; // 0..100 (for processing)
  addedAt: string;
}

export const kbDocuments: Record<string, KbDocument[]> = {
  kb_1: [
    { id: "doc_1", name: "product-guide.pdf", type: "pdf", status: "ready", chunks: 214, sizeKb: 2480, progress: 100, addedAt: "2026-07-16T09:12:00Z" },
    { id: "doc_2", name: "api-reference.md", type: "md", status: "ready", chunks: 96, sizeKb: 320, progress: 100, addedAt: "2026-07-16T09:20:00Z" },
    { id: "doc_3", name: "changelog-2026.txt", type: "txt", status: "processing", chunks: 0, sizeKb: 88, progress: 62, addedAt: "2026-07-17T05:40:00Z" },
    { id: "doc_4", name: "https://docs.aurozen.ai/faq", type: "url", status: "ready", chunks: 41, sizeKb: 0, progress: 100, addedAt: "2026-07-15T11:00:00Z" },
    { id: "doc_5", name: "pricing-sheet.csv", type: "csv", status: "failed", chunks: 0, sizeKb: 24, progress: 0, addedAt: "2026-07-17T04:10:00Z" },
    { id: "doc_6", name: "onboarding.docx", type: "docx", status: "queued", chunks: 0, sizeKb: 540, progress: 0, addedAt: "2026-07-17T06:05:00Z" },
  ],
  kb_2: [
    { id: "doc_7", name: "help-center-export.pdf", type: "pdf", status: "ready", chunks: 612, sizeKb: 8100, progress: 100, addedAt: "2026-07-14T10:00:00Z" },
    { id: "doc_8", name: "macros.md", type: "md", status: "ready", chunks: 88, sizeKb: 210, progress: 100, addedAt: "2026-07-14T10:30:00Z" },
  ],
  kb_3: [
    { id: "doc_9", name: "returns-policy.pdf", type: "pdf", status: "ready", chunks: 42, sizeKb: 640, progress: 100, addedAt: "2026-07-10T09:05:00Z" },
    { id: "doc_10", name: "shipping-zones.csv", type: "csv", status: "ready", chunks: 168, sizeKb: 96, progress: 100, addedAt: "2026-07-10T09:10:00Z" },
  ],
};

export const docStatusMeta: Record<
  DocStatus,
  { label: string; variant: "success" | "warn" | "info" | "error" | "default" }
> = {
  ready: { label: "Ready", variant: "success" },
  processing: { label: "Processing", variant: "info" },
  queued: { label: "Queued", variant: "default" },
  failed: { label: "Failed", variant: "error" },
};
