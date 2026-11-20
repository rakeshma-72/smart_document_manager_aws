import React from 'react'
import { CheckCircle2, Clock, AlertTriangle, Loader2 } from 'lucide-react'

const PIPELINE_STEPS = [
  { key: 'validate', label: 'Validate File' },
  { key: 'extract', label: 'Extract Text' },
  { key: 'summarize', label: 'AI Summary & Classification' },
  { key: 'detect_pii', label: 'Detect PII' },
  { key: 'save_results', label: 'Save Results' },
  { key: 'chunk_text', label: 'Chunk Text' },
  { key: 'embed_chunks', label: 'Embeddings (Titan V2)' },
]

export default function PipelineTracker({ currentStep, stepStatus = {}, status, errorCode, failedStep, createdAt, updatedAt }) {
  const isFailed = status === 'FAILED'
  const isProcessed = status === 'PROCESSED'

  // Calculate elapsed seconds between createdAt and updatedAt
  const getElapsedSeconds = () => {
    if (!createdAt) return null
    const start = new Date(createdAt).getTime()
    const end = updatedAt ? new Date(updatedAt).getTime() : Date.now()
    const secs = Math.max(0, Math.round((end - start) / 1000))
    return secs
  }

  const elapsed = getElapsedSeconds()

  return (
    <div className="bg-slate-950/70 border border-slate-800 rounded-xl p-4">
      <div className="flex items-center justify-between mb-3 border-b border-slate-800 pb-2">
        <div className="flex items-center space-x-2">
          <Clock className="w-4 h-4 text-indigo-400" />
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Pipeline Execution Tracker
          </h4>
        </div>
        {elapsed !== null && (
          <span className="text-[11px] font-mono text-slate-400">
            Duration: {elapsed}s
          </span>
        )}
      </div>

      <div className="relative pl-4 space-y-4 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-800">
        {PIPELINE_STEPS.map((step, idx) => {
          const stepInfo = stepStatus[step.key]
          const isCurrent = currentStep === step.key && !isProcessed && !isFailed
          const isStepFailed = isFailed && (failedStep === step.key || currentStep === step.key)
          const isDone = isProcessed || (stepInfo && stepInfo.status === 'COMPLETED')

          let icon = <div className="w-2.5 h-2.5 rounded-full bg-slate-700" />
          let textColor = 'text-slate-500'
          let statusLabel = 'Pending'

          if (isStepFailed) {
            icon = <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
            textColor = 'text-rose-400 font-semibold'
            statusLabel = `Failed (${errorCode || 'Error'})`
          } else if (isDone) {
            icon = <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
            textColor = 'text-slate-200'
            statusLabel = 'Completed'
          } else if (isCurrent) {
            icon = <Loader2 className="w-4 h-4 text-indigo-400 animate-spin shrink-0" />
            textColor = 'text-indigo-300 font-semibold'
            statusLabel = 'Processing...'
          }

          return (
            <div key={step.key} className="relative flex items-start space-x-3 text-xs">
              <div className="absolute -left-4 mt-0.5 flex items-center justify-center bg-slate-950 ring-4 ring-slate-950">
                {icon}
              </div>
              <div className="flex-1 flex items-center justify-between">
                <span className={textColor}>{step.label}</span>
                <span className="text-[10px] font-mono text-slate-500">
                  {stepInfo?.timestamp ? new Date(stepInfo.timestamp).toLocaleTimeString() : statusLabel}
                </span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
