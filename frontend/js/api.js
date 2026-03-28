/**
 * VN-Agent API client.
 * Wraps all HTTP endpoints (fetch) and SSE streaming (ReadableStream).
 */
const API = {
  async generate(params) {
    const resp = await fetch('/generate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });
    if (!resp.ok) {
      const detail = await resp.text();
      throw new Error(detail);
    }
    return resp.json();
  },

  async status(jobId) {
    const resp = await fetch(`/status/${jobId}`);
    if (!resp.ok) throw new Error(`Status check failed: ${resp.status}`);
    return resp.json();
  },

  async listJobs(limit = 20) {
    const resp = await fetch(`/jobs?limit=${limit}`);
    if (!resp.ok) return [];
    return resp.json();
  },

  async deleteJob(jobId) {
    const resp = await fetch(`/jobs/${jobId}`, { method: 'DELETE' });
    return resp.json();
  },

  downloadUrl(jobId) {
    return `/download/${jobId}`;
  },

  /**
   * Stream outline via POST /generate/stream (SSE).
   * Uses fetch + ReadableStream because EventSource only supports GET.
   */
  async streamOutline(params, onToken, onDone) {
    const resp = await fetch('/generate/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    });

    if (!resp.ok) {
      onDone(await resp.text());
      return;
    }

    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      const lines = buffer.split('\n\n');
      buffer = lines.pop(); // keep incomplete chunk

      for (const line of lines) {
        const match = line.match(/^data: (.+)$/m);
        if (match) {
          const data = match[1].trim();
          if (data === '[DONE]') {
            onDone();
            return;
          }
          try {
            const { token } = JSON.parse(data);
            if (token) onToken(token);
          } catch { /* skip malformed */ }
        }
      }
    }
    onDone();
  },
};
