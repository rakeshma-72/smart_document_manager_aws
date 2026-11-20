import React from 'react'
import { useAuth } from '../context/AuthContext'
import { FileText, LogOut, User, Sun, Moon } from 'lucide-react'

export default function Navbar({ theme, onToggleTheme }) {
  const { currentUser, logout, isAuthenticated } = useAuth()
  const currentRegion = import.meta.env.VITE_AWS_REGION || 'ap-southeast-2'

  return (
    <header className="border-b border-slate-800 bg-slate-950/70 backdrop-blur sticky top-0 z-50 px-6 py-4">
      <div className="max-w-6xl mx-auto flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="p-2 bg-indigo-600 rounded-xl shadow-lg shadow-indigo-600/30">
            <FileText className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-base font-bold tracking-tight text-white flex items-center space-x-2">
              <span>Smart Document Manager</span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
                AWS
              </span>
            </h1>
            <p className="text-xs text-slate-400">Serverless &bull; {currentRegion}</p>
          </div>
        </div>

        <div className="flex items-center space-x-3">
          {/* Theme Toggle Button */}
          <button
            type="button"
            onClick={onToggleTheme}
            aria-label="Toggle dark/light theme"
            className="p-2 rounded-xl bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800 transition focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            {theme === 'light' ? (
              <Moon className="w-4 h-4 text-indigo-400" />
            ) : (
              <Sun className="w-4 h-4 text-amber-400" />
            )}
          </button>

          <div className="hidden sm:flex items-center space-x-2 text-xs font-mono bg-slate-900 px-3 py-1.5 rounded-full border border-slate-800 text-slate-300">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            <span>{currentRegion}</span>
          </div>

          {isAuthenticated && currentUser && (
            <div className="flex items-center space-x-3">
              <div className="flex items-center space-x-2 text-xs text-slate-300 bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-xl">
                <User className="w-3.5 h-3.5 text-indigo-400" />
                <span className="font-medium truncate max-w-[150px]">{currentUser.email}</span>
              </div>
              <button
                onClick={logout}
                title="Sign Out"
                className="flex items-center space-x-1.5 text-xs text-slate-400 hover:text-rose-400 bg-slate-900 hover:bg-rose-500/10 border border-slate-800 hover:border-rose-500/20 px-3 py-1.5 rounded-xl transition"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span className="hidden sm:inline">Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  )
}
