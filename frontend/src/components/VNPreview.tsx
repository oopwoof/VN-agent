import { useState, useCallback } from 'react'
import useStore from '../store'

interface DialogueLine { character_id: string | null; text: string; emotion: string }
interface Branch { text: string; next_scene_id: string }
interface SceneScript {
  id: string; title: string; background_id: string;
  characters_present: string[]; dialogue: DialogueLine[];
  branches: Branch[]; next_scene_id: string | null
}

export default function VNPreview() {
  const { blackboard, currentJobId, toggleVNPreview } = useStore()
  const scenes = (blackboard.scene_scripts || []) as SceneScript[]
  const chars = (blackboard.characters || blackboard._characters_json || {}) as Record<string, { name?: string; color?: string }>

  const [sceneIdx, setSceneIdx] = useState(0)
  const [lineIdx, setLineIdx] = useState(-1) // -1 = scene title card
  const [ended, setEnded] = useState(false)

  const scene = scenes[sceneIdx]

  const goToScene = useCallback((id: string) => {
    const idx = scenes.findIndex(s => s.id === id)
    if (idx >= 0) { setSceneIdx(idx); setLineIdx(-1); setEnded(false) }
  }, [scenes])

  const advance = useCallback(() => {
    if (!scene || ended) return

    if (lineIdx < scene.dialogue.length - 1) {
      setLineIdx(lineIdx + 1)
    } else if (scene.branches.length > 0) {
      // branches shown, wait for choice
    } else if (scene.next_scene_id) {
      goToScene(scene.next_scene_id)
    } else {
      setEnded(true)
    }
  }, [scene, lineIdx, ended, goToScene])

  if (!scene) return null

  const line = lineIdx >= 0 ? scene.dialogue[lineIdx] : null
  const showBranches = lineIdx >= scene.dialogue.length - 1 && scene.branches.length > 0
  const bgUrl = currentJobId ? `/api/projects/${currentJobId}/assets/file/game/images/backgrounds/${scene.background_id}.png` : ''

  const charName = line?.character_id ? (chars[line.character_id]?.name || line.character_id) : null
  const charColor = line?.character_id ? (chars[line.character_id]?.color || '#6366f1') : '#9ca3af'

  return (
    <div className="flex flex-col h-full bg-black">
      {/* Back button */}
      <div className="absolute top-2 right-2 z-20">
        <button onClick={toggleVNPreview}
          className="px-3 py-1 bg-gray-800/80 hover:bg-gray-700 text-gray-300 text-xs rounded transition-colors">
          Back to Editor
        </button>
      </div>

      {/* Game viewport */}
      <div className="flex-1 relative cursor-pointer select-none" onClick={advance}>
        {/* Background */}
        <div className="absolute inset-0 bg-gray-900">
          <img src={bgUrl} alt="" className="w-full h-full object-cover opacity-80"
            onError={e => (e.currentTarget.style.display = 'none')} />
        </div>

        {/* Character sprites */}
        {line?.character_id && (
          <div className="absolute bottom-32 left-1/2 -translate-x-1/2 z-10">
            <img
              src={currentJobId ? `/api/projects/${currentJobId}/assets/file/game/images/characters/${line.character_id}/${line.emotion || 'neutral'}.png` : ''}
              alt="" className="h-48 object-contain"
              onError={e => (e.currentTarget.style.display = 'none')}
            />
          </div>
        )}

        {/* Scene title card */}
        {lineIdx === -1 && (
          <div className="absolute inset-0 flex items-center justify-center z-10 bg-black/60">
            <div className="text-center">
              <h2 className="text-2xl font-bold text-white mb-2">{scene.title}</h2>
              <p className="text-sm text-gray-400">Click to start</p>
            </div>
          </div>
        )}

        {/* Dialogue box */}
        {line && (
          <div className="absolute bottom-0 left-0 right-0 z-10 bg-gradient-to-t from-black/90 via-black/70 to-transparent p-6 pt-16">
            {charName && (
              <p className="text-sm font-bold mb-1" style={{ color: charColor }}>{charName}</p>
            )}
            <p className="text-base text-white leading-relaxed">{line.text}</p>
            {!showBranches && (
              <p className="text-[10px] text-gray-500 mt-2 text-right">Click to continue</p>
            )}
          </div>
        )}

        {/* Branch choices */}
        {showBranches && (
          <div className="absolute bottom-0 left-0 right-0 z-20 p-6 bg-black/80 space-y-2">
            {scene.branches.map((b, i) => (
              <button key={i} onClick={e => { e.stopPropagation(); goToScene(b.next_scene_id) }}
                className="w-full py-3 px-4 bg-indigo-900/60 hover:bg-indigo-700/60 border border-indigo-600/40 rounded-lg text-white text-sm text-left transition-colors">
                {b.text}
              </button>
            ))}
          </div>
        )}

        {/* End screen */}
        {ended && (
          <div className="absolute inset-0 flex items-center justify-center z-20 bg-black/80">
            <div className="text-center">
              <h2 className="text-2xl font-bold text-white mb-4">Fin</h2>
              <button onClick={toggleVNPreview}
                className="px-6 py-2 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg transition-colors">
                Back to Editor
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Status */}
      <div className="px-4 py-1 bg-gray-950 text-[10px] text-gray-600 flex justify-between">
        <span>Scene {sceneIdx + 1}/{scenes.length}: {scene.title}</span>
        <span>Line {Math.max(lineIdx + 1, 0)}/{scene.dialogue.length}</span>
      </div>
    </div>
  )
}
