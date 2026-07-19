import type { AssetManifest, GenerateConfig, JobSummary, StatusResponse } from './types'

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
      body: JSON.stringify(config),
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
}

export default api
