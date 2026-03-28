import { create } from 'zustand'
import type { ChatMessage, GenerateConfig, JobSummary } from './types'
import api from './api'

export type AppStep = 'idle' | 'generating_setting' | 'setting_review' | 'generating_script' | 'completed' | 'failed'

interface AppState {
  currentJobId: string | null
  step: AppStep
  progress: string
  errors: string[]
  blackboard: Record<string, unknown>
  messages: ChatMessage[]
  config: GenerateConfig
  jobs: JobSummary[]
  startTime: number | null
  elapsed: number

  setConfig: (partial: Partial<GenerateConfig>) => void
  generate: () => Promise<void>
  confirmSetting: () => Promise<void>
  regenerateSetting: () => Promise<void>
  selectJob: (jobId: string) => Promise<void>
  deleteJob: (jobId: string) => Promise<void>
  refreshJobs: () => Promise<void>
}

let pollTimer: ReturnType<typeof setInterval> | null = null
let elapsedTimer: ReturnType<typeof setInterval> | null = null

function addMsg(get: () => AppState, set: (s: Partial<AppState>) => void, role: 'user' | 'system', content: string) {
  set({ messages: [...get().messages, { role, content, timestamp: Date.now() }] })
}

function stopTimers() {
  if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null }
}

function startElapsed(set: (s: Partial<AppState>) => void, get: () => AppState) {
  stopTimers()
  set({ startTime: Date.now(), elapsed: 0 })
  elapsedTimer = setInterval(() => {
    const st = get().startTime
    if (st) set({ elapsed: Math.round((Date.now() - st) / 1000) })
  }, 1000)
}

const useStore = create<AppState>((set, get) => ({
  currentJobId: null,
  step: 'idle',
  progress: '',
  errors: [],
  blackboard: {},
  messages: [{ role: 'system', content: 'Welcome to VN-Agent Studio! Enter a story theme to generate a visual novel.', timestamp: Date.now() }],
  config: { theme: '', max_scenes: 5, num_characters: 3, text_only: true },
  jobs: [],
  startTime: null,
  elapsed: 0,

  setConfig: (partial) => set({ config: { ...get().config, ...partial } }),

  generate: async () => {
    const { config } = get()
    if (!config.theme.trim()) return

    addMsg(get, set, 'user', config.theme)
    set({ step: 'generating_setting', progress: 'Creating project...', errors: [], blackboard: {} })
    startElapsed(set, get)

    try {
      // Step 1: Create project
      const { job_id } = await api.generate(config)
      set({ currentJobId: job_id })
      addMsg(get, set, 'system', `Project ${job_id} created.`)
      get().refreshJobs()

      // Step 2: Generate setting (Director)
      addMsg(get, set, 'system', 'Director is planning the story...')
      set({ progress: 'Director planning story structure' })
      const { blackboard } = await api.generateSetting(job_id)
      stopTimers()

      set({ step: 'setting_review', blackboard, progress: 'Setting ready for review' })
      const ws = blackboard.world_setting as Record<string, string> | undefined
      addMsg(get, set, 'system',
        `Story outline ready: "${ws?.title || 'Untitled'}". ` +
        `Review the setting on the right, then click Confirm to continue.`
      )
      get().refreshJobs()
    } catch (e) {
      stopTimers()
      set({ step: 'failed', errors: [String(e)] })
      addMsg(get, set, 'system', `Error: ${e}`)
    }
  },

  confirmSetting: async () => {
    const { currentJobId } = get()
    if (!currentJobId) return

    set({ step: 'generating_script', progress: 'Writer creating dialogue...' })
    startElapsed(set, get)
    addMsg(get, set, 'system', 'Setting confirmed. Writer is creating dialogue...')

    try {
      await api.generateScript(currentJobId)

      // Poll for completion
      pollTimer = setInterval(async () => {
        try {
          const res = await api.status(currentJobId)
          set({ progress: res.progress })

          if (res.status === 'completed') {
            stopTimers()
            set({ step: 'completed', errors: res.errors })
            addMsg(get, set, 'system', `Done! ${res.progress}`)
            get().refreshJobs()
          } else if (res.status === 'failed') {
            stopTimers()
            set({ step: 'failed', errors: res.errors })
            addMsg(get, set, 'system', `Failed: ${res.errors.join(', ')}`)
            get().refreshJobs()
          }
        } catch {
          stopTimers()
          set({ step: 'failed', errors: ['Connection lost'] })
        }
      }, 1500)
    } catch (e) {
      stopTimers()
      set({ step: 'failed', errors: [String(e)] })
      addMsg(get, set, 'system', `Error: ${e}`)
    }
  },

  regenerateSetting: async () => {
    const { currentJobId } = get()
    if (!currentJobId) return

    set({ step: 'generating_setting', progress: 'Regenerating setting...' })
    startElapsed(set, get)
    addMsg(get, set, 'system', 'Regenerating setting...')

    try {
      const { blackboard } = await api.generateSetting(currentJobId)
      stopTimers()
      set({ step: 'setting_review', blackboard, progress: 'Setting ready for review' })
      addMsg(get, set, 'system', 'New setting generated. Review and confirm.')
    } catch (e) {
      stopTimers()
      set({ step: 'failed', errors: [String(e)] })
    }
  },

  selectJob: async (jobId) => {
    try {
      const res = await api.status(jobId)
      const { blackboard } = await api.getBlackboard(jobId)
      let step: AppStep = 'idle'
      if (res.status === 'completed') step = 'completed'
      else if (res.status === 'failed') step = 'failed'
      else if (res.status === 'setting_generated') step = 'setting_review'
      else if (res.status === 'running') step = 'generating_script'

      set({ currentJobId: jobId, step, progress: res.progress, errors: res.errors, blackboard })
    } catch { /* ignore */ }
  },

  deleteJob: async (jobId) => {
    await api.deleteJob(jobId)
    if (get().currentJobId === jobId) set({ currentJobId: null, step: 'idle', blackboard: {} })
    get().refreshJobs()
  },

  refreshJobs: async () => {
    const jobs = await api.listJobs()
    set({ jobs })
  },
}))

export default useStore
