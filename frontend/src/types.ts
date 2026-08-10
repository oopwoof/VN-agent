export interface GenerateConfig {
  theme: string
  max_scenes: number
  num_characters: number
  text_only: boolean
  fast_mode: boolean
  // v4 P0-7: per-request mock. When true, backend routes every LLM call
  // through `services/mock_llm.py` fixtures — zero API cost, useful for
  // dev + validating upload/library flow without burning tokens.
  mock: boolean
  // v4 P5: Autopilot entry point. When true, the backend resolves a preset
  // (M0: always "autopilot_best") and applies it via a per-job Settings
  // override; the store also auto-enters the VN player on the first scene
  // instead of waiting for a manual "Watch Live" click.
  autopilot: boolean
}

export interface ChatMessage {
  role: 'user' | 'system'
  /** Pre-rendered text. Always populated. It is the ONLY source for messages
   *  that embed server-supplied prose (reviewer output, chat-ops results),
   *  and the fallback whenever `tkey` cannot be resolved. */
  content: string
  // v4 P6 i18n: keyed messages. Storing an already-translated string would
  // freeze the chat log in whatever language was active when it was written,
  // so static messages carry their dictionary key plus its `{name}` variables
  // instead and ChatPanel resolves them at paint time — flipping the language
  // retranslates the entire history, not just the next message.
  tkey?: string
  tvars?: Record<string, string | number>
  timestamp: number
}

export interface JobSummary {
  job_id: string
  theme: string
  status: string
  progress: string
  created_at: string
}

export interface StatusResponse {
  status: string
  progress: string
  errors: string[]
}

export interface AssetEntry {
  id?: string
  char_id?: string
  emotion?: string
  mood?: string
  path: string
  is_placeholder: boolean
  url: string
}

export interface AssetManifest {
  backgrounds: AssetEntry[]
  characters: AssetEntry[]
  bgm: AssetEntry[]
}

// v4 P4: PlaytestAgent — mirrors src/vn_agent/playtest/schema.py field-for-field.
export interface PlaytestFrameFinding {
  category: 'ui_coherence' | 'dead_end' | 'pacing' | 'player_agency' | 'advisory'
  message: string
  severity: 'info' | 'warning' | 'critical'
}

export interface PlaytestFrameJudgment {
  ui_coherence_score: number
  dead_end_risk: 'none' | 'low' | 'high'
  interactivity_pacing_score: number
  player_agency_score: number
  findings: PlaytestFrameFinding[]
  summary: string
}

export interface PlaytestFrameEntry {
  node_id: string
  scene_id: string
  kind: 'scene' | 'choice_menu'
  frame_path: string
  judgment: PlaytestFrameJudgment | null
  judge_error: string | null
}

export interface PlaytestReport {
  generated_at: string
  script_title: string
  total_scenes: number
  visited_scenes: number
  unreachable_scene_ids: string[]
  total_declared_branches: number
  reachable_branches: number
  coverage_score: number
  branch_reachability_score: number
  dimension_scores: Record<string, number>
  frames: PlaytestFrameEntry[]
  judge_model: string
  frames_judged: number
  frames_skipped: number
}
