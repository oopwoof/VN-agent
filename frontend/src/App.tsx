import ChatPanel from './components/ChatPanel'
import PreviewPanel from './components/PreviewPanel'
import JobHistory from './components/JobHistory'
import StatusBar from './components/StatusBar'

export default function App() {
  return (
    <div className="flex h-screen bg-gray-950 text-gray-100 overflow-hidden">
      {/* Sidebar */}
      <aside className="w-64 bg-gray-900 border-r border-gray-800 shrink-0 flex flex-col">
        <JobHistory />
      </aside>

      {/* Main area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex-1 flex overflow-hidden">
          {/* Left: Chat */}
          <div className="w-1/2 border-r border-gray-800 flex flex-col">
            <ChatPanel />
          </div>
          {/* Right: Preview */}
          <div className="w-1/2 overflow-y-auto custom-scrollbar">
            <PreviewPanel />
          </div>
        </div>
        <StatusBar />
      </div>
    </div>
  )
}
