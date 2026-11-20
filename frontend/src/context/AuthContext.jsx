import React, { createContext, useContext, useState, useEffect } from 'react'
import {
  signIn as cognitoSignIn,
  signUp as cognitoSignUp,
  confirmSignUp as cognitoConfirmSignUp,
  signOut as cognitoSignOut,
  getCurrentSession,
  isCognitoConfigured
} from '../lib/cognito'

const AuthContext = createContext(null)

export const AuthProvider = ({ children }) => {
  const [currentUser, setCurrentUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Verify session on mount
  useEffect(() => {
    checkAuth()
  }, [])

  const checkAuth = async () => {
    try {
      if (!isCognitoConfigured()) {
        setLoading(false)
        return
      }
      const session = await getCurrentSession()
      setCurrentUser(session)
    } catch (err) {
      console.error('Session verification failed:', err)
      setCurrentUser(null)
    } finally {
      setLoading(false)
    }
  }

  const login = async (email, password) => {
    setError(null)
    try {
      await cognitoSignIn(email, password)
      const session = await getCurrentSession()
      setCurrentUser(session)
      return { success: true }
    } catch (err) {
      setError(err.message || 'Login failed')
      return { success: false, error: err.message || 'Login failed' }
    }
  }

  const register = async (email, password) => {
    setError(null)
    try {
      await cognitoSignUp(email, password)
      return { success: true }
    } catch (err) {
      setError(err.message || 'Registration failed')
      return { success: false, error: err.message || 'Registration failed' }
    }
  }

  const confirm = async (email, code) => {
    setError(null)
    try {
      await cognitoConfirmSignUp(email, code)
      return { success: true }
    } catch (err) {
      setError(err.message || 'Verification failed')
      return { success: false, error: err.message || 'Verification failed' }
    }
  }

  const logout = () => {
    cognitoSignOut()
    setCurrentUser(null)
  }

  const clearError = () => setError(null)

  return (
    <AuthContext.Provider
      value={{
        currentUser,
        isAuthenticated: Boolean(currentUser),
        loading,
        error,
        login,
        register,
        confirm,
        logout,
        clearError,
        isConfigured: isCognitoConfigured()
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export const useAuth = () => {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
