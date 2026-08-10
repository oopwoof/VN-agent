import type { AssetManifest, GenerateConfig, JobSummary, PlaytestReport, StatusResponse } from './types'

// v4 P3: one chat-ops turn's lifecycle state. A preview (requires_confirmation
// true, executed false) becomes a resolved turn (executed true) after
// /chat/execute — or resolves immediately for non-mutating intents (explain/
// unknown), which /chat/preview alone already returns as resolved.
export interface ChatTurn {
  turn_id: string
  message: string
  intent: 'local_regen' | 'add_character' | 'edit_asset' | 'explain' | 'unknown'
  confidence: number
  target_scene_id: string | null
  target_character_id: string | null
  instruction: string
  reasoning: string
  preview_text: string
  requires_confirmation: boolean
  executed: boolean
  success: boolean | null
  result_text: string
  diff: string | null
  wall_seconds: number | null
  error: string | null
}

// v4 P1-1: aggregated feedback counters for the data-flywheel widget.
export interface FeedbackSummary {
  total: number
  by_verdict: { up: number; down: number }
  by_scene: Record<string, number>
  by_job: Record<string, number>
  top_tags: Record<string, number>
}

// v4 P0-7: text-upload response from POST /assets/upload.
// Image/audio uploads return only status/size; text returns chunk stats.
export interface UploadResult {
  status: string
  asset_type: string
  asset_id: string
  size: number
  // Present only for asset_type=text:
  chunks?: number
  cjk_dominant?: boolean
  jsonl_path?: string
  summary?: {
    chunks: number
    by_source: Record<string, number>
    by_license: Record<string, number>
    files: string[]
  }
}

