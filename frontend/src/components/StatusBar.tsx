import { useEffect, useState } from 'react'
import useStore from '../store'

const STEP_LABELS: Record<string, string> = {
  idle: 'Ready',
  generating_setting: 'Planning...',
  setting_review: 'Review setting',
  generating_script: 'Writing...',
  script_review: 'Review script',
  compiling: 'Compiling...',
  asset_management: 'Manage assets',
  completed: 'Done',
  failed: 'Failed',
}

export default function StatusBar() {
  const { step, elapsed, currentJobId, config } = useStore()
  const busy = step.startsWith('generating') || step === 'compiling'
  const [tokenInfo, setTokenInfo] = useState<{ tokens: number; cost: number } | null>(null)

  useEffect(() => {
    if (!currentJobId || step === 'idle') { setTokenInfo(null); return }
    const fetchUsage = async () => {
      try {
        const resp = await fetch(`/api/projects/${currentJobId}/token-usage`)
        if (resp.ok) {
          const data = await resp.json()
          if (data.calls > 0) setTokenInfo({ tokens: data.total_input + data.total_output, cost: data.estimated_cost_usd })
        }
      } catch { /* ignore */ }
    }
    fetchUsage()
    const timer = setInterval(fetchUsage, 5000)
    return () => clearInterval(timer)
  }, [currentJobId, step])

  return (
    <div className="flex items-center gap-4 px-4 py-1.5 border-t border-gray-800 text-[11px] text-gray-500 bg-gray-950">
      <span className={busy ? 'text-indigo-400' : step === 'failed' ? 'text-red-400' : ''}>
        {busy ? '\u23F3' : step === 'completed' ? '\u2705' : step === 'failed' ? '\u274C' : '\u25CB'}{' '}
        {STEP_LABELS[step] || step}
      </span>
      {elapsed > 0 && <span>&#9201; {elapsed}s</span>}
      {tokenInfo && <span>&#128200; {tokenInfo.tokens.toLocaleString()} tok</span>}
      {tokenInfo && tokenInfo.cost > 0 && <span>&#128176; ${tokenInfo.cost.toFixed(4)}</span>}
      {config.fast_mode && <span className="text-yellow-500">Fast</span>}
      {currentJobId && <span className="font-mono">{currentJobId}</span>}
    </div>
  )
}
