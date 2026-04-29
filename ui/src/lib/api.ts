import type { AgentAnswer, PdfInfo, Studio, UploadResponse } from "./types";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function uploadPdf(file: File): Promise<UploadResponse> {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch(`${API_URL}/upload`, { method: "POST", body: fd });
  if (!r.ok) throw new Error(`Upload failed: ${r.status} ${await r.text()}`);
  return r.json();
}

export async function getPdfInfo(docId: string): Promise<PdfInfo> {
  const r = await fetch(`${API_URL}/pdf/${docId}/info`);
  if (!r.ok) throw new Error(`Info failed: ${r.status}`);
  return r.json();
}

export async function getStudio(docId: string): Promise<Studio> {
  const r = await fetch(`${API_URL}/studio/${docId}`);
  if (!r.ok) throw new Error(`Studio failed: ${r.status}`);
  return r.json();
}

export function pdfRawUrl(docId: string): string {
  return `${API_URL}/pdf/${docId}/raw`;
}

export async function chat(
  query: string,
  docId: string,
  sessionId: string
): Promise<AgentAnswer> {
  const r = await fetch(`${API_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, doc_id: docId, session_id: sessionId }),
  });
  if (!r.ok) throw new Error(`Chat failed: ${r.status} ${await r.text()}`);
  const data = await r.json();
  return data.answer as AgentAnswer;
}

type StreamCallbacks = {
  onStage?: (label: string) => void;
  onPartialAnswer?: (partial: string) => void;
  onAnswer?: (answer: AgentAnswer) => void;
  onError?: (message: string) => void;
};

export async function chatStream(
  query: string,
  docId: string,
  sessionId: string,
  cb: StreamCallbacks
): Promise<void> {
  const { parse: parsePartial } = await import("partial-json");
  const r = await fetch(`${API_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, doc_id: docId, session_id: sessionId }),
  });
  if (!r.ok || !r.body) {
    throw new Error(`Stream failed: ${r.status} ${await r.text().catch(() => "")}`);
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let accumulatedArgs = "";
  let lastPartialAnswer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    for (const block of events) {
      const line = block.split("\n").find((l) => l.startsWith("data: "));
      if (!line) continue;
      const raw = line.slice(6).trim();
      if (raw === "[DONE]") return;
      try {
        const ev = JSON.parse(raw);
        if (ev.type === "stage") {
          cb.onStage?.(ev.label);
        } else if (ev.type === "args_delta") {
          accumulatedArgs += ev.delta as string;
          try {
            const parsed = parsePartial(accumulatedArgs) as
              | { answer?: string }
              | undefined;
            const a = parsed?.answer;
            if (typeof a === "string" && a !== lastPartialAnswer) {
              lastPartialAnswer = a;
              cb.onPartialAnswer?.(a);
            }
          } catch {
            // partial JSON not yet valid — wait for more deltas
          }
        } else if (ev.type === "answer") {
          cb.onAnswer?.(ev.answer);
        } else if (ev.type === "error") {
          cb.onError?.(ev.message);
        }
      } catch {
        // ignore malformed line
      }
    }
  }
}
