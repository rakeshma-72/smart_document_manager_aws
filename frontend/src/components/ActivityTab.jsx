import React, { useState, useEffect } from 'react'
import {
  Activity,
  RefreshCw,
  Clock,
  Shield,
  FileText,
  Upload,
  Trash2,
  Share2,
  Lock,
  MessageSquare,
  BarChart3,
  ExternalLink
} from 'lucide-react'
import { getAuditTrail } from '../lib/api'

export default function ActivityTab({ idToken }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchEvents = async () => {
    if (!idToken) return
    setLoading(true)
    setError(null)
    try {
      const data = await getAuditTrail(idToken, 100)
      setEvents(data.events || [])
    } catch (err) {
      setError(err.message || 'Failed to load activity events')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchEvents()
  }, [idToken])

  const formatDate = (isoString) => {
    if (!isoString) return '-'
    try {
      return new Date(isoString).toLocaleString()
    } catch {
      return isoString
    }
  }

  const getActionBadge = (action) => {
    switch (action) {
      case 'UPLOAD':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-500/10 text-blue-400 border border-blue-500/20">
            <Upload className="w-3 h-3" />
            <span>UPLOAD</span>
          </span>
        )
      case 'VIEW':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-500/10 text-slate-300 border border-slate-500/20">
            <FileText className="w-3 h-3" />
            <span>VIEW</span>
          </span>
        )
      case 'DELETE':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-rose-500/10 text-rose-400 border border-rose-500/20">
            <Trash2 className="w-3 h-3" />
            <span>DELETE</span>
          </span>
        )
      case 'SHARE_CREATE':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <Share2 className="w-3 h-3" />
            <span>SHARE_CREATE</span>
          </span>
        )
      case 'SHARE_REVOKE':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
            <Lock className="w-3 h-3" />
            <span>SHARE_REVOKE</span>
          </span>
        )
      case 'SHARE_ACCESS':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">
            <ExternalLink className="w-3 h-3" />
            <span>SHARE_ACCESS</span>
          </span>
        )
      case 'ASK':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            <MessageSquare className="w-3 h-3" />
            <span>ASK</span>
          </span>
        )
      case 'ADMIN_STATS_VIEW':
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-cyan-500/10 text-cyan-400 border border-cyan-500/20">
            <BarChart3 className="w-3 h-3" />
            <span>ADMIN_VIEW</span>
          </span>
        )
      default:
        return (
          <span className="inline-flex items-center space-x-1 px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-700 text-slate-300">
            <span>{action}</span>
          </span>
        )
    }
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-slate-800">
        <div>
          <h3 className="text-xl font-bold text-white flex items-center space-x-2">
            <Activity className="w-5 h-5 text-indigo-400" />
            <span>Security &amp; Activity Audit Log</span>
          </h3>
          <p className="text-xs text-slate-400 mt-1">
            Immutable log of all user events. Zero document text or raw tokens are stored. Log entries expire automatically after 90 days.
          </p>
        </div>

        <button
          onClick={fetchEvents}
          disabled={loading}
          className="flex items-center space-x-2 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-500/30 rounded-xl text-xs text-rose-300">
          {error}
        </div>
      )}

      {/* Events Table */}
      <div className="bg-slate-950 border border-slate-800 rounded-2xl overflow-hidden shadow-xl">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-slate-800 bg-slate-900/50 text-slate-400 font-semibold uppercase tracking-wider text-[11px]">
                <th className="px-6 py-4">Timestamp</th>
                <th className="px-6 py-4">Action</th>
                <th className="px-6 py-4">Status</th>
                <th className="px-6 py-4">Hashed IP (Pseudonymized)</th>
                <th className="px-6 py-4">Details / Metadata</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-mono">
              {loading && events.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-slate-500">
                    <div className="flex flex-col items-center justify-center space-y-2">
                      <div className="w-5 h-5 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
                      <span className="font-sans text-xs">Loading audit events...</span>
                    </div>
                  </td>
                </tr>
              ) : events.length === 0 ? (
                <tr>
                  <td colSpan={5} className="px-6 py-12 text-center text-slate-500 font-sans">
                    No activity recorded yet.
                  </td>
                </tr>
              ) : (
                events.map((ev, idx) => (
                  <tr key={ev.eventId || idx} className="hover:bg-slate-900/30 transition">
                    <td className="px-6 py-3 text-slate-300 whitespace-nowrap">
                      {formatDate(ev.timestamp)}
                    </td>
                    <td className="px-6 py-3 whitespace-nowrap">
                      {getActionBadge(ev.action)}
                    </td>
                    <td className="px-6 py-3 whitespace-nowrap">
                      <span
                        className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                          ev.status === 'SUCCESS' || ev.status === 'ALLOWED'
                            ? 'bg-emerald-500/10 text-emerald-400'
                            : 'bg-rose-500/10 text-rose-400'
                        }`}
                      >
                        {ev.status || 'OK'}
                      </span>
                    </td>
                    <td className="px-6 py-3 text-slate-400 whitespace-nowrap text-[11px]">
                      {ev.ipHash || '-'}
                    </td>
                    <td className="px-6 py-3 text-slate-300 font-sans text-xs">
                      {ev.details && Object.keys(ev.details).length > 0 ? (
                        <div className="flex flex-wrap gap-2 text-[11px] font-mono text-slate-400">
                          {Object.entries(ev.details).map(([k, v]) => (
                            <span key={k} className="bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
                              <span className="text-slate-500">{k}:</span> {String(v)}
                            </span>
                          ))}
                        </div>
                      ) : (
                        <span className="text-slate-500">-</span>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