const api = {
  async generate(config: GenerateConfig): Promise<{ job_id: string }> {
    const resp = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      // v4 P5 bugfix: interactive=true tells the backend to skip its
      // internal _run_job background task, which otherwise re-runs the
      // whole pipeline a second time (writing a zip, invisible to SSE)
      // concurrently with the generate-setting/generate-script chain below
      // — a real double-execution + status-write race, not just wasted
      // API spend. The SPA always drives that chain, so it always opts in.
      body: JSON.stringify({ ...config, interactive: true }),
    })
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  async status(jobId: string): Promise<StatusResponse> {
    const resp = await fetch(`/status/${jobId}`)
    if (!resp.ok) throw new Error(`Status check failed: ${resp.status}`)
    return resp.json()
  },

  async listJobs(limit = 20): Promise<JobSummary[]> {
    const resp = await fetch(`/jobs?limit=${limit}`)
    if (!resp.ok) return []
    return resp.json()
  },

  async deleteJob(jobId: string): Promise<void> {
    await fetch(`/jobs/${jobId}`, { method: 'DELETE' })
  },

  downloadUrl(jobId: string): string {
    return `/download/${jobId}`
  },

  // ── Step APIs ─────────────────────────────────────────────────────────────

  async generateSetting(jobId: string): Promise<{ blackboard: Record<string, unknown> }> {
    const resp = await fetch(`/api/projects/${jobId}/generate-setting`, { method: 'POST' })
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  async getBlackboard(jobId: string): Promise<{ blackboard: Record<string, unknown> }> {
    const resp = await fetch(`/api/projects/${jobId}/blackboard`)
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  async updateSetting(jobId: string, update: Record<string, unknown>): Promise<{ blackboard: Record<string, unknown> }> {
    const resp = await fetch(`/api/projects/${jobId}/setting`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  async generateScript(jobId: string): Promise<void> {
    const resp = await fetch(`/api/projects/${jobId}/generate-script`, { method: 'POST' })
    if (!resp.ok) throw new Error(await resp.text())
  },

  async updateScene(jobId: string, sceneId: string, update: Record<string, unknown>): Promise<void> {
    const resp = await fetch(`/api/projects/${jobId}/script/${sceneId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(update),
    })
    if (!resp.ok) throw new Error(await resp.text())
  },

  async exportScript(jobId: string): Promise<Record<string, unknown>> {
    const resp = await fetch(`/api/projects/${jobId}/export-script`)
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  // ── Asset APIs (Sprint 4) ────────────────────────────────────────────────

  async listAssets(jobId: string): Promise<AssetManifest> {
    const resp = await fetch(`/api/projects/${jobId}/assets`)
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  async uploadAsset(jobId: string, file: File, assetType: string, assetId: string, license?: string): Promise<UploadResult> {
    const form = new FormData()
    form.append('file', file)
    form.append('asset_type', assetType)
    form.append('asset_id', assetId)
    if (license) form.append('license', license)
    const resp = await fetch(`/api/projects/${jobId}/assets/upload`, { method: 'POST', body: form })
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  assetFileUrl(jobId: string, path: string): string {
    return `/api/projects/${jobId}/assets/file/${path}`
  },

  async compile(jobId: string): Promise<void> {
    const resp = await fetch(`/api/projects/${jobId}/compile`, { method: 'POST' })
    if (!resp.ok) throw new Error(await resp.text())
  },

  // v4 P2 ⑤: subscribe to scene_ready SSE events as Writer finishes each
  // scene, so playback can start before the whole script is done. Connect
  // BEFORE calling generateScript — events fired before a subscriber
  // connects aren't buffered/replayed (see backend stream_scenes docstring).
  // Caller owns the returned EventSource and should not need to close it
  // manually — it self-closes on 'done'/'failed'.
  streamScenes(jobId: string, handlers: {
    onScene: (scene: Record<string, unknown>) => void
    // v4 P6: graph-node transitions, published alongside scene_ready on the
    // same stream. Optional so existing callers are unaffected.
    onNode?: (node: string, label: string) => void
    onDone?: () => void
    onError?: (error?: string) => void
  }): EventSource {
    const es = new EventSource(`/api/projects/${jobId}/stream/scenes`)
    es.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data)
        if (data.event === 'scene_ready') {
          handlers.onScene(data.scene)
        } else if (data.event === 'node') {
          handlers.onNode?.(data.node, data.label)
        } else if (data.event === 'done') {
          handlers.onDone?.()
          es.close()
        } else if (data.event === 'failed') {
          handlers.onError?.(data.error)
          es.close()
        }
      } catch (e) {
        console.error('stream_scenes: failed to parse event', e)
      }
    }
    es.onerror = () => {
      // One-shot per-job stream — don't let the browser auto-retry into a
      // finished/gone job.
      es.close()
    }
    return es
  },

  // v4 P3: classify a chat-ops message. Non-mutating intents (explain/
  // unknown) come back already resolved; mutating intents (local_regen/
  // add_character/edit_asset) come back as a preview needing chatExecute.
  async chatPreview(jobId: string, message: string): Promise<ChatTurn> {
    const resp = await fetch(`/api/projects/${jobId}/chat/preview`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    })
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  // v4 P3: confirm and run a previewed mutating turn. Pass the exact turn
  // object chatPreview returned — the server re-validates nothing about it
  // client-side is trusted beyond what preview_turn already classified.
  async chatExecute(jobId: string, turn: ChatTurn): Promise<ChatTurn> {
    const resp = await fetch(`/api/projects/${jobId}/chat/execute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(turn),
    })
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  // v4 P4: run PlaytestAgent (branch walk + composited frames + vision
  // judge) against the job's current on-disk script. Can take 10-60s
  // (sequential per-frame LLM calls) — caller should show a spinner.
  async runPlaytest(jobId: string, maxFrames?: number): Promise<PlaytestReport> {
    const resp = await fetch(`/api/projects/${jobId}/playtest/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ max_frames: maxFrames ?? null }),
    })
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  // v4 P4: fetch the most recent playtest report, if one exists (404 before
  // the first run for this job).
  async getPlaytestReport(jobId: string): Promise<PlaytestReport> {
    const resp = await fetch(`/api/projects/${jobId}/playtest/report`)
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  // v4 P1-1: creator 👍/👎 into the flywheel JSONL. Reason optional but
  // strongly encouraged — reason-less records don't hit the BM25 injector.
  async postFeedback(record: {
    verdict: 'up' | 'down'
    job_id?: string
    scene_id?: string
    reason?: string
    tags?: string[]
    context?: Record<string, unknown>
  }): Promise<{ status: string; id: string; summary: FeedbackSummary }> {
    const resp = await fetch('/api/feedback', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(record),
    })
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  async feedbackSummary(): Promise<FeedbackSummary> {
    const resp = await fetch('/api/feedback/summary')
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },

  // v4 P0-upload-delete: remove a single uploaded doc's chunks from the
  // job's RAG pool, or (filename omitted) clear every upload for the job.
  async deleteUpload(jobId: string, filename?: string): Promise<UploadResult['summary'] & { removed: number; status: string }> {
    const qs = filename ? `?filename=${encodeURIComponent(filename)}` : ''
    const resp = await fetch(`/api/projects/${jobId}/assets/upload${qs}`, { method: 'DELETE' })
    if (!resp.ok) throw new Error(await resp.text())
    const data = await resp.json()
    return { ...data.summary, removed: data.removed, status: data.status }
  },

  // v4 P0-resume: rescue a stuck/crashed job by merging snapshot dialogue
  // into vn_script.json and (for text_only runs) recompiling.
  async resumeProject(jobId: string, opts?: { force?: boolean; dryRun?: boolean }): Promise<{
    salvage: {
      action: 'noop' | 'already_complete' | 'merged_snapshots' | 'failed'
      scenes_before: number
      scenes_after: number
      dialogue_before: number
      dialogue_after: number
      snapshots_found: number
      snapshots_merged: number
      warnings: string[]
    }
    compiled?: boolean
    compile_error?: string
    next_step?: string
  }> {
    const params = new URLSearchParams()
    if (opts?.force) params.set('force', 'true')
    if (opts?.dryRun) params.set('dry_run', 'true')
    const url = `/api/projects/${jobId}/resume${params.toString() ? '?' + params.toString() : ''}`
    const resp = await fetch(url, { method: 'POST' })
    if (!resp.ok) throw new Error(await resp.text())
    return resp.json()
  },
}

export default api
