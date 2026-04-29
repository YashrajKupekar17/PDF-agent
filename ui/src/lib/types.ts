export type Citation = {
  page: number;
  quote: string;
};

export type AgentAnswer = {
  answer: string;
  citations: Citation[];
  refused: boolean;
  refusal_reason: string | null;
};

export type UploadResponse = {
  doc_id: string;
  n_chunks: number;
  filename: string;
};

export type PdfInfo = {
  doc_id: string;
  n_pages: number;
};

export type Studio = {
  overview: string;
  suggested_questions: string[];
};

export type ChatMessage =
  | { role: "user"; content: string; ts: number }
  | {
      role: "assistant";
      ts: number;
      content: string;
      citations: Citation[];
      refused: boolean;
    };
