/**
 * VN-Agent Studio — main application logic.
 * Handles form submission, polling, streaming, and job management.
 */
const App = {
  currentJobId: null,
  pollInterval: null,
  stepHistory: [],

  /** Get form parameters */
  getParams() {
    return {
      theme: document.getElementById('theme-input').value.trim(),
      max_scenes: parseInt(document.getElementById('max-scenes').value),
      num_characters: parseInt(document.getElementById('num-characters').value),
      text_only: document.getElementById('text-only').checked,
    };
  },

  /** Start generation */
  async generate() {
    const params = this.getParams();
    if (!params.theme) {
      UI.showError('Please enter a story theme.');
      return;
    }

    UI.resetOutput();
    UI.setDisabled('generate-btn', true);
    UI.setDisabled('preview-btn', true);
    this.stepHistory = [];

    try {
      const { job_id } = await API.generate(params);
      this.currentJobId = job_id;
      this.startPolling(job_id);
      this.refreshJobList();
    } catch (e) {
      UI.showError(e.message);
      UI.setDisabled('generate-btn', false);
      UI.setDisabled('preview-btn', false);
    }
  },

  /** Poll job status every 1.5s */
  startPolling(jobId) {
    if (this.pollInterval) clearInterval(this.pollInterval);

    UI.showProgress('Starting pipeline...', []);

    this.pollInterval = setInterval(async () => {
      try {
        const { status, progress, errors } = await API.status(jobId);

        // Track step history (avoid duplicates)
        if (progress && !this.stepHistory.includes(progress)) {
          this.stepHistory.push(progress);
        }

        if (status === 'completed') {
          this.stopPolling();
          UI.showResult(jobId, progress);
          this.refreshJobList();
        } else if (status === 'failed') {
          this.stopPolling();
          UI.showError(errors);
          this.refreshJobList();
        } else {
          UI.showProgress(progress, this.stepHistory);
        }
      } catch (e) {
        this.stopPolling();
        UI.showError(`Polling error: ${e.message}`);
      }
    }, 1500);
  },

  stopPolling() {
    if (this.pollInterval) {
      clearInterval(this.pollInterval);
      this.pollInterval = null;
    }
    UI.setDisabled('generate-btn', false);
    UI.setDisabled('preview-btn', false);
  },

  /** Stream outline preview via SSE */
  async previewOutline() {
    const params = this.getParams();
    if (!params.theme) {
      UI.showError('Please enter a story theme.');
      return;
    }

    UI.resetOutput();
    UI.show('preview-section');
    UI.setDisabled('generate-btn', true);
    UI.setDisabled('preview-btn', true);

    const previewEl = document.getElementById('preview-output');
    previewEl.textContent = '';
    previewEl.classList.add('streaming');

    try {
      await API.streamOutline(
        params,
        (token) => UI.appendStreamToken(token),
        (err) => {
          previewEl.classList.remove('streaming');
          UI.setDisabled('generate-btn', false);
          UI.setDisabled('preview-btn', false);
          if (err) UI.showError(err);
        },
      );
    } catch (e) {
      previewEl.classList.remove('streaming');
      UI.showError(e.message);
      UI.setDisabled('generate-btn', false);
      UI.setDisabled('preview-btn', false);
    }
  },

  /** Select a job from history */
  async selectJob(jobId) {
    try {
      const { status, progress, errors } = await API.status(jobId);
      UI.resetOutput();
      this.currentJobId = jobId;

      if (status === 'completed') {
        UI.showResult(jobId, progress);
      } else if (status === 'failed') {
        UI.showError(errors);
      } else if (status === 'running') {
        this.startPolling(jobId);
      }

      // Highlight active item
      document.querySelectorAll('.job-item').forEach(el => el.classList.remove('active'));
      const active = document.querySelector(`[data-job-id="${jobId}"]`);
      if (active) active.classList.add('active');
    } catch (e) {
      UI.showError(e.message);
    }
  },

  /** Delete a job */
  async deleteJob(jobId) {
    try {
      await API.deleteJob(jobId);
      this.refreshJobList();
      if (this.currentJobId === jobId) {
        UI.resetOutput();
        this.currentJobId = null;
      }
    } catch (e) {
      UI.showError(e.message);
    }
  },

  /** Refresh job history sidebar */
  async refreshJobList() {
    const jobs = await API.listJobs();
    UI.renderJobList(jobs);
  },
};

// ── Event Wiring ──────────────────────────────────────────────────────────────

document.getElementById('generate-btn').addEventListener('click', () => App.generate());
document.getElementById('preview-btn').addEventListener('click', () => App.previewOutline());
document.getElementById('close-preview').addEventListener('click', () => UI.hide('preview-section'));

// Slider value display
document.getElementById('max-scenes').addEventListener('input', (e) => {
  UI.setText('max-scenes-val', e.target.value);
});
document.getElementById('num-characters').addEventListener('input', (e) => {
  UI.setText('num-chars-val', e.target.value);
});

// Enter key to generate
document.getElementById('theme-input').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    App.generate();
  }
});

// Load job history on page load
App.refreshJobList();
