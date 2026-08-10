import useStore from '../store'
import PipelineGraph from './PipelineGraph'
import { useT, useNodeLabel } from '../i18n/useT'

interface SceneLike { id: string; title?: string }

/** v4 P6 pipeline theatre: what the workbench shows while the graph runs.
 *  Replaces the old spinner-plus-one-string placeholder — the multi-agent
 *  pipeline is the product's differentiator and was previously invisible. */
export default function PipelineStage() {
  const t = useT()
  const nodeLabel = useNodeLabel()
  const { pipelineActive, pipelineLabel, progress, elapsed, blackboard, tokenUsage, streamActive, toggleVNPreview } = useStore()
  const scenes = (blackboard.scene_scripts as SceneLike[] | undefined) ?? []
  const maxScenes = useStore(s => s.config.max_scenes)
  const slots = Math.max(maxScenes, scenes.length)

  // Prefer the localised sentence keyed off the structured node id. The
  // backend deliberately keeps emitting English prose (it also feeds
  // `progress`, which non-UI consumers read), so translation lives here.
  // An id the dictionary does not know degrades to the server's own label;
  // with no node active at all we fall back to `progress`.
  const headline = nodeLabel(pipelineActive, pipelineLabel) || progress || t('preview.working')

  return (
    <div className="flex flex-col h-full p-6 gap-6">
      {/* Live pipeline */}
      <div
        className="rounded-lg border p-5"
        style={{ background: 'var(--surface)', borderColor: 'var(--rule)' }}
      >
        <div className="flex items-center gap-2 mb-4">
          {streamActive && (
            <span
              className="w-1.5 h-1.5 rounded-full animate-pulse"
              style={{ background: 'var(--crit)' }}
              aria-hidden="true"
            />
          )}
          <span className="face-instrument text-[11px] uppercase tracking-wider" style={{ color: 'var(--ink-faint)' }}>
            {headline}
          </span>
          <span className="face-instrument text-[11px] ml-auto" style={{ color: 'var(--ink-faint)' }}>
            {elapsed}s
          </span>
        </div>
        <PipelineGraph />
      </div>

      {/* Scene filmstrip */}
      <div className="flex flex-col gap-2">
        <span className="face-instrument text-[10px] uppercase tracking-wider" style={{ color: 'var(--ink-faint)' }}>
          {t('pipeline.scenes')} {scenes.length}/{slots}
        </span>
        <div className="flex flex-wrap gap-1.5">
          {Array.from({ length: slots }).map((_, i) => (
            <div
              key={i}
              className="h-1.5 w-10 rounded-full transition-colors duration-300"
              style={{ background: i < scenes.length ? 'var(--instrument)' : 'var(--rule)' }}
            />
          ))}
        </div>
      </div>

      {/* Cost meter */}
      {tokenUsage && (
        <div className="face-instrument flex items-baseline gap-4 text-[12px]" style={{ color: 'var(--ink-soft)' }}>
          <span>{tokenUsage.tokens.toLocaleString()} tok</span>
          <span style={{ color: 'var(--instrument)' }}>
            {t('pipeline.cost')} ${tokenUsage.cost.toFixed(4)}
          </span>
        </div>
      )}

      {/* Watch live — unchanged behaviour, restyled */}
      {scenes.length > 0 && (
        <button
          onClick={toggleVNPreview}
          className="self-start px-4 py-2 rounded-lg text-sm font-medium transition-opacity hover:opacity-90
            focus-visible:outline focus-visible:outline-2"
          style={{ background: 'var(--instrument)', color: 'var(--ground)' }}
        >
          ▶ {t('preview.watchLive')}（{scenes.length} {t('preview.scenesReady')}）
        </button>
      )}
    </div>
  )
}
