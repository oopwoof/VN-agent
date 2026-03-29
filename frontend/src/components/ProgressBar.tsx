interface Props {
  steps: string[]
  currentStep: number
  percent: number
}

export default function ProgressBar({ steps, currentStep, percent }: Props) {
  return (
    <div className="space-y-3">
      {/* Bar with shimmer on active */}
      <div className="w-full bg-gray-800 rounded-full h-2 overflow-hidden">
        <div
          className="bg-indigo-500 h-2 rounded-full transition-all duration-1000 ease-in-out relative"
          style={{ width: `${percent}%` }}
        >
          {percent < 100 && (
            <div className="absolute inset-0 bg-gradient-to-r from-transparent via-indigo-400/30 to-transparent animate-shimmer" />
          )}
        </div>
      </div>
      {/* Steps */}
      <div className="flex justify-between text-[10px]">
        {steps.map((s, i) => (
          <span key={s} className={`flex items-center gap-1 transition-colors duration-300 ${
            i < currentStep ? 'text-green-400' :
            i === currentStep ? 'text-indigo-400 font-semibold' :
            'text-gray-600'
          }`}>
            {i < currentStep ? '\u2713' : i === currentStep ? (
              <span className="inline-block w-2 h-2 rounded-full bg-indigo-500 animate-pulse" />
            ) : '\u25CB'} {s}
          </span>
        ))}
      </div>
    </div>
  )
}
