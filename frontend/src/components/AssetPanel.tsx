import { useState, useRef } from 'react'
import useStore from '../store'
import api, { type UploadResult } from '../api'
import type { AssetEntry } from '../types'

type Tab = 'backgrounds' | 'characters' | 'bgm' | 'world_docs'

// v4 P0-7: text-upload license options — labels the creator picks from
// so the export gate (P0-4) can trust the metadata later. Matches the
// backend whitelist in assets/license_gate.py.
const _LICENSE_OPTIONS: { value: string; label: string }[] = [
  { value: 'user_owned', label: '我自己写的（user_owned）' },
  { value: 'CC0', label: 'CC0 / 公共领域' },
  { value: 'CC-BY', label: 'CC-BY 署名' },
  { value: 'CC-BY-SA', label: 'CC-BY-SA 相同方式共享' },
]

const _TEXT_ACCEPT = '.md,.txt,.markdown,.pdf,.docx'

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

// v4 P0-7: dedicated pane for creator-uploaded world-building docs (md/pdf/docx).
// Persists to data/uploads/{job_id}/uploads.jsonl on the backend and joins the
// FAISS RAG pool the next time Writer runs.
function WorldDocsPane({ jobId }: { jobId: string }) {
  const [license, setLicense] = useState<string>('user_owned')
  const [dragOver, setDragOver] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [lastResult, setLastResult] = useState<UploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  const doUpload = async (file: File) => {
    setError(null)
    if (file.size > 20 * 1024 * 1024) {
      setError('文件超过 20 MB — 请拆分或压缩')
      return
    }
    // Backend expects an asset_id token — derive one from the filename
    // (server further normalizes it, so a raw stem is fine here).
    const stem = file.name.replace(/\.[^.]+$/, '') || 'doc'
    const assetId = `text_${Date.now()}_${stem}`.replace(/[^\w.-]/g, '_').slice(0, 60)
    setUploading(true)
    try {
      const res = await api.uploadAsset(jobId, file, 'text', assetId, license)
      setLastResult(res)
    } catch (e) {
      setError(String(e))
    } finally {
      setUploading(false)
    }
  }

  const summary = lastResult?.summary
  const totalChunks = summary?.chunks ?? 0
  const files = summary?.files ?? []
  const sources = Object.entries(summary?.by_source ?? {})
  const licenses = Object.entries(summary?.by_license ?? {})

  return (
    <div className="flex flex-col gap-4">
      <div className="text-[11px] text-gray-500 leading-relaxed">
        上传世界观 / 角色设定 / 参考文档，会被自动切块并进入 RAG，下一次生成时 Writer 可以引用。
        支持 md / txt / pdf / docx，最大 20 MB。中英文均自动分块（CJK 密度触发中文分块设置）。
      </div>

      <div className="flex items-center gap-2">
        <label className="text-xs text-gray-400 whitespace-nowrap">授权声明</label>
        <select
          value={license}
          onChange={e => setLicense(e.target.value)}
          className="flex-1 bg-gray-900 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200"
        >
          {_LICENSE_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      <div
        className={`relative rounded-lg border-2 border-dashed transition-colors p-8 text-center cursor-pointer ${
          dragOver ? 'border-indigo-500 bg-indigo-950/20' : 'border-gray-700 bg-gray-900/60 hover:border-gray-500'
        }`}
        onDragOver={e => { e.preventDefault(); setDragOver(true) }}
        onDragLeave={() => setDragOver(false)}
        onDrop={e => {
          e.preventDefault()
          setDragOver(false)
          const f = e.dataTransfer.files[0]
          if (f) doUpload(f)
        }}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          className="hidden"
          accept={_TEXT_ACCEPT}
          onChange={e => { const f = e.target.files?.[0]; if (f) doUpload(f) }}
        />
        {uploading ? (
          <div className="text-sm text-indigo-300">正在切块 + 嵌入…</div>
        ) : (
          <>
            <div className="text-sm text-gray-300">拖拽文件到这里，或点击选择</div>
            <div className="text-[10px] text-gray-500 mt-2">{_TEXT_ACCEPT}</div>
          </>
        )}
      </div>

      {error && (
        <div className="rounded border border-red-900 bg-red-950/40 px-3 py-2 text-xs text-red-300">
          上传失败：{error}
        </div>
      )}

      {lastResult && (
        <div className="rounded border border-emerald-900 bg-emerald-950/40 px-3 py-2 text-xs text-emerald-200">
          最近上传：
          <span className="ml-1 text-emerald-100">{lastResult.asset_id}</span>
          — 切块 {lastResult.chunks ?? '?'} 个
          {lastResult.cjk_dominant ? '（中文分块）' : '（英文分块）'}
        </div>
      )}

      {summary && (
        <div className="rounded border border-gray-800 bg-gray-900/60 p-3 space-y-2">
          <div className="text-xs text-gray-400">当前 job 累积</div>
          <div className="text-sm text-gray-100">
            共 <span className="text-indigo-300">{totalChunks}</span> 块，来自 {files.length} 个来源
          </div>
          {sources.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {sources.map(([src, n]) => (
                <span key={src} className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-950/50 text-indigo-300">
                  {src} · {n}
                </span>
              ))}
              {licenses.map(([lic, n]) => (
                <span key={lic} className="text-[10px] px-1.5 py-0.5 rounded bg-amber-950/50 text-amber-300">
                  {lic} · {n}
                </span>
              ))}
            </div>
          )}
          {files.length > 0 && (
            <ul className="text-[11px] text-gray-500 space-y-0.5 max-h-32 overflow-y-auto">
              {files.map(f => <li key={f} className="truncate">• {f}</li>)}
            </ul>
          )}
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

  const tabs: { key: Tab; label: string; count?: number }[] = [
    { key: 'backgrounds', label: 'Backgrounds', count: assets.backgrounds.length },
    { key: 'characters', label: 'Characters', count: assets.characters.length },
    { key: 'bgm', label: 'BGM', count: assets.bgm.length },
    // v4 P0-7: text uploads live in their own tab because they don't have
    // per-slot placeholders like image/audio assets — they're a stream of
    // creator-provided reference material, counted at the job level.
    { key: 'world_docs', label: 'World Docs' },
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
            {t.label}{t.count !== undefined ? ` (${t.count})` : ''}
          </button>
        ))}
      </div>

      {/* Grid */}
      <div className="flex-1 overflow-y-auto p-4 custom-scrollbar">
        {tab === 'world_docs' ? (
          <WorldDocsPane jobId={currentJobId} />
        ) : (
          <>
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
          </>
        )}
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
