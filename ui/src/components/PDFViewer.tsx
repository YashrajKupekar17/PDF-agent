"use client";

import { ChevronLeft, ChevronRight, Loader2 } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";

import { cn } from "@/lib/utils";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

type Props = {
  url: string;
  page: number;
  onPageChange: (page: number) => void;
  highlights?: string[];
};

const _normalize = (s: string) => s.replace(/\s+/g, " ").trim().toLowerCase();

function _escapeHtml(s: string): string {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function _shouldHighlight(itemText: string, normalizedQuotes: string[]): boolean {
  const item = _normalize(itemText);
  if (item.length < 3) return false;
  for (const q of normalizedQuotes) {
    if (q.length < 5) continue;
    if (q.includes(item)) return true;
  }
  return false;
}

export function PDFViewer({ url, page, onPageChange, highlights = [] }: Props) {
  const [numPages, setNumPages] = useState<number | null>(null);
  const [width, setWidth] = useState<number>(640);

  useEffect(() => {
    const update = () => {
      const el = document.getElementById("pdf-viewer-container");
      if (el) setWidth(Math.max(320, el.clientWidth - 32));
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  const total = numPages ?? 0;
  const safePage = total > 0 ? Math.min(Math.max(1, page), total) : 1;

  const normalizedHighlights = useMemo(
    () => highlights.map(_normalize).filter((s) => s.length >= 5),
    [highlights]
  );

  const customTextRenderer = useMemo(() => {
    if (normalizedHighlights.length === 0) return undefined;
    return ({ str }: { str: string }) => {
      if (!str || !str.trim()) return str;
      if (_shouldHighlight(str, normalizedHighlights)) {
        return `<mark class="pdf-hl">${_escapeHtml(str)}</mark>`;
      }
      return _escapeHtml(str);
    };
  }, [normalizedHighlights]);

  return (
    <div className="flex h-full flex-col bg-white dark:bg-zinc-950">
      <div className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 bg-zinc-50 dark:bg-zinc-900 px-3 py-2">
        <button
          onClick={() => onPageChange(Math.max(1, safePage - 1))}
          disabled={safePage <= 1}
          className={cn(
            "inline-flex items-center justify-center rounded-md border border-transparent p-1.5",
            "hover:bg-zinc-200 dark:hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed"
          )}
          aria-label="Previous page"
        >
          <ChevronLeft className="h-4 w-4" />
        </button>
        <div className="text-sm text-zinc-600 dark:text-zinc-400 tabular-nums">
          Page <span className="font-semibold text-zinc-900 dark:text-zinc-100">{safePage}</span> of {total || "…"}
        </div>
        <button
          onClick={() => onPageChange(Math.min(total, safePage + 1))}
          disabled={safePage >= total}
          className={cn(
            "inline-flex items-center justify-center rounded-md border border-transparent p-1.5",
            "hover:bg-zinc-200 dark:hover:bg-zinc-800 disabled:opacity-30 disabled:cursor-not-allowed"
          )}
          aria-label="Next page"
        >
          <ChevronRight className="h-4 w-4" />
        </button>
      </div>
      <div
        id="pdf-viewer-container"
        className="flex-1 overflow-y-auto px-4 py-4 flex justify-center"
      >
        <Document
          file={url}
          onLoadSuccess={({ numPages }) => setNumPages(numPages)}
          loading={
            <div className="flex items-center justify-center pt-10 text-zinc-500 gap-2 text-sm">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading PDF…
            </div>
          }
          error={
            <div className="text-sm text-red-600 pt-10">Could not load PDF.</div>
          }
        >
          <Page
            pageNumber={safePage}
            width={width}
            className="shadow-md rounded-sm overflow-hidden"
            renderAnnotationLayer={false}
            customTextRenderer={customTextRenderer}
          />
        </Document>
      </div>
    </div>
  );
}
