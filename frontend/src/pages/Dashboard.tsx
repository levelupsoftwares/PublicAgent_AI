import { useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { ArrowLeft, FileWarning, Landmark, Plus, Zap } from 'lucide-react'
import { api, Complaint } from '../api/client'
import { useAuth } from '../state/AuthContext'

const STATUS_STYLES: Record<string, { label: string; cls: string }> = {
  draft: { label: 'Draft', cls: 'bg-slate-100 text-slate-600' },
  submitted: { label: 'Submitted', cls: 'bg-sky-100 text-sky-700' },
  received: { label: 'Received', cls: 'bg-indigo-100 text-indigo-700' },
  under_review: { label: 'Under Review', cls: 'bg-amber-100 text-amber-700' },
  additional_info_required: { label: 'Additional Info Required', cls: 'bg-orange-100 text-orange-700' },
  investigating: { label: 'Investigating', cls: 'bg-purple-100 text-purple-700' },
  resolved: { label: 'Resolved', cls: 'bg-emerald-100 text-emerald-700' },
  closed: { label: 'Closed', cls: 'bg-slate-200 text-slate-600' },
}

export function StatusBadge({ status }: { status: string }) {
  const s = STATUS_STYLES[status] || { label: status, cls: 'bg-slate-100 text-slate-600' }
  return <span className={`chip ${s.cls}`}>{s.label}</span>
}

export default function Dashboard() {
  const [complaints, setComplaints] = useState<Complaint[]>([])
  const [loading, setLoading] = useState(true)
  const [advancing, setAdvancing] = useState<string | null>(null)
  const navigate = useNavigate()
  const { user } = useAuth()

  const load = () => {
    api.complaints().then(setComplaints).catch(() => {}).finally(() => setLoading(false))
  }
  useEffect(load, [])

  const advance = async (c: Complaint) => {
    setAdvancing(c.id)
    try {
      await api.advanceStatus({ complaint_id: c.id })
      load()
    } catch { /* ignore */ } finally {
      setAdvancing(null)
    }
  }

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="border-b border-slate-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-5xl items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600 text-white">
              <Landmark className="h-5 w-5" />
            </div>
            <div>
              <p className="text-sm font-bold leading-tight text-slate-900">My Complaints</p>
              <p className="text-[11px] text-slate-400">{user?.name} · demo data only</p>
            </div>
          </div>
          <div className="flex items-center gap-2">
            <button className="btn-primary !py-1.5 !min-h-0 text-xs" onClick={() => navigate('/chat')}>
              <Plus className="h-4 w-4" /> New complaint
            </button>
            <button className="btn-secondary !py-1.5 !min-h-0 text-xs" onClick={() => navigate('/chat')}>
              <ArrowLeft className="h-4 w-4" /> Back to chat
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-4 py-6">
        {loading ? (
          <div className="grid place-items-center py-24">
            <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-600" />
          </div>
        ) : complaints.length === 0 ? (
          <div className="card grid place-items-center gap-3 p-12 text-center">
            <FileWarning className="h-10 w-10 text-slate-300" />
            <p className="text-sm text-slate-500">No complaints yet. Start a conversation and file your first one.</p>
            <button className="btn-primary" onClick={() => navigate('/chat')}>Describe a problem</button>
          </div>
        ) : (
          <div className="space-y-3">
            {complaints.map((c) => (
              <div key={c.id} className="card flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                <button className="min-w-0 flex-1 text-left" onClick={() => navigate(`/complaints/${c.id}`)}>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-sm font-bold text-slate-900">{c.reference_number || '(draft)'}</span>
                    <StatusBadge status={c.status} />
                  </div>
                  <p className="mt-1 truncate text-sm text-slate-600">{c.description || c.category.replace(/_/g, ' ')}</p>
                  <p className="mt-0.5 text-xs text-slate-400">
                    {c.department} · updated {c.updated_at ? new Date(c.updated_at).toLocaleString() : '—'}
                  </p>
                </button>
                <div className="flex items-center gap-2">
                  <button
                    className="btn-secondary !py-1.5 !min-h-0 text-[11px] text-amber-700 hover:bg-amber-50"
                    onClick={() => advance(c)}
                    disabled={advancing === c.id || c.status === 'resolved' || c.status === 'closed'}
                    title="Demo-only: force-advance the mock status"
                  >
                    <Zap className="h-3.5 w-3.5" /> {advancing === c.id ? 'Advancing…' : 'Demo: advance status'}
                  </button>
                  <Link to={`/complaints/${c.id}`} className="btn-secondary !py-1.5 !min-h-0 text-xs">Timeline</Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  )
}
