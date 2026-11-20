import React, { useState, useEffect } from 'react'
import {
  BarChart3,
  Users,
  Files,
  HardDrive,
  Clock,
  CheckCircle,
  AlertTriangle,
  RefreshCw,
  Cpu,
  HelpCircle,
  Activity,
  Layers
} from 'lucide-react'
import { getAdminStats } from '../lib/api'

export default function AdminTab({ idToken }) {
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const fetchStats = async () => {
    setLoading(true)
    setError(null)
    try {
      const data = await getAdminStats(idToken)
      setStats(data)
    } catch (err) {
      setError(err.message || 'Failed to load administrator analytics.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (idToken) {
      fetchStats()
    }
  }, [idToken])

  const formatBytes = (bytes) => {
    if (!bytes || bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
  }

  return (
    <div className="space-y-6">
      {/* Header Banner */}
      <div className="bg-gradient-to-br from-indigo-950/60 via-slate-900 to-slate-950 border border-indigo-900/40 rounded-2xl p-6 shadow-xl flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-3 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
            <BarChart3 className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center space-x-2">
              <h3 className="text-xl font-bold text-white">Platform Administrator Analytics</h3>
              <span className="text-xs font-mono font-semibold px-2 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                Admin Verified
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-0.5">
              Aggregate operational insights across tenant partitions. Raw document text and questions are strictly omitted.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={fetchStats}
          disabled={loading}
          className="flex items-center space-x-1.5 px-3.5 py-2 bg-slate-800 hover:bg-slate-700 disabled:opacity-50 text-slate-200 text-xs font-semibold rounded-xl border border-slate-700 transition"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          <span>Refresh</span>
        </button>
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4 bg-rose-950/40 border border-rose-800/60 rounded-xl flex items-start space-x-3 text-rose-300 text-sm">
          <AlertTriangle className="w-5 h-5 shrink-0 text-rose-400 mt-0.5" />
          <div>
            <p className="font-semibold text-rose-200">Analytics Error</p>
            <p className="text-xs text-rose-300/90 mt-0.5">{error}</p>
          </div>
        </div>
      )}

      {/* Loading state */}
      {loading && !stats && (
        <div className="min-h-[40vh] flex flex-col items-center justify-center text-slate-400">
          <div className="w-8 h-8 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin mb-4"></div>
          <p className="text-xs font-mono">Aggregating platform metrics...</p>
        </div>
      )}

      {/* Empty state */}
      {!loading && stats && stats.totalDocuments === 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-12 text-center text-slate-400">
          <Files className="w-12 h-12 mx-auto text-slate-600 mb-3" />
          <h4 className="text-base font-semibold text-slate-200">No Documents Uploaded</h4>
          <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1">
            The platform currently has zero documents. Upload files from the library tab to view analytics.
          </p>
        </div>
      )}

      {/* Populated State */}
      {stats && (
        <div className="space-y-6">
          {/* Top Row Cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-slate-950/50 border border-slate-800 rounded-xl p-4">
              <div className="flex items-center space-x-2 text-slate-400 text-xs font-medium">
                <Users className="w-3.5 h-3.5 text-indigo-400" />
                <span>Active users (with documents)</span>
              </div>
              <p className="text-2xl font-bold text-white mt-2">{stats.activeUsers ?? stats.totalUsers}</p>
            </div>

            <div className="bg-slate-950/50 border border-slate-800 rounded-xl p-4">
              <div className="flex items-center space-x-2 text-slate-400 text-xs font-medium">
                <Files className="w-3.5 h-3.5 text-blue-400" />
                <span>Total Documents</span>
              </div>
              <p className="text-2xl font-bold text-white mt-2">{stats.totalDocuments}</p>
            </div>

            <div className="bg-slate-950/50 border border-slate-800 rounded-xl p-4">
              <div className="flex items-center space-x-2 text-slate-400 text-xs font-medium">
                <HardDrive className="w-3.5 h-3.5 text-emerald-400" />
                <span>Total Storage Used</span>
              </div>
              <p className="text-2xl font-bold text-white mt-2">{formatBytes(stats.storage?.totalBytes)}</p>
            </div>

            <div className="bg-slate-950/50 border border-slate-800 rounded-xl p-4">
              <div className="flex items-center space-x-2 text-slate-400 text-xs font-medium">
                <Activity className="w-3.5 h-3.5 text-amber-400" />
                <span>Success Rate</span>
              </div>
              <p className="text-2xl font-bold text-white mt-2">{stats.reliability?.successRate}%</p>
            </div>
          </div>

          {/* Performance & Status Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Document Status Breakdown */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <h4 className="text-sm font-semibold uppercase tracking-wider text-slate-300 mb-4 flex items-center space-x-2">
                <Layers className="w-4 h-4 text-indigo-400" />
                <span>Document Status Breakdown</span>
              </h4>
              <div className="space-y-3">
                {Object.entries(stats.documentsByStatus || {}).map(([st, cnt]) => {
                  const percent = stats.totalDocuments > 0 ? Math.round((cnt / stats.totalDocuments) * 100) : 0
                  return (
                    <div key={st}>
                      <div className="flex justify-between text-xs text-slate-300 mb-1">
                        <span className="font-mono">{st}</span>
                        <span>{cnt} ({percent}%)</span>
                      </div>
                      <div className="w-full bg-slate-950 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full ${
                            st === 'PROCESSED'
                              ? 'bg-emerald-500'
                              : st === 'FAILED'
                              ? 'bg-rose-500'
                              : st === 'PROCESSING'
                              ? 'bg-amber-500'
                              : 'bg-blue-500'
                          }`}
                          style={{ width: `${percent}%` }}
                        ></div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* Pipeline Performance Card */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <h4 className="text-sm font-semibold uppercase tracking-wider text-slate-300 mb-4 flex items-center space-x-2">
                <Clock className="w-4 h-4 text-indigo-400" />
                <span>Pipeline Processing Latency</span>
              </h4>
              <div className="grid grid-cols-2 gap-4">
                <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80">
                  <span className="text-xs text-slate-400">Average Duration</span>
                  <p className="text-2xl font-bold text-white mt-1">
                    {stats.performance?.avgProcessingTimeSec} s
                  </p>
                </div>
                <div className="bg-slate-950/60 p-4 rounded-xl border border-slate-800/80">
                  <span className="text-xs text-slate-400">p95 Latency</span>
                  <p className="text-2xl font-bold text-amber-300 mt-1">
                    {stats.performance?.p95ProcessingTimeSec} s
                  </p>
                </div>
              </div>
              <div className="mt-4 pt-4 border-t border-slate-800/60 text-xs text-slate-400 flex items-center justify-between">
                <span>Measured Completed Runs: {stats.performance?.measuredCount}</span>
                <span className="text-rose-400">7-Day Failures: {stats.reliability?.failedDocumentsLast7Days}</span>
              </div>
            </div>
          </div>

          {/* AI Providers & Ask Questions Timeline */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Summary Provider Split */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <h4 className="text-sm font-semibold uppercase tracking-wider text-slate-300 mb-4 flex items-center space-x-2">
                <Cpu className="w-4 h-4 text-indigo-400" />
                <span>Summary AI Provider Split</span>
              </h4>
              <div className="space-y-3">
                {Object.entries(stats.summaryProviderSplit || {}).map(([prov, cnt]) => (
                  <div key={prov} className="flex items-center justify-between p-3 rounded-xl bg-slate-950/40 border border-slate-800">
                    <span className="text-xs font-mono font-semibold uppercase text-slate-300">{prov}</span>
                    <span className="text-xs font-mono font-bold text-indigo-400">{cnt} documents</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Ask Questions Timeline */}
            <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg">
              <h4 className="text-sm font-semibold uppercase tracking-wider text-slate-300 mb-4 flex items-center space-x-2">
                <HelpCircle className="w-4 h-4 text-indigo-400" />
                <span>RAG &ldquo;Ask&rdquo; Queries (Last 14 Days)</span>
              </h4>
              <div className="space-y-2 max-h-48 overflow-y-auto pr-1">
                {stats.askUsageLast14Days?.map((entry) => (
                  <div key={entry.date} className="flex items-center justify-between text-xs py-1.5 px-3 rounded-lg bg-slate-950/30">
                    <span className="font-mono text-slate-400">{entry.date}</span>
                    <span className="font-mono font-semibold text-slate-200">{entry.count} queries</span>
                  </div>
                ))}
              </div>
            </div>
          </div>

          {/* Per-User Storage Table */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <h4 className="text-sm font-semibold uppercase tracking-wider text-slate-300 mb-3 flex items-center space-x-2">
              <HardDrive className="w-4 h-4 text-indigo-400" />
              <span>Storage Consumption by Anonymized Tenant</span>
            </h4>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-500">
                    <th className="pb-2 font-medium">Tenant Anonymized Identifier</th>
                    <th className="pb-2 font-medium text-right">Storage Footprint</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono">
                  {stats.storage?.byUser?.map((u) => (
                    <tr key={u.user} className="hover:bg-slate-800/20">
                      <td className="py-2.5 text-slate-300">{u.user}</td>
                      <td className="py-2.5 text-right text-indigo-400">{formatBytes(u.bytes)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>

          {/* Phase 4: Recent Security Events Section */}
          <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 shadow-lg">
            <div className="flex items-center justify-between mb-3">
              <h4 className="text-sm font-semibold uppercase tracking-wider text-slate-300 flex items-center space-x-2">
                <Activity className="w-4 h-4 text-emerald-400" />
                <span>Recent Platform Security Events</span>
              </h4>
              <div className="flex items-center space-x-2">
                {Object.entries(stats.security?.actionCounts || {}).map(([act, count]) => (
                  <span
                    key={act}
                    className="text-[10px] font-mono px-2 py-0.5 rounded bg-slate-950 border border-slate-800 text-slate-300"
                  >
                    {act}: <strong className="text-indigo-400">{count}</strong>
                  </span>
                ))}
              </div>
            </div>
            <p className="text-xs text-slate-400 mb-3">
              Latest security and access operations across tenants. Tenant IDs are cryptographically anonymized and client addresses are recorded as hashed IP (pseudonymized).
            </p>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-800 text-slate-500 font-semibold text-[11px] uppercase">
                    <th className="pb-2">Timestamp</th>
                    <th className="pb-2">Action</th>
                    <th className="pb-2">Status</th>
                    <th className="pb-2">Anonymized Tenant</th>
                    <th className="pb-2">Hashed IP (Pseudonymized)</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60 font-mono text-[11px]">
                  {stats.security?.recentEvents && stats.security.recentEvents.length > 0 ? (
                    stats.security.recentEvents.map((ev, idx) => (
                      <tr key={idx} className="hover:bg-slate-800/20">
                        <td className="py-2 text-slate-400 whitespace-nowrap">
                          {new Date(ev.timestamp).toLocaleString()}
                        </td>
                        <td className="py-2 text-slate-200 font-bold whitespace-nowrap">
                          {ev.action}
                        </td>
                        <td className="py-2 whitespace-nowrap">
                          <span
                            className={`px-1.5 py-0.5 rounded text-[10px] ${
                              ev.status === 'SUCCESS' || ev.status === 'ALLOWED'
                                ? 'bg-emerald-500/10 text-emerald-400'
                                : 'bg-rose-500/10 text-rose-400'
                            }`}
                          >
                            {ev.status || 'OK'}
                          </span>
                        </td>
                        <td className="py-2 text-slate-400 whitespace-nowrap">{ev.userId}</td>
                        <td className="py-2 text-slate-500 whitespace-nowrap">{ev.ipHash || '-'}</td>
                      </tr>
                    ))
                  ) : (
                    <tr>
                      <td colSpan={5} className="py-4 text-center text-slate-500 font-sans">
                        No security events recorded in the audit trail yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
