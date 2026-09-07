import { useState } from 'react'
import { Landmark, ShieldCheck, Sparkles, AlertTriangle } from 'lucide-react'
import { useAuth } from '../state/AuthContext'

export default function Login() {
  const { demoLogin, login, register } = useAuth()
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setBusy(true)
    try {
      if (mode === 'login') await login(email, password)
      else await register(name, email, password)
    } catch (err: any) {
      setError(err?.message || 'Something went wrong')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row">
      {/* Left: brand panel */}
      <div className="relative flex flex-col justify-between bg-slate-900 text-white p-8 lg:w-[46%] lg:p-14">
        <div className="flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-xl bg-brand-600">
            <Landmark className="h-6 w-6" />
          </div>
          <div>
            <h1 className="text-lg font-bold leading-tight">PublicAgent AI</h1>
            <p className="text-xs text-slate-400">Agentic GovTech complaint assistant</p>
          </div>
        </div>

        <div className="my-10 lg:my-0">
          <h2 className="text-3xl lg:text-4xl font-bold leading-tight">
            Describe your problem in plain words.
            <span className="text-brand-400"> We handle the maze.</span>
          </h2>
          <p className="mt-4 max-w-md text-slate-300 leading-relaxed">
            No need to know which department, form or category applies. The agent figures it
            out with you, prepares the complaint, and keeps watching it after submission —
            translating every government reply into plain language.
          </p>
          <ul className="mt-6 space-y-3 text-sm text-slate-300">
            <li className="flex items-start gap-2">
              <Sparkles className="mt-0.5 h-4 w-4 text-brand-400" />
              Real multi-step agent graph — options first, never auto-filing
            </li>
            <li className="flex items-start gap-2">
              <ShieldCheck className="mt-0.5 h-4 w-4 text-brand-400" />
              Clear separation: what you report vs. verified vs. unverified
            </li>
            <li className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-4 w-4 text-amber-400" />
              All government data in this demo is <strong>mock/demo data</strong>
            </li>
          </ul>
        </div>

        <p className="text-xs text-slate-500">
          Alibaba Cloud AI Hackathon Pakistan 2026 · demo prototype · not affiliated with any
          real government institution
        </p>
      </div>

      {/* Right: auth card */}
      <div className="flex flex-1 items-center justify-center p-6 lg:p-10">
        <div className="w-full max-w-md">
          <button
            onClick={async () => {
              setBusy(true)
              setError('')
              try {
                await demoLogin()
              } catch (err: any) {
                setError(err?.message || 'Demo login failed')
              } finally {
                setBusy(false)
              }
            }}
            disabled={busy}
            className="btn-primary w-full text-base shadow-lg shadow-brand-600/20"
          >
            Continue as Demo Citizen
          </button>
          <p className="mt-2 text-center text-xs text-slate-500">
            One click — uses the seeded demo account (citizen@demo.pk)
          </p>

          <div className="my-6 flex items-center gap-3 text-xs text-slate-400">
            <span className="h-px flex-1 bg-slate-300" />
            or use your own account
            <span className="h-px flex-1 bg-slate-300" />
          </div>

          <div className="card p-6">
            <div className="mb-4 flex rounded-lg bg-slate-100 p-1 text-sm font-medium">
              <button
                className={`flex-1 rounded-md py-1.5 ${mode === 'login' ? 'bg-white shadow' : 'text-slate-500'}`}
                onClick={() => setMode('login')}
              >
                Log in
              </button>
              <button
                className={`flex-1 rounded-md py-1.5 ${mode === 'register' ? 'bg-white shadow' : 'text-slate-500'}`}
                onClick={() => setMode('register')}
              >
                Register
              </button>
            </div>

            <form onSubmit={submit} className="space-y-3">
              {mode === 'register' && (
                <input
                  className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
                  placeholder="Full name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              )}
              <input
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
                placeholder="Email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
              />
              <input
                className="w-full rounded-lg border border-slate-300 px-3 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
                placeholder="Password (min 6 chars)"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                minLength={6}
              />
              {error && (
                <p className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</p>
              )}
              <button type="submit" className="btn-secondary w-full" disabled={busy}>
                {busy ? 'Please wait…' : mode === 'login' ? 'Log in' : 'Create account'}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  )
}
