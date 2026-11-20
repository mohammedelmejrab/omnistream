// Runs and steps exactly as the FastAPI backend returns them (GET /api/runs/{id} and
// GET /api/runs/{id}/steps), captured from the E2E server with the fake model runtime.
// They pin the summary keys the trace reads from the real server. Normal runs record
// route, retrieve and answer; Agentic runs add subagent, seed, score, join. Shape changes
// here mean the backend and the UI have drifted apart.
//
// Regenerate by running the E2E server and copying GET /api/runs/{id} and /steps; do not
// edit by hand.

import type { Citation, Run, Step } from '../../api/types';

// Fields the backend adds on top of the shared contract (api/types.ts is owned by the
// app shell and stays as it is). `seq` is the start order; `question` is on the run;
// `number` is the citation's 1-based position.
type BackendRun = Run & { question?: string };
type BackendStep = Omit<Step, 'citations'> & {
  seq?: number;
  citations: Array<Citation & { number?: number }>;
};

export const BACKEND_NORMAL_RUN: BackendRun = {
  "id": "2568975dac9d47bfb2481cde37b30a00",
  "chat_id": "469f4a4aed3644a39047a1b52f0b28ae",
  "mode": "normal",
  "question": "Who leads Acme?",
  "status": "ok",
  "answer": "Alice leads Acme [1].",
  "error": null,
  "started_at": "2026-11-18T02:35:44.163225+00:00",
  "finished_at": "2026-11-18T02:35:44.174085+00:00"
};

export const BACKEND_NORMAL_STEPS: BackendStep[] = [
  {
    "id": "d0dd4ac47ad744ac83d9e93d9fbf9ed5",
    "run_id": "2568975dac9d47bfb2481cde37b30a00",
    "seq": 1,
    "parent_step_id": null,
    "kind": "route",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.166809+00:00",
    "duration_ms": 0.132,
    "status": "ok",
    "summary": {
      "question_chars": 15,
      "strategy": "simple",
      "bubbles": [
        "news",
        "finance"
      ],
      "rationale": "fake route",
      "time_scope": null
    },
    "node_ids": [],
    "edge_ids": [],
    "citations": [],
    "error": null
  },
  {
    "id": "5bda8eb217f143299670d6e1836ecc33",
    "run_id": "2568975dac9d47bfb2481cde37b30a00",
    "seq": 2,
    "parent_step_id": "d0dd4ac47ad744ac83d9e93d9fbf9ed5",
    "kind": "retrieve",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.169308+00:00",
    "duration_ms": 0.133,
    "status": "ok",
    "summary": {
      "bubbles": [
        "news",
        "finance"
      ],
      "count": 1,
      "seeds": 1,
      "facts": 1,
      "chunks": 0,
      "top_facts": [
        {
          "id": "f-news",
          "score": 0.9,
          "bubble": "news"
        }
      ],
      "no_relevant_sources": false,
      "source_text": "Alice leads Acme.",
      "relevance": 1.0
    },
    "node_ids": [
      "e-alice",
      "e-acme"
    ],
    "edge_ids": [
      "f-news"
    ],
    "citations": [],
    "error": null
  },
  {
    "id": "4af7f97ff842439fa2177f61d2a65f0d",
    "run_id": "2568975dac9d47bfb2481cde37b30a00",
    "seq": 3,
    "parent_step_id": "5bda8eb217f143299670d6e1836ecc33",
    "kind": "seed",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.170683+00:00",
    "duration_ms": 0.092,
    "status": "ok",
    "summary": {
      "count": 1
    },
    "node_ids": [
      "e-alice"
    ],
    "edge_ids": [],
    "citations": [],
    "error": null
  },
  {
    "id": "82e6b1b295c1418699487c7f04cceb9a",
    "run_id": "2568975dac9d47bfb2481cde37b30a00",
    "seq": 4,
    "parent_step_id": "5bda8eb217f143299670d6e1836ecc33",
    "kind": "score",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.171448+00:00",
    "duration_ms": 0.084,
    "status": "ok",
    "summary": {
      "count": 1,
      "relevance": 1.0
    },
    "node_ids": [],
    "edge_ids": [
      "f-news"
    ],
    "citations": [],
    "error": null
  },
  {
    "id": "dfd5d5c8a6ca456e89e97e9f4d134911",
    "run_id": "2568975dac9d47bfb2481cde37b30a00",
    "seq": 5,
    "parent_step_id": "5bda8eb217f143299670d6e1836ecc33",
    "kind": "answer",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.172135+00:00",
    "duration_ms": 1.317,
    "status": "ok",
    "summary": {
      "citations": 1,
      "citation_count": 1,
      "invalid_citations": [],
      "conflicts": 0
    },
    "node_ids": [],
    "edge_ids": [],
    "citations": [
      {
        "number": 1,
        "item_id": "i1",
        "url": "https://example.test/i1",
        "title": "Item one"
      }
    ],
    "error": null
  }
];

