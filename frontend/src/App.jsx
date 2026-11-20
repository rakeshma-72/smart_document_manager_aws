import React, { useState, useEffect, useCallback, useRef } from 'react'
import { AuthProvider, useAuth } from './context/AuthContext'
import Navbar from './components/Navbar'
import AuthModal from './components/AuthModal'
import UploadModal from './components/UploadModal'
import DocumentList from './components/DocumentList'
import DocumentDetailModal from './components/DocumentDetailModal'
import AskTab from './components/AskTab'
import AdminTab from './components/AdminTab'
import ActivityTab from './components/ActivityTab'
import { listDocuments, searchDocuments, deleteDocument } from './lib/api'
import { Cloud, FileText, ShieldCheck, Database, Zap, Plus, CheckCircle2, AlertCircle, MessageSquare, BarChart3, Activity } from 'lucide-react'

function Dashboard() {
  const { currentUser } = useAuth()
  const [documents, setDocuments] = useState([])
  const [loadingDocs, setLoadingDocs] = useState(false)
  const [isUploadOpen, setIsUploadOpen] = useState(false)
  const [activeTab, setActiveTab] = useState('library') // 'library' | 'ask' | 'activity' | 'admin'
  const [selectedDoc, setSelectedDoc] = useState(null)
  const [activeQuery, setActiveQuery] = useState('')
  const [activeTag, setActiveTag] = useState('')
  const [activeType, setActiveType] = useState('all')
  const [searchMode, setSearchMode] = useState('keyword')
  const [toast, setToast] = useState(null)
  const pollTimerRef = useRef(null)
  const pollCountRef = useRef(0)

  const isAdmin = currentUser?.isAdmin || (currentUser?.groups || []).includes('Admin')

  const showToast = (message, type = 'success') => {
    setToast({ message, type })
    setTimeout(() => setToast(null), 3500)
  }

  const fetchDocs = useCallback(async ({ query = activeQuery, tag = activeTag, type = activeType, mode = searchMode } = {}, silent = false) => {
    if (!currentUser?.idToken) return
    if (!silent) setLoadingDocs(true)
    try {
      if (query || tag || (type && type !== 'all') || mode === 'semantic') {
        const data = await searchDocuments(currentUser.idToken, { query, tag, type, mode })
        setDocuments(data.results || [])
        if (data.fallback && data.fallbackReason) {
          showToast(data.fallbackReason, 'info')
        }
      } else {
        const data = await listDocuments(currentUser.idToken)
        setDocuments(data.documents || [])
      }
    } catch (err) {
      console.warn('Could not fetch documents:', err.message)
      if (!silent) showToast(err.message || 'Search failed', 'error')
    } finally {
      if (!silent) setLoadingDocs(false)
    }
  }, [currentUser?.idToken, activeQuery, activeTag, activeType, searchMode])

  // Initial fetch
  useEffect(() => {
    fetchDocs()
  }, [])

  // Smart Auto-Polling with backoff: every 2s initially, backing off if still processing, stops on PROCESSED/FAILED
  useEffect(() => {
    const hasActiveProcessing = documents.some(
      (d) => d.status === 'UPLOADED' || d.status === 'PROCESSING'
    )

    if (hasActiveProcessing) {
      // 2s base polling with gentle backoff after 10 iterations up to 5s
      const delay = pollCountRef.current > 10 ? 5000 : 2000
      pollTimerRef.current = setTimeout(() => {
        pollCountRef.current += 1
        fetchDocs({}, true)
      }, delay)
    } else {
      pollCountRef.current = 0
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }

    return () => {
      if (pollTimerRef.current) clearTimeout(pollTimerRef.current)
    }
  }, [documents, fetchDocs])

  const handleSearch = ({ query, tag, type, mode }) => {
    if (query !== undefined) setActiveQuery(query)
    if (tag !== undefined) setActiveTag(tag)
    if (type !== undefined) setActiveType(type)
    if (mode !== undefined) setSearchMode(mode)
    fetchDocs({ query, tag, type, mode })
  }

  const handleClearSearch = () => {
    setActiveQuery('')
    setActiveTag('')
    setActiveType('all')
    fetchDocs({ query: '', tag: '', type: 'all', mode: searchMode })
  }

  const handleDelete = async (docId) => {
    if (!currentUser?.idToken) return
    try {
      await deleteDocument(currentUser.idToken, docId)
      showToast('Document deleted successfully.', 'success')
      fetchDocs({}, true)
    } catch (err) {
      console.error('Delete failed:', err)
      showToast(err.message || 'Failed to delete document', 'error')
    }
  }

  const uploadedCount = documents.filter(d => d.status === 'UPLOADED').length
  const processingCount = documents.filter(d => d.status === 'PROCESSING').length
  const processedCount = documents.filter(d => d.status === 'PROCESSED').length

  return (
    <div className="space-y-8 relative">
      {/* Toast Notification */}
      {toast && (
        <div
          className={`fixed bottom-6 right-6 z-50 flex items-center space-x-2 px-4 py-3 rounded-xl border shadow-2xl transition animate-bounce ${
            toast.type === 'error'
              ? 'bg-rose-950/90 border-rose-700 text-rose-200'
              : 'bg-emerald-950/90 border-emerald-700 text-emerald-200'
          }`}
        >
          {toast.type === 'error' ? (
            <AlertCircle className="w-4 h-4 shrink-0 text-rose-400" />
          ) : (
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-400" />
          )}
          <span className="text-xs font-semibold">{toast.message}</span>
        </div>
      )}

      {/* Header Banner */}
      <div className="bg-gradient-to-br from-indigo-950/60 via-slate-900 to-slate-950 border border-indigo-900/40 rounded-2xl p-8 shadow-2xl">
        <div className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 mb-3">
              <ShieldCheck className="w-3.5 h-3.5" />
              <span>Phase 8: Polish &amp; Full Lifecycle Active</span>
            </div>
            <h2 className="text-3xl font-extrabold tracking-tight text-white">
              Smart Document Workspace
            </h2>
            <p className="mt-1 text-slate-400 text-sm max-w-xl">
              Serverless document intelligence pipeline with real-time status transitions, AI summaries, keyword search, and deletion.
            </p>
          </div>

          <button
            onClick={() => setIsUploadOpen(true)}
            className="flex items-center space-x-2 px-5 py-3 bg-indigo-600 hover:bg-indigo-500 text-white text-sm font-semibold rounded-xl shadow-lg shadow-indigo-600/30 transition"
          >
            <Plus className="w-4 h-4" />
            <span>Upload Document</span>
          </button>
        </div>

        {/* Stats Row */}
        <div className="mt-8 grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-4">
            <span className="text-xs text-slate-400 font-medium">Total Listed</span>
            <p className="text-2xl font-bold text-white mt-1">{documents.length}</p>
          </div>
          <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-4">
            <span className="text-xs text-blue-400 font-medium">Uploaded</span>
            <p className="text-2xl font-bold text-white mt-1">{uploadedCount}</p>
          </div>
          <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-4">
            <span className="text-xs text-amber-400 font-medium">In Extraction</span>
            <p className="text-2xl font-bold text-amber-300 mt-1 flex items-center space-x-2">
              <span>{processingCount}</span>
              {processingCount > 0 && <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping"></span>}
            </p>
          </div>
          <div className="bg-slate-950/40 border border-slate-800 rounded-xl p-4">
            <span className="text-xs text-emerald-400 font-medium">AI Processed</span>
            <p className="text-2xl font-bold text-white mt-1">{processedCount}</p>
          </div>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex border-b border-slate-800 space-x-8">
        <button
          type="button"
          onClick={() => setActiveTab('library')}
          className={`pb-3 px-1 flex items-center space-x-2 text-sm font-semibold transition border-b-2 -mb-px ${
            activeTab === 'library'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <FileText className="w-4 h-4" />
          <span>Document Library</span>
          <span className="ml-1.5 text-xs font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-400">
            {documents.length}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('ask')}
          className={`pb-3 px-1 flex items-center space-x-2 text-sm font-semibold transition border-b-2 -mb-px ${
            activeTab === 'ask'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          <span>Ask Documents (RAG)</span>
          <span className="ml-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
            AI
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('activity')}
          className={`pb-3 px-1 flex items-center space-x-2 text-sm font-semibold transition border-b-2 -mb-px ${
            activeTab === 'activity'
              ? 'border-purple-500 text-purple-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          <Activity className="w-4 h-4" />
          <span>Activity Audit</span>
        </button>

        {isAdmin && (
          <button
            type="button"
            onClick={() => setActiveTab('admin')}
            className={`pb-3 px-1 flex items-center space-x-2 text-sm font-semibold transition border-b-2 -mb-px ${
              activeTab === 'admin'
                ? 'border-emerald-500 text-emerald-400'
                : 'border-transparent text-slate-400 hover:text-slate-200'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Admin Dashboard</span>
            <span className="ml-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
              Admin
            </span>
          </button>
        )}
      </div>

      {/* Tab Content */}
      {activeTab === 'library' ? (
        <DocumentList
          documents={documents}
          loading={loadingDocs}
          onRefresh={() => fetchDocs({}, false)}
          onSearch={handleSearch}
          onClearSearch={handleClearSearch}
          onDeleteDocument={handleDelete}
          activeQuery={activeQuery}
          activeTag={activeTag}
          activeType={activeType}
          searchMode={searchMode}
          onSearchModeChange={setSearchMode}
          idToken={currentUser?.idToken}
        />
      ) : activeTab === 'ask' ? (
        <AskTab
          idToken={currentUser?.idToken}
          documents={documents}
          onSelectDocument={(doc) => setSelectedDoc(doc)}
        />
      ) : activeTab === 'activity' ? (
        <ActivityTab idToken={currentUser?.idToken} />
      ) : (
        <AdminTab idToken={currentUser?.idToken} />
      )}

      {/* Document Detail Modal for viewing cited documents */}
      {selectedDoc && (
        <DocumentDetailModal
          doc={selectedDoc}
          isOpen={!!selectedDoc}
          onClose={() => setSelectedDoc(null)}
          onDelete={handleDelete}
          idToken={currentUser?.idToken}
        />
      )}

      {/* Upload Modal */}
      <UploadModal
        isOpen={isUploadOpen}
        onClose={() => setIsUploadOpen(false)}
        onUploadSuccess={() => {
          showToast('File uploaded successfully! Starting extraction pipeline.', 'success')
          fetchDocs(activeQuery, activeTag)
        }}
      />
    </div>
  )
}

function MainContent() {
  const { isAuthenticated, loading } = useAuth()

  if (loading) {
    return (
      <div className="min-h-[60vh] flex flex-col items-center justify-center text-slate-400">
        <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4"></div>
        <p className="text-xs font-mono">Verifying authentication session...</p>
      </div>
    )
  }

  return (
    <main className="flex-1 max-w-6xl mx-auto px-6 py-12 w-full">
      {isAuthenticated ? (
        <Dashboard />
      ) : (
        <div className="py-6">
          <AuthModal />
        </div>
      )}
    </main>
  )
}

export default function App() {
  const [theme, setTheme] = useState(() => {
    const saved = localStorage.getItem('smd_theme')
    if (saved) return saved
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
  })

  useEffect(() => {
    localStorage.setItem('smd_theme', theme)
    if (theme === 'light') {
      document.documentElement.classList.add('light-theme')
    } else {
      document.documentElement.classList.remove('light-theme')
    }
  }, [theme])

  const toggleTheme = () => {
    setTheme((prev) => (prev === 'light' ? 'dark' : 'light'))
  }

  return (
    <AuthProvider>
      <div className={`min-h-screen ${theme === 'light' ? 'bg-slate-100 text-slate-900' : 'bg-slate-900 text-slate-100'} flex flex-col transition-colors duration-200`}>
        <Navbar theme={theme} onToggleTheme={toggleTheme} />
        <MainContent />
        <footer className="border-t border-slate-800/60 py-6 text-center text-xs text-slate-500">
          Smart Document Manager &bull; AWS Free Tier Architecture &bull; Budget Cap: $10/month
        </footer>
      </div>
    </AuthProvider>
  )
}
