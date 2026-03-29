import { create } from 'zustand'
import type { AssetManifest, ChatMessage, GenerateConfig, JobSummary } from './types'
import api from './api'

export type AppStep =
  | 'idle' | 'generating_setting' | 'setting_review'
  | 'generating_script' | 'script_review'
  | 'asset_management' | 'compiling' | 'completed' | 'failed'

interface AppState {
  currentJobId: string | null
  step: AppStep
  progress: string
  errors: string[]
  blackboard: Record<string, unknown>
  messages: ChatMessage[]
  config: GenerateConfig
  jobs: JobSummary[]
  assets: AssetManifest | null
  vnPreview: boolean
  startTime: number | null
  elapsed: number

  setConfig: (partial: Partial<GenerateConfig>) => void
  generate: () => Promise<void>
  confirmSetting: () => Promise<void>
  regenerateSetting: () => Promise<void>
  confirmScript: () => Promise<void>
  fetchAssets: () => Promise<void>
  uploadAsset: (file: File, assetType: string, assetId: string) => Promise<void>
  recompile: () => Promise<void>
  toggleVNPreview: () => void
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
  config: { theme: '', max_scenes: 5, num_characters: 3, text_only: true, fast_mode: false },
  jobs: [],
  assets: null,
  vnPreview: false,
  startTime: null,
  elapsed: 0,

  setConfig: (partial) => set({ config: { ...get().config, ...partial } }),

  generate: async () => {
    const { config } = get()
    if (!config.theme.trim()) return

    addMsg(get, set, 'user', config.theme)
    set({ step: 'generating_setting', progress: 'Creating project...', errors: [], blackboard: {}, assets: null, vnPreview: false })
    startElapsed(set, get)

    try {
      const { job_id } = await api.generate(config)
      set({ currentJobId: job_id })
      addMsg(get, set, 'system', `Project ${job_id} created.`)
      get().refreshJobs()

      addMsg(get, set, 'system', 'Director is planning the story...')
      set({ progress: 'Director planning story structure' })
      const { blackboard } = await api.generateSetting(job_id)
      stopTimers()

      const ws = blackboard.world_setting as Record<string, string> | undefined

      if (get().config.fast_mode) {
        // Fast mode: skip setting review, auto-confirm
        set({ blackboard, progress: 'Fast mode: auto-confirming setting...' })
        addMsg(get, set, 'system', `Story: "${ws?.title || 'Untitled'}". Fast mode — auto-generating script...`)
        get().refreshJobs()
        await get().confirmSetting()
        return
      }

      set({ step: 'setting_review', blackboard, progress: 'Setting ready for review' })
      addMsg(get, set, 'system', `Story outline ready: "${ws?.title || 'Untitled'}". Review and confirm.`)
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
      pollTimer = setInterval(async () => {
        try {
          const res = await api.status(currentJobId)
          set({ progress: res.progress })

          if (res.status === 'completed') {
            stopTimers()
            const { blackboard } = await api.getBlackboard(currentJobId)

            if (get().config.fast_mode) {
              // Fast mode: skip script review, auto-compile
              set({ blackboard, errors: res.errors })
              addMsg(get, set, 'system', `Script done. Fast mode — compiling...`)
              get().refreshJobs()
              await get().confirmScript()
              return
            }

            set({ step: 'script_review', blackboard, errors: res.errors })
            addMsg(get, set, 'system', `Script ready! ${res.progress}. Review and confirm.`)
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

  confirmScript: async () => {
    const { currentJobId } = get()
    if (!currentJobId) return

    set({ step: 'compiling', progress: 'Compiling Ren\'Py project...' })
    addMsg(get, set, 'system', 'Script confirmed. Compiling project...')

    try {
      await api.compile(currentJobId)
      await get().fetchAssets()
      set({ step: 'asset_management', progress: 'Assets ready for review' })
      addMsg(get, set, 'system', 'Project compiled! Review assets, upload replacements, or download.')
      get().refreshJobs()
    } catch (e) {
      set({ step: 'failed', errors: [String(e)] })
    }
  },

  fetchAssets: async () => {
    const { currentJobId } = get()
    if (!currentJobId) return
    try {
      const assets = await api.listAssets(currentJobId)
      set({ assets })
    } catch { /* ignore */ }
  },

  uploadAsset: async (file, assetType, assetId) => {
    const { currentJobId } = get()
    if (!currentJobId) return
    await api.uploadAsset(currentJobId, file, assetType, assetId)
    await get().fetchAssets()
  },

  recompile: async () => {
    const { currentJobId } = get()
    if (!currentJobId) return
    set({ step: 'compiling', progress: 'Re-compiling with updated assets...' })
    try {
      await api.compile(currentJobId)
      await get().fetchAssets()
      set({ step: 'completed', progress: 'Project ready for download' })
      addMsg(get, set, 'system', 'Re-compiled! Download your project.')
      get().refreshJobs()
    } catch (e) {
      set({ step: 'failed', errors: [String(e)] })
    }
  },

  toggleVNPreview: () => set({ vnPreview: !get().vnPreview }),

  selectJob: async (jobId) => {
    try {
      const res = await api.status(jobId)
      const { blackboard } = await api.getBlackboard(jobId)
      const statusMap: Record<string, AppStep> = {
        completed: 'completed', failed: 'failed',
        setting_generated: 'setting_review', running: 'generating_script',
      }
      const step: AppStep = statusMap[res.status] || 'idle'

      set({ currentJobId: jobId, step, progress: res.progress, errors: res.errors, blackboard, vnPreview: false })
      if (step === 'completed' as AppStep) get().fetchAssets()
    } catch { /* ignore */ }
  },

  deleteJob: async (jobId) => {
    await api.deleteJob(jobId)
    if (get().currentJobId === jobId) set({ currentJobId: null, step: 'idle', blackboard: {}, assets: null })
    get().refreshJobs()
  },

  refreshJobs: async () => {
    const jobs = await api.listJobs()
    set({ jobs })
  },
}))

export default useStore