export const BACKEND_AGENTIC_RUN: BackendRun = {
  "id": "458a8a436eea4ca1a0fb67d2246fd194",
  "chat_id": "c8dd5d64cade47279be3a4d218114b64",
  "mode": "agentic",
  "question": "Who leads Acme?",
  "status": "ok",
  "answer": "Alice leads Acme [1].",
  "error": null,
  "started_at": "2026-11-18T02:35:44.398312+00:00",
  "finished_at": "2026-11-18T02:35:44.414975+00:00"
};

export const BACKEND_AGENTIC_STEPS: BackendStep[] = [
  {
    "id": "b29c7927ee254a408aa455e442e1dac1",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 1,
    "parent_step_id": null,
    "kind": "route",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.405282+00:00",
    "duration_ms": 0.154,
    "status": "ok",
    "summary": {
      "question_chars": 15,
      "strategy": "simple",
      "bubbles": [
        "news",
        "finance"
      ],
      "rationale": "fake route",
      "time_scope": null
    },
    "node_ids": [],
    "edge_ids": [],
    "citations": [],
    "error": null
  },
  {
    "id": "4b5a3b6d86f34f858a1ea150fa164a5f",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 2,
    "parent_step_id": "b29c7927ee254a408aa455e442e1dac1",
    "kind": "subagent",
    "bubble": "news",
    "started_at": "2026-11-18T02:35:44.406735+00:00",
    "duration_ms": 5.073,
    "status": "ok",
    "summary": {
      "bubble": "news",
      "count": 1,
      "tool_calls": 1,
      "stopped_reason": "answered",
      "facts": 1,
      "chunks": 0,
      "source_text": "Alice leads Acme.",
      "relevance": 1.0
    },
    "node_ids": [
      "e-alice",
      "e-acme"
    ],
    "edge_ids": [
      "f-news"
    ],
    "citations": [],
    "error": null
  },
  {
    "id": "176025bda07e42849a3d53d272157426",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 3,
    "parent_step_id": "4b5a3b6d86f34f858a1ea150fa164a5f",
    "kind": "retrieve",
    "bubble": "news",
    "started_at": "2026-11-18T02:35:44.406809+00:00",
    "duration_ms": 0.532,
    "status": "ok",
    "summary": {
      "bubbles": [
        "news"
      ],
      "count": 1,
      "seeds": 1,
      "facts": 1,
      "chunks": 0,
      "top_facts": [
        {
          "id": "f-news",
          "score": 0.9,
          "bubble": "news"
        }
      ],
      "no_relevant_sources": false,
      "source_text": "Alice leads Acme.",
      "relevance": 1.0
    },
    "node_ids": [
      "e-alice",
      "e-acme"
    ],
    "edge_ids": [
      "f-news"
    ],
    "citations": [],
    "error": null
  },
  {
    "id": "7a478bc9c6484ccc94858541b8e6af23",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 4,
    "parent_step_id": "b29c7927ee254a408aa455e442e1dac1",
    "kind": "subagent",
    "bubble": "finance",
    "started_at": "2026-11-18T02:35:44.406906+00:00",
    "duration_ms": 5.476,
    "status": "ok",
    "summary": {
      "bubble": "finance",
      "count": 1,
      "tool_calls": 1,
      "stopped_reason": "answered",
      "facts": 1,
      "chunks": 0,
      "source_text": "Alice leads Acme.",
      "relevance": 1.0
    },
    "node_ids": [
      "e-alice",
      "e-acme"
    ],
    "edge_ids": [
      "f-finance"
    ],
    "citations": [],
    "error": null
  },
  {
    "id": "c81900cba06b4d68b04e04c6b15336c6",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 5,
    "parent_step_id": "7a478bc9c6484ccc94858541b8e6af23",
    "kind": "retrieve",
    "bubble": "finance",
    "started_at": "2026-11-18T02:35:44.406959+00:00",
    "duration_ms": 2.759,
    "status": "ok",
    "summary": {
      "bubbles": [
        "finance"
      ],
      "count": 1,
      "seeds": 1,
      "facts": 1,
      "chunks": 0,
      "top_facts": [
        {
          "id": "f-finance",
          "score": 0.9,
          "bubble": "finance"
        }
      ],
      "no_relevant_sources": false,
      "source_text": "Alice leads Acme.",
      "relevance": 1.0
    },
    "node_ids": [
      "e-alice",
      "e-acme"
    ],
    "edge_ids": [
      "f-finance"
    ],
    "citations": [],
    "error": null
  },
  {
    "id": "3ec68192cd2441f68a5894d5ced360c8",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 6,
    "parent_step_id": "176025bda07e42849a3d53d272157426",
    "kind": "seed",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.408309+00:00",
    "duration_ms": 0.066,
    "status": "ok",
    "summary": {
      "count": 1
    },
    "node_ids": [
      "e-alice"
    ],
    "edge_ids": [],
    "citations": [],
    "error": null
  },
  {
    "id": "ab4d89129dc547feb6275f0c7c630875",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 7,
    "parent_step_id": "176025bda07e42849a3d53d272157426",
    "kind": "score",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.409014+00:00",
    "duration_ms": 0.057,
    "status": "ok",
    "summary": {
      "count": 1,
      "relevance": 1.0
    },
    "node_ids": [],
    "edge_ids": [
      "f-news"
    ],
    "citations": [],
    "error": null
  },
  {
    "id": "5561197ea90445349efcf8b2b679e491",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 8,
    "parent_step_id": "c81900cba06b4d68b04e04c6b15336c6",
    "kind": "seed",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.410332+00:00",
    "duration_ms": 0.058,
    "status": "ok",
    "summary": {
      "count": 1
    },
    "node_ids": [
      "e-alice"
    ],
    "edge_ids": [],
    "citations": [],
    "error": null
  },
  {
    "id": "2ce13c5be31b411d9fe01c5f99cc3a3e",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 9,
    "parent_step_id": "c81900cba06b4d68b04e04c6b15336c6",
    "kind": "score",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.410938+00:00",
    "duration_ms": 0.053,
    "status": "ok",
    "summary": {
      "count": 1,
      "relevance": 1.0
    },
    "node_ids": [],
    "edge_ids": [
      "f-finance"
    ],
    "citations": [],
    "error": null
  },
  {
    "id": "ccd38e2b35424772a0d955f1d862bc25",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 10,
    "parent_step_id": "b29c7927ee254a408aa455e442e1dac1",
    "kind": "join",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.412384+00:00",
    "duration_ms": 0.97,
    "status": "ok",
    "summary": {
      "bubbles": [
        "finance",
        "news"
      ],
      "failed_bubbles": [],
      "joined_groups": [],
      "count": 0
    },
    "node_ids": [],
    "edge_ids": [],
    "citations": [],
    "error": null
  },
  {
    "id": "008079612fc94c95bc2e279963effec0",
    "run_id": "458a8a436eea4ca1a0fb67d2246fd194",
    "seq": 11,
    "parent_step_id": "ccd38e2b35424772a0d955f1d862bc25",
    "kind": "answer",
    "bubble": null,
    "started_at": "2026-11-18T02:35:44.413956+00:00",
    "duration_ms": 0.399,
    "status": "ok",
    "summary": {
      "citations": 1,
      "citation_count": 1,
      "invalid_citations": [],
      "conflicts": 0
    },
    "node_ids": [],
    "edge_ids": [],
    "citations": [
      {
        "number": 1,
        "item_id": "i1",
        "url": "https://example.test/i1",
        "title": "Item one"
      }
    ],
    "error": null
  }
];
