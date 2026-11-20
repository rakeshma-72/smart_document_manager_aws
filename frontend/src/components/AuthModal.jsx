import React, { useState } from 'react'
import { useAuth } from '../context/AuthContext'
import { Lock, Mail, KeyRound, AlertCircle, CheckCircle, ArrowRight, ShieldCheck } from 'lucide-react'

export default function AuthModal() {
  const { login, register, confirm, error, clearError, isConfigured } = useAuth()
  const [tab, setTab] = useState('login') // 'login' | 'register' | 'confirm'
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmCode, setConfirmCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [successMessage, setSuccessMessage] = useState('')

  const handleTabChange = (newTab) => {
    clearError()
    setSuccessMessage('')
    setTab(newTab)
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    setLoading(true)
    setSuccessMessage('')

    if (tab === 'login') {
      const res = await login(email, password)
      if (res.success) {
        setSuccessMessage('Successfully signed in!')
      }
    } else if (tab === 'register') {
      const res = await register(email, password)
      if (res.success) {
        setSuccessMessage('Account created! Please check your email for the verification code.')
        setTab('confirm')
      }
    } else if (tab === 'confirm') {
      const res = await confirm(email, confirmCode)
      if (res.success) {
        setSuccessMessage('Email verified successfully! You can now log in.')
        setTab('login')
      }
    }
    setLoading(false)
  }

  return (
    <div className="max-w-md w-full mx-auto bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl p-8 backdrop-blur">
      {/* Brand Icon & Heading */}
      <div className="text-center mb-6">
        <div className="inline-flex p-3 bg-indigo-600/20 text-indigo-400 rounded-2xl border border-indigo-500/30 mb-3">
          <ShieldCheck className="w-8 h-8" />
        </div>
        <h2 className="text-2xl font-bold tracking-tight text-white">
          {tab === 'login' && 'Sign in to Document Manager'}
          {tab === 'register' && 'Create your account'}
          {tab === 'confirm' && 'Verify your email'}
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          {tab === 'login' && 'Enter your credentials to access your secure documents'}
          {tab === 'register' && 'Sign up with email to start uploading and analyzing files'}
          {tab === 'confirm' && `Enter the 6-digit confirmation code sent to ${email || 'your email'}`}
        </p>
      </div>

      {!isConfigured && (
        <div className="mb-6 p-3 bg-amber-500/10 border border-amber-500/30 rounded-xl text-xs text-amber-300 flex items-start space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
          <div>
            <strong>Cognito Not Connected:</strong> Populate <code className="bg-amber-950 px-1 py-0.5 rounded">VITE_COGNITO_USER_POOL_ID</code> and <code className="bg-amber-950 px-1 py-0.5 rounded">VITE_COGNITO_CLIENT_ID</code> in <code className="bg-amber-950 px-1 py-0.5 rounded">.env</code> after <code className="bg-amber-950 px-1 py-0.5 rounded">terraform apply</code>.
          </div>
        </div>
      )}

      {/* Tabs */}
      <div className="flex border-b border-slate-800 mb-6 text-sm">
        <button
          type="button"
          onClick={() => handleTabChange('login')}
          className={`flex-1 pb-3 text-center font-medium border-b-2 transition ${
            tab === 'login'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Sign In
        </button>
        <button
          type="button"
          onClick={() => handleTabChange('register')}
          className={`flex-1 pb-3 text-center font-medium border-b-2 transition ${
            tab === 'register'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Sign Up
        </button>
        <button
          type="button"
          onClick={() => handleTabChange('confirm')}
          className={`flex-1 pb-3 text-center font-medium border-b-2 transition ${
            tab === 'confirm'
              ? 'border-indigo-500 text-indigo-400'
              : 'border-transparent text-slate-400 hover:text-slate-200'
          }`}
        >
          Confirm Code
        </button>
      </div>

      {/* Alerts */}
      {error && (
        <div className="mb-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-center space-x-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {successMessage && (
        <div className="mb-4 p-3 bg-emerald-500/10 border border-emerald-500/30 rounded-xl text-xs text-emerald-300 flex items-center space-x-2">
          <CheckCircle className="w-4 h-4 shrink-0" />
          <span>{successMessage}</span>
        </div>
      )}

      {/* Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-xs font-semibold text-slate-300 mb-1">Email Address</label>
          <div className="relative">
            <Mail className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
              className="w-full pl-10 pr-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition"
            />
          </div>
        </div>

        {tab !== 'confirm' && (
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">Password</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="At least 8 characters"
                className="w-full pl-10 pr-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition"
              />
            </div>
          </div>
        )}

        {tab === 'confirm' && (
          <div>
            <label className="block text-xs font-semibold text-slate-300 mb-1">Verification Code</label>
            <div className="relative">
              <KeyRound className="w-4 h-4 text-slate-500 absolute left-3 top-3" />
              <input
                type="text"
                required
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value.trim())}
                placeholder="6-digit code"
                className="w-full pl-10 pr-4 py-2.5 bg-slate-950 border border-slate-800 rounded-xl text-sm text-slate-100 placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition font-mono tracking-widest text-center"
              />
            </div>
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !isConfigured}
          className="w-full mt-2 py-2.5 px-4 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed text-white font-medium text-sm rounded-xl transition flex items-center justify-center space-x-2 shadow-lg shadow-indigo-600/20"
        >
          {loading ? (
            <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
          ) : (
            <>
              <span>
                {tab === 'login' && 'Sign In'}
                {tab === 'register' && 'Create Account'}
                {tab === 'confirm' && 'Verify Code'}
              </span>
              <ArrowRight className="w-4 h-4" />
            </>
          )}
        </button>
      </form>
    </div>
  )
}
