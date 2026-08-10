import useStore, { type AppStep } from '../store'
import ProgressBar from './ProgressBar'
import SettingPanel from './SettingPanel'
import ScriptPanel from './ScriptPanel'
import AssetPanel from './AssetPanel'
import VNPreview from './VNPreview'
import { useT, useActivityLine } from '../i18n/useT'

const STEP_KEYS = ['steps.setting', 'steps.script', 'steps.review', 'steps.assets', 'steps.done'] as const

// Which of STEP_KEYS the progress bar sits on, derived from the state machine
// and the live graph node.
//
// This used to lowercase `progress + step` and substring-match English tokens
// ('setting', 'writer', 'compil'). That was the exact defect
// FRONTEND_REDESIGN_v4.md §1 names — a structured signal downgraded to prose
// and then guessed back out of it — and it had two concrete consequences:
// the step could never be localised (translating `progress` would silently
// break the bar), and index 2 ('审校'/Review) was UNREACHABLE, because the
// 'script' test fired first for every step whose name contains "script".
const STEP_OF: Record<AppStep, number> = {
  idle: -1,
  generating_setting: 0,
  setting_review: 0,
  generating_script: 1,
  script_review: 2,
  asset_management: 3,
  compiling: 3,
  completed: 4,
  failed: -1,
}

function stepIndex(step: AppStep, pipelineActive: string | null): number {
  // The reviewer node runs inside generating_script, so surface the review
  // step while it is active instead of leaving the bar parked on "script".
  if (step === 'generating_script' && pipelineActive === 'reviewer') return 2
  return STEP_OF[step]
}

export default function PreviewPanel() {
  const { step, progress, progressKey, errors, elapsed, vnPreview, blackboard, streamActive, toggleVNPreview } = useStore()
  const pipelineActive = useStore(s => s.pipelineActive)
  const pipelineLabel = useStore(s => s.pipelineLabel)
  const t = useT()
  const activityLine = useActivityLine()
  const STEPS = STEP_KEYS.map(k => t(k))

  const activity = activityLine(pipelineActive, pipelineLabel, progressKey, progress) || t('preview.working')

  // VN Preview mode takes over the entire panel
  if (vnPreview) return <VNPreview />

  if (step === 'idle') {
    return (
      <div className="flex items-center justify-center h-full text-gray-600">
        <div className="text-center space-y-2">
          <div className="text-4xl">&#127918;</div>
          <p className="text-sm">{t('preview.empty')}</p>
        </div>
      </div>
    )
  }

  const si = step === 'completed' ? STEPS.length : stepIndex(step, pipelineActive)
  const pct = step === 'completed' ? 100 : Math.min(10 + (si + 1) * 18, 90)

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-gray-800">
        <ProgressBar steps={STEPS} currentStep={si} percent={pct} />
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {step === 'setting_review' && <SettingPanel />}

        {step === 'script_review' && <ScriptPanel />}

        {(step === 'asset_management' || step === 'completed') && <AssetPanel />}

        {(step === 'generating_setting' || step === 'generating_script' || step === 'compiling') && (
          <div className="p-6">
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
              <div className="flex items-center gap-3">
                <div className="spinner" />
                <span className="text-sm text-gray-300">{activity}</span>
                {streamActive && (
                  <span className="flex items-center gap-1 text-[10px] text-red-400 font-medium uppercase tracking-wider">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
                    {t('preview.live')}
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-600 mt-2">{t('preview.elapsed')}: {elapsed}s</p>
              {/* v4 P2 ⑤: JIT playback — scenes stream into blackboard.scene_scripts
                  as Writer finishes them, so preview can start before the full
                  script (and Reviewer pass) is done. */}
              {step === 'generating_script' && Array.isArray(blackboard.scene_scripts) && (blackboard.scene_scripts as unknown[]).length > 0 && (
                <button
                  onClick={toggleVNPreview}
                  className="mt-4 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
                >
                  ▶ {t('preview.watchLive')}（{(blackboard.scene_scripts as unknown[]).length} {t('preview.scenesReady')}）
                </button>
              )}
            </div>
          </div>
        )}

        {step === 'failed' && (
          <div className="p-6">
            <div className="bg-gray-900 border border-red-800/50 rounded-lg p-6">
              <div className="flex items-center gap-3 mb-3">
                <svg className="w-6 h-6 text-red-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
                <span className="text-red-400 font-medium">{t('preview.failed')}</span>
              </div>
              <pre className="text-xs text-red-300 bg-gray-950 rounded p-3 overflow-x-auto whitespace-pre-wrap">
                {errors.join('\n') || t('preview.unknownError')}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
