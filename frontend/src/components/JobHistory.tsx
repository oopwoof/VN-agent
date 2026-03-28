import { useEffect } from 'react'
import useStore from '../store'

const BADGE: Record<string, string> = {
  pending: 'bg-gray-700 text-gray-400',
  running: 'bg-blue-900/50 text-blue-400',
  completed: 'bg-green-900/50 text-green-400',
  failed: 'bg-red-900/50 text-red-400',
}

export default function JobHistory() {
  const { jobs, refreshJobs, selectJob, deleteJob, currentJobId } = useStore()

  useEffect(() => { refreshJobs() }, [refreshJobs])

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b border-gray-800">
        <h1 className="text-lg font-bold text-indigo-400">VN-Agent Studio</h1>
        <p className="text-[10px] text-gray-500 mt-0.5">AI Visual Novel Generator</p>
      </div>
      <div className="px-3 pt-3">
        <h2 className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-2">History</h2>
      </div>
      <div className="flex-1 overflow-y-auto px-3 space-y-1 custom-scrollbar">
        {jobs.length === 0 && <p className="text-xs text-gray-700 px-2">No jobs yet</p>}
        {jobs.map(j => (
          <div
            key={j.job_id}
            onClick={() => selectJob(j.job_id)}
            className={`p-2 rounded-md cursor-pointer transition-colors text-xs
              ${currentJobId === j.job_id ? 'bg-indigo-950 border-l-2 border-indigo-500' : 'hover:bg-gray-800'}`}
          >
            <div className="flex items-center justify-between">
              <span className="font-mono text-gray-500">{j.job_id}</span>
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-semibold uppercase ${BADGE[j.status] || ''}`}>
                {j.status}
              </span>
            </div>
            <p className="text-gray-400 mt-1 truncate">{j.theme}</p>
            <div className="flex justify-between mt-1">
              <span className="text-[10px] text-gray-600">
                {j.created_at ? new Date(j.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
              </span>
              <button
                onClick={e => { e.stopPropagation(); deleteJob(j.job_id) }}
                className="text-[10px] text-gray-600 hover:text-red-400"
              >
                delete
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
