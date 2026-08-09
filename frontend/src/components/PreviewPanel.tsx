import useStore from '../store'
import ProgressBar from './ProgressBar'
import SettingPanel from './SettingPanel'
import ScriptPanel from './ScriptPanel'
import AssetPanel from './AssetPanel'
import VNPreview from './VNPreview'
import { useT } from '../i18n/useT'

const STEP_KEYS = ['steps.setting', 'steps.script', 'steps.review', 'steps.assets', 'steps.done'] as const

function stepIndex(step: string, progress: string): number {
  const p = (progress + ' ' + step).toLowerCase()
  if (p.includes('setting')) return 0
  if (p.includes('script') || p.includes('writer')) return 1
  if (p.includes('review') || p.includes('reviewer')) return 2
  if (p.includes('asset') || p.includes('compil')) return 3
  if (p.includes('completed') || p.includes('done')) return 4
  return -1
}

export default function PreviewPanel() {
  const { step, progress, errors, elapsed, vnPreview, blackboard, streamActive, toggleVNPreview } = useStore()
  const t = useT()
  const STEPS = STEP_KEYS.map(k => t(k))

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

  const si = step === 'completed' ? STEPS.length : stepIndex(step, progress)
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
                <span className="text-sm text-gray-300">{progress || t('preview.working')}</span>
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
