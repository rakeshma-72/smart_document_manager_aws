import React, { useState, useEffect } from 'react'
import {
  X,
  Sparkles,
  Tag,
  FileText,
  Copy,
  Check,
  Trash2,
  AlertTriangle,
  CheckCircle2,
  Clock,
  ArrowRight,
  Share2,
  Link,
  ShieldAlert,
  Download,
  FileDown,
  Layers
} from 'lucide-react'
import { createShareLink, listShareLinks, revokeShareLink } from '../lib/api'
import { exportDocumentToPdf } from '../lib/exportPdf'
import PipelineTracker from './PipelineTracker'

export default function DocumentDetailModal({ doc, isOpen, onClose, onDelete, idToken }) {
  const [copied, setCopied] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [deleting, setDeleting] = useState(false)

  // Share state
  const [shares, setShares] = useState([])
  const [loadingShares, setLoadingShares] = useState(false)
  const [expiresIn, setExpiresIn] = useState('24h')
  const [maxDownloads, setMaxDownloads] = useState('')
  const [createdLink, setCreatedLink] = useState('')
  const [creatingShare, setCreatingShare] = useState(false)
  const [shareError, setShareError] = useState(null)
  const [copiedShare, setCopiedShare] = useState(false)

  useEffect(() => {
    if (isOpen && doc?.docId && idToken) {
      loadShares()
    } else {
      setShares([])
      setCreatedLink('')
      setShareError(null)
    }
  }, [isOpen, doc?.docId, idToken])

  const loadShares = async () => {
    if (!idToken || !doc?.docId) return
    setLoadingShares(true)
    try {
      const data = await listShareLinks(idToken, doc.docId)
      setShares(data.shares || [])
    } catch (err) {
      console.warn('Failed to load shares:', err.message)
    } finally {
      setLoadingShares(false)
    }
  }

  const handleCreateShare = async (e) => {
    e.preventDefault()
    if (!idToken || !doc?.docId) return
    setCreatingShare(true)
    setShareError(null)
    setCreatedLink('')
    try {
      const res = await createShareLink(idToken, doc.docId, {
        expiresIn,
        maxDownloads: maxDownloads ? parseInt(maxDownloads, 10) : null
      })
      setCreatedLink(res.shareUrl)
      setMaxDownloads('')
      await loadShares()
    } catch (err) {
      setShareError(err.message || 'Failed to create share link')
    } finally {
      setCreatingShare(false)
    }
  }

  const handleRevokeShare = async (shareId) => {
    if (!idToken) return
    try {
      await revokeShareLink(idToken, shareId)
      await loadShares()
    } catch (err) {
      console.error('Revoke failed:', err)
      setShareError(err.message || 'Failed to revoke link')
    }
  }

  const handleCopyShareLink = () => {
    if (!createdLink) return
    navigator.clipboard.writeText(createdLink)
    setCopiedShare(true)
    setTimeout(() => setCopiedShare(false), 2000)
  }

  if (!isOpen || !doc) return null

  const handleCopyText = () => {
    if (!doc.preview) return
    navigator.clipboard.writeText(doc.preview)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const handleDeleteClick = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setDeleting(true)
    try {
      await onDelete?.(doc.docId)
      onClose()
    } catch (err) {
      console.error('Delete failed:', err)
      setDeleting(false)
    }
  }

  const formatSize = (bytes) => {
    if (!bytes || bytes === 0) return '-'
    if (bytes < 1024) return `${bytes} B`
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`
  }

  const formatDate = (isoString) => {
    if (!isoString) return '-'
    try {
      return new Date(isoString).toLocaleString()
    } catch {
      return isoString
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative max-h-[90vh] flex flex-col">
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center space-x-3">
            <div className="p-2.5 bg-indigo-500/10 text-indigo-400 rounded-xl">
              <FileText className="w-6 h-6" />
            </div>
            <div>
              <h3 className="text-lg font-bold text-white truncate max-w-md">{doc.fileName}</h3>
              <p className="text-xs text-slate-400 font-mono">ID: {doc.docId}</p>
            </div>
          </div>
          <button
            onClick={() => {
              setConfirmDelete(false)
              onClose()
            }}
            className="text-slate-400 hover:text-white p-1 rounded-lg transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content Body */}
        <div className="overflow-y-auto py-4 space-y-6 flex-1 pr-1">
          {/* Metadata Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Document Type</span>
              <p className="text-xs font-semibold text-indigo-400 mt-1 uppercase">
                {doc.docType || 'other'}
              </p>
            </div>
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Status</span>
              <p className="text-xs font-semibold text-emerald-400 mt-1 flex items-center space-x-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>{doc.status}</span>
              </p>
            </div>
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">File Size</span>
              <p className="text-xs font-semibold text-slate-200 mt-1">{formatSize(doc.fileSize)}</p>
            </div>
            <div className="bg-slate-950/60 border border-slate-800 rounded-xl p-3">
              <span className="text-[10px] text-slate-500 uppercase font-semibold">Word Count</span>
              <p className="text-xs font-semibold text-slate-200 mt-1">{doc.wordCount || 0} words</p>
            </div>
          </div>

          {/* Live Pipeline Stepper */}
          <PipelineTracker
            currentStep={doc.currentStep}
            stepStatus={doc.stepStatus}
            status={doc.status}
            errorCode={doc.errorCode}
            failedStep={doc.failedStep}
            createdAt={doc.createdAt}
            updatedAt={doc.updatedAt}
          />

          {/* AI Executive Summary */}
          <div className="bg-gradient-to-br from-indigo-950/30 via-slate-950 to-slate-900 border border-indigo-900/50 rounded-xl p-4 shadow-inner">
            <div className="flex items-center justify-between mb-2">
              <div className="flex items-center space-x-2 text-indigo-400">
                <Sparkles className="w-4 h-4" />
                <h4 className="text-xs font-bold uppercase tracking-wider">AI Executive Summary</h4>
              </div>
              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={() => exportDocumentToPdf(doc)}
                  className="flex items-center space-x-1 px-2.5 py-1 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-semibold shadow transition"
                >
                  <FileDown className="w-3.5 h-3.5" />
                  <span>Export as PDF</span>
                </button>
                {doc.summaryProvider && (
                  <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-300 border border-indigo-500/30">
                    {doc.summaryProvider}
                  </span>
                )}
              </div>
            </div>
            <p className="text-sm text-slate-200 leading-relaxed italic">
              {doc.summary || 'Summary generation is in progress or not available.'}
            </p>
          </div>

          {/* Key Fields */}
          {doc.keyFields && doc.keyFields.length > 0 && (
            <div>
              <div className="flex items-center space-x-2 text-slate-400 mb-2">
                <Layers className="w-4 h-4 text-indigo-400" />
                <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">
                  Extracted Key Fields
                </h4>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {doc.keyFields.map((field, idx) => (
                  <div
                    key={idx}
                    className="p-2.5 bg-slate-950/60 border border-slate-800 rounded-xl flex flex-col space-y-0.5"
                  >
                    <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wide">
                      {field.label}
                    </span>
                    <span className="text-xs font-mono text-slate-200 break-words">
                      {field.value}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Topic Tags */}
          <div>
            <div className="flex items-center space-x-2 text-slate-400 mb-2">
              <Tag className="w-4 h-4" />
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-300">Generated Tags</h4>
            </div>
            <div className="flex flex-wrap gap-2">
              {doc.tags && doc.tags.length > 0 ? (
                doc.tags.map((tag, idx) => (
                  <span
                    key={idx}
                    className="px-2.5 py-1 rounded-lg text-xs font-medium bg-indigo-500/10 text-indigo-300 border border-indigo-500/20"
                  >
                    #{tag}
                  </span>
                ))
              ) : (
                <span className="text-xs text-slate-500">No tags identified</span>
              )}
            </div>
          </div>

          {/* Extracted Text Preview with Copy */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">
                Extracted Text Preview
              </h4>
              {doc.preview && (
                <button
                  type="button"
                  onClick={handleCopyText}
                  className="flex items-center space-x-1 text-xs text-slate-400 hover:text-white transition"
                >
                  {copied ? (
                    <>
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                      <span className="text-emerald-400">Copied</span>
                    </>
                  ) : (
                    <>
                      <Copy className="w-3.5 h-3.5" />
                      <span>Copy Text</span>
                    </>
                  )}
                </button>
              )}
            </div>
            <div className="bg-slate-950 border border-slate-800 rounded-xl p-4 max-h-48 overflow-y-auto">
              <pre className="text-xs font-mono text-slate-300 whitespace-pre-wrap leading-relaxed">
                {doc.preview || 'No text extracted.'}
              </pre>
            </div>
          </div>

          {/* Expiring Share Links Section */}
          <div className="bg-slate-950/80 border border-slate-800 rounded-xl p-4 space-y-4">
            <div className="flex items-center space-x-2 text-indigo-400">
              <Share2 className="w-4 h-4" />
              <h4 className="text-xs font-bold uppercase tracking-wider">Share Document</h4>
            </div>

            <div className="bg-amber-950/20 border border-amber-900/30 rounded-lg p-2.5 flex items-start space-x-2 text-xs text-amber-300">
              <ShieldAlert className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
              <span>
                Anyone with this link can download the document until it expires or is revoked.
              </span>
            </div>

            <form onSubmit={handleCreateShare} className="space-y-3">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                    Link Expiration
                  </label>
                  <select
                    value={expiresIn}
                    onChange={(e) => setExpiresIn(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-indigo-500"
                  >
                    <option value="1h">1 hour</option>
                    <option value="24h">24 hours</option>
                    <option value="7d">7 days</option>
                  </select>
                </div>
                <div>
                  <label className="block text-[11px] font-semibold text-slate-400 mb-1">
                    Max Downloads (Optional)
                  </label>
                  <input
                    type="number"
                    min="1"
                    max="1000"
                    placeholder="Unlimited"
                    value={maxDownloads}
                    onChange={(e) => setMaxDownloads(e.target.value)}
                    className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500"
                  />
                </div>
              </div>

              {shareError && (
                <p className="text-xs text-rose-400 font-medium">{shareError}</p>
              )}

              <button
                type="submit"
                disabled={creatingShare}
                className="w-full py-2 bg-indigo-600 hover:bg-indigo-500 disabled:bg-indigo-900/50 text-white text-xs font-semibold rounded-lg transition flex items-center justify-center space-x-1.5"
              >
                <Link className="w-3.5 h-3.5" />
                <span>{creatingShare ? 'Generating Secure Link...' : 'Create Share Link'}</span>
              </button>
            </form>

            {/* Generated Link Alert */}
            {createdLink && (
              <div className="p-3 bg-indigo-950/40 border border-indigo-500/40 rounded-lg space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-bold text-indigo-300 uppercase tracking-wider">
                    New Share Link Created
                  </span>
                  <button
                    type="button"
                    onClick={handleCopyShareLink}
                    className="flex items-center space-x-1 text-xs text-indigo-300 hover:text-white transition"
                  >
                    {copiedShare ? (
                      <>
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400 font-semibold">Copied!</span>
                      </>
                    ) : (
                      <>
                        <Copy className="w-3.5 h-3.5" />
                        <span>Copy Link</span>
                      </>
                    )}
                  </button>
                </div>
                <p className="text-xs font-mono text-slate-200 break-all bg-slate-900/80 p-2 rounded border border-slate-800">
                  {createdLink}
                </p>
                <p className="text-[10px] text-slate-400 italic">
                  Note: The raw link token is shown only once and cannot be recovered later.
                </p>
              </div>
            )}

            {/* Existing Active/Revoked Shares List */}
            <div className="pt-2">
              <h5 className="text-[11px] font-bold text-slate-400 uppercase tracking-wider mb-2">
                Active &amp; Past Share Links
              </h5>
              {loadingShares ? (
                <p className="text-xs text-slate-500 italic">Loading links...</p>
              ) : shares.length === 0 ? (
                <p className="text-xs text-slate-500 italic">No share links created for this document.</p>
              ) : (
                <div className="space-y-2 max-h-40 overflow-y-auto pr-1">
                  {shares.map((s) => (
                    <div
                      key={s.shareId}
                      className="flex items-center justify-between p-2.5 bg-slate-900/60 border border-slate-800 rounded-lg text-xs"
                    >
                      <div className="space-y-0.5">
                        <div className="flex items-center space-x-2">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] font-bold uppercase ${
                              s.status === 'ACTIVE'
                                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/30'
                                : s.status === 'EXPIRED'
                                ? 'bg-amber-500/20 text-amber-400 border border-amber-500/30'
                                : 'bg-slate-700/50 text-slate-400 border border-slate-600/30'
                            }`}
                          >
                            {s.status}
                          </span>
                          <span className="text-slate-400 text-[11px]">
                            {s.downloadCount} {s.maxDownloads ? `/ ${s.maxDownloads}` : ''} downloads
                          </span>
                        </div>
                        <p className="text-[10px] text-slate-500">
                          Expires: {formatDate(s.expiresAt)} &bull; Created: {formatDate(s.createdAt)}
                        </p>
                      </div>

                      {s.status === 'ACTIVE' && (
                        <button
                          type="button"
                          onClick={() => handleRevokeShare(s.shareId)}
                          className="px-2 py-1 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 rounded text-[11px] font-medium transition"
                        >
                          Revoke
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

        </div>

        {/* Footer with Actions */}
        <div className="pt-4 border-t border-slate-800 flex items-center justify-between">
          <div>
            {confirmDelete ? (
              <div className="flex items-center space-x-2">
                <span className="text-xs text-rose-400 font-medium">Delete this document permanently?</span>
                <button
                  onClick={handleDeleteClick}
                  disabled={deleting}
                  className="px-3 py-1.5 bg-rose-600 hover:bg-rose-500 text-white text-xs font-semibold rounded-lg transition"
                >
                  {deleting ? 'Deleting...' : 'Yes, Delete'}
                </button>
                <button
                  onClick={() => setConfirmDelete(false)}
                  className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 text-xs font-semibold rounded-lg transition"
                >
                  Cancel
                </button>
              </div>
            ) : (
              <button
                onClick={handleDeleteClick}
                className="flex items-center space-x-1.5 px-3 py-1.5 text-xs font-semibold text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/20 rounded-xl transition"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Delete Document</span>
              </button>
            )}
          </div>

          <button
            onClick={() => {
              setConfirmDelete(false)
              onClose()
            }}
            className="px-4 py-2 bg-slate-800 hover:bg-slate-700 text-white text-xs font-semibold rounded-xl transition"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
