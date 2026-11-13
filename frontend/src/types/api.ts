// Mirrors the Pydantic schemas in backend/app/schemas. Keep both sides in sync.

export type ProcessingStatus =
  | "uploaded"
  | "queued"
  | "extracting"
  | "chunking"
  | "embedding"
  | "indexing"
  | "completed"
  | "failed";

export const IN_PROGRESS_STATUSES: ProcessingStatus[] = ["queued", "extracting", "chunking", "embedding", "indexing"];

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  document_count: number;
  conversation_count: number;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceCreate {
  name: string;
  description?: string | null;
}

export interface DocumentRecord {
  id: string;
  workspace_id: string;
  original_filename: string;
  file_size: number;
  mime_type: string;
  detected_language: string | null;
  language_confidence: number | null;
  language_override: string | null;
  effective_language: string | null;
  language_status: string | null;
  processing_status: ProcessingStatus;
  processing_error: string | null;
  processing_progress: { done: number; total: number } | null;
  page_count: number | null;
  chunk_count: number | null;
  processing_started_at: string | null;
  processing_completed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface DocumentStatus {
  id: string;
  processing_status: ProcessingStatus;
  processing_error: string | null;
  processing_progress: { done: number; total: number } | null;
  page_count: number | null;
  chunk_count: number | null;
  detected_language: string | null;
  language_status: string | null;
  processing_started_at: string | null;
  processing_completed_at: string | null;
  extraction: {
    page_count: number;
    text_pages: number;
    ocr_pages: number[];
    empty_pages: number[];
    ocr_skipped_pages: number[];
    characters: number;
    warnings: string[];
  } | null;
}

export interface DocumentQuery {
  workspace_id?: string;
  search?: string;
  status?: ProcessingStatus;
  limit?: number;
}

export interface Chunk {
  id: string;
  document_id: string;
  chunk_index: number;
  content: string;
  page_start: number;
  page_end: number;
  language: string | null;
  section_title: string | null;
  token_count: number;
  created_at: string;
}

export interface Conversation {
  id: string;
  workspace_id: string;
  title: string;
  message_count: number;
  created_at: string;
  updated_at: string;
}

export type ResponseLanguage = "match" | "en" | "hi" | "bn" | "mr" | "pa" | "fr";

export interface Citation {
  marker: number;
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_start: number;
  page_end: number;
  section_title: string | null;
  source_language: string | null;
  quoted_text: string;
  quote_verified: boolean;
  quote_page?: number | null;
}

export interface RetrievedPassage {
  chunk_id: string;
  document_id: string;
  document_name: string;
  page_start: number;
  page_end: number;
  section_title: string | null;
  language: string | null;
  rank: number;
  dense_rank: number | null;
  dense_similarity: number | null;
  bm25_rank: number | null;
  bm25_score: number | null;
  rrf_score: number;
  rerank_score: number | null;
}

export interface RetrievalInfo {
  passages: RetrievedPassage[];
  dense_candidates: number;
  bm25_candidates: number;
  fused_candidates: number;
  reranked: boolean;
  reranker_model: string | null;
  timings_ms: Record<string, number>;
}

export interface AnswerResponse {
  answer: string;
  language: string;
  query_language: string | null;
  query_language_status: string;
  evidence_sufficient: boolean;
  answer_source: "model" | "system";
  citations: Citation[];
  retrieval: RetrievalInfo | null;
  generation: { provider: string; model: string; duration_ms: number } | null;
  warnings: string[];
  disclaimer: string;
}

export interface MessageDetails {
  answer_source?: "model" | "system";
  query_language?: string | null;
  warnings?: string[];
  generation?: { provider: string; model: string; duration_ms: number } | null;
  retrieval?: RetrievalInfo | null;
  document_ids?: string[] | null;
  response_language?: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: "user" | "assistant" | "system";
  content: string;
  language: string | null;
  citations: Citation[] | null;
  evidence_sufficient: boolean | null;
  details: MessageDetails | null;
  created_at: string;
}

export interface ConversationDetail {
  id: string;
  workspace_id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages: Message[];
}

export interface MessageExchange {
  conversation_id: string;
  user_message: Message;
  assistant_message: Message;
  answer: AnswerResponse;
}

export interface MessageCreate {
  content: string;
  document_ids?: string[] | null;
  response_language: ResponseLanguage;
}

export interface HealthResponse {
  status: "ok" | "degraded";
  version: string;
  database: { status: string; pgvector: boolean; pgvector_version?: string | null };
}

export interface ModelProviderInfo {
  provider: string;
  model: string | null;
  configured: boolean;
}

export interface SystemInfo {
  name: string;
  version: string;
  environment: string;
  supported_languages: { code: string; name: string; native_name: string; script: string }[];
  accepted_mime_types: string[];
  max_upload_size_bytes: number;
  model_provider: ModelProviderInfo;
  retrieval_engine_available: boolean;
  answering_available: boolean;
}

export interface LocalModelInfo {
  model: string;
  enabled: boolean;
  downloaded: boolean;
  loaded: boolean;
  device: string | null;
  dimension?: number | null;
}

export interface ModelsInfo {
  embedding: LocalModelInfo;
  reranker: LocalModelInfo;
  generation: ModelProviderInfo;
  ocr: {
    enabled: boolean;
    available: boolean;
    version: string | null;
    installed_languages: string[];
    missing_languages: string[];
    message: string | null;
  };
  retrieval: {
    dense_top_k: number;
    bm25_top_k: number;
    rrf_k: number;
    rerank_candidates: number;
    final_top_k: number;
    chunk_target_tokens: number;
    chunk_overlap_tokens: number;
  };
  models_allow_download: boolean;
  processing_queue: number;
}

export interface ApiErrorBody {
  error: { code: string; message: string; details?: unknown };
}

// ── FIR explainer (backend/app/schemas/fir.py) ──
export type FirClassification = "cognizable" | "non-cognizable" | "bailable" | "non-bailable" | "depends";

export interface FirAnalyzeRequest {
  document_id?: string | null;
  workspace_id?: string | null;
  text?: string | null;
  offence_date?: string | null;
}

export interface FirCharge {
  section: string;
  code: string | null;
  code_source: "explicit" | "offence_date" | "unknown" | "other_act";
  matched_text: string;
  in_reference: boolean;
  reference_section: string | null;
  title: string | null;
  kind: "offence" | "liability" | null;
  punishment: string | null;
  cognizable: FirClassification | null;
  bailable: FirClassification | null;
  court: string | null;
  note: string | null;
  corresponds_to: { code: string; section: string; title: string | null }[];
}

export interface FirAnalysis {
  source: { kind: "document" | "text"; document_id: string | null; document_name: string | null; characters: number };
  offence_date: string | null;
  offence_date_source: "provided" | "occurrence" | "earliest" | "none";
  date_candidates: { date: string; text: string; kind: "occurrence" | "report" | "other" }[];
  applicable_code: "IPC" | "BNS" | null;
  bns_commencement: string;
  charges: FirCharge[];
  reference: { validated: boolean; sources: string[]; caveats: string[] };
  warnings: string[];
  disclaimer: string;
}

export interface QueryRequest {
  workspace_id: string;
  question: string;
  document_ids?: string[] | null;
  response_language: ResponseLanguage;
}
