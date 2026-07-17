import { FileText, FileSpreadsheet, FileCode, Link2, FileType, File } from "lucide-react";
import type { DocType } from "@/lib/mock/knowledge";

const map = {
  pdf: FileType,
  docx: FileText,
  txt: File,
  csv: FileSpreadsheet,
  md: FileCode,
  url: Link2,
} as const;

export function DocIcon({ type, className }: { type: DocType; className?: string }) {
  const Icon = map[type];
  return <Icon className={className ?? "size-4"} />;
}
