import useStore from '../store'
import ProgressBar from './ProgressBar'
import api from '../api'

const STEPS = ['Director planning', 'Writer creating', 'Reviewer checking', 'Generating assets', 'building project']

function matchStep(progress: string): number {
  const p = progress.toLowerCase()
  for (let i = STEPS.length - 1; i >= 0; i--) {
    if (p.includes(STEPS[i].toLowerCase().split(' ')[0])) return i
  }
  return -1
}

export default function PreviewPanel() {
  const { status, progress, errors, currentJobId, elapsed } = useStore()

  if (status === 'idle') {
    return (
      <div className="flex items-center justify-center h-full text-gray-600">
        <div className="text-center space-y-2">
          <div className="text-4xl">&#127918;</div>
          <p className="text-sm">Enter a theme to start generating</p>
        </div>
      </div>
    )
  }

  const stepIdx = matchStep(progress)
  const pct = status === 'completed' ? 100 : Math.min(10 + (stepIdx + 1) * 20, 90)

  return (
    <div className="p-6 space-y-6">
      {/* Progress */}
      <ProgressBar steps={STEPS} currentStep={stepIdx} percent={pct} />

      {/* Generating */}
      {status === 'generating' && (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-6">
          <div className="flex items-center gap-3">
            <div className="spinner" />
            <span className="text-sm text-gray-300">{progress || 'Starting...'}</span>
          </div>
          <p className="text-xs text-gray-600 mt-2">Elapsed: {elapsed}s</p>
        </div>
      )}

      {/* Completed */}
      {status === 'completed' && currentJobId && (
        <div className="bg-gray-900 border border-green-800/50 rounded-lg p-6 space-y-4">
          <div className="flex items-center gap-3">
            <svg className="w-6 h-6 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            <span className="text-green-400 font-medium">{progress}</span>
          </div>
          <div className="flex gap-3">
            <a
              href={api.downloadUrl(currentJobId)}
              className="inline-flex items-center gap-2 px-6 py-2.5 bg-green-600 hover:bg-green-500
                text-white font-medium rounded-lg transition-colors"
            >
              Download ZIP
            </a>
          </div>
          <p className="text-xs text-gray-600">Elapsed: {elapsed}s</p>
        </div>
      )}

      {/* Failed */}
      {status === 'failed' && (
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
      )}
    </div>
  )
}
