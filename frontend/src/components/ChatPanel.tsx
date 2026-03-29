import { useRef, useEffect, useState } from 'react'
import useStore from '../store'

function TypewriterText({ text }: { text: string }) {
  const [displayed, setDisplayed] = useState('')
  useEffect(() => {
    setDisplayed('')
    let i = 0
    const timer = setInterval(() => {
      i++
      setDisplayed(text.slice(0, i))
      if (i >= text.length) clearInterval(timer)
    }, 15)
    return () => clearInterval(timer)
  }, [text])
  return <>{displayed}</>
}

export default function ChatPanel() {
  const { messages, config, setConfig, step } = useStore()
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const busy = step === 'generating_setting' || step === 'generating_script' || step === 'compiling'

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])

  const handleSend = () => {
    if (!input.trim() || busy) return
    setConfig({ theme: input.trim() })
    setInput('')
    setTimeout(() => useStore.getState().generate(), 50)
  }

  return (
    <div className="flex flex-col h-full">
      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3 custom-scrollbar">
        {messages.map((m, i) => (
          <div key={i} className={`flex ${m.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div className={`max-w-[85%] px-4 py-2 rounded-2xl text-sm leading-relaxed ${
              m.role === 'user'
                ? 'bg-indigo-600 text-white rounded-br-md'
                : 'bg-gray-800 text-gray-200 rounded-bl-md'
            }`}>
              {m.role === 'system' && i === messages.length - 1 ? (
                <TypewriterText text={m.content} />
              ) : (
                m.content
              )}
            </div>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>

      {/* Error retry */}
      {step === 'failed' && (
        <div className="px-4 py-2 border-t border-red-900/50 bg-red-950/20">
          <button onClick={() => useStore.getState().generate()}
            className="text-xs text-red-400 hover:text-red-300 underline">
            Retry generation
          </button>
        </div>
      )}

      {/* Config */}
      <details className="px-4 py-2 border-t border-gray-800">
        <summary className="text-xs text-gray-500 cursor-pointer select-none">Settings</summary>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-2 text-xs">
          <label className="text-gray-400">
            Scenes: <span className="text-indigo-400">{config.max_scenes}</span>
            <input type="range" min={2} max={20} value={config.max_scenes}
              onChange={e => setConfig({ max_scenes: +e.target.value })}
              className="w-full accent-indigo-500" />
          </label>
          <label className="text-gray-400">
            Characters: <span className="text-indigo-400">{config.num_characters}</span>
            <input type="range" min={1} max={8} value={config.num_characters}
              onChange={e => setConfig({ num_characters: +e.target.value })}
              className="w-full accent-indigo-500" />
          </label>
          <label className="flex items-center gap-2 text-gray-400">
            <input type="checkbox" checked={config.text_only}
              onChange={e => setConfig({ text_only: e.target.checked })}
              className="accent-indigo-500" />
            Text Only
          </label>
          <label className="flex items-center gap-2 text-gray-400">
            <input type="checkbox" checked={config.fast_mode}
              onChange={e => setConfig({ fast_mode: e.target.checked })}
              className="accent-indigo-500" />
            Fast Mode
          </label>
        </div>
      </details>

      {/* Input */}
      <div className="p-3 border-t border-gray-800">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder="Enter your story theme..."
            disabled={busy}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
              text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2
              focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || busy}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium
              rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy ? '...' : 'Send'}
          </button>
        </div>
      </div>
    </div>
  )
}
