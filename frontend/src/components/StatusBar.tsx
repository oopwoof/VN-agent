import useStore from '../store'

export default function StatusBar() {
  const { step, elapsed, currentJobId } = useStore()

  return (
    <div className="flex items-center gap-6 px-4 py-1.5 border-t border-gray-800 text-[11px] text-gray-500 bg-gray-950">
      <span>
        {step.includes('generating') ? '\u23F3' : step === 'completed' ? '\u2705' : step === 'failed' ? '\u274C' : '\u25CB'}{' '}
        {step}
      </span>
      {elapsed > 0 && <span>&#9201; {elapsed}s</span>}
      {currentJobId && <span className="font-mono">Job: {currentJobId}</span>}
    </div>
  )
}
