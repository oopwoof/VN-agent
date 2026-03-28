import { create } from 'zustand'
import type { ChatMessage, GenerateConfig, JobSummary } from './types'
import api from './api'

interface AppState {
  // Job state
  currentJobId: string | null
  status: 'idle' | 'generating' | 'completed' | 'failed'
  progress: string
  errors: string[]
  // Chat
  messages: ChatMessage[]
  // Config
  config: GenerateConfig
  // History
  jobs: JobSummary[]
  // Timer
  startTime: number | null
  elapsed: number
  // Actions
  setConfig: (partial: Partial<GenerateConfig>) => void
  generate: () => Promise<void>
  selectJob: (jobId: string) => Promise<void>
  deleteJob: (jobId: string) => Promise<void>
  refreshJobs: () => Promise<void>
}

let pollTimer: ReturnType<typeof setInterval> | null = null
let elapsedTimer: ReturnType<typeof setInterval> | null = null

function addMessage(get: () => AppState, set: (s: Partial<AppState>) => void, role: 'user' | 'system', content: string) {
  set({ messages: [...get().messages, { role, content, timestamp: Date.now() }] })
}

function stopTimers() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null }
}

const useStore = create<AppState>((set, get) => ({
  currentJobId: null,
  status: 'idle',
  progress: '',
  errors: [],
  messages: [{ role: 'system', content: 'Welcome to VN-Agent Studio! Enter a story theme to generate a visual novel.', timestamp: Date.now() }],
  config: { theme: '', max_scenes: 5, num_characters: 3, text_only: true },
  jobs: [],
  startTime: null,
  elapsed: 0,

  setConfig: (partial) => set({ config: { ...get().config, ...partial } }),

  generate: async () => {
    const { config } = get()
    if (!config.theme.trim()) return

    addMessage(get, set, 'user', config.theme)
    addMessage(get, set, 'system', 'Starting generation...')
    set({ status: 'generating', progress: 'Starting...', errors: [], startTime: Date.now(), elapsed: 0 })

    // Elapsed timer
    stopTimers()
    elapsedTimer = setInterval(() => {
      const st = get().startTime
      if (st) set({ elapsed: Math.round((Date.now() - st) / 1000) })
    }, 1000)

    try {
      const { job_id } = await api.generate(config)
      set({ currentJobId: job_id })
      addMessage(get, set, 'system', `Job ${job_id} created. Generating...`)
      get().refreshJobs()

      // Start polling
      pollTimer = setInterval(async () => {
        try {
          const res = await api.status(job_id)
          set({ progress: res.progress })

          if (res.status === 'completed') {
            stopTimers()
            set({ status: 'completed', errors: res.errors })
            addMessage(get, set, 'system', `Done! ${res.progress}`)
            get().refreshJobs()
          } else if (res.status === 'failed') {
            stopTimers()
            set({ status: 'failed', errors: res.errors })
            addMessage(get, set, 'system', `Failed: ${res.errors.join(', ')}`)
            get().refreshJobs()
          }
        } catch {
          stopTimers()
          set({ status: 'failed', errors: ['Connection lost'] })
        }
      }, 1500)
    } catch (e) {
      stopTimers()
      set({ status: 'failed', errors: [String(e)] })
      addMessage(get, set, 'system', `Error: ${e}`)
    }
  },

  selectJob: async (jobId) => {
    try {
      const res = await api.status(jobId)
      set({ currentJobId: jobId, status: res.status as AppState['status'], progress: res.progress, errors: res.errors })
    } catch { /* ignore */ }
  },

  deleteJob: async (jobId) => {
    await api.deleteJob(jobId)
    if (get().currentJobId === jobId) set({ currentJobId: null, status: 'idle' })
    get().refreshJobs()
  },

  refreshJobs: async () => {
    const jobs = await api.listJobs()
    set({ jobs })
  },
}))

export default useStore
