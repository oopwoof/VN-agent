import type { GenerateConfig, JobSummary, StatusResponse } from './types'

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
}

export default api
