import useStore from '../store'
import { useT } from '../i18n/useT'
import type { TKey } from '../i18n/dict'

// Display spine, mirroring the linear path in src/vn_agent/agents/graph.py
// (set_entry_point("director") … add_edge("asset_generation", END)).
//
// director_step2_redo / director_full_redo are deliberately NOT columns:
// they are loop-backs from structure_reviewer, so they surface as a
// "revising" badge on that node instead of as extra steps that would make
// the pipeline look longer than it is.
const SPINE = [
  'director',
  'structure_reviewer',
  'state_orchestrator',
  'thinking_fanout',
  'cross_ref_sync',
  'writer',
  'reviewer',
  'asset_generation',
] as const

const REDO_NODES = ['director_step2_redo', 'director_full_redo'] as const

export default function PipelineGraph() {
  const t = useT()
  const pipelineNodes = useStore(s => s.pipelineNodes)
  const textOnly = useStore(s => s.config.text_only)
  const revising = REDO_NODES.some(n => pipelineNodes[n] === 'active')

  return (
    <ol className="face-instrument flex flex-wrap items-center gap-y-3" aria-label="pipeline">
      {SPINE.map((node, i) => {
        // asset_generation never runs while text_only is on, so it must read
        // as deliberately skipped rather than sitting on 'pending' forever —
        // a stalled-looking final step is worse than an honest empty one.
        const skipped = node === 'asset_generation' && textOnly
        const state = pipelineNodes[node] ?? 'pending'
        const isActive = state === 'active'
        const isDone = state === 'done'
        const color = skipped
          ? 'var(--ink-faint)'
          : isActive || isDone ? 'var(--instrument)' : 'var(--ink-faint)'

        return (
          <li key={node} className="flex items-center">
            {i > 0 && (
              <span
                aria-hidden="true"
                className="w-5 h-px mx-1.5 shrink-0"
                style={{ background: !skipped && (isDone || isActive) ? 'var(--instrument)' : 'var(--rule)' }}
              />
            )}
            <span
              className={`relative px-2.5 py-1 rounded text-[11px] border whitespace-nowrap${
                isActive && !skipped ? ' vn-pulse' : ''
              }`}
              style={{
                color,
                borderColor: isActive && !skipped ? 'var(--instrument)' : 'var(--rule)',
                background: isActive && !skipped ? 'var(--instrument-wash)' : 'transparent',
                fontWeight: isActive && !skipped ? 600 : 400,
                opacity: skipped ? 0.45 : 1,
              }}
            >
              {t(`node.${node}` as TKey)}
              {node === 'structure_reviewer' && revising && (
                <span className="ml-1.5 text-[9px]" style={{ color: 'var(--warn)' }}>
                  ↻ {t('pipeline.revising')}
                </span>
              )}
              {skipped && (
                <span className="ml-1.5 text-[9px]" style={{ color: 'var(--ink-faint)' }}>
                  {t('pipeline.skipped')}
                </span>
              )}
            </span>
          </li>
        )
      })}
    </ol>
  )
}
