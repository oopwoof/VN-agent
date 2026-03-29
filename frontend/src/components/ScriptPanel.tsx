import { useState } from 'react'
import useStore from '../store'
import api from '../api'

interface DialogueLine {
  character_id: string | null
  text: string
  emotion: string
}

interface Branch {
  text: string
  next_scene_id: string
}

interface SceneScript {
  id: string
  title: string
  description: string
  background_id: string
  characters_present: string[]
  narrative_strategy: string | null
  dialogue: DialogueLine[]
  branches: Branch[]
  next_scene_id: string | null
}

const EMOTIONS = ['neutral', 'happy', 'sad', 'angry', 'surprised', 'scared', 'thoughtful', 'loving', 'determined']

export default function ScriptPanel() {
  const { blackboard, currentJobId, step } = useStore()
  const scenes = (blackboard.scene_scripts || []) as SceneScript[]
  const reviewer = (blackboard.reviewer || {}) as {
    passed?: boolean; feedback?: string; revision_count?: number;
    scores?: Record<string, number> | null
  }
  const [activeScene, setActiveScene] = useState(0)
  const [editing, setEditing] = useState(false)
  const [editDialogue, setEditDialogue] = useState<DialogueLine[]>([])

  const scene = scenes[activeScene]

  const startEdit = () => {
    if (!scene) return
    setEditDialogue(scene.dialogue.map(d => ({ ...d })))
    setEditing(true)
  }

  const saveEdit = async () => {
    if (!currentJobId || !scene) return
    try {
      await api.updateScene(currentJobId, scene.id, { dialogue: editDialogue })
      // Update local blackboard
      const updatedScenes = [...scenes]
      updatedScenes[activeScene] = { ...scene, dialogue: editDialogue }
      useStore.setState({
        blackboard: { ...blackboard, scene_scripts: updatedScenes },
      })
      setEditing(false)
    } catch (e) {
      alert(`Save failed: ${e}`)
    }
  }

  const exportJSON = async () => {
    if (!currentJobId) return
    try {
      const data = await api.exportScript(currentJobId)
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `vn_script_${currentJobId}.json`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      alert(`Export failed: ${e}`)
    }
  }

  if (!scenes.length) return null

  return (
    <div className="flex flex-col h-full">
      {/* Reviewer result banner */}
      <div className={`px-4 py-2 text-xs border-b ${
        reviewer.passed ? 'bg-green-950/50 border-green-800/50 text-green-400' : 'bg-yellow-950/50 border-yellow-800/50 text-yellow-400'
      }`}>
        <span className="font-semibold">
          {reviewer.passed ? '\u2705 Reviewer: PASS' : `\u26A0\uFE0F Reviewer: ${reviewer.revision_count || 0} revision(s)`}
        </span>
        {reviewer.scores && (
          <span className="ml-3 text-[10px] opacity-70">
            {Object.entries(reviewer.scores).map(([k, v]) => `${k}=${v}`).join(' ')}
          </span>
        )}
        {reviewer.feedback && !reviewer.passed && (
          <p className="mt-1 text-[11px] opacity-80 line-clamp-2">{reviewer.feedback}</p>
        )}
      </div>

      {/* Scene navigation tabs */}
      <div className="flex gap-1 px-3 py-2 border-b border-gray-800 overflow-x-auto custom-scrollbar">
        {scenes.map((s, i) => (
          <button
            key={s.id}
            onClick={() => { setActiveScene(i); setEditing(false) }}
            className={`px-3 py-1.5 rounded text-xs whitespace-nowrap transition-colors ${
              i === activeScene
                ? 'bg-indigo-600 text-white'
                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}
          >
            S{i + 1}: {s.title}
          </button>
        ))}
      </div>

      {/* Scene content */}
      {scene && (
        <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
          {/* Scene header */}
          <div className="mb-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-gray-200">{scene.title}</h3>
              {!editing ? (
                <button onClick={startEdit} className="text-xs text-indigo-400 hover:text-indigo-300">Edit</button>
              ) : (
                <div className="flex gap-2">
                  <button onClick={saveEdit} className="text-xs text-green-400 hover:text-green-300">Save</button>
                  <button onClick={() => setEditing(false)} className="text-xs text-gray-500 hover:text-gray-400">Cancel</button>
                </div>
              )}
            </div>
            <p className="text-xs text-gray-500 mt-1">{scene.description}</p>
            <div className="flex gap-2 mt-2 text-[10px]">
              <span className="bg-gray-800 px-2 py-0.5 rounded text-gray-400">{scene.background_id}</span>
              {scene.narrative_strategy && (
                <span className="bg-indigo-950 px-2 py-0.5 rounded text-indigo-400">{scene.narrative_strategy}</span>
              )}
              <span className="text-gray-600">{scene.dialogue.length} lines</span>
            </div>
          </div>

          {/* Dialogue */}
          <div className="space-y-2">
            {(editing ? editDialogue : scene.dialogue).map((d, i) => (
              <div key={i} className={`rounded-lg p-3 text-sm ${
                d.character_id ? 'bg-gray-900 border border-gray-800' : 'bg-gray-950 border border-gray-900 italic'
              }`}>
                {editing ? (
                  <div className="space-y-2">
                    <div className="flex gap-2 text-xs">
                      <input
                        value={d.character_id || ''}
                        onChange={e => {
                          const updated = [...editDialogue]
                          updated[i] = { ...d, character_id: e.target.value || null }
                          setEditDialogue(updated)
                        }}
                        placeholder="narrator"
                        className="bg-gray-800 border border-gray-700 rounded px-2 py-1 w-32 text-gray-300"
                      />
                      <select
                        value={d.emotion}
                        onChange={e => {
                          const updated = [...editDialogue]
                          updated[i] = { ...d, emotion: e.target.value }
                          setEditDialogue(updated)
                        }}
                        className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-300"
                      >
                        {EMOTIONS.map(em => <option key={em} value={em}>{em}</option>)}
                      </select>
                    </div>
                    <textarea
                      value={d.text}
                      onChange={e => {
                        const updated = [...editDialogue]
                        updated[i] = { ...d, text: e.target.value }
                        setEditDialogue(updated)
                      }}
                      rows={2}
                      className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 resize-none"
                    />
                  </div>
                ) : (
                  <>
                    <div className="flex items-center gap-2 mb-1">
                      {d.character_id ? (
                        <span className="text-xs font-semibold text-indigo-400">{d.character_id}</span>
                      ) : (
                        <span className="text-xs text-gray-600">Narrator</span>
                      )}
                      <span className="text-[10px] bg-gray-800 px-1.5 py-0.5 rounded text-gray-500">{d.emotion}</span>
                    </div>
                    <p className="text-gray-300">{d.text}</p>
                  </>
                )}
              </div>
            ))}
          </div>

          {/* Branches */}
          {scene.branches.length > 0 && (
            <div className="mt-4 p-3 bg-indigo-950/30 border border-indigo-800/30 rounded-lg">
              <p className="text-xs text-indigo-400 font-semibold mb-2">Player Choices:</p>
              {scene.branches.map((b, i) => (
                <div key={i} className="flex items-center gap-2 text-sm text-gray-300 py-1">
                  <span className="text-indigo-500">&rarr;</span>
                  <span>{b.text}</span>
                  <span className="text-[10px] text-gray-600">({b.next_scene_id})</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      {step === 'script_review' && (
        <div className="flex flex-wrap gap-2 p-4 border-t border-gray-800">
          <button
            onClick={() => useStore.getState().confirmScript()}
            className="px-5 py-2 bg-green-600 hover:bg-green-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Confirm & Continue
          </button>
          <button
            onClick={() => useStore.getState().confirmSetting()}
            className="px-5 py-2 bg-yellow-600 hover:bg-yellow-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Regenerate Script
          </button>
          <button
            onClick={() => useStore.getState().toggleVNPreview()}
            className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors"
          >
            Preview VN
          </button>
          <button
            onClick={exportJSON}
            className="px-5 py-2 bg-gray-700 hover:bg-gray-600 text-gray-200 text-sm font-medium rounded-lg transition-colors"
          >
            Export JSON
          </button>
          <button
            onClick={() => useStore.setState({ step: 'setting_review' })}
            className="px-5 py-2 bg-gray-800 hover:bg-gray-700 text-gray-400 text-sm rounded-lg transition-colors"
          >
            Back to Setting
          </button>
        </div>
      )}
    </div>
  )
}
