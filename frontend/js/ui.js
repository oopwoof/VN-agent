/**
 * DOM manipulation helpers for VN-Agent Studio.
 */
const UI = {
  show(id) { document.getElementById(id).classList.remove('hidden'); },
  hide(id) { document.getElementById(id).classList.add('hidden'); },
  setText(id, text) { document.getElementById(id).textContent = text; },

  setDisabled(id, disabled) {
    const el = document.getElementById(id);
    el.disabled = disabled;
    if (disabled) el.classList.add('opacity-50');
    else el.classList.remove('opacity-50');
  },

  /** Render job history sidebar */
  renderJobList(jobs) {
    const container = document.getElementById('job-list');
    if (!jobs.length) {
      container.innerHTML = '<p class="text-xs text-gray-600 px-2">No jobs yet</p>';
      return;
    }
    container.innerHTML = jobs.map(j => `
      <div class="job-item" data-job-id="${j.job_id}" onclick="App.selectJob('${j.job_id}')">
        <div class="flex items-center justify-between">
          <span class="text-xs font-mono text-gray-500">${j.job_id}</span>
          <span class="badge badge-${j.status}">${j.status}</span>
        </div>
        <p class="text-xs text-gray-400 mt-1 truncate">${this._escapeHtml(j.theme)}</p>
        <div class="flex items-center justify-between mt-1">
          <span class="text-[10px] text-gray-600">${this._formatTime(j.created_at)}</span>
          <button onclick="event.stopPropagation(); App.deleteJob('${j.job_id}')"
            class="text-[10px] text-gray-600 hover:text-red-400">delete</button>
        </div>
      </div>
    `).join('');
  },

  /** Show progress panel with step tracking */
  showProgress(progress, stepHistory) {
    UI.show('progress-section');
    UI.hide('result-section');
    UI.hide('error-section');
    UI.setText('progress-text', progress);

    // Update progress bar based on step
    const stepOrder = ['starting pipeline', 'Director', 'Writer', 'Reviewer', 'assets', 'building project'];
    let pct = 10;
    for (let i = 0; i < stepOrder.length; i++) {
      if (progress.toLowerCase().includes(stepOrder[i].toLowerCase())) {
        pct = Math.min(10 + (i + 1) * 15, 90);
      }
    }
    document.getElementById('progress-bar').style.width = `${pct}%`;

    // Render step history
    const stepsEl = document.getElementById('progress-steps');
    stepsEl.innerHTML = (stepHistory || []).map((s, i, arr) => {
      const cls = i === arr.length - 1 ? 'step-item active' : 'step-item done';
      const icon = i === arr.length - 1 ? '>' : '\u2713';
      return `<div class="${cls}">${icon} ${this._escapeHtml(s)}</div>`;
    }).join('');
  },

  /** Show completion result */
  showResult(jobId, progress) {
    UI.hide('progress-section');
    UI.show('result-section');
    UI.hide('error-section');
    document.getElementById('progress-bar').style.width = '100%';
    UI.setText('result-text', progress || 'Generation complete!');
    document.getElementById('download-btn').onclick = () => {
      window.location.href = API.downloadUrl(jobId);
    };
  },

  /** Show error */
  showError(errors) {
    UI.hide('progress-section');
    UI.show('error-section');
    UI.hide('result-section');
    const msg = Array.isArray(errors) ? errors.join('\n') : String(errors);
    UI.setText('error-text', msg);
  },

  /** Reset all output panels */
  resetOutput() {
    UI.hide('progress-section');
    UI.hide('result-section');
    UI.hide('error-section');
    UI.hide('preview-section');
    document.getElementById('progress-bar').style.width = '0%';
    document.getElementById('progress-steps').innerHTML = '';
  },

  /** Append streaming token to preview */
  appendStreamToken(token) {
    const el = document.getElementById('preview-output');
    el.textContent += token;
    el.scrollTop = el.scrollHeight;
  },

  _escapeHtml(str) {
    const div = document.createElement('div');
    div.textContent = str;
    return div.innerHTML;
  },

  _formatTime(iso) {
    if (!iso) return '';
    try {
      const d = new Date(iso);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    } catch { return iso; }
  },
};
