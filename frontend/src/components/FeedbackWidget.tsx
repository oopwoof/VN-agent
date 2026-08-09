import { useState } from 'react'
import api, { type FeedbackSummary } from '../api'
import { useT } from '../i18n/useT'

// v4 P1-4: creator 👍/👎 into the data flywheel.
// Reason is optional but strongly encouraged — the BM25 injector (P1-2)
// and Reflection Agent (P1-3) both need it. Empty reason still counts
// for aggregate ratios but skips the ranker.

interface Props {
  jobId?: string
  sceneId?: string
  // Compact = inline (no textarea) for the ChatPanel footer; full = expanded
  // per-scene under VNPreview.
  variant?: 'compact' | 'full'
  onSubmit?: (summary: FeedbackSummary) => void
}

export default function FeedbackWidget({ jobId, sceneId, variant = 'compact', onSubmit }: Props) {
  const t = useT()
  const [reason, setReason] = useState('')
  const [busy, setBusy] = useState(false)
  const [flash, setFlash] = useState<'up' | 'down' | 'error' | null>(null)

  const submit = async (verdict: 'up' | 'down') => {
    if (busy) return
    setBusy(true)
    try {
      const res = await api.postFeedback({
        verdict,
        job_id: jobId,
        scene_id: sceneId,
        reason: reason.trim() || undefined,
      })
      setReason('')
      setFlash(verdict)
      onSubmit?.(res.summary)
      setTimeout(() => setFlash(null), 1500)
    } catch (e) {
      console.error('feedback post failed', e)
      setFlash('error')
      setTimeout(() => setFlash(null), 2500)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className={variant === 'full' ? 'space-y-2 p-2' : 'flex items-center gap-2'}>
      {variant === 'full' && (
        <textarea
          value={reason}
          onChange={e => setReason(e.target.value)}
          placeholder={t('feedback.reasonPlaceholderFull')}
          rows={2}
          disabled={busy}
          className="w-full bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-indigo-500"
        />
      )}
      <div className={variant === 'full' ? 'flex items-center gap-2' : 'flex items-center gap-1.5'}>
        <button
          onClick={() => submit('up')}
          disabled={busy}
          className={`px-2 py-1 rounded text-xs transition-colors ${
            flash === 'up' ? 'bg-emerald-600 text-white' :
            'bg-gray-800 hover:bg-emerald-900/50 text-emerald-400 border border-emerald-900/60'
          } disabled:opacity-40`}
          title={t('feedback.thumbsUp')}
        >
          👍
        </button>
        <button
          onClick={() => submit('down')}
          disabled={busy}
          className={`px-2 py-1 rounded text-xs transition-colors ${
            flash === 'down' ? 'bg-red-600 text-white' :
            'bg-gray-800 hover:bg-red-900/50 text-red-400 border border-red-900/60'
          } disabled:opacity-40`}
          title={t('feedback.thumbsDown')}
        >
          👎
        </button>
        {variant === 'compact' && (
          <input
            value={reason}
            onChange={e => setReason(e.target.value)}
            placeholder={t('feedback.reasonPlaceholderCompact')}
            disabled={busy}
            className="flex-1 min-w-0 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-[11px] text-gray-100 placeholder-gray-600 focus:outline-none focus:ring-1 focus:ring-indigo-500"
          />
        )}
        {flash === 'error' && (
          <span className="text-[10px] text-red-400">{t('feedback.submitFailed')}</span>
        )}
      </div>
    </div>
  )
}
