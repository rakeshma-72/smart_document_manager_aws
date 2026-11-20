import React, { useState } from 'react'
import {
  MessageSquare,
  Send,
  Sparkles,
  FileText,
  AlertCircle,
  HelpCircle,
  Cpu,
  Layers,
  ChevronRight,
  ExternalLink
} from 'lucide-react'
import { askQuestion } from '../lib/api'

export default function AskTab({ idToken, documents = [], onSelectDocument }) {
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)

  const handleSubmit = async (e) => {
    e.preventDefault()
    const trimmed = question.trim()
    if (!trimmed || loading) return

    if (trimmed.length > 500) {
      setError('Question exceeds maximum allowed length of 500 characters.')
      return
    }

    setLoading(true)
    setError(null)

    try {
      const data = await askQuestion(idToken, trimmed)
      setResult(data)
    } catch (err) {
      setError(err.message || 'Failed to query documents')
    } finally {
      setLoading(false)
    }
  }

  const handleSourceClick = (docId) => {
    const doc = documents.find(d => d.docId === docId)
    if (doc && onSelectDocument) {
      onSelectDocument(doc)
    }
  }

  return (
    <div className="space-y-6">
      {/* Ask Header Card */}
      <div className="bg-gradient-to-br from-indigo-950/40 via-slate-900 to-slate-950 border border-indigo-900/40 rounded-2xl p-6 shadow-xl">
        <div className="flex items-center space-x-3 mb-2">
          <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <MessageSquare className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-xl font-bold text-white flex items-center space-x-2">
              <span>Ask Your Documents</span>
              <span className="text-xs font-semibold px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                RAG Powered
              </span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Ask natural language questions across your processed document library. Queries are matched using vector embeddings and synthesized with AI.
            </p>
          </div>
        </div>

        {/* Question Form */}
        <form onSubmit={handleSubmit} className="mt-5">
          <div className="relative">
            <textarea
              rows={3}
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What are the main requirements mentioned in my documents? (Max 500 characters)"
              maxLength={500}
              className="w-full bg-slate-950/70 border border-slate-700/80 rounded-xl px-4 py-3 text-sm text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 resize-none transition"
            />
            <div className="absolute right-3 bottom-3 flex items-center space-x-3">
              <span className={`text-[11px] font-mono ${question.length > 450 ? 'text-amber-400' : 'text-slate-500'}`}>
                {question.length}/500
              </span>
              <button
                type="submit"
                disabled={loading || !question.trim()}
                className="flex items-center space-x-1.5 px-4 py-2 bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:hover:bg-indigo-600 text-white text-xs font-semibold rounded-lg shadow-md transition"
              >
                {loading ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    <span>Searching...</span>
                  </>
                ) : (
                  <>
                    <Send className="w-3.5 h-3.5" />
                    <span>Ask</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </form>

        {/* Quick hint */}
        <div className="flex items-center space-x-2 mt-3 text-xs text-slate-500">
          <HelpCircle className="w-3.5 h-3.5 shrink-0 text-slate-400" />
          <span>
            Searches up to the first ~25 chunks per document. Throttle rate limit (5 req/sec) applies route-wide; each account has a 50 questions/day allowance.
          </span>
        </div>
      </div>

      {/* Error Display */}
      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800/60 rounded-xl flex items-start space-x-3 text-rose-300 text-sm">
          <AlertCircle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
          <div>
            <p className="font-semibold text-rose-200">Query Failed</p>
            <p className="text-xs text-rose-300/90 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Answer & Sources Result */}
      {result && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-xl space-y-6 animate-fadeIn">
          {/* Answer Box */}
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center space-x-2">
                <Sparkles className="w-4 h-4 text-indigo-400" />
                <h4 className="text-sm font-semibold uppercase tracking-wider text-slate-300">Synthesized Answer</h4>
              </div>
              {result.provider && (
                <span className="flex items-center space-x-1 text-[11px] font-mono px-2.5 py-0.5 rounded-full bg-slate-800 border border-slate-700 text-slate-300">
                  <Cpu className="w-3 h-3 text-emerald-400" />
                  <span>Provider: {result.provider}</span>
                </span>
              )}
            </div>
            <div className="bg-slate-950/60 border border-slate-800/80 rounded-xl p-4 text-sm text-slate-200 leading-relaxed whitespace-pre-line font-sans">
              {result.answer}
            </div>
          </div>

          {/* Sources Section */}
          <div>
            <div className="flex items-center space-x-2 mb-3">
              <Layers className="w-4 h-4 text-indigo-400" />
              <h4 className="text-sm font-semibold uppercase tracking-wider text-slate-300">
                Source Citations ({result.sources ? result.sources.length : 0})
              </h4>
            </div>

            {(!result.sources || result.sources.length === 0) ? (
              <p className="text-xs text-slate-500 italic">No matching document chunks found with high similarity.</p>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {result.sources.map((src, idx) => (
                  <div
                    key={`${src.docId}-${src.chunkIndex || idx}`}
                    className="group bg-slate-950/40 hover:bg-slate-950/80 border border-slate-800 hover:border-indigo-600/50 rounded-xl p-3.5 transition flex flex-col justify-between"
                  >
                    <div>
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="flex items-center space-x-2 min-w-0">
                          <FileText className="w-4 h-4 shrink-0 text-indigo-400" />
                          <span className="text-xs font-semibold text-slate-200 truncate">
                            {src.fileName || 'Untitled Document'}
                          </span>
                        </div>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-500/10 text-indigo-300 border border-indigo-500/20 shrink-0">
                          {Math.round((src.similarity || 0) * 100)}% match
                        </span>
                      </div>
                      <p className="text-xs text-slate-400 line-clamp-3 bg-slate-900/50 p-2 rounded-lg border border-slate-800/50 font-mono">
                        &ldquo;{src.snippet}&rdquo;
                      </p>
                    </div>

                    <div className="mt-3 pt-2 border-t border-slate-800/60 flex items-center justify-between">
                      <span className="text-[10px] text-slate-500 font-mono">
                        Chunk #{src.chunkIndex ?? idx}
                      </span>
                      <button
                        type="button"
                        onClick={() => handleSourceClick(src.docId)}
                        className="text-xs font-medium text-indigo-400 hover:text-indigo-300 inline-flex items-center space-x-1 group-hover:translate-x-0.5 transition"
                      >
                        <span>View Document</span>
                        <ChevronRight className="w-3 h-3" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
