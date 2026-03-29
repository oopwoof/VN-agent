import { useState } from 'react'
import useStore from '../store'
import api from '../api'

interface Character {
  id?: string; name?: string; role?: string; personality?: string; background?: string; color?: string
}
interface Scene {
  id?: string; title?: string; description?: string; narrative_strategy?: string | null
}

export default function SettingPanel() {
  const { blackboard, confirmSetting, regenerateSetting, step, currentJobId } = useStore()
  const ws = (blackboard.world_setting || {}) as Record<string, string>
  const chars = (blackboard.characters || {}) as Record<string, Character>
  const outline = (blackboard.plot_outline || {}) as { scenes?: Scene[]; start_scene_id?: string }
  const scenes = outline.scenes || []
  const [editing, setEditing] = useState(false)
  const [editTitle, setEditTitle] = useState(ws.title || '')
  const [editDesc, setEditDesc] = useState(ws.description || '')
  const [editChars, setEditChars] = useState(chars)

  const startEdit = () => {
    setEditTitle(ws.title || '')
    setEditDesc(ws.description || '')
    setEditChars({ ...chars })
    setEditing(true)
  }

  const saveEdit = async () => {
    if (!currentJobId) return
    try {
      await api.updateSetting(currentJobId, {
        world_setting: { ...ws, title: editTitle, description: editDesc },
        characters: editChars,
      })
      // Update local state
      useStore.setState({
        blackboard: {
          ...blackboard,
          world_setting: { ...ws, title: editTitle, description: editDesc },
          characters: editChars,
        },
      })
      setEditing(false)
    } catch (e) {
      alert(`Save failed: ${e}`)
    }
  }

  const updateChar = (id: string, field: string, value: string) => {
    setEditChars({ ...editChars, [id]: { ...editChars[id], [field]: value } })
  }

  return (
    <div className="p-6 space-y-6">
      {/* World Setting */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-sm font-semibold text-indigo-400 uppercase tracking-wider">World Setting</h3>
          {step === 'setting_review' && !editing && (
            <button onClick={startEdit} className="text-xs text-indigo-400 hover:text-indigo-300">Edit</button>
          )}
          {editing && (
            <div className="flex gap-2">
              <button onClick={saveEdit} className="text-xs text-green-400 hover:text-green-300">Save</button>
              <button onClick={() => setEditing(false)} className="text-xs text-gray-500 hover:text-gray-400">Cancel</button>
            </div>
          )}
        </div>
        {editing ? (
          <div className="space-y-2">
            <input value={editTitle} onChange={e => setEditTitle(e.target.value)}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200" placeholder="Title" />
            <textarea value={editDesc} onChange={e => setEditDesc(e.target.value)} rows={2}
              className="w-full bg-gray-800 border border-gray-700 rounded px-3 py-2 text-sm text-gray-200 resize-none" placeholder="Description" />
          </div>
        ) : (
          <div className="space-y-2 text-sm">
            <div><span className="text-gray-500">Title: </span><span className="text-gray-200 font-medium">{ws.title || '—'}</span></div>
            <div><span className="text-gray-500">Description: </span><span className="text-gray-300">{ws.description || '—'}</span></div>
          </div>
        )}
      </div>

      {/* Characters */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <h3 className="text-sm font-semibold text-indigo-400 uppercase tracking-wider mb-3">Characters ({Object.keys(chars).length})</h3>
        <div className="space-y-3">
          {Object.entries(editing ? editChars : chars).map(([id, c]) => (
            <div key={id} className="bg-gray-950 rounded-md p-3 border border-gray-800">
              {editing ? (
                <div className="grid grid-cols-2 gap-2 text-xs">
                  <input value={c.name || ''} onChange={e => updateChar(id, 'name', e.target.value)}
                    className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-200" placeholder="Name" />
                  <input value={c.role || ''} onChange={e => updateChar(id, 'role', e.target.value)}
                    className="bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-200" placeholder="Role" />
                  <input value={c.personality || ''} onChange={e => updateChar(id, 'personality', e.target.value)}
                    className="col-span-2 bg-gray-800 border border-gray-700 rounded px-2 py-1 text-gray-200" placeholder="Personality" />
                </div>
              ) : (
                <>
                  <div className="flex items-center gap-2 mb-1">
                    <div className="w-3 h-3 rounded-full" style={{ backgroundColor: c.color || '#6366f1' }} />
                    <span className="font-medium text-sm text-gray-200">{c.name || id}</span>
                    <span className="text-[10px] text-gray-500 bg-gray-800 px-1.5 py-0.5 rounded">{c.role || '—'}</span>
                  </div>
                  <p className="text-xs text-gray-400">{c.personality || ''}</p>
                  {c.background && <p className="text-xs text-gray-500 mt-1">{c.background}</p>}
                </>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Plot Outline */}
      <div className="bg-gray-900 border border-gray-800 rounded-lg p-5">
        <h3 className="text-sm font-semibold text-indigo-400 uppercase tracking-wider mb-3">Plot Outline ({scenes.length} scenes)</h3>
        <div className="space-y-2">
          {scenes.map((s, i) => (
            <div key={s.id || i} className="flex gap-3 text-xs">
              <div className="flex flex-col items-center">
                <div className="w-2 h-2 rounded-full bg-indigo-500 mt-1.5" />
                {i < scenes.length - 1 && <div className="w-px flex-1 bg-gray-700" />}
              </div>
              <div className="pb-3">
                <div className="font-medium text-gray-200">{s.title || s.id}</div>
                <div className="text-gray-400">{s.description}</div>
                {s.narrative_strategy && (
                  <span className="text-[10px] text-indigo-400 bg-indigo-950 px-1.5 py-0.5 rounded mt-1 inline-block">{s.narrative_strategy}</span>
                )}
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Actions */}
      {step === 'setting_review' && !editing && (
        <div className="flex gap-3">
          <button onClick={confirmSetting}
            className="px-6 py-2.5 bg-green-600 hover:bg-green-500 text-white font-medium rounded-lg transition-colors">
            Confirm & Generate Script
          </button>
          <button onClick={regenerateSetting}
            className="px-6 py-2.5 bg-gray-700 hover:bg-gray-600 text-gray-200 font-medium rounded-lg transition-colors">
            Regenerate
          </button>
        </div>
      )}
    </div>
  )
}
