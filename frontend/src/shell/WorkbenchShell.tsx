import { useState } from 'react'
import { AnimatePresence, motion } from 'framer-motion'
import ChatPanel from '../components/ChatPanel'
import JobHistory from '../components/JobHistory'
import StatusBar from '../components/StatusBar'
import PipelineStage from '../components/PipelineStage'
import StoryboardBoard from '../components/StoryboardBoard'
import SettingPanel from '../components/SettingPanel'
import AssetPanel from '../components/AssetPanel'
import VNPreview from '../components/VNPreview'
import useStore from '../store'
import { useT } from '../i18n/useT'

type Form = 'player' | 'pipeline' | 'setting' | 'assets' | 'failed' | 'board'

/** Workbench form follows AppStep — see FRONTEND_REDESIGN_v4.md §2.
 *  vnPreview wins over everything so Autopilot's zero-click path into the
 *  player is unaffected. */
function resolveForm(step: string, vnPreview: boolean): Form {
  if (vnPreview) return 'player'
  if (step === 'generating_setting' || step === 'generating_script' || step === 'compiling') return 'pipeline'
  // SettingPanel owns the only Confirm & Generate Script / Regenerate
  // buttons — routing this step anywhere else breaks the non-fast-mode flow.
  if (step === 'setting_review') return 'setting'
  if (step === 'asset_management' || step === 'completed') return 'assets'
  if (step === 'failed') return 'failed'
  return 'board'
}

// The chat column is not a fixed half. A constant 50/50 split is exactly what
// made the old shell read as a generic template; here the workbench yields
// space to whatever the current form is actually about.
const CHAT_WIDTH: Record<Form, string> = {
  player: '0',       // full-bleed artifact, workbench out of the way
  pipeline: '20rem', // narrow — the stage is the subject
  setting: '24rem',
  assets: '24rem',
  failed: '24rem',
  board: '24rem',
}

export default function WorkbenchShell() {
  const t = useT()
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const step = useStore(s => s.step)
  const vnPreview = useStore(s => s.vnPreview)
  const errors = useStore(s => s.errors)

  const form = resolveForm(step, vnPreview)

  const main =
    form === 'player' ? <VNPreview />
    : form === 'pipeline' ? <PipelineStage />
    : form === 'setting' ? <SettingPanel />
    : form === 'assets' ? <AssetPanel />
    : form === 'failed' ? (
      <div className="p-6">
        <div className="rounded-lg border p-5" style={{ background: 'var(--surface)', borderColor: 'var(--crit)' }}>
          <p className="face-instrument text-sm mb-3" style={{ color: 'var(--crit)' }}>{t('preview.failed')}</p>
          <pre
            className="text-xs rounded p-3 overflow-x-auto whitespace-pre-wrap"
            style={{ background: 'var(--ground)', color: 'var(--ink-soft)' }}
          >
            {errors.join('\n') || t('preview.unknownError')}
          </pre>
        </div>
      </div>
    ) : <StoryboardBoard />

  return (
    <div className="flex h-screen overflow-hidden" style={{ background: 'var(--ground)', color: 'var(--ink)' }}>
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="md:hidden fixed top-3 left-3 z-50 p-2 rounded-lg
          focus-visible:outline focus-visible:outline-2"
        style={{ background: 'var(--surface-raised)', color: 'var(--ink-soft)' }}
      >
        {sidebarOpen ? '✕' : '☰'}
      </button>

      <aside
        className={`${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
          md:translate-x-0 fixed md:static z-40 w-64 shrink-0 flex flex-col h-full
          border-r transition-transform duration-200`}
        style={{ background: 'var(--surface)', borderColor: 'var(--rule)' }}
      >
        <JobHistory />
      </aside>

      {sidebarOpen && (
        <div className="md:hidden fixed inset-0 z-30 bg-black/50" onClick={() => setSidebarOpen(false)} />
      )}

      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Chat column — width follows the form; fully collapsed in player */}
          <div
            className="flex flex-col overflow-hidden border-b md:border-b-0 md:border-r
              transition-[width] duration-300 shrink-0"
            style={{
              borderColor: 'var(--rule)',
              width: CHAT_WIDTH[form],
              display: form === 'player' ? 'none' : undefined,
            }}
          >
            <ChatPanel />
          </div>

          {/* Main region — cross-dissolve between forms */}
          <div className="flex-1 overflow-y-auto custom-scrollbar relative">
            <AnimatePresence mode="wait" initial={false}>
              <motion.div
                key={form}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
                transition={{ duration: 0.25 }}
                className="h-full"
              >
                {main}
              </motion.div>
            </AnimatePresence>
          </div>
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
