import { useState } from 'react'
import ChatPanel from './components/ChatPanel'
import PreviewPanel from './components/PreviewPanel'
import JobHistory from './components/JobHistory'
import StatusBar from './components/StatusBar'

export default function App() {
  const [sidebarOpen, setSidebarOpen] = useState(false)

  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 overflow-hidden">
      {/* Mobile sidebar toggle */}
      <button
        onClick={() => setSidebarOpen(!sidebarOpen)}
        className="md:hidden fixed top-3 left-3 z-50 p-2 bg-gray-800 rounded-lg text-gray-400"
      >
        {sidebarOpen ? '\u2715' : '\u2630'}
      </button>

      {/* Sidebar */}
      <aside className={`
        ${sidebarOpen ? 'translate-x-0' : '-translate-x-full'}
        md:translate-x-0 fixed md:static z-40
        w-64 bg-gray-900 border-r border-gray-800 shrink-0 flex flex-col h-full
        transition-transform duration-200
      `}>
        <JobHistory />
      </aside>

      {/* Overlay for mobile sidebar */}
      {sidebarOpen && (
        <div className="md:hidden fixed inset-0 z-30 bg-black/50" onClick={() => setSidebarOpen(false)} />
      )}

      {/* Main area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 flex flex-col md:flex-row overflow-hidden">
          {/* Left: Chat */}
          <div className="h-1/2 md:h-auto md:w-1/2 border-b md:border-b-0 md:border-r border-gray-800 flex flex-col">
            <ChatPanel />
          </div>
          {/* Right: Preview */}
          <div className="h-1/2 md:h-auto md:w-1/2 overflow-y-auto custom-scrollbar">
            <PreviewPanel />
          </div>
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
