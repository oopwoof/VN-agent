import { create } from 'zustand'
import type { AssetManifest, ChatMessage, GenerateConfig, JobSummary } from './types'
import api, { type ChatTurn } from './api'
import { dict, type Lang, type TKey } from './i18n/dict'
import { interpolate } from './i18n/interpolate'

export type AppStep =
  | 'idle' | 'generating_setting' | 'setting_review'
  | 'generating_script' | 'script_review'
  | 'asset_management' | 'compiling' | 'completed' | 'failed'

// v4 P6: per-node state for the pipeline view. 'active' is the node the
// graph is currently executing; loop-backs (the director redo nodes) can
// re-activate a node already marked 'done', which is the correct display
// for a revision round.
export type PipelineNodeState = 'pending' | 'active' | 'done'

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
  // v4 P6: UI-chrome language. Chinese is the default (primary demo
  // audience); generated content language is driven by the theme, not this.
  lang: Lang
  pipelineNodes: Record<string, PipelineNodeState>
  pipelineActive: string | null
  pipelineLabel: string
  // Lifted out of StatusBar so StatusBar and PipelineStage share ONE 5s poll
  // instead of each owning an interval against the same endpoint.
  tokenUsage: { tokens: number; cost: number } | null
  // Storyboard → player / detail hand-off. Read as the initial index by
  // VNPreview and ScriptPanel when they mount.
  playFromScene: number
  scriptFocusIndex: number

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
  setLang: (lang: Lang) => void
  refreshTokenUsage: () => Promise<void>
  jumpToScene: (index: number) => void
  focusScene: (index: number) => void
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

/** Append a message whose text is genuinely dynamic — the creator's own
 *  input, or prose the server produced. Nothing to translate, so it is
 *  stored as-is. */
function addMsg(get: () => AppState, set: (s: Partial<AppState>) => void, role: 'user' | 'system', content: string) {
  set({ messages: [...get().messages, { role, content, timestamp: Date.now() }] })
}

/** Build a keyed message. Pure and store-free on purpose: the store's
 *  initial `messages` array is evaluated *during* `create(...)`, so anything
 *  that touched `useStore.getState()` would hit the TDZ and throw. It reads
 *  only the static `dict` import.
 *
 *  `content` is filled with the Chinese rendering as a snapshot fallback for
 *  any consumer that reads `content` directly; the live text a reader sees
 *  comes from re-resolving `tkey` in ChatPanel. */
function keyedMsg(
  role: 'user' | 'system',
  tkey: TKey,
  tvars?: Record<string, string | number>,
): ChatMessage {
  return { role, content: interpolate(dict.zh[tkey] ?? tkey, tvars), tkey, tvars, timestamp: Date.now() }
}

/** Append a message that is static UI copy (optionally with `{name}` slots),
 *  so it re-renders in whatever language is active at paint time. */
