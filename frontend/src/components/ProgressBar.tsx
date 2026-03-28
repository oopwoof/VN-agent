interface Props {
  steps: string[]
  currentStep: number
  percent: number
}

export default function ProgressBar({ steps, currentStep, percent }: Props) {
  return (
    <div className="space-y-3">
      {/* Bar */}
      <div className="w-full bg-gray-800 rounded-full h-2">
        <div
          className="bg-indigo-500 h-2 rounded-full transition-all duration-700"
          style={{ width: `${percent}%` }}
        />
      </div>
      {/* Steps */}
      <div className="flex justify-between text-[10px]">
        {steps.map((s, i) => (
          <span key={s} className={
            i < currentStep ? 'text-green-400' :
            i === currentStep ? 'text-indigo-400 font-semibold' :
            'text-gray-600'
          }>
            {i < currentStep ? '\u2713' : i === currentStep ? '\u25CF' : '\u25CB'} {s.split(' ')[0]}
          </span>
        ))}
      </div>
    </div>
  )
}
