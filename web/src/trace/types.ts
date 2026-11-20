// Trace types. The contract lives in web/src/api/types.ts (owned by the app shell);
// this file re-exports the parts trace and graph use, under the names used here.
//
// Summary keys the trace UI reads (all optional; the UI degrades to plain counts):
//   route     { bubbles?: string[] }                 bubbles the question was routed to
//   seed      { count?: number }
//   retrieve  { count?: number }                     items found in one bubble (or in total)
//   score     { relevance?: number }                 0..1, relevance of the evidence
//   subagent  { count?: number, relevance?: number } one bubble's result (Agentic)
//   join      { count?: number }                     joined entities / chunks
//   merge     {}
//   answer    { citation_count?: number }
//   any       { source_text?: string }               text the step read, shown in the detail panel

export type {
  Citation,
  GraphEdge as GraphEdgeDto,
  GraphNode as GraphNodeDto,
  GraphResponse,
  Run,
  RunMode as Mode,
  RunStatus,
  Step,
  StepKind,
  StepStatus,
} from '../api/types';
