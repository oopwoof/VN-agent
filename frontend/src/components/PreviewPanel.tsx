import useStore from '../store'
import ProgressBar from './ProgressBar'
import SettingPanel from './SettingPanel'
import ScriptPanel from './ScriptPanel'
import AssetPanel from './AssetPanel'
import VNPreview from './VNPreview'

const STEPS = ['Setting', 'Script', 'Review', 'Assets', 'Done']

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
  const { step, progress, errors, elapsed, vnPreview } = useStore()

  // VN Preview mode takes over the entire panel
  if (vnPreview) return <VNPreview />

  if (step === 'idle') {
    return (
      <div className="flex items-center justify-center h-full text-gray-600">
        <div className="text-center space-y-2">
          <div className="text-4xl">&#127918;</div>
          <p className="text-sm">Enter a theme to start generating</p>
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
                <span className="text-sm text-gray-300">{progress || 'Working...'}</span>
              </div>
              <p className="text-xs text-gray-600 mt-2">Elapsed: {elapsed}s</p>
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
                <span className="text-red-400 font-medium">Generation failed</span>
              </div>
              <pre className="text-xs text-red-300 bg-gray-950 rounded p-3 overflow-x-auto whitespace-pre-wrap">
                {errors.join('\n') || 'Unknown error'}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
