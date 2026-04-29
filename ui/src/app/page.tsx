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
  getStudio,
  pdfRawUrl,
  uploadPdf,
} from "@/lib/api";
import {
  clearSession,
  loadSession,
  saveSession,
} from "@/lib/storage";
import type { ChatMessage as Msg, Studio } from "@/lib/types";

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
  const [highlights, setHighlights] = useState<string[]>([]);
  const [studio, setStudio] = useState<Studio | null>(null);
  const [studioLoading, setStudioLoading] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // Hydrate from localStorage on mount.
  useEffect(() => {
    const s = loadSession();
    if (s && s.docId) {
      setDocId(s.docId);
      setFilename(s.filename);
      setNPages(s.nPages);
      setMessages(s.messages || []);
      setSessionId(s.sessionId || crypto.randomUUID());
      setStudio(s.studio ?? null);
      setPage(s.page || 1);
    }
    setHydrated(true);
  }, []);

  // Persist on relevant state changes (after hydration so we don't blow over fresh load).
  useEffect(() => {
    if (!hydrated) return;
    if (!docId || !filename) {
      clearSession();
      return;
    }
    saveSession({
      docId,
      filename,
      nPages,
      messages,
      sessionId,
      studio,
      page,
      updatedAt: Date.now(),
    });
  }, [hydrated, docId, filename, nPages, messages, sessionId, studio, page]);

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
    setStudio(null);
    setSessionId(crypto.randomUUID());
    setStudioLoading(true);
    getStudio(res.doc_id)
      .then((s) => setStudio(s))
      .catch(() => {})
      .finally(() => setStudioLoading(false));
  };

  const handleSubmit = async (q: string) => {
    if (!docId) return;
    setError(null);
    const userMsg: Msg = { role: "user", content: q, ts: Date.now() };
    // push the user msg + a placeholder streaming assistant msg
    const placeholder: Msg = {
      role: "assistant",
      ts: Date.now(),
      content: "",
      citations: [],
      refused: false,
    };
    setMessages((m) => [...m, userMsg, placeholder]);
    setBusy(true);
    setStage("Starting…");
    try {
      await chatStream(q, docId, sessionId, {
        onStage: (label) => setStage(label),
        onPartialAnswer: (partial) => {
          // update last assistant msg's content as tokens stream in
          setMessages((m) => {
            const out = m.slice();
            const last = out[out.length - 1];
            if (last && last.role === "assistant") {
              out[out.length - 1] = { ...last, content: partial };
            }
            return out;
          });
        },
        onAnswer: (ans) => {
          // settle final verified answer, replace the streaming placeholder
          setMessages((m) => {
            const out = m.slice();
            const last = out[out.length - 1];
            if (last && last.role === "assistant") {
              out[out.length - 1] = {
                role: "assistant",
                ts: last.ts,
                content: ans.refused ? (ans.refusal_reason ?? "") : ans.answer,
                citations: ans.citations ?? [],
                refused: ans.refused,
              };
            }
            return out;
          });
          if (!ans.refused && ans.citations?.length > 0) {
            setPage(ans.citations[0].page);
            setHighlights(ans.citations.map((c) => c.quote));
          } else {
            setHighlights([]);
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
    setHighlights([]);
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
            highlights={highlights}
          />
        </section>
        <section className="flex flex-1 flex-col min-w-0">
          <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-6 space-y-4">
            {messages.length === 0 && (
              <div className="flex h-full items-start justify-center pt-6">
                <div className="max-w-xl w-full space-y-5">
                  <div>
                    <h3 className="text-lg font-semibold tracking-tight">
                      About{" "}
                      <span className="text-blue-600 dark:text-blue-400">
                        {filename}
                      </span>
                    </h3>
                    {studioLoading ? (
                      <div className="mt-3 space-y-2 animate-pulse">
                        <div className="h-3 bg-zinc-200 dark:bg-zinc-800 rounded w-full" />
                        <div className="h-3 bg-zinc-200 dark:bg-zinc-800 rounded w-5/6" />
                      </div>
                    ) : studio ? (
                      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed">
                        {studio.overview}
                      </p>
                    ) : (
                      <p className="mt-2 text-sm text-zinc-500">
                        Every answer cites the exact page and a verbatim quote.
                        Out-of-scope queries are refused.
                      </p>
                    )}
                  </div>
                  {studio && studio.suggested_questions.length > 0 && (
                    <div>
                      <p className="text-xs font-medium uppercase tracking-wide text-zinc-500 dark:text-zinc-400 mb-2">
                        Try asking
                      </p>
                      <div className="flex flex-col gap-1.5">
                        {studio.suggested_questions.map((q, i) => (
                          <button
                            key={i}
                            onClick={() => handleSubmit(q)}
                            disabled={busy}
                            className="text-left text-sm rounded-xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 px-3 py-2 hover:bg-zinc-50 dark:hover:bg-zinc-800 transition-colors disabled:opacity-50"
                          >
                            {q}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}
            {messages.map((m, i) => {
              const isStreaming =
                busy &&
                i === messages.length - 1 &&
                m.role === "assistant" &&
                m.content.length > 0;
              const isWaiting =
                busy &&
                i === messages.length - 1 &&
                m.role === "assistant" &&
                m.content.length === 0;
              if (isWaiting) {
                return (
                  <div key={i} className="flex justify-start">
                    <div className="rounded-2xl bg-zinc-100 dark:bg-zinc-900 px-4 py-3 text-sm text-zinc-500">
                      <StageDots label={stage ?? "Working…"} />
                    </div>
                  </div>
                );
              }
              return (
                <ChatMessage
                  key={i}
                  message={m}
                  onCitationClick={setPage}
                  streaming={isStreaming}
                />
              );
            })}
            {error && (
              <div className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-400">
                {error}
              </div>
            )}
          </div>
          <div className="border-t border-zinc-200 dark:border-zinc-800 px-6 py-4 bg-white dark:bg-zinc-950">
            <ChatComposer onSubmit={handleSubmit} busy={busy} />
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
