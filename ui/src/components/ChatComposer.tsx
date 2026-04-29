"use client";

import { ArrowUp, Loader2 } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

type Props = {
  onSubmit: (q: string) => void;
  disabled?: boolean;
  busy?: boolean;
  suggestions?: string[];
};

export function ChatComposer({ onSubmit, disabled, busy, suggestions }: Props) {
  const [value, setValue] = useState("");
  const ref = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.style.height = "auto";
      ref.current.style.height = `${Math.min(160, ref.current.scrollHeight)}px`;
    }
  }, [value]);

  const submit = (q: string) => {
    if (!q.trim() || busy) return;
    onSubmit(q.trim());
    setValue("");
  };

  return (
    <div className="space-y-2">
      {suggestions && suggestions.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {suggestions.map((s) => (
            <button
              key={s}
              onClick={() => submit(s)}
              disabled={disabled || busy}
              className={cn(
                "rounded-full border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900",
                "px-3 py-1 text-xs text-zinc-600 dark:text-zinc-400",
                "hover:bg-zinc-100 dark:hover:bg-zinc-800 hover:text-zinc-900 dark:hover:text-zinc-100",
                "transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              )}
            >
              {s}
            </button>
          ))}
        </div>
      )}
      <form
        className="relative flex items-end rounded-2xl border border-zinc-200 dark:border-zinc-800 bg-white dark:bg-zinc-900 shadow-sm focus-within:ring-2 focus-within:ring-blue-500/20"
        onSubmit={(e: FormEvent) => {
          e.preventDefault();
          submit(value);
        }}
      >
        <textarea
          ref={ref}
          value={value}
          rows={1}
          disabled={disabled}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              submit(value);
            }
          }}
          placeholder="Ask about the PDF…"
          className="flex-1 resize-none bg-transparent px-4 py-3 text-sm placeholder:text-zinc-400 focus:outline-none disabled:opacity-50"
        />
        <button
          type="submit"
          disabled={disabled || busy || !value.trim()}
          className={cn(
            "m-1.5 inline-flex h-9 w-9 items-center justify-center rounded-full",
            "bg-zinc-900 text-zinc-50 dark:bg-zinc-100 dark:text-zinc-900",
            "hover:opacity-90 disabled:opacity-30 disabled:cursor-not-allowed transition-opacity"
          )}
          aria-label="Send"
        >
          {busy ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <ArrowUp className="h-4 w-4" />
          )}
        </button>
      </form>
    </div>
  );
}
