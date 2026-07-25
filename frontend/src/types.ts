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
}

export interface ChatMessage {
  role: 'user' | 'system'
  content: string
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
