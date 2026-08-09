import { create } from 'zustand'
import type { AssetManifest, ChatMessage, GenerateConfig, JobSummary } from './types'
import api, { type ChatTurn } from './api'

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
  // v4 P2 ⑤: true while the scene_ready SSE stream is subscribed during
  // script generation — drives the "Watch Live" affordance.
  streamActive: boolean
  // v4 P3: chat-ops turn awaiting creator confirm (local_regen/add_character/
  // edit_asset). null once resolved or cancelled. explain/unknown never sit
  // here — they resolve straight into a chat message.
  pendingChatTurn: ChatTurn | null
  chatBusy: boolean

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
  // v4 P3: Chat Ops — send a message; non-mutating intents resolve inline,
  // mutating ones populate pendingChatTurn for confirmChatTurn/cancelChatTurn.
  sendChatMessage: (message: string) => Promise<void>
  confirmChatTurn: () => Promise<void>
  cancelChatTurn: () => void
  // Gate for ChatPanel: is there a generated script to chat-edit right now?
  chatOpsAvailable: () => boolean
}

let pollTimer: ReturnType<typeof setInterval> | null = null
let elapsedTimer: ReturnType<typeof setInterval> | null = null
let sceneStream: EventSource | null = null
// Guards against overlapping setInterval ticks: if api.status() takes longer
// than the poll period, multiple ticks can be in flight at once and each
// independently see status === 'completed', each firing the completion
// side effects (including api.compile() in fast_mode) more than once.
let pollInFlight = false

