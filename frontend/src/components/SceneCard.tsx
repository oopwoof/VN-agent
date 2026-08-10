import { Play, Pencil } from 'lucide-react'
import { useT } from '../i18n/useT'

export interface SceneCardScene {
  id: string
  title: string
  background_id: string
  dialogue: unknown[]
  branches: { text: string; next_scene_id: string }[]
}

interface SceneCardProps {
  scene: SceneCardScene
  index: number
  jobId: string | null
  onPlay: (index: number) => void
  onRewrite: (sceneId: string) => void
}

export default function SceneCard({ scene, index, jobId, onPlay, onRewrite }: SceneCardProps) {
  const t = useT()
  // Same URL shape VNPreview uses for its backdrop, so a card and the player
  // resolve the identical file; a missing asset hides the img rather than
  // showing a broken-image glyph.
  const bgUrl = jobId
    ? `/api/projects/${jobId}/assets/file/game/images/backgrounds/${scene.background_id}.png`
    : ''

  return (
    <div
      className="group relative flex flex-col rounded-lg border overflow-hidden transition-colors"
      style={{ background: 'var(--surface)', borderColor: 'var(--rule)' }}
    >
      <div className="relative h-20 overflow-hidden" style={{ background: 'var(--surface-raised)' }}>
        {bgUrl && (
          <img
            src={bgUrl}
            alt=""
            className="w-full h-full object-cover opacity-60"
            onError={e => (e.currentTarget.style.display = 'none')}
          />
        )}
        <span
          className="face-instrument absolute top-1.5 left-2 text-[10px] px-1.5 py-0.5 rounded"
          style={{ background: 'var(--ground)', color: 'var(--ink-faint)' }}
        >
          {index + 1}
        </span>
      </div>

      <div className="flex flex-col gap-1 p-3 flex-1">
        <h3 className="face-narrative text-sm" style={{ color: 'var(--ink)', lineHeight: 1.4 }}>
          {scene.title || scene.id}
        </h3>
        <span className="face-instrument text-[10px]" style={{ color: 'var(--ink-faint)' }}>
          {scene.dialogue.length} {t('card.lines')}
          {scene.branches.length > 0 && ` · ${scene.branches.length} ${t('card.branches')}`}
        </span>
      </div>

      <div className="flex border-t" style={{ borderColor: 'var(--rule)' }}>
        <button
          onClick={() => onPlay(index)}
          title={t('card.play')}
          className="flex-1 flex items-center justify-center gap-1 py-1.5 text-[11px] transition-colors
            hover:opacity-80 focus-visible:outline focus-visible:outline-2"
          style={{ color: 'var(--ink-soft)' }}
        >
          <Play size={11} aria-hidden="true" /> {t('card.play')}
        </button>
        <button
          onClick={() => onRewrite(scene.id)}
          title={t('card.rewrite')}
          aria-label={t('card.rewrite')}
          className="flex items-center justify-center gap-1 px-3 py-1.5 text-[11px] border-l transition-colors
            hover:opacity-80 focus-visible:outline focus-visible:outline-2"
          style={{ color: 'var(--instrument)', borderColor: 'var(--rule)' }}
        >
          <Pencil size={11} aria-hidden="true" />
        </button>
      </div>
    </div>
  )
}
