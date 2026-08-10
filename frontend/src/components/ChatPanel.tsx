import { useRef, useEffect, useState } from 'react'
import useStore from '../store'
import FeedbackWidget from './FeedbackWidget'
import { useT, useTVars } from '../i18n/useT'
import type { TKey } from '../i18n/dict'
import type { ChatMessage } from '../types'

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

// v4 P3: icon per dispatchable intent. Labels come from i18n (see
// dict.ts `intent.*`) so the confirm card reads in the creator's language.
const INTENT_ICON: Record<string, string> = {
  local_regen: '✏️',
  add_character: '👤',
  edit_asset: '🖼️',
}

export default function ChatPanel() {
  const {
    messages, config, setConfig, step, currentJobId,
    pendingChatTurn, chatBusy, sendChatMessage, confirmChatTurn, cancelChatTurn, chatOpsAvailable,
  } = useStore()
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const generating = step === 'generating_setting' || step === 'generating_script' || step === 'compiling'
  const busy = generating || chatBusy
  const chatOps = chatOpsAvailable()
  const t = useT()
  const tv = useTVars()

  // v4 P6 i18n: the chat log is stored as key + variables, not as resolved
  // text, so the whole history — welcome line included — retranslates when
  // the language toggle flips. Messages carrying server prose have no `tkey`
  // and fall through to their pre-rendered `content`, as does any key the
  // dictionary no longer knows about.
  const msgText = (m: ChatMessage): string => {
    if (!m.tkey) return m.content
    return tv(m.tkey, m.tvars) ?? m.content
  }

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages, pendingChatTurn])

  const handleSend = () => {
    if (!input.trim() || busy || pendingChatTurn) return
    const message = input.trim()
    setInput('')
    if (chatOps) {
      sendChatMessage(message)
    } else {
      setConfig({ theme: message, autopilot: false })
      setTimeout(() => useStore.getState().generate(), 50)
    }
  }

  // v4 P5: one-click theme -> playable VN, no review-step clicking. The
  // "skip review steps" behavior is entirely the existing fast_mode
  // auto-chain (generate() -> confirmSetting() -> confirmScript()); this
  // only adds preset resolution (config.autopilot, applied server-side)
  // and auto-entering the player (handled in store.ts's onScene handler).
  const handleAutopilot = () => {
    if (!input.trim() || busy || pendingChatTurn) return
    const message = input.trim()
    setInput('')
    setConfig({ theme: message, autopilot: true, fast_mode: true })
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
                <TypewriterText text={msgText(m)} />
              ) : (
                msgText(m)
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
            {t('chat.retry')}
          </button>
        </div>
      )}

      {/* Config */}
      <details className="px-4 py-2 border-t border-gray-800">
        <summary className="text-xs text-gray-500 cursor-pointer select-none">{t('chat.settings')}</summary>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-2 text-xs">
          <label className="text-gray-400">
            {t('chat.scenes')}: <span className="text-indigo-400">{config.max_scenes}</span>
            <input type="range" min={2} max={20} value={config.max_scenes}
              onChange={e => setConfig({ max_scenes: +e.target.value })}
              className="w-full accent-indigo-500" />
          </label>
          <label className="text-gray-400">
            {t('chat.characters')}: <span className="text-indigo-400">{config.num_characters}</span>
            <input type="range" min={1} max={8} value={config.num_characters}
              onChange={e => setConfig({ num_characters: +e.target.value })}
              className="w-full accent-indigo-500" />
          </label>
          <label className="flex items-center gap-2 text-gray-400">
            <input type="checkbox" checked={config.text_only}
              onChange={e => setConfig({ text_only: e.target.checked })}
              className="accent-indigo-500" />
            {t('chat.textOnly')}
          </label>
          <label className="flex items-center gap-2 text-gray-400">
            <input type="checkbox" checked={config.fast_mode}
              onChange={e => setConfig({ fast_mode: e.target.checked })}
              className="accent-indigo-500" />
            {t('chat.fastMode')}
          </label>
          {/* v4 P0-7: mock toggle — routes all LLM calls to fixtures.
              Zero API cost. Recommended for dev testing + validating
              upload/library/UI flow without burning tokens. */}
          <label className="flex items-center gap-2 text-amber-300">
            <input type="checkbox" checked={config.mock}
              onChange={e => setConfig({ mock: e.target.checked })}
              className="accent-amber-500" />
            <span>{t('chat.mock')}</span>
          </label>
        </div>
        {config.mock && (
          <div className="mt-2 rounded border border-amber-900 bg-amber-950/30 px-3 py-2 text-[11px] text-amber-200">
            {t('chat.mockNotice')}
          </div>
        )}
      </details>

      {/* v4 P1-4: whole-job feedback strip. Sits above the theme input so
          creators can 👍/👎 an entire generation on their way to typing
          the next one. Scene-scoped feedback lives in VNPreview. */}
      {currentJobId && (step === 'completed' || step === 'script_review') && (
        <div className="px-3 py-2 border-t border-gray-800 flex items-center gap-2">
          <span className="text-[10px] text-gray-500 uppercase tracking-wider">{t('chat.feedback')}</span>
          <FeedbackWidget jobId={currentJobId} variant="compact" />
        </div>
      )}

      {/* v4 P3: intent-preview card — L1 safety net. Every mutating chat-ops
          intent (local_regen/add_character/edit_asset) stops here for an
          explicit confirm before anything on disk changes. Non-mutating
          intents (explain/unknown) never produce a pendingChatTurn — they
          resolve straight into a chat message. */}
      {pendingChatTurn && (
        <div className="mx-3 mb-2 rounded-lg border border-indigo-700/60 bg-indigo-950/40 p-3 space-y-2">
          <div className="flex items-center gap-2 text-xs">
            <span>{INTENT_ICON[pendingChatTurn.intent] ?? '❓'}</span>
            <span className="font-medium text-indigo-300">
              {t(`intent.${pendingChatTurn.intent}` as TKey)}
            </span>
            <span className="text-gray-500 ml-auto">
              {Math.round(pendingChatTurn.confidence * 100)}% {t('chat.confidence')}
            </span>
          </div>
          <p className="text-sm text-gray-200 leading-relaxed">{pendingChatTurn.preview_text}</p>
          <div className="flex gap-2 pt-1">
            <button
              onClick={confirmChatTurn}
              disabled={chatBusy}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-medium
                rounded-md transition-colors disabled:opacity-50"
            >
              {chatBusy ? t('chat.running') : t('chat.confirm')}
            </button>
            <button
              onClick={cancelChatTurn}
              disabled={chatBusy}
              className="px-3 py-1.5 bg-gray-800 hover:bg-gray-700 text-gray-300 text-xs rounded-md
                transition-colors disabled:opacity-50"
            >
              {t('chat.cancel')}
            </button>
          </div>
        </div>
      )}

      {/* Input */}
      <div className="p-3 border-t border-gray-800">
        <div className="flex gap-2">
          <input
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && !e.shiftKey && handleSend()}
            placeholder={chatOps ? t('chat.placeholderChatOps') : t('chat.placeholderTheme')}
            disabled={busy || !!pendingChatTurn}
            className="flex-1 bg-gray-800 border border-gray-700 rounded-lg px-4 py-2.5 text-sm
              text-gray-100 placeholder-gray-500 focus:outline-none focus:ring-2
              focus:ring-indigo-500 disabled:opacity-50"
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || busy || !!pendingChatTurn}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-medium
              rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {busy ? t('chat.sending') : t('chat.send')}
          </button>
          {/* v4 P5: Autopilot — theme in, straight into the player, no
              review-step clicking. Only shown in theme-entry mode (not
              chat-ops), same gate as the Send/theme branch above. */}
          {!chatOps && (
            <button
              onClick={handleAutopilot}
              disabled={!input.trim() || busy || !!pendingChatTurn}
              title={t('chat.autopilotHint')}
              className="px-4 py-2.5 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium
                rounded-lg transition-colors disabled:opacity-50 disabled:cursor-not-allowed whitespace-nowrap"
            >
              ⚡ {t('chat.autopilot')}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