function addKeyedMsg(
  get: () => AppState,
  set: (s: Partial<AppState>) => void,
  role: 'user' | 'system',
  tkey: TKey,
  tvars?: Record<string, string | number>,
) {
  set({ messages: [...get().messages, keyedMsg(role, tkey, tvars)] })
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
  messages: [keyedMsg('system', 'chat.msg.welcome')],
  config: { theme: '', max_scenes: 5, num_characters: 3, text_only: true, fast_mode: false, mock: false, autopilot: false },
  jobs: [],
  assets: null,
  vnPreview: false,
  startTime: null,
  elapsed: 0,
  streamActive: false,
  pendingChatTurn: null,
  chatBusy: false,
  lang: 'zh',
  pipelineNodes: {},
  pipelineActive: null,
  pipelineLabel: '',
  tokenUsage: null,
  playFromScene: 0,
  scriptFocusIndex: 0,

  setConfig: (partial) => set({ config: { ...get().config, ...partial } }),

  generate: async () => {
    const { config } = get()
    if (!config.theme.trim()) return

    stopSceneStream()
    addMsg(get, set, 'user', config.theme)
    set({
      step: 'generating_setting', progress: 'Creating project...', errors: [], blackboard: {},
      assets: null, vnPreview: false, streamActive: false,
      pipelineNodes: {}, pipelineActive: null, pipelineLabel: '', tokenUsage: null,
    })
    startElapsed(set, get)

    try {
      const { job_id } = await api.generate(config)
      set({ currentJobId: job_id })
      addKeyedMsg(get, set, 'system', 'chat.msg.projectCreated', { id: job_id })
      get().refreshJobs()

      addKeyedMsg(get, set, 'system', 'chat.msg.directorPlanning')
      set({ progress: 'Director planning story structure' })
      const { blackboard } = await api.generateSetting(job_id)
      stopTimers()

      const ws = blackboard.world_setting as Record<string, string> | undefined

      if (get().config.fast_mode) {
        // Fast mode: skip setting review, auto-confirm
        set({ blackboard, progress: 'Fast mode: auto-confirming setting...' })
        addKeyedMsg(get, set, 'system', 'chat.msg.fastModeStory', { title: ws?.title || 'Untitled' })
        get().refreshJobs()
        await get().confirmSetting()
        return
      }

      set({ step: 'setting_review', blackboard, progress: 'Setting ready for review' })
      addKeyedMsg(get, set, 'system', 'chat.msg.outlineReady', { title: ws?.title || 'Untitled' })
      get().refreshJobs()
    } catch (e) {
      stopTimers()
      set({ step: 'failed', errors: [String(e)] })
      addKeyedMsg(get, set, 'system', 'chat.msg.error', { error: String(e) })
    }
  },

  confirmSetting: async () => {
    const { currentJobId } = get()
    if (!currentJobId) return

    // `director` never reports over the node stream: publish_node is wired
    // only into _run_script_generation, which enters the graph with the
    // outline already built ("skip director since we already have plan",
    // web/app.py). Reaching this call means director HAS run, so seed it as
    // done rather than leaving the pipeline's first node stuck on 'pending'.
    set({
      step: 'generating_script',
      progress: 'Writer creating dialogue...',
      pipelineNodes: { ...get().pipelineNodes, director: 'done' },
    })
    startElapsed(set, get)
    addKeyedMsg(get, set, 'system', 'chat.msg.settingConfirmed')

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
            addKeyedMsg(get, set, 'system', 'chat.msg.sceneReadyLive', { title: String(scene.title || scene.id) })
          } else {
            addKeyedMsg(get, set, 'system', 'chat.msg.sceneReadyWatch', { title: String(scene.title || scene.id) })
          }
        }
      },
      onNode: (node, label) => {
        const next: Record<string, PipelineNodeState> = { ...get().pipelineNodes }
        // The graph only ever runs one node at a time, so whatever was
        // active has finished by the time the next node reports in.
        for (const key of Object.keys(next)) {
          if (next[key] === 'active') next[key] = 'done'
        }
        next[node] = 'active'
        set({ pipelineNodes: next, pipelineActive: node, pipelineLabel: label })
      },
      onDone: () => {
        const next: Record<string, PipelineNodeState> = { ...get().pipelineNodes }
        for (const key of Object.keys(next)) {
          if (next[key] === 'active') next[key] = 'done'
        }
        set({ streamActive: false, pipelineNodes: next, pipelineActive: null })
      },
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
              addKeyedMsg(get, set, 'system', 'chat.msg.scriptDoneFast')
              get().refreshJobs()
              await get().confirmScript()
              return
            }

            set({ step: 'script_review', blackboard, errors: res.errors })
            // res.progress is server prose ("done - 5 scenes"); it rides
            // through as a variable so the surrounding sentence still flips.
            addKeyedMsg(get, set, 'system', 'chat.msg.scriptReady', { progress: res.progress })
            get().refreshJobs()
          } else if (res.status === 'failed') {
            stopTimers()
            stopSceneStream()
            set({ streamActive: false, step: 'failed', errors: res.errors })
            addKeyedMsg(get, set, 'system', 'chat.msg.failed', { errors: res.errors.join(', ') })
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
    addKeyedMsg(get, set, 'system', 'chat.msg.regenerating')

    try {
      const { blackboard } = await api.generateSetting(currentJobId)
      stopTimers()
      set({ step: 'setting_review', blackboard, progress: 'Setting ready for review' })
      addKeyedMsg(get, set, 'system', 'chat.msg.settingRegenerated')
    } catch (e) {
      stopTimers()
      set({ step: 'failed', errors: [String(e)] })
    }
  },

  confirmScript: async () => {
    const { currentJobId } = get()
    if (!currentJobId) return

    set({ step: 'compiling', progress: 'Compiling Ren\'Py project...' })
    addKeyedMsg(get, set, 'system', 'chat.msg.scriptConfirmed')

    try {
      await api.compile(currentJobId)
      await get().fetchAssets()
      set({ step: 'asset_management', progress: 'Assets ready for review' })
      addKeyedMsg(get, set, 'system', 'chat.msg.compiled')
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
      addKeyedMsg(get, set, 'system', 'chat.msg.recompiled')
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
    // tokenUsage is cleared here now that it lives in the store: StatusBar used
    // to null its own local copy when the job went away, and without this the
    // deleted job's cost readout would stay on screen.
    if (get().currentJobId === jobId) set({ currentJobId: null, step: 'idle', blackboard: {}, assets: null, streamActive: false, tokenUsage: null })
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
        // explain / unknown — already resolved, nothing to confirm. Pure
        // server prose, so it stays on `content` and does not retranslate.
        addMsg(get, set, 'system', turn.result_text || turn.preview_text)
      }
    } catch (e) {
      addKeyedMsg(get, set, 'system', 'chat.msg.chatError', { error: String(e) })
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
      // Server prose wins verbatim; only the bare success/failure fallback is
      // ours to translate.
      if (resolved.result_text) {
        addMsg(get, set, 'system', resolved.result_text)
      } else {
        addKeyedMsg(get, set, 'system', resolved.success ? 'chat.msg.done' : 'chat.msg.actionFailed')
      }
      if (resolved.success) {
        // local_regen mutated vn_script.json on disk directly — refetch the
        // blackboard the backend already re-synced from it (see chat_execute
        // in web/app.py) so VNPreview/ScriptPanel reflect the new dialogue.
        const { blackboard } = await api.getBlackboard(currentJobId)
        set({ blackboard })
      }
    } catch (e) {
      addKeyedMsg(get, set, 'system', 'chat.msg.chatError', { error: String(e) })
    } finally {
      set({ pendingChatTurn: null, chatBusy: false })
    }
  },

  cancelChatTurn: () => {
    addKeyedMsg(get, set, 'system', 'chat.msg.cancelled')
    set({ pendingChatTurn: null })
  },

  setLang: (lang) => set({ lang }),

  refreshTokenUsage: async () => {
    const { currentJobId } = get()
    if (!currentJobId) { set({ tokenUsage: null }); return }
    try {
      const resp = await fetch(`/api/projects/${currentJobId}/token-usage`)
      if (!resp.ok) return
      const data = await resp.json()
      if (data.calls > 0) {
        set({ tokenUsage: { tokens: data.total_input + data.total_output, cost: data.estimated_cost_usd } })
      }
    } catch { /* transient — keep the last known value */ }
  },

  jumpToScene: (index) => set({ playFromScene: index, vnPreview: true }),
  focusScene: (index) => set({ scriptFocusIndex: index }),
}))

export default useStore
