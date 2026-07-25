import { useEffect, useState } from 'react'
import api from '../api'
import type { PlaytestFrameEntry, PlaytestReport } from '../types'

// v4 P4: opt-in post-generation "health check" — walks the script's branch
// graph, composites a representative frame per scene/choice-menu node
// (Pillow, not a real Ren'Py engine run — see backend
// playtest/frame_compositor.py docstring for why), judges each with a
// vision LLM, and shows the aggregated report. M0 is report-only: nothing
// here feeds back into generation.

const DIMENSION_LABELS: Record<string, string> = {
  ui_coherence: 'UI Coherence',
  interactivity_pacing: 'Pacing',
  player_agency: 'Player Agency',
  dead_end_risk_pct: 'Dead-End Risk',
  coverage: 'Coverage',
  branch_reachability: 'Branch Reachability',
}

const SEVERITY_COLOR: Record<string, string> = {
  info: 'bg-gray-800 text-gray-300',
  warning: 'bg-amber-950/50 text-amber-300',
  critical: 'bg-red-950/50 text-red-300',
}

function StatTile({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-2">
      <div className="text-[10px] text-gray-500 uppercase tracking-wider">{label}</div>
      <div className="text-lg text-indigo-300 font-medium">{value}</div>
    </div>
  )
}

function FrameCard({ jobId, frame }: { jobId: string; frame: PlaytestFrameEntry }) {
  const j = frame.judgment
  return (
    <div className="bg-gray-900 border border-gray-800 rounded-lg overflow-hidden">
      <div className="aspect-video bg-gray-950">
        <img src={api.assetFileUrl(jobId, frame.frame_path)} alt={frame.node_id}
          className="w-full h-full object-cover" />
      </div>
      <div className="p-3 space-y-2">
        <div className="flex items-center justify-between">
          <span className="text-xs text-gray-300 truncate" title={frame.node_id}>{frame.node_id}</span>
          <span className="text-[9px] text-gray-600 uppercase">{frame.kind}</span>
        </div>
        {j ? (
          <>
            <div className="flex flex-wrap gap-1.5 text-[10px]">
              <span className="px-1.5 py-0.5 rounded bg-indigo-950/50 text-indigo-300">UI {j.ui_coherence_score}/5</span>
              <span className="px-1.5 py-0.5 rounded bg-indigo-950/50 text-indigo-300">Pacing {j.interactivity_pacing_score}/5</span>
              <span className="px-1.5 py-0.5 rounded bg-indigo-950/50 text-indigo-300">Agency {j.player_agency_score}/5</span>
              {j.dead_end_risk !== 'none' && (
                <span className="px-1.5 py-0.5 rounded bg-amber-950/50 text-amber-300">dead-end: {j.dead_end_risk}</span>
              )}
            </div>
            <p className="text-[11px] text-gray-400 leading-relaxed">{j.summary}</p>
            {j.findings.length > 0 && (
              <div className="flex flex-col gap-1">
                {j.findings.map((f, i) => (
                  <span key={i} className={`text-[10px] px-1.5 py-0.5 rounded ${SEVERITY_COLOR[f.severity]}`}>
                    {f.message}
                  </span>
                ))}
              </div>
            )}
          </>
        ) : (
          <p className="text-[11px] text-red-400">Judge failed: {frame.judge_error}</p>
        )}
      </div>
    </div>
  )
}

export default function PlaytestPane({ jobId }: { jobId: string }) {
  const [report, setReport] = useState<PlaytestReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loaded, setLoaded] = useState(false)

  useEffect(() => {
    setLoaded(false)
    api.getPlaytestReport(jobId)
      .then(setReport)
      .catch(() => setReport(null))
      .finally(() => setLoaded(true))
  }, [jobId])

  const runPlaytest = async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await api.runPlaytest(jobId)
      setReport(result)
    } catch (e) {
      setError(String(e))
    } finally {
      setLoading(false)
    }
  }

  if (!loaded) {
    return <div className="text-xs text-gray-500 p-4">Loading…</div>
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-[11px] text-gray-500 leading-relaxed max-w-md">
          Walks every reachable scene/branch, renders a representative frame for each, and asks a
          vision LLM to judge UI coherence, dead-end risk, pacing, and player agency.
        </p>
        <button
          onClick={runPlaytest}
          disabled={loading}
          className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 text-white text-xs
            font-medium rounded-lg transition-colors whitespace-nowrap"
        >
          {loading ? 'Running…' : report ? 'Re-run Playtest' : 'Run Playtest'}
        </button>
      </div>

      {error && (
        <div className="rounded border border-red-900 bg-red-950/40 px-3 py-2 text-xs text-red-300">
          {error}
        </div>
      )}

      {!report && !loading && !error && (
        <div className="text-xs text-gray-600 border border-dashed border-gray-800 rounded-lg p-8 text-center">
          No playtest report yet — run one to see coverage and frame-level judgments.
        </div>
      )}

      {report && (
        <>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-2">
            {Object.entries(report.dimension_scores).map(([key, value]) => (
              <StatTile key={key} label={DIMENSION_LABELS[key] ?? key} value={value.toFixed(2)} />
            ))}
          </div>
          <div className="text-[10px] text-gray-600">
            {report.visited_scenes}/{report.total_scenes} scenes visited ·
            {' '}{report.reachable_branches}/{report.total_declared_branches} branches reachable ·
            {' '}{report.frames_judged} frames judged ({report.frames_skipped} skipped) ·
            {' '}judge: {report.judge_model}
          </div>
          {report.unreachable_scene_ids.length > 0 && (
            <div className="text-[10px] text-amber-400">
              Unreachable scenes: {report.unreachable_scene_ids.join(', ')}
            </div>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
            {report.frames.map(f => <FrameCard key={f.node_id} jobId={jobId} frame={f} />)}
          </div>
        </>
      )}
    </div>
  )
}
