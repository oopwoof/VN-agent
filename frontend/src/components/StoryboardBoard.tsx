import { useState } from 'react'
import { ArrowLeft } from 'lucide-react'
import useStore from '../store'
import SceneCard, { type SceneCardScene } from './SceneCard'
import ScriptPanel from './ScriptPanel'
import { useT, useTVars } from '../i18n/useT'

/** v4 P6 storyboard: the workbench form once a script exists. Makes the
 *  branching structure legible at a glance and turns Chat Ops scene
 *  targeting from "describe which scene" into a spatial pick.
 *
 *  ScriptPanel is not replaced — it becomes the card detail view, because it
 *  owns the only per-scene dialogue editor AND the only script_review action
 *  bar (Confirm & Continue / Regenerate / Export / Back to Setting). */
export default function StoryboardBoard() {
  const t = useT()
  const tv = useTVars()
  const { blackboard, currentJobId, jumpToScene, focusScene, sendChatMessage } = useStore()
  const scenes = (blackboard.scene_scripts as SceneCardScene[] | undefined) ?? []
  const [detail, setDetail] = useState(false)

  if (scenes.length === 0) {
    return (
      <div className="flex items-center justify-center h-full" style={{ color: 'var(--ink-faint)' }}>
        <p className="text-sm">{t('preview.empty')}</p>
      </div>
    )
  }

  if (detail) {
    return (
      <div className="flex flex-col h-full">
        <button
          onClick={() => setDetail(false)}
          className="face-instrument flex items-center gap-1.5 px-4 py-2 text-[11px] border-b self-start
            focus-visible:outline focus-visible:outline-2"
          style={{ color: 'var(--ink-soft)', borderColor: 'var(--rule)' }}
        >
          <ArrowLeft size={12} aria-hidden="true" /> {t('board.backToBoard')}
        </button>
        <div className="flex-1 overflow-y-auto custom-scrollbar">
          <ScriptPanel />
        </div>
      </div>
    )
  }

  const openDetail = (index: number) => {
    focusScene(index)
    setDetail(true)
  }

  const handleRewrite = (sceneId: string) => {
    const scene = scenes.find(s => s.id === sceneId)
    // Reuses the existing P3 chat-ops chain end to end: this message goes
    // through intent classification and the preview/confirm card exactly as
    // a typed request would. No new execution path.
    const prompt = tv('board.rewritePrompt', { title: scene?.title || sceneId })
    if (prompt) sendChatMessage(prompt)
  }

  return (
    <div className="p-6">
      <div className="grid gap-3 grid-cols-[repeat(auto-fill,minmax(180px,1fr))]">
        {scenes.map((scene, i) => (
          <SceneCard
            key={scene.id}
            scene={scene}
            index={i}
            jobId={currentJobId}
            onPlay={jumpToScene}
            onOpen={openDetail}
            onRewrite={handleRewrite}
          />
        ))}
      </div>
    </div>
  )
}
