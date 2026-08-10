import { useEffect } from 'react'
import useStore from '../store'
import { useT } from '../i18n/useT'
import type { TKey } from '../i18n/dict'

export default function StatusBar() {
  const { step, elapsed, currentJobId, config } = useStore()
  const t = useT()
  const busy = step.startsWith('generating') || step === 'compiling'
  // Reads the shared store value rather than owning a fetch: PipelineStage
  // needs the same numbers, and two components each polling the same endpoint
  // every 5s would double the request rate for no benefit.
  const tokenInfo = useStore(s => s.tokenUsage)
  const refreshTokenUsage = useStore(s => s.refreshTokenUsage)

  useEffect(() => {
    if (!currentJobId || step === 'idle') return
    refreshTokenUsage()
    const timer = setInterval(refreshTokenUsage, 5000)
    return () => clearInterval(timer)
  }, [currentJobId, step, refreshTokenUsage])

  return (
    <div className="flex items-center gap-4 px-4 py-1.5 border-t border-gray-800 text-[11px] text-gray-500 bg-gray-950">
      <span className={busy ? 'text-indigo-400' : step === 'failed' ? 'text-red-400' : ''}>
        {busy ? '\u23F3' : step === 'completed' ? '\u2705' : step === 'failed' ? '\u274C' : '\u25CB'}{' '}
        {t(`status.${step}` as TKey)}
      </span>
      {elapsed > 0 && <span>&#9201; {elapsed}s</span>}
      {tokenInfo && <span>&#128200; {tokenInfo.tokens.toLocaleString()} tok</span>}
      {tokenInfo && tokenInfo.cost > 0 && <span>&#128176; ${tokenInfo.cost.toFixed(4)}</span>}
      {config.fast_mode && <span className="text-yellow-500">{t('status.fast')}</span>}
      {currentJobId && <span className="font-mono">{currentJobId}</span>}
    </div>
  )
}
