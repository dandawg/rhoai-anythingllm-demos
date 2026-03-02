import { useState, useEffect, useCallback } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface QuotaInfo {
  used: number
  quota: number
  available: number
}

interface SignupResult {
  success: boolean
  username: string
  workspaceName: string
  anythingllmUrl: string
}

type FormState = 'idle' | 'submitting' | 'success' | 'error'

// ---------------------------------------------------------------------------
// Sub-components
// ---------------------------------------------------------------------------

function QuotaSkeleton() {
  return (
    <div className="quota-card quota-skeleton">
      <div className="skeleton-line short" />
      <div className="quota-bar-bg">
        <div className="quota-bar-fill skeleton-bar" style={{ width: '40%' }} />
      </div>
    </div>
  )
}

function QuotaBar({ quota }: { quota: QuotaInfo }) {
  const pct = quota.quota > 0 ? Math.min(100, (quota.used / quota.quota) * 100) : 0
  const isFull = quota.available === 0
  const isWarning = !isFull && pct >= 80

  const fillColor = isFull ? 'var(--color-error)' : isWarning ? 'var(--color-warning)' : 'var(--color-success)'
  const label = isFull
    ? 'All slots are full'
    : quota.available === 1
    ? '1 slot remaining'
    : `${quota.available} of ${quota.quota} slots remaining`

  return (
    <div className="quota-card">
      <div className="quota-header">
        <span className="quota-label">Demo Capacity</span>
        <span className={`quota-count ${isFull ? 'full' : ''}`}>{label}</span>
      </div>
      <div className="quota-bar-bg" role="progressbar" aria-valuenow={quota.used} aria-valuemin={0} aria-valuemax={quota.quota}>
        <div className="quota-bar-fill" style={{ width: `${pct}%`, backgroundColor: fillColor }} />
      </div>
    </div>
  )
}

