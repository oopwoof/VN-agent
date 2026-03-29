export interface GenerateConfig {
  theme: string
  max_scenes: number
  num_characters: number
  text_only: boolean
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
