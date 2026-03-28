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
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress: string
  errors: string[]
}
