import React, { useState, useRef } from 'react'
import { useAuth } from '../context/AuthContext'
import { getUploadUrl, uploadFileToS3 } from '../lib/api'
import { UploadCloud, X, File, AlertCircle, CheckCircle2 } from 'lucide-react'

const ALLOWED_TYPES = [
  'application/pdf',
  'image/jpeg',
  'image/png',
  'image/tiff'
]

export default function UploadModal({ isOpen, onClose, onUploadSuccess }) {
  const { currentUser } = useAuth()
  const [selectedFile, setSelectedFile] = useState(null)
  const [uploadProgress, setUploadProgress] = useState(0)
  const [uploading, setUploading] = useState(false)
  const [errorMessage, setErrorMessage] = useState('')
  const [dragActive, setDragActive] = useState(false)
  const fileInputRef = useRef(null)

  if (!isOpen) return null

  const handleDrag = (e) => {
    e.preventDefault()
    e.stopPropagation()
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true)
    } else if (e.type === 'dragleave') {
      setDragActive(false)
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    e.stopPropagation()
    setDragActive(false)
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndSetFile(e.dataTransfer.files[0])
    }
  }

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files[0]) {
      validateAndSetFile(e.target.files[0])
    }
  }

  const validateAndSetFile = (file) => {
    setErrorMessage('')
    if (!ALLOWED_TYPES.includes(file.type)) {
      setErrorMessage('Unsupported file type. Please upload a PDF or image (PNG, JPG, TIFF).')
      return
    }
    if (file.size > 4 * 1024 * 1024) {
      setErrorMessage('File size exceeds 4 MB limit.')
      return
    }
    setSelectedFile(file)
  }

  const handleUpload = async () => {
    if (!selectedFile || !currentUser?.idToken) return

    setUploading(true)
    setErrorMessage('')
    setUploadProgress(10)

    try {
      // 1. Get pre-signed URL from API Gateway Lambda
      const { uploadUrl, docId } = await getUploadUrl(currentUser.idToken, {
        fileName: selectedFile.name,
        contentType: selectedFile.type,
        fileSize: selectedFile.size
      })

      setUploadProgress(30)

      // 2. Direct PUT to S3
      await uploadFileToS3(uploadUrl, selectedFile, (percent) => {
        // Map 0-100% S3 progress to 30-95%
        setUploadProgress(30 + Math.round((percent * 65) / 100))
      })

      setUploadProgress(100)

      setTimeout(() => {
        onUploadSuccess?.()
        handleClose()
      }, 500)
    } catch (err) {
      console.error('Upload failed:', err)
      setErrorMessage(err.message || 'File upload failed. Please try again.')
      setUploading(false)
    }
  }

  const handleClose = () => {
    if (uploading) return
    setSelectedFile(null)
    setUploadProgress(0)
    setErrorMessage('')
    onClose()
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 shadow-2xl relative">
        <div className="flex items-center justify-between pb-4 border-b border-slate-800">
          <div className="flex items-center space-x-2">
            <div className="p-2 bg-indigo-500/10 text-indigo-400 rounded-xl">
              <UploadCloud className="w-5 h-5" />
            </div>
            <h3 className="text-lg font-bold text-white">Upload Document</h3>
          </div>
          <button
            onClick={handleClose}
            disabled={uploading}
            className="text-slate-400 hover:text-white p-1 rounded-lg transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {errorMessage && (
          <div className="mt-4 p-3 bg-rose-500/10 border border-rose-500/30 rounded-xl text-xs text-rose-300 flex items-center space-x-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{errorMessage}</span>
          </div>
        )}

        {/* Drag and Drop Box */}
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => !uploading && fileInputRef.current?.click()}
          className={`mt-4 border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition ${
            dragActive
              ? 'border-indigo-500 bg-indigo-500/5'
              : selectedFile
              ? 'border-emerald-500/50 bg-emerald-500/5'
              : 'border-slate-700 hover:border-slate-600 bg-slate-950/40'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept=".pdf,image/png,image/jpeg,image/tiff"
            className="hidden"
            onChange={handleFileChange}
            disabled={uploading}
          />

          {selectedFile ? (
            <div className="flex flex-col items-center">
              <div className="p-3 bg-emerald-500/20 text-emerald-400 rounded-2xl mb-2">
                <File className="w-8 h-8" />
              </div>
              <p className="text-sm font-semibold text-white">{selectedFile.name}</p>
              <p className="text-xs text-slate-400 mt-1">
                {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB &bull; {selectedFile.type}
              </p>
            </div>
          ) : (
            <div className="flex flex-col items-center">
              <div className="p-3 bg-slate-800 text-slate-400 rounded-2xl mb-2">
                <UploadCloud className="w-8 h-8" />
              </div>
              <p className="text-sm font-medium text-slate-200">
                Drag and drop your file here, or <span className="text-indigo-400">browse</span>
              </p>
              <p className="text-xs text-slate-500 mt-2">
                Supported: PDF, PNG, JPG, JPEG, TIFF (Max 4 MB)
              </p>
            </div>
          )}
        </div>

        {/* Upload Progress Bar */}
        {uploading && (
          <div className="mt-4 space-y-2">
            <div className="flex justify-between text-xs text-slate-400 font-mono">
              <span>Uploading to S3...</span>
              <span>{uploadProgress}%</span>
            </div>
            <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
              <div
                className="bg-indigo-500 h-2 rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              ></div>
            </div>
          </div>
        )}

        {/* Modal Actions */}
        <div className="mt-6 flex items-center justify-end space-x-3">
          <button
            type="button"
            onClick={handleClose}
            disabled={uploading}
            className="px-4 py-2 text-xs font-semibold text-slate-400 hover:text-white transition"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleUpload}
            disabled={!selectedFile || uploading}
            className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-500 disabled:bg-slate-800 disabled:text-slate-600 disabled:cursor-not-allowed text-white text-xs font-semibold rounded-xl shadow-lg shadow-indigo-600/20 transition flex items-center space-x-2"
          >
            {uploading ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin"></span>
                <span>Uploading...</span>
              </>
            ) : (
              <span>Start Upload</span>
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