function SuccessView({ result }: { result: SignupResult }) {
  return (
    <div className="success-view">
      <div className="success-icon" aria-hidden="true">✓</div>
      <h2 className="success-title">You're all set!</h2>
      <p className="success-body">
        Welcome, <strong>{result.username}</strong>! Your personal workspace{' '}
        <strong>"{result.workspaceName}"</strong> has been created and is ready to use.
      </p>
      {result.anythingllmUrl ? (
        <a
          href={result.anythingllmUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="btn btn-primary btn-open"
        >
          Open AnythingLLM →
        </a>
      ) : (
        <p className="success-hint">Open the AnythingLLM URL shared by the presenter to get started.</p>
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Field with inline error
// ---------------------------------------------------------------------------

interface FieldProps {
  id: string
  label: string
  type?: string
  value: string
  onChange: (v: string) => void
  onBlur?: () => void
  error?: string
  placeholder?: string
  autoComplete?: string
  disabled?: boolean
}

function Field({ id, label, type = 'text', value, onChange, onBlur, error, placeholder, autoComplete, disabled }: FieldProps) {
  const [showPassword, setShowPassword] = useState(false)
  const isPassword = type === 'password'
  const inputType = isPassword ? (showPassword ? 'text' : 'password') : type

  return (
    <div className={`field ${error ? 'field--error' : ''}`}>
      <label htmlFor={id} className="field-label">{label}</label>
      <div className="field-input-wrap">
        <input
          id={id}
          type={inputType}
          value={value}
          onChange={e => onChange(e.target.value)}
          onBlur={onBlur}
          placeholder={placeholder}
          autoComplete={autoComplete}
          disabled={disabled}
          className="field-input"
          aria-describedby={error ? `${id}-error` : undefined}
          aria-invalid={!!error}
        />
        {isPassword && (
          <button
            type="button"
            className="toggle-password"
            onClick={() => setShowPassword(s => !s)}
            tabIndex={-1}
            aria-label={showPassword ? 'Hide password' : 'Show password'}
          >
            {showPassword ? '🙈' : '👁️'}
          </button>
        )}
      </div>
      {error && <p id={`${id}-error`} className="field-error" role="alert">{error}</p>}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main App
// ---------------------------------------------------------------------------

const USERNAME_RE = /^[a-zA-Z0-9_-]{3,32}$/

export default function App() {
  const [quota, setQuota] = useState<QuotaInfo | null>(null)
  const [quotaLoading, setQuotaLoading] = useState(true)

  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')

  const [touched, setTouched] = useState({ username: false, password: false, confirmPassword: false })

  const [formState, setFormState] = useState<FormState>('idle')
  const [errorMessage, setErrorMessage] = useState('')
  const [signupResult, setSignupResult] = useState<SignupResult | null>(null)

  const fetchQuota = useCallback(async () => {
    setQuotaLoading(true)
    try {
      const res = await fetch('/api/quota')
      if (res.ok) setQuota(await res.json())
    } catch {
      // non-fatal; quota display just won't show
    } finally {
      setQuotaLoading(false)
    }
  }, [])

  useEffect(() => { fetchQuota() }, [fetchQuota])

  // Derived validation (only shown after field is touched or submit attempted)
  const usernameError =
    touched.username && !USERNAME_RE.test(username)
      ? 'Must be 3–32 characters: letters, numbers, _ or -'
      : ''

  const passwordError =
    touched.password && password.length > 0 && password.length < 8
      ? 'Password must be at least 8 characters'
      : ''

  const confirmPasswordError =
    touched.confirmPassword && confirmPassword !== password
      ? 'Passwords do not match'
      : ''

  function touchAll() {
    setTouched({ username: true, password: true, confirmPassword: true })
  }

  function isFormValid() {
    return (
      USERNAME_RE.test(username) &&
      password.length >= 8 &&
      password === confirmPassword
    )
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    touchAll()
    if (!isFormValid()) return

    setFormState('submitting')
    setErrorMessage('')

    try {
      const res = await fetch('/api/signup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: username.trim().toLowerCase(), password }),
      })

      const data = await res.json()

      if (res.ok) {
        setSignupResult(data)
        setFormState('success')
        fetchQuota()
      } else {
        setErrorMessage(data.detail || 'Signup failed. Please try again.')
        setFormState('error')
      }
    } catch {
      setErrorMessage('Network error. Please check your connection and try again.')
      setFormState('error')
    }
  }

  const isSubmitting = formState === 'submitting'
  const isFull = quota !== null && quota.available === 0

  return (
    <div className="page">
      <main className="card">
        {/* Header */}
        <header className="card-header">
          <div className="logo" aria-hidden="true">🤖</div>
          <h1 className="card-title">AnythingLLM Demo Access</h1>
          <p className="card-subtitle">Create your personal AI workspace</p>
        </header>

        {/* Quota */}
        <div className="quota-section">
          {quotaLoading ? <QuotaSkeleton /> : quota ? <QuotaBar quota={quota} /> : null}
        </div>

        {/* Body */}
        {formState === 'success' && signupResult ? (
          <SuccessView result={signupResult} />
        ) : (
          <form className="signup-form" onSubmit={handleSubmit} noValidate>
            {isFull && (
              <div className="banner banner--error" role="alert">
                All demo slots are currently full. Please contact the presenter.
              </div>
            )}

            <Field
              id="username"
              label="Username"
              value={username}
              onChange={setUsername}
              onBlur={() => setTouched(t => ({ ...t, username: true }))}
              error={usernameError}
              placeholder="your-username"
              autoComplete="username"
              disabled={isSubmitting || isFull}
            />

            <Field
              id="password"
              label="Password"
              type="password"
              value={password}
              onChange={setPassword}
              onBlur={() => setTouched(t => ({ ...t, password: true }))}
              error={passwordError}
              placeholder="Min. 8 characters"
              autoComplete="new-password"
              disabled={isSubmitting || isFull}
            />

            <Field
              id="confirm-password"
              label="Confirm Password"
              type="password"
              value={confirmPassword}
              onChange={setConfirmPassword}
              onBlur={() => setTouched(t => ({ ...t, confirmPassword: true }))}
              error={confirmPasswordError}
              placeholder="Re-enter your password"
              autoComplete="new-password"
              disabled={isSubmitting || isFull}
            />

            {formState === 'error' && errorMessage && (
              <div className="banner banner--error" role="alert">{errorMessage}</div>
            )}

            <button
              type="submit"
              className="btn btn-primary"
              disabled={isSubmitting || isFull}
            >
              {isSubmitting ? (
                <span className="spinner-wrap"><span className="spinner" aria-hidden="true" /> Creating account…</span>
              ) : (
                'Create Account'
              )}
            </button>
          </form>
        )}

        <footer className="card-footer">
          <p>Accounts are for demo use only and may be deleted after the session.</p>
        </footer>
      </main>
    </div>
  )
}
