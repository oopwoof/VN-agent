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
}

export default api