function stopSceneStream() {
  if (sceneStream) { sceneStream.close(); sceneStream = null }
}

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
  config: { theme: '', max_scenes: 5, num_characters: 3, text_only: true, fast_mode: false, mock: false, autopilot: false },
  jobs: [],
  assets: null,
  vnPreview: false,
  startTime: null,
  elapsed: 0,
  streamActive: false,
  pendingChatTurn: null,
  chatBusy: false,

  setConfig: (partial) => set({ config: { ...get().config, ...partial } }),

  generate: async () => {
    const { config } = get()
    if (!config.theme.trim()) return

    stopSceneStream()
    addMsg(get, set, 'user', config.theme)
    set({ step: 'generating_setting', progress: 'Creating project...', errors: [], blackboard: {}, assets: null, vnPreview: false, streamActive: false })
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

    // v4 P2 ⑤: open the scene stream BEFORE kicking off generation so the
    // subscriber is registered before Writer can finish scene 1 — events
    // published with no subscriber connected are dropped (no buffering in
    // M0). Scenes stream straight into blackboard.scene_scripts so VNPreview
    // can play them as they arrive; the final getBlackboard() fetch below
    // still overwrites with the authoritative full script.
    stopSceneStream()
    set({ streamActive: true })
    let firstSceneSeen = false
    sceneStream = api.streamScenes(currentJobId, {
      onScene: (scene) => {
        const bb = get().blackboard
        const existing = (bb.scene_scripts as Array<Record<string, unknown>>) || []
        const idx = existing.findIndex(s => s.id === scene.id)
        const updated = idx >= 0
          ? existing.map((s, i) => (i === idx ? scene : s))
          : [...existing, scene]
        set({ blackboard: { ...bb, scene_scripts: updated } })
        if (!firstSceneSeen) {
          firstSceneSeen = true
          if (get().config.autopilot) {
            // v4 P5 Autopilot: auto-enter the player instead of waiting for
            // a manual "Watch Live" click. Gated strictly on config.autopilot
            // (not fast_mode) so existing fast-mode users see no behavior
            // change. PreviewPanel's vnPreview guard takes priority over
            // `step`, so this stays showing through the rest of script
            // generation and the subsequent auto-compile.
            set({ vnPreview: true })
            addMsg(get, set, 'system', `Scene "${scene.title || scene.id}" ready — playing live.`)
          } else {
            addMsg(get, set, 'system', `Scene "${scene.title || scene.id}" ready — you can Watch Live while the rest generates.`)
          }
        }
      },
      onDone: () => set({ streamActive: false }),
      onError: () => set({ streamActive: false }),
    })

    try {
      await api.generateScript(currentJobId)
      pollTimer = setInterval(async () => {
        if (pollInFlight) return
        pollInFlight = true
        try {
          const res = await api.status(currentJobId)
          set({ progress: res.progress })

          if (res.status === 'completed') {
            stopTimers()
            stopSceneStream()
            set({ streamActive: false })
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
            stopSceneStream()
            set({ streamActive: false, step: 'failed', errors: res.errors })
            addMsg(get, set, 'system', `Failed: ${res.errors.join(', ')}`)
            get().refreshJobs()
          }
        } catch {
          stopTimers()
          stopSceneStream()
          set({ streamActive: false, step: 'failed', errors: ['Connection lost'] })
        } finally {
          pollInFlight = false
        }
      }, 1500)
    } catch (e) {
      stopTimers()
      stopSceneStream()
      set({ streamActive: false, step: 'failed', errors: [String(e)] })
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
    stopTimers()
    stopSceneStream()
    try {
      const res = await api.status(jobId)
      const { blackboard } = await api.getBlackboard(jobId)
      const statusMap: Record<string, AppStep> = {
        completed: 'completed', failed: 'failed',
        setting_generated: 'setting_review', running: 'generating_script',
      }
      const step: AppStep = statusMap[res.status] || 'idle'

      set({ currentJobId: jobId, step, progress: res.progress, errors: res.errors, blackboard, vnPreview: false, streamActive: false })
      if (step === 'completed' as AppStep) get().fetchAssets()
    } catch { /* ignore */ }
  },

  deleteJob: async (jobId) => {
    if (get().currentJobId === jobId) { stopTimers(); stopSceneStream() }
    await api.deleteJob(jobId)
    if (get().currentJobId === jobId) set({ currentJobId: null, step: 'idle', blackboard: {}, assets: null, streamActive: false })
    get().refreshJobs()
  },

  refreshJobs: async () => {
    const jobs = await api.listJobs()
    set({ jobs })
  },

  chatOpsAvailable: () => {
    const { currentJobId, blackboard, step } = get()
    const scenes = blackboard.scene_scripts as unknown[] | undefined
    return !!currentJobId && Array.isArray(scenes) && scenes.length > 0
      && step !== 'generating_setting' && step !== 'idle'
  },

  sendChatMessage: async (message) => {
    const { currentJobId, chatBusy } = get()
    if (!currentJobId || chatBusy || !message.trim()) return

    addMsg(get, set, 'user', message)
    set({ chatBusy: true })
    try {
      const turn = await api.chatPreview(currentJobId, message.trim())
      if (turn.requires_confirmation) {
        set({ pendingChatTurn: turn })
      } else {
        // explain / unknown — already resolved, nothing to confirm.
        addMsg(get, set, 'system', turn.result_text || turn.preview_text)
      }
    } catch (e) {
      addMsg(get, set, 'system', `Chat error: ${e}`)
    } finally {
      set({ chatBusy: false })
    }
  },

  confirmChatTurn: async () => {
    const { currentJobId, pendingChatTurn, chatBusy } = get()
    if (!currentJobId || !pendingChatTurn || chatBusy) return

    set({ chatBusy: true })
    try {
      const resolved = await api.chatExecute(currentJobId, pendingChatTurn)
      addMsg(get, set, 'system', resolved.result_text || (resolved.success ? 'Done.' : 'Failed.'))
      if (resolved.success) {
        // local_regen mutated vn_script.json on disk directly — refetch the
        // blackboard the backend already re-synced from it (see chat_execute
        // in web/app.py) so VNPreview/ScriptPanel reflect the new dialogue.
        const { blackboard } = await api.getBlackboard(currentJobId)
        set({ blackboard })
      }
    } catch (e) {
      addMsg(get, set, 'system', `Chat error: ${e}`)
    } finally {
      set({ pendingChatTurn: null, chatBusy: false })
    }
  },

  cancelChatTurn: () => {
    addMsg(get, set, 'system', 'Cancelled.')
    set({ pendingChatTurn: null })
  },
}))

export default useStore
