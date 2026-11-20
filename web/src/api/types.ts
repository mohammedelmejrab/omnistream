// API contract types. Owned by the app shell (Agent B). Trace and graph code
// imports from here. Shapes follow spec section 12 and the brief's contract.

export type RunMode = 'normal' | 'agentic';

export type RunStatus = 'running' | 'ok' | 'failed' | 'cancelled' | 'interrupted';

export interface Run {
  id: string;
  chat_id: string;
  mode: RunMode;
  status: RunStatus;
  answer: string | null;
  error: string | null;
  started_at: string;
  finished_at: string | null;
}

export type StepKind =
  | 'route'
  | 'seed'
  | 'retrieve'
  | 'score'
  | 'subagent'
  | 'join'
  | 'merge'
  | 'answer';

export type StepStatus = 'running' | 'ok' | 'error' | 'cancelled';

export interface Citation {
  item_id: string;
  url: string;
  title: string;
}

export interface Step {
  id: string;
  run_id: string;
  parent_step_id: string | null;
  kind: StepKind;
  bubble: string | null;
  started_at: string;
  duration_ms: number | null;
  status: StepStatus;
  summary: Record<string, unknown>;
  node_ids: string[];
  edge_ids: string[];
  citations: Citation[];
  error: string | null;
}

export interface Chat {
  id: string;
  title: string;
  mode: RunMode;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  chat_id: string;
  role: 'user' | 'assistant';
  content: string;
  run_id: string | null;
  mode: RunMode;
  created_at: string;
}

/** GET /api/chats/{id}: the chat and its messages. */
export interface ChatDetail {
  chat: Chat;
  messages: Message[];
}

/** POST /api/chats/{id}/messages returns the run that answers the question. */
export interface SendMessageResult {
  run_id: string;
}

export interface Bubble {
  id: string;
  name: string;
  description: string;
  half_life_days: number;
  created_at: string;
  updated_at: string;
}

export interface ApiMapping {
  items: string;
  title: string | null;
  body: string;
  date: string | null;
  url: string;
  /** Server masks every header value as "***"; only names are meaningful. */
  headers: Record<string, string>;
}

export type SourceType = 'rss' | 'api' | 'document' | 'log';

export interface Source {
  id: string;
  type: SourceType;
  url: string | null;
  credibility: number;
  poll_interval: number;
  bubble_ids: string[];
  api_mapping: ApiMapping | null;
  max_items_per_hour: number;
  store_full_text: boolean;
  enabled: boolean;
  last_polled_at: string | null;
  status: 'ok' | 'error' | 'pending';
  last_error: string | null;
}

export interface IngestResult {
  status: 'queued' | 'duplicate';
  item_hash: string;
}

export interface ProviderSettings {
  key_set: boolean;
  /** Last four characters of the saved key, or null. Never the key itself. */
  key_hint: string | null;
  key_source: 'ui' | 'env' | null;
  base_url: string;
  model: string;
}

/** PUT /api/settings/provider. `api_key` is omitted to keep the saved key. */
export interface ProviderInput {
  api_key?: string;
  base_url: string;
  model: string;
}

export interface ProviderTestResult {
  ok: boolean;
  message: string;
}

export interface GraphNode {
  id: string;
  label: string;
  bubble: string;
  kind: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
  total: number;
}
