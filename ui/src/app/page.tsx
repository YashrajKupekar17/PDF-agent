"use client";

import { FileText, RefreshCw } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ChatComposer } from "@/components/ChatComposer";
import { ChatMessage } from "@/components/ChatMessage";
import { PDFViewer } from "@/components/PDFViewer";
import { UploadCard } from "@/components/UploadCard";
import {
  API_URL,
  chatStream,
  getPdfInfo,
  pdfRawUrl,
  uploadPdf,
} from "@/lib/api";
import type { ChatMessage as Msg } from "@/lib/types";

const SUGGESTIONS = [
  "What are the submission deliverables?",
  "How is the visual story output evaluated?",
  "Is multilingual support rewarded?",
];

export default function Home() {
  const [docId, setDocId] = useState<string | null>(null);
  const [filename, setFilename] = useState<string | null>(null);
  const [nPages, setNPages] = useState<number>(0);
  const [page, setPage] = useState<number>(1);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [sessionId, setSessionId] = useState<string>(() => crypto.randomUUID());
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, busy]);

  const handleUpload = async (file: File) => {
    const res = await uploadPdf(file);
    const info = await getPdfInfo(res.doc_id);
    setDocId(res.doc_id);
    setFilename(res.filename);
    setNPages(info.n_pages);
    setPage(1);
    setMessages([]);
    setSessionId(crypto.randomUUID());
  };

  const handleSubmit = async (q: string) => {
    if (!docId) return;
    setError(null);
    const userMsg: Msg = { role: "user", content: q, ts: Date.now() };
    setMessages((m) => [...m, userMsg]);
    setBusy(true);
    setStage("Starting…");
    try {
      await chatStream(q, docId, sessionId, {
        onStage: (label) => setStage(label),
        onAnswer: (ans) => {
          const assistant: Msg = {
            role: "assistant",
            ts: Date.now(),
            content: ans.refused ? (ans.refusal_reason ?? "") : ans.answer,
            citations: ans.citations ?? [],
            refused: ans.refused,
          };
          setMessages((m) => [...m, assistant]);
          if (!ans.refused && ans.citations?.length > 0) {
            setPage(ans.citations[0].page);
          }
        },
        onError: (msg) => setError(msg),
      });
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Chat failed");
    } finally {
      setBusy(false);
      setStage(null);
    }
  };

  const newConversation = () => {
    setMessages([]);
    setSessionId(crypto.randomUUID());
  };

  if (!docId) {
    return (
      <main className="flex h-dvh flex-col bg-zinc-50 dark:bg-zinc-950">
        <Header />
        <div className="flex-1">
          <UploadCard onUpload={handleUpload} />
        </div>
      </main>
    );
  }

  return (
    <main className="flex h-dvh flex-col bg-zinc-50 dark:bg-zinc-950">
      <Header
        filename={filename}
        nPages={nPages}
        onNewConv={newConversation}
        onSwitchDoc={() => setDocId(null)}
      />
      <div className="flex flex-1 min-h-0">
        <section className="w-[42%] min-w-[320px] border-r border-zinc-200 dark:border-zinc-800">
          <PDFViewer
            url={pdfRawUrl(docId)}
            page={page}
            onPageChange={setPage}
          />
        </section>
        <section className="flex flex-1 flex-col min-w-0">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
            {messages.length === 0 && (
              <div className="flex h-full items-center justify-center">
                <div className="max-w-md text-center">
                  <h3 className="text-lg font-semibold tracking-tight">
                    Ask anything about{" "}
                    <span className="text-blue-600 dark:text-blue-400">{filename}</span>
                  </h3>
                  <p className="mt-1.5 text-sm text-zinc-500">
                    Every answer cites the exact page and a verbatim quote. Out-of-scope queries are refused.
                  </p>
                </div>
              </div>
            )}
            {messages.map((m, i) => (
              <ChatMessage key={i} message={m} onCitationClick={setPage} />
            ))}
            {busy && (
              <div className="flex justify-start">
                <div className="rounded-2xl bg-zinc-100 dark:bg-zinc-900 px-4 py-3 text-sm text-zinc-500">
                  <StageDots label={stage ?? "Working…"} />
                </div>
              </div>
            )}
            {error && (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
                {error}
              </div>
            )}
          </div>
          <div className="border-t border-zinc-200 dark:border-zinc-800 px-6 py-4 bg-white dark:bg-zinc-950">
            <ChatComposer
              onSubmit={handleSubmit}
              busy={busy}
              suggestions={messages.length === 0 ? SUGGESTIONS : undefined}
            />
            <p className="mt-2 text-[11px] text-zinc-400 dark:text-zinc-600 tabular-nums">
              {API_URL} · session {sessionId.slice(0, 8)}
            </p>
          </div>
        </section>
      </div>
    </main>
  );
}

function Header({
  filename,
  nPages,
  onNewConv,
  onSwitchDoc,
}: {
  filename?: string | null;
  nPages?: number;
  onNewConv?: () => void;
  onSwitchDoc?: () => void;
}) {
  return (
    <header className="flex items-center justify-between border-b border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-950 px-6 py-3">
      <div className="flex items-center gap-3 min-w-0">
        <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900">
          <FileText className="h-4 w-4" />
        </div>
        <div className="min-w-0">
          <h1 className="text-sm font-semibold tracking-tight">PDF Agent</h1>
          {filename ? (
            <p className="truncate text-xs text-zinc-500 dark:text-zinc-400">
              {filename} · {nPages} pages
            </p>
          ) : (
            <p className="text-xs text-zinc-500 dark:text-zinc-400">
              Strict-grounded chat over your PDF
            </p>
          )}
        </div>
      </div>
      {filename && (
        <div className="flex items-center gap-2">
          <button
            onClick={onNewConv}
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium text-zinc-600 hover:bg-zinc-100 dark:text-zinc-400 dark:hover:bg-zinc-900"
          >
            <RefreshCw className="h-3 w-3" /> New chat
          </button>
          <button
            onClick={onSwitchDoc}
            className="rounded-full bg-zinc-900 px-3 py-1.5 text-xs font-medium text-zinc-50 hover:opacity-90 dark:bg-zinc-100 dark:text-zinc-900"
          >
            Switch document
          </button>
        </div>
      )}
    </header>
  );
}

function StageDots({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs">
      <span className="inline-flex gap-1">
        <span className="h-1.5 w-1.5 rounded-full bg-zinc-400 animate-pulse" />
        <span
          className="h-1.5 w-1.5 rounded-full bg-zinc-400 animate-pulse"
          style={{ animationDelay: "120ms" }}
        />
        <span
          className="h-1.5 w-1.5 rounded-full bg-zinc-400 animate-pulse"
          style={{ animationDelay: "240ms" }}
        />
      </span>
      <span>{label}</span>
    </span>
  );
}
