import React, { useState } from 'react'
import {
  FileText,
  Image,
  RefreshCw,
  Clock,
  CheckCircle2,
  AlertTriangle,
  FileCode,
  Eye,
  Tag,
  Search,
  X,
  Trash2,
  Sparkles,
  Layers,
  FileDown
} from 'lucide-react'
import DocumentDetailModal from './DocumentDetailModal'
import { exportDocumentToPdf } from '../lib/exportPdf'

const DOC_TYPES = [
  { id: 'all', label: 'All Types' },
  { id: 'invoice', label: 'Invoices' },
  { id: 'resume', label: 'Resumes' },
  { id: 'report', label: 'Reports' },
  { id: 'contract', label: 'Contracts' },
  { id: 'notes', label: 'Notes' },
  { id: 'letter', label: 'Letters' },
  { id: 'other', label: 'Other' },
]

export default function DocumentList({
  documents,
  loading,
  onRefresh,
  onSearch,
  onClearSearch,
  onDeleteDocument,
  activeQuery,
  activeTag,
  activeType,
  searchMode = 'keyword',
  onSearchModeChange,
  idToken
}) {
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [searchInput, setSearchInput] = useState(activeQuery || '')

  const handleSearchSubmit = (e) => {
    e.preventDefault()
    onSearch?.({ query: searchInput, tag: activeTag, type: activeType, mode: searchMode })
  }

  const handleTypeClick = (typeId) => {
    const nextType = activeType === typeId ? 'all' : typeId
    onSearch?.({ query: searchInput, tag: activeTag, type: nextType, mode: searchMode })
  }

  const handleTagClick = (tag) => {
    const nextTag = activeTag === tag ? '' : tag
    onSearch?.({ query: searchInput, tag: nextTag, type: activeType, mode: searchMode })
  }

  const handleModeToggle = (mode) => {
    onSearchModeChange?.(mode)
    onSearch?.({ query: searchInput, tag: activeTag, type: activeType, mode })
  }

  const handleClear = () => {
    setSearchInput('')
    onClearSearch?.()
  }

  const getStatusBadge = (doc) => {
    const status = doc.status
    switch (status) {
      case 'UPLOADED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Clock className="w-3 h-3" />
            <span>Uploaded</span>
          </span>
        )
      case 'PROCESSING':
        return (
          <span className="inline-flex items-center space-x-1.5 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-500/10 text-amber-400 border border-amber-500/20 animate-pulse">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping"></span>
            <span>{doc.currentStep ? `Running ${doc.currentStep}...` : 'Processing...'}</span>
          </span>
        )
      case 'PROCESSED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <CheckCircle2 className="w-3 h-3" />
            <span>Processed</span>
          </span>
        )
      case 'FAILED':
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <AlertTriangle className="w-3 h-3" />
            <span>Failed ({doc.errorCode || 'Error'})</span>
          </span>
        )
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-500/10 text-slate-400 border border-slate-500/20">
            <span>{status || 'Unknown'}</span>
          </span>
        )
    }
  }

  const getTypeBadge = (type) => {
    const t = (type || 'other').toLowerCase()
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-mono uppercase bg-indigo-500/10 text-indigo-400 border border-indigo-500/30">
        {t}
      </span>
    )
  }

  const getFileIcon = (contentType) => {
    if (contentType?.includes('pdf')) {
      return <FileText className="w-4 h-4 text-rose-400" />
    }
    return <Image className="w-4 h-4 text-cyan-400" />
  }

  const formatDate = (isoString) => {
    if (!isoString) return '-'
    try {
      const date = new Date(isoString)
      return date.toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric'
      })
    } catch {
      return isoString
    }
  }

  const formatSize = (bytes) => {
    if (!bytes || bytes === 0) return '-'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  }

  const isFiltering = Boolean(activeQuery || activeTag || (activeType && activeType !== 'all'))

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
      {/* Search & Actions Bar */}
      <div className="p-6 border-b border-slate-800 space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div>
            <h3 className="text-base font-bold text-white flex items-center space-x-2">
              <span>Document Library</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                Live Serverless RAG
              </span>
            </h3>
            <p className="text-xs text-slate-400 mt-0.5">
              Secure multi-tenant storage, automatic Titan embeddings &amp; classification
            </p>
          </div>

          <button
            onClick={onRefresh}
            disabled={loading}
            className="self-start sm:self-auto flex items-center space-x-1.5 px-3 py-1.5 text-xs font-semibold text-slate-300 hover:text-white bg-slate-800/80 hover:bg-slate-800 border border-slate-700 rounded-xl transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>

        {/* Search Mode Toggle & Input Bar */}
        <div className="flex flex-col sm:flex-row gap-3">
          {/* Mode Pill Toggle */}
          <div className="flex bg-slate-950 p-1 rounded-xl border border-slate-800 shrink-0">
            <button
              type="button"
              onClick={() => handleModeToggle('keyword')}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition ${
                searchMode === 'keyword'
                  ? 'bg-slate-800 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              Keyword
            </button>
            <button
              type="button"
              onClick={() => handleModeToggle('semantic')}
              className={`flex items-center space-x-1 px-3 py-1.5 text-xs font-medium rounded-lg transition ${
                searchMode === 'semantic'
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'text-slate-400 hover:text-white'
              }`}
            >
              <Sparkles className="w-3.5 h-3.5" />
              <span>Semantic</span>
            </button>
          </div>

          {/* Search Input */}
          <form onSubmit={handleSearchSubmit} className="flex-1 flex gap-2">
            <div className="relative flex-1">
              <Search className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="text"
                value={searchInput}
                onChange={(e) => setSearchInput(e.target.value)}
                placeholder={
                  searchMode === 'semantic'
                    ? 'Search by meaning using Titan Embeddings (e.g. "quarterly financial results")...'
                    : 'Search keywords in document title, summary, or text...'
                }
                className="w-full pl-9 pr-9 py-2 bg-slate-950 border border-slate-800 rounded-xl text-xs text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition"
              />
              {searchInput && (
                <button
                  type="button"
                  onClick={() => {
                    setSearchInput('')
                    if (activeQuery) onSearch?.({ query: '', tag: activeTag, type: activeType, mode: searchMode })
                  }}
                  className="absolute right-3 top-2.5 text-slate-500 hover:text-slate-300"
                >
                  <X className="w-4 h-4" />
                </button>
              )}
            </div>
            <button
              type="submit"
              className="px-4 py-2 bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold rounded-xl transition shadow-md shadow-indigo-600/20"
            >
              Search
            </button>
          </form>
        </div>

        {/* Filter-by-Type Chip Row */}
        <div className="flex items-center gap-1.5 overflow-x-auto pb-1 text-xs">
          <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider shrink-0 mr-1">
            Type:
          </span>
          {DOC_TYPES.map((dt) => {
            const isSelected = (activeType || 'all') === dt.id
            return (
              <button
                key={dt.id}
                type="button"
                onClick={() => handleTypeClick(dt.id)}
                className={`px-2.5 py-1 rounded-lg text-xs font-medium whitespace-nowrap transition cursor-pointer ${
                  isSelected
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'bg-slate-950 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-800'
                }`}
              >
                {dt.label}
              </button>
            )
          })}
        </div>

        {/* Active Filters Display */}
        {isFiltering && (
          <div className="flex items-center flex-wrap gap-2 text-xs pt-1">
            <span className="text-slate-500">Active Filters:</span>
            {activeQuery && (
              <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 bg-slate-800 text-slate-300 rounded-lg border border-slate-700">
                <span>query: &quot;{activeQuery}&quot; ({searchMode})</span>
                <button
                  type="button"
                  onClick={() => {
                    setSearchInput('')
                    onSearch?.({ query: '', tag: activeTag, type: activeType, mode: searchMode })
                  }}
                  className="hover:text-white ml-1"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            {activeTag && (
              <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 bg-indigo-500/10 text-indigo-400 rounded-lg border border-indigo-500/20">
                <span>tag: #{activeTag}</span>
                <button
                  type="button"
                  onClick={() => onSearch?.({ query: activeQuery, tag: '', type: activeType, mode: searchMode })}
                  className="hover:text-white ml-1"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            {activeType && activeType !== 'all' && (
              <span className="inline-flex items-center space-x-1 px-2.5 py-0.5 bg-indigo-500/10 text-indigo-400 rounded-lg border border-indigo-500/20">
                <span>type: {activeType}</span>
                <button
                  type="button"
                  onClick={() => onSearch?.({ query: activeQuery, tag: activeTag, type: 'all', mode: searchMode })}
                  className="hover:text-white ml-1"
                >
                  <X className="w-3 h-3" />
                </button>
              </span>
            )}
            <button
              onClick={handleClear}
              className="text-xs text-indigo-400 hover:underline ml-1"
            >
              Clear all
            </button>
          </div>
        )}
      </div>

      {/* Table / Empty State / Skeleton */}
      {loading ? (
        <div className="p-8 space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="animate-pulse flex items-center justify-between p-4 bg-slate-950/40 rounded-xl border border-slate-800/50">
              <div className="flex items-center space-x-3">
                <div className="w-9 h-9 bg-slate-800 rounded-lg"></div>
                <div className="space-y-2">
                  <div className="w-40 h-3 bg-slate-800 rounded"></div>
                  <div className="w-20 h-2 bg-slate-800 rounded"></div>
                </div>
              </div>
              <div className="w-24 h-3 bg-slate-800 rounded"></div>
              <div className="w-16 h-6 bg-slate-800 rounded-lg"></div>
            </div>
          ))}
        </div>
      ) : documents.length === 0 ? (
        <div className="p-12 text-center text-slate-400">
          <div className="p-3 bg-slate-800 rounded-2xl w-fit mx-auto mb-3 text-slate-500">
            <FileCode className="w-8 h-8" />
          </div>
          <p className="text-sm font-medium text-slate-300">
            {isFiltering ? 'No matching documents found' : 'No documents uploaded yet'}
          </p>
          <p className="text-xs text-slate-500 mt-1">
            {isFiltering
              ? 'Try modifying your search query or removing the filter chips.'
              : 'Click "Upload Document" above to add your first PDF or image.'}
          </p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-slate-950/60 text-xs font-semibold text-slate-400 border-b border-slate-800 uppercase tracking-wider">
              <tr>
                <th className="px-6 py-3">Document</th>
                <th className="px-6 py-3">Type</th>
                <th className="px-6 py-3">Status</th>
                <th className="px-6 py-3">Summary &amp; Key Details</th>
                <th className="px-6 py-3">Date</th>
                <th className="px-6 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800 text-xs text-slate-300">
              {documents.map((doc) => (
                <tr key={doc.docId} className="hover:bg-slate-800/30 transition">
                  {/* File Name & Icon */}
                  <td className="px-6 py-4 font-medium text-white">
                    <div className="flex items-center space-x-3">
                      <div className="p-2 bg-slate-800 rounded-lg shrink-0">
                        {getFileIcon(doc.contentType)}
                      </div>
                      <div>
                        <p className="font-semibold text-white truncate max-w-[180px]">{doc.fileName}</p>
                        <p className="text-[10px] text-slate-500 font-mono mt-0.5">{formatSize(doc.fileSize)}</p>
                      </div>
                    </div>
                  </td>

                  {/* Doc Type Badge */}
                  <td className="px-6 py-4">
                    {getTypeBadge(doc.docType)}
                  </td>

                  {/* Status Badge */}
                  <td className="px-6 py-4">{getStatusBadge(doc)}</td>

                  {/* Summary & Tags / Semantic score */}
                  <td className="px-6 py-4 max-w-sm">
                    {doc.similarityScore !== undefined && (
                      <div className="mb-1.5 flex items-center space-x-1 text-xs">
                        <span className="font-mono text-indigo-400 font-semibold">
                          {doc.matchPercentage}% match
                        </span>
                        {doc.matchingSnippet && (
                          <span className="text-[11px] text-slate-400 truncate max-w-xs italic">
                            &quot;{doc.matchingSnippet}&quot;
                          </span>
                        )}
                      </div>
                    )}
                    {doc.summary ? (
                      <p className="text-slate-300 line-clamp-1 text-xs mb-1.5 italic">
                        &quot;{doc.summary}&quot;
                      </p>
                    ) : (
                      <p className="text-slate-500 text-xs mb-1.5">
                        {doc.status === 'PROCESSING' ? 'Generating summary...' : 'No summary generated'}
                      </p>
                    )}

                    {/* Key Fields Snippet */}
                    {doc.keyFields && doc.keyFields.length > 0 && (
                      <div className="flex flex-wrap gap-1 mb-1.5">
                        {doc.keyFields.slice(0, 2).map((kf, i) => (
                          <span
                            key={i}
                            className="text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-300 font-mono border border-slate-700 truncate max-w-[140px]"
                          >
                            {kf.label}: {kf.value}
                          </span>
                        ))}
                      </div>
                    )}

                    <div className="flex flex-wrap gap-1">
                      {doc.tags && doc.tags.length > 0 ? (
                        doc.tags.map((tag, idx) => (
                          <button
                            key={idx}
                            type="button"
                            onClick={() => handleTagClick(tag)}
                            className={`text-[10px] px-2 py-0.5 rounded-md font-mono transition cursor-pointer ${
                              activeTag === tag
                                ? 'bg-indigo-600 text-white'
                                : 'bg-indigo-500/10 text-indigo-300 hover:bg-indigo-500/20 border border-indigo-500/20'
                            }`}
                          >
                            #{tag}
                          </button>
                        ))
                      ) : null}
                    </div>
                  </td>

                  {/* Upload Date */}
                  <td className="px-6 py-4 text-slate-400 font-mono">{formatDate(doc.createdAt)}</td>

                  {/* Actions: Export PDF, Details, Delete */}
                  <td className="px-6 py-4 text-right space-x-1.5 whitespace-nowrap">
                    <button
                      onClick={() => exportDocumentToPdf(doc)}
                      title="Export Summary as PDF"
                      className="inline-flex items-center p-1.5 bg-slate-800 hover:bg-indigo-600/30 text-slate-300 hover:text-indigo-300 rounded-lg transition"
                    >
                      <FileDown className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => setSelectedDoc(doc)}
                      className="inline-flex items-center space-x-1 px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white rounded-lg transition text-xs font-semibold"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      <span>Details</span>
                    </button>
                    <button
                      onClick={() => onDeleteDocument?.(doc.docId)}
                      title="Delete document"
                      className="inline-flex items-center p-1.5 text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 rounded-lg transition"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Details Modal */}
      <DocumentDetailModal
        doc={selectedDoc}
        isOpen={Boolean(selectedDoc)}
        onClose={() => setSelectedDoc(null)}
        onDelete={onDeleteDocument}
        idToken={idToken}
      />
    </div>
  )
}
