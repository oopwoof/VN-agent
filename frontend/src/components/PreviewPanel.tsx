import useStore from '../store'
import ProgressBar from './ProgressBar'
import SettingPanel from './SettingPanel'
import api from '../api'

const STEPS = ['Setting', 'Script', 'Review', 'Assets', 'Compile']

function stepIndex(step: string): number {
  if (step.includes('setting')) return 0
  if (step.includes('script')) return 1
  if (step.includes('review') || step.includes('Reviewer')) return 2
  if (step.includes('asset')) return 3
  if (step.includes('build') || step.includes('compil')) return 4
  return -1
}

export default function PreviewPanel() {
  const { step, progress, errors, currentJobId, elapsed } = useStore()

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

  const si = step === 'completed' ? STEPS.length : stepIndex(progress || step)
  const pct = step === 'completed' ? 100 : Math.min(10 + (si + 1) * 18, 90)

  return (
    <div className="flex flex-col h-full">
      {/* Progress bar */}
      <div className="p-4 border-b border-gray-800">
        <ProgressBar steps={STEPS} currentStep={si} percent={pct} />
      </div>

      {/* Content */}
      <div className="flex-1 overflow-y-auto custom-scrollbar">
        {/* Setting review */}
        {step === 'setting_review' && <SettingPanel />}

        {/* Generating states */}
        {(step === 'generating_setting' || step === 'generating_script') && (
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

        {/* Completed */}
        {step === 'completed' && currentJobId && (
          <div className="p-6">
            <div className="bg-gray-900 border border-green-800/50 rounded-lg p-6 space-y-4">
              <div className="flex items-center gap-3">
                <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
                </svg>
                <span className="text-green-400 font-medium">{progress}</span>
              </div>
              <a
                href={api.downloadUrl(currentJobId)}
                className="inline-flex items-center gap-2 px-6 py-2.5 bg-green-600 hover:bg-green-500 text-white font-medium rounded-lg transition-colors"
              >
                Download Ren'Py Project (ZIP)
              </a>
              <p className="text-xs text-gray-600">Total time: {elapsed}s</p>
            </div>
          </div>
        )}

        {/* Failed */}
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
