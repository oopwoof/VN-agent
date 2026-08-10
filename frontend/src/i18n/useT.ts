import useStore from '../store'
import { dict, type TKey } from './dict'
import { interpolate } from './interpolate'

/** Translate a UI-chrome key using the language currently in the store.
 *  Falls back to the Chinese string if a key is somehow missing from the
 *  active language, so a gap shows up as the wrong language rather than as
 *  a blank button. */
export function useT(): (key: TKey) => string {
  const lang = useStore(s => s.lang)
  return (key: TKey) => dict[lang][key] ?? dict.zh[key]
}

/** Translate a key that carries `{name}` placeholders.
 *
 *  Used for the chat log, whose messages are stored as key + variables and
 *  resolved at paint time (see ChatMessage.tkey in types.ts) so that flipping
 *  the language re-renders the entire history, not just new messages.
 *
 *  `key` is typed loosely because it round-trips through the store as a
 *  plain string; an unrecognised key returns undefined and the caller is
 *  expected to fall back to the message's pre-rendered `content`.
 */
export function useTVars(): (
  key: string,
  vars?: Record<string, string | number>,
) => string | undefined {
  const lang = useStore(s => s.lang)
  return (key, vars) => {
    const template = dict[lang][key as TKey] ?? dict.zh[key as TKey]
    return template === undefined ? undefined : interpolate(template, vars)
  }
}

/** Full-sentence, localised label for a LangGraph pipeline node.
 *
 *  The backend deliberately keeps emitting stable English identifiers
 *  (`_STEP_LABELS` in web/app.py) plus the structured node id, so translation
 *  lives here. A node id the dictionary does not know about — a graph change
 *  the frontend has not caught up with — degrades to the server-supplied
 *  sentence rather than rendering `undefined`: the dictionary lookup is typed
 *  as returning `string`, but a key outside `TKey` resolves to undefined at
 *  runtime, so the guard is load-bearing.
 */
/** The one-line "what is happening right now" string, with a single precedence
 *  chain shared by PipelineStage and PreviewPanel (they previously carried
 *  identical copy-pasted expressions).
 *
 *  Order: the running graph node, then the phase the store is in, then the raw
 *  server progress string, then a generic fallback. The node wins because it is
 *  the most specific thing we know; `progress` survives underneath because it
 *  can carry server prose that has no key. */
export function useActivityLine(): (
  node: string | null,
  nodeFallback: string,
  progressKey: TKey | null,
  progress: string,
) => string {
  const lang = useStore(s => s.lang)
  const nodeLabel = useNodeLabel()
  return (node, nodeFallback, progressKey, progress) => {
    const fromNode = nodeLabel(node, '')
    if (fromNode) return fromNode
    if (progressKey) {
      const phase: string | undefined = dict[lang][progressKey] ?? dict.zh[progressKey]
      if (phase) return phase
    }
    return nodeFallback || progress
  }
}

export function useNodeLabel(): (node: string | null, fallback?: string) => string {
  const lang = useStore(s => s.lang)
  return (node, fallback = '') => {
    if (!node) return fallback
    const key = `nodeLabel.${node}` as TKey
    const label: string | undefined = dict[lang][key] ?? dict.zh[key]
    return label ?? fallback
  }
}
