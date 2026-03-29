import { useState, useRef } from 'react'
import useStore from '../store'
import api from '../api'
import type { AssetEntry } from '../types'

type Tab = 'backgrounds' | 'characters' | 'bgm'

function AssetCard({ asset, onUpload, type }: { asset: AssetEntry; onUpload: (file: File) => void; type: Tab }) {
  const [dragOver, setDragOver] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const audioRef = useRef<HTMLAudioElement>(null)
  const [playing, setPlaying] = useState(false)

  const handleFile = (file: File) => {
    const maxSize = type === 'bgm' ? 10 * 1024 * 1024 : 5 * 1024 * 1024
    if (file.size > maxSize) { alert(`File too large (max ${maxSize / 1024 / 1024}MB)`); return }
    onUpload(file)
  }

  const label = type === 'backgrounds' ? (asset.id || '') :
    type === 'characters' ? `${asset.char_id}/${asset.emotion}` :
    (asset.mood || '')

  return (
    <div
      className={`relative bg-gray-900 border rounded-lg overflow-hidden transition-colors ${
        dragOver ? 'border-indigo-500 bg-indigo-950/20' : 'border-gray-800'
      }`}
      onDragOver={e => { e.preventDefault(); setDragOver(true) }}
      onDragLeave={() => setDragOver(false)}
      onDrop={e => { e.preventDefault(); setDragOver(false); if (e.dataTransfer.files[0]) handleFile(e.dataTransfer.files[0]) }}
      onClick={() => inputRef.current?.click()}
    >
      <input ref={inputRef} type="file" className="hidden"
        accept={type === 'bgm' ? '.ogg,.mp3,.wav' : '.png,.jpg,.webp'}
        onChange={e => { if (e.target.files?.[0]) handleFile(e.target.files[0]) }} />

      {/* Preview */}
      {type !== 'bgm' ? (
        <div className="aspect-video bg-gray-950 flex items-center justify-center">
          {asset.is_placeholder ? (
            <span className="text-gray-700 text-xs">No image</span>
          ) : (
            <img src={asset.url} alt={label} className="w-full h-full object-cover" />
          )}
        </div>
      ) : (
        <div className="p-3 flex items-center gap-3">
          <audio ref={audioRef} src={asset.url} onEnded={() => setPlaying(false)} />
          <button
            onClick={e => { e.stopPropagation(); playing ? audioRef.current?.pause() : audioRef.current?.play(); setPlaying(!playing) }}
            className="w-8 h-8 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white flex items-center justify-center text-xs"
          >
            {playing ? '\u23F8' : '\u25B6'}
          </button>
          <span className="text-sm text-gray-300">{label}</span>
        </div>
      )}

      {/* Label */}
      <div className="px-3 py-2 flex items-center justify-between">
        <span className="text-xs text-gray-400 truncate">{label}</span>
        {asset.is_placeholder && (
          <span className="text-[9px] bg-yellow-900/50 text-yellow-400 px-1.5 py-0.5 rounded">placeholder</span>
        )}
      </div>

      {/* Drag overlay */}
      {dragOver && (
        <div className="absolute inset-0 bg-indigo-600/20 flex items-center justify-center">
          <span className="text-indigo-300 text-sm font-medium">Drop to upload</span>
        </div>
      )}
    </div>
  )
}

export default function AssetPanel() {
  const { assets, currentJobId, uploadAsset, recompile, step } = useStore()
  const [tab, setTab] = useState<Tab>('backgrounds')

  if (!assets || !currentJobId) return null

  const handleUpload = (assetType: string, assetId: string) => (file: File) => {
    uploadAsset(file, assetType, assetId)
  }

  const tabs: { key: Tab; label: string; count: number }[] = [
    { key: 'backgrounds', label: 'Backgrounds', count: assets.backgrounds.length },
    { key: 'characters', label: 'Characters', count: assets.characters.length },
    { key: 'bgm', label: 'BGM', count: assets.bgm.length },
  ]

  return (
    <div className="flex flex-col h-full">
      {/* Tabs */}
      <div className="flex gap-1 px-3 py-2 border-b border-gray-800">
        {tabs.map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-1.5 rounded text-xs transition-colors ${
              tab === t.key ? 'bg-indigo-600 text-white' : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
            }`}>
            {t.label} ({t.count})
          </button>
        ))}
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        <p className="text-[10px] text-gray-600 mb-3">Click or drag-drop to upload replacements</p>
        <div className={`grid gap-3 ${tab === 'bgm' ? 'grid-cols-1' : 'grid-cols-2'}`}>
          {tab === 'backgrounds' && assets.backgrounds.map(a => (
            <AssetCard key={a.id} asset={a} type="backgrounds" onUpload={handleUpload('background', a.id || '')} />
          ))}
          {tab === 'characters' && assets.characters.map(a => (
            <AssetCard key={`${a.char_id}/${a.emotion}`} asset={a} type="characters"
              onUpload={handleUpload('character_sprite', `${a.char_id}/${a.emotion}`)} />
          ))}
          {tab === 'bgm' && assets.bgm.map(a => (
            <AssetCard key={a.mood} asset={a} type="bgm" onUpload={handleUpload('bgm', a.mood || '')} />
          ))}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3 p-4 border-t border-gray-800">
        {(step === 'asset_management' || step === 'completed') && (
          <>
            <button onClick={recompile}
              className="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium rounded-lg transition-colors">
              Re-compile & Download
            </button>
            <a href={api.downloadUrl(currentJobId)}
              className="px-5 py-2 bg-green-600 hover:bg-green-500 text-white text-sm font-medium rounded-lg transition-colors">
              Download ZIP
            </a>
          </>
        )}
      </div>
    </div>
  )
}
