import { useState } from 'react'
import ChatPanel from '../components/ChatPanel'
import PreviewPanel from '../components/PreviewPanel'
import JobHistory from '../components/JobHistory'
import StatusBar from '../components/StatusBar'

/** v4 P6 workbench. Task 7 stands the shell up rendering exactly what
 *  LegacyShell renders, so the variant switch itself is provably a no-op;
 *  Task 13 swaps the main region for the form-driven panes. */
export default function WorkbenchShell() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

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
          <div
            className="h-1/2 md:h-auto md:w-1/2 border-b md:border-b-0 md:border-r flex flex-col"
            style={{ borderColor: 'var(--rule)' }}
          >
            <ChatPanel />
          </div>
          <div className="h-1/2 md:h-auto md:w-1/2 overflow-y-auto custom-scrollbar">
            <PreviewPanel />
          </div>
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
