"use client";

import { FileText, Loader2, Upload } from "lucide-react";
import { type ChangeEvent, type DragEvent, useState } from "react";

import { cn } from "@/lib/utils";

type Props = {
  onUpload: (file: File) => Promise<void>;
};

export function UploadCard({ onUpload }: Props) {
  const [busy, setBusy] = useState(false);
  const [drag, setDrag] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handle = async (file: File) => {
    setError(null);
    if (file.type !== "application/pdf" && !file.name.endsWith(".pdf")) {
      setError("Please choose a PDF file.");
      return;
    }
    setBusy(true);
    try {
      await onUpload(file);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Upload failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex h-full items-center justify-center px-6">
      <div
        onDragOver={(e: DragEvent) => {
          e.preventDefault();
          setDrag(true);
        }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e: DragEvent) => {
          e.preventDefault();
          setDrag(false);
          const f = e.dataTransfer.files?.[0];
          if (f) handle(f);
        }}
        className={cn(
          "w-full max-w-xl rounded-3xl border-2 border-dashed p-12 text-center transition-colors",
          drag
            ? "border-blue-500 bg-blue-50 dark:bg-blue-950/30"
            : "border-zinc-300 dark:border-zinc-700 bg-zinc-50 dark:bg-zinc-900/50"
        )}
      >
        <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900">
          <FileText className="h-7 w-7" />
        </div>
        <h2 className="text-2xl font-semibold tracking-tight">
          Upload a PDF
        </h2>
        <p className="mt-2 max-w-sm mx-auto text-sm text-zinc-600 dark:text-zinc-400">
          Drag & drop or browse. The agent answers strictly from the document and
          cites the exact page + verbatim quote for every claim.
        </p>
        <label className="mt-6 inline-flex cursor-pointer items-center gap-2 rounded-full bg-zinc-900 px-5 py-2.5 text-sm font-medium text-zinc-50 hover:opacity-90 dark:bg-zinc-100 dark:text-zinc-900">
          {busy ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" /> Indexing…
            </>
          ) : (
            <>
              <Upload className="h-4 w-4" /> Choose PDF
            </>
          )}
          <input
            type="file"
            accept="application/pdf,.pdf"
            disabled={busy}
            className="hidden"
            onChange={(e: ChangeEvent<HTMLInputElement>) => {
              const f = e.target.files?.[0];
              if (f) handle(f);
            }}
          />
        </label>
        {error && (
          <p className="mt-4 text-sm text-red-600 dark:text-red-400">{error}</p>
        )}
        <p className="mt-6 text-xs text-zinc-400 dark:text-zinc-600">
          Max 25 MB · PDF only · stays local during the session
        </p>
      </div>
    </div>
  );
}
