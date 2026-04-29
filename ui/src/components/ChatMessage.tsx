"use client";

import { AlertCircle, BookOpen, ChevronDown, ChevronUp } from "lucide-react";
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChatMessage as Msg } from "@/lib/types";
import { cn } from "@/lib/utils";

type Props = {
  message: Msg;
  onCitationClick: (page: number) => void;
  streaming?: boolean;
};

export function ChatMessage({ message, onCitationClick, streaming = false }: Props) {
  const isUser = message.role === "user";
  const isRefused = !isUser && message.refused;
  const [showSources, setShowSources] = useState(false);

  return (
    <div className={cn("flex w-full", isUser ? "justify-end" : "justify-start")}>
      <div
        className={cn(
          "max-w-[88%] rounded-2xl px-4 py-3 text-sm leading-relaxed shadow-sm",
          isUser
            ? "bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900"
            : isRefused
              ? "bg-amber-50 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-900 text-amber-900 dark:text-amber-200"
              : "bg-zinc-100 dark:bg-zinc-900 text-zinc-900 dark:text-zinc-100"
        )}
      >
        {isRefused && (
          <div className="flex items-center gap-1.5 text-xs font-medium mb-1.5 text-amber-700 dark:text-amber-300">
            <AlertCircle className="h-3.5 w-3.5" />
            Out of scope
          </div>
        )}
        {isUser ? (
          <div className="whitespace-pre-wrap">{message.content}</div>
        ) : (
          <div className="prose-msg">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
            {streaming && (
              <span
                className="inline-block w-1.5 h-4 bg-zinc-500 align-middle animate-pulse ml-0.5"
                aria-hidden
              />
            )}
          </div>
        )}

        {!isUser && !isRefused && message.citations.length > 0 && (
          <div className="mt-3 space-y-2">
            <div className="flex flex-wrap items-center gap-1.5">
              {[...new Set(message.citations.map((c) => c.page))]
                .sort((a, b) => a - b)
                .map((p) => (
                  <button
                    key={p}
                    onClick={() => onCitationClick(p)}
                    className={cn(
                      "inline-flex items-center gap-1 rounded-full border px-2.5 py-0.5 text-xs font-medium",
                      "border-blue-200 bg-blue-50 text-blue-700 hover:bg-blue-100",
                      "dark:border-blue-900 dark:bg-blue-950/40 dark:text-blue-300 dark:hover:bg-blue-950/70",
                      "transition-colors"
                    )}
                  >
                    <BookOpen className="h-3 w-3" />
                    p.{p}
                  </button>
                ))}
              <button
                onClick={() => setShowSources((s) => !s)}
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium",
                  "text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100",
                  "hover:bg-zinc-200/60 dark:hover:bg-zinc-800",
                  "transition-colors"
                )}
                aria-expanded={showSources}
              >
                {showSources ? (
                  <>
                    <ChevronUp className="h-3 w-3" />
                    Hide sources
                  </>
                ) : (
                  <>
                    <ChevronDown className="h-3 w-3" />
                    Show {message.citations.length} source
                    {message.citations.length === 1 ? "" : "s"}
                  </>
                )}
              </button>
            </div>
            {showSources && (
              <div className="space-y-1.5 pt-1">
                {message.citations.map((c, i) => (
                  <blockquote
                    key={i}
                    className="border-l-2 border-blue-200 dark:border-blue-900 pl-3 text-xs italic text-zinc-600 dark:text-zinc-400"
                  >
                    <button
                      onClick={() => onCitationClick(c.page)}
                      className="not-italic font-medium text-blue-700 dark:text-blue-400 hover:underline"
                    >
                      [p.{c.page}]
                    </button>{" "}
                    {c.quote}
                  </blockquote>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
