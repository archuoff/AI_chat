export type Health = {
  status: string
  llm: 'offline' | 'azure-openai'
  documents: number // documents this user may query
  // developer only
  llm_deployment?: string | null
  embedding?: string
  reranker?: string | null
  chunks?: number
}

export type ManagedUser = {
  id: number
  username: string
  display_name: string
  role: 'user' | 'superuser' | 'developer'
  domains: string[]
  is_active: boolean
  created_at: string | null
  last_login_at: string | null
  questions_30d: number
  tokens_30d: number
  last_active: string | null
}

export type UsageSummary = {
  days: number
  totals: { questions: number; input_tokens: number; output_tokens: number; not_found: number; active_users: number; users: number }
  per_user: {
    user_id: number
    username: string
    display_name: string
    role: string
    questions: number
    input_tokens: number
    output_tokens: number
    not_found: number
    avg_latency_ms: number
    last_active: string | null
  }[]
  daily: { date: string; questions: number; tokens: number }[]
}

export type DocumentInfo = {
  doc_id: string
  file_name: string
  file_type: string
  content_hash: string
  size_bytes: number
  records: number
  text_blocks: number
  stats: DocStats
  warnings: string[]
  chunks: number
  meta: Record<string, unknown>
  ingested_at: string
  domain?: string
  confidential?: boolean
  parse_options?: ParseOptions
  source_path?: string
  embedding_model?: string
  images?: ImageCounts | null
}

export type ImageStatus = 'waiting' | 'described' | 'skipped' | 'unsupported' | 'failed'
export type ImageCounts = Record<ImageStatus, number> & { total: number }

export type DocImage = {
  id: string
  doc_id: string
  position: number
  location: { slide?: number; page?: number; sheet?: string; row?: number; cell?: string; section?: string }
  context: string
  width: number
  height: number
  status: ImageStatus
  reason: string
  manual: boolean
  description: string
  input_tokens: number
  output_tokens: number
  described_at: string | null
}

export type VisionConfig = { enabled: boolean; deployment: string | null; detail: string; priced: boolean }
export type VisionEstimate = { images: number; input_tokens: number; output_tokens: number; cost: number | null }
export type DescribeJob = {
  state: 'idle' | 'running' | 'finished' | 'cancelled' | 'failed'
  total?: number
  done?: number
  described?: number
  decorative?: number
  failed?: number
  input_tokens?: number
  output_tokens?: number
  error?: string
}
export type DocImages = { images: DocImage[]; counts: ImageCounts; vision: VisionConfig; estimate: VisionEstimate }
export type ImagesSummary = { counts: ImageCounts; vision: VisionConfig; job: DescribeJob; estimate: VisionEstimate }

export type DocStats = {
  sheets?: Record<string, SheetReport>
  skipped_sheets?: string[]
  coverage_percent?: number
  tables?: number
  pages?: number
  slides?: number
  pictures?: number
  images?: number
  [k: string]: unknown
}

export type Domain = { id: string; name: string; description: string; documents?: number; chunks?: number }

export type DomainSuggestion = {
  domain: string
  confidence: number
  reason: string
  method: 'azure-openai' | 'keywords'
  notice?: string
}

export type ParseOptions = {
  sheets?: Record<string, { skip?: boolean }>
  tables?: Record<string, { header_rows?: number | null; skip?: boolean }>
}

export type TableInfo = {
  id: string
  range: string
  kind: 'table' | 'text'
  title: string | null
  preamble_rows: number[]
  header_rows: number[]
  data_rows: number[]
  section_rows: number[]
  columns: { col: string; name: string; filled: number }[]
  records: number
  header_rows_detected: number
  overridden: boolean
  skipped: boolean
}

export type Coverage = {
  nonempty_cells: number
  captured_cells: number
  percent: number
  missed: { cell: string; value: string }[]
  ignored: { cell: string; value: string }[]
  ignored_count: number
}

export type SheetReport = {
  skipped: boolean
  dims: string
  max_row: number
  max_col: number
  merged_ranges: number
  images: number
  tables: TableInfo[]
  records: number
  coverage: Coverage
}

export type CellStatus = 'header' | 'data' | 'title' | 'section' | 'ignored' | 'missed' | 'skipped'

export type ExcelPreview = {
  file_name: string
  sheets: { name: string }[]
  hidden_sheets: string[]
  sheet: Omit<SheetReport, 'records'> & {
    name: string
    shown_rows: number
    shown_cols: number
    truncated: boolean
    rows: { r: number; cells: { c: number; v: string; s: CellStatus; full: boolean }[] }[]
    merges: { r0: number; c0: number; r1: number; c1: number }[]
    records: Record<string, { row: number; section: string[]; fields: Record<string, unknown> }[]>
    record_count: number
  }
}

export type IngestResult = {
  file_name: string
  status: 'indexed' | 'skipped' | 'reclassified' | 'failed'
  doc_id?: string
  chunks?: number
  records?: number
  text_blocks?: number
  warnings?: string[]
  error?: string
  reason?: string
  seconds: number
}

export type Location = Record<string, string | number>

export type Source = {
  n: number
  file_name: string
  file_type: string
  doc_id: string
  location: Location
  context: string
  title: string | null
  score: number
  snippet: string
  cited: boolean
  image_id?: string | null
}

export type ChatFinal = {
  session_id: string
  answer: string
  sources: Source[]
  mode: string | null
  intent: string | null
  notices: string[]
  timings?: Record<string, number>
}

export type StreamEvent =
  | { type: 'status'; step: string; message: string }
  | { type: 'token'; text: string }
  | { type: 'reset' }
  | ({ type: 'final' } & ChatFinal)
  | { type: 'error'; message: string }

export type ChunkInfo = {
  id: string
  chunk_index: number
  kind: 'text' | 'record'
  text: string
  context: string
  title: string | null
  fields: Record<string, unknown> | null
  location: Location
}

export type UIMessage = {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  mode?: string | null
  intent?: string | null
  notices?: string[]
  steps?: { step: string; message: string }[]
  streaming?: boolean
  error?: string
  elapsedMs?: number
  images?: string[] // thumbnails of images attached to a user message
  timings?: Record<string, number>
}

export type Session = { id: string; title: string; updatedAt: number }
