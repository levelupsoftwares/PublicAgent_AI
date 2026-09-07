import { useEffect, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { ArrowLeft, CheckCircle2, Circle, CircleDot, Landmark, Paperclip } from 'lucide-react'
import { api, ComplaintDetail } from '../api/client'
import { StatusBadge } from './Dashboard'

const LIFECYCLE = ['submitted', 'received', 'under_review', 'investigating', 'resolved']

export default function ComplaintDetailPage() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [c, setC] = useState<ComplaintDetail | null>(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.complaint(id!).then(setC).catch((e) => setError(e?.message || 'Failed to load'))
  }, [id])

  if (error) {
    return (
      <div className="grid min-h-screen place-items-center bg-slate-100">
        <div className="card p-8 text-center">
          <p className="text-sm text-rose-600">{error}</p>
          <button className="btn-secondary mt-3" onClick={() => navigate('/dashboard')}>Back</button>
        </div>
      </div>
    )
  }
  if (!c) {
    return (
      <div className="grid min-h-screen place-items-center bg-slate-100">
        <div className="h-8 w-8 animate-spin rounded-full border-4 border-brand-200 border-t-brand-600" />
      </div>
    )
  }

  const idx = c.status === 'additional_info_required'
    ? LIFECYCLE.indexOf('under_review') // info request typically happens during review
    : LIFECYCLE.indexOf(c.status)
  const additionalInfo = c.status === 'additional_info_required'

  return (
    <div className="min-h-screen bg-slate-100">
      <header className="border-b border-slate-200 bg-white px-4 py-3">
        <div className="mx-auto flex max-w-4xl items-center justify-between">
          <button className="btn-ghost !px-2 !min-h-0" onClick={() => navigate('/dashboard')}>
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="flex items-center gap-2 text-slate-900">
            <Landmark className="h-4 w-4 text-brand-600" />
            <span className="text-sm font-bold">Complaint {c.reference_number}</span>
          </div>
          <StatusBadge status={c.status} />
        </div>
      </header>

      <main className="mx-auto max-w-4xl space-y-4 px-4 py-6">
        {/* Lifecycle stepper */}
        <div className="card p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Lifecycle</p>
          <div className="mt-3 flex flex-wrap items-center gap-y-3">
            {LIFECYCLE.map((s, i) => {
              const active = idx >= i && idx !== -1
              const current = idx === i
              return (
                <div key={s} className="flex items-center">
                  <div className="flex flex-col items-center">
                    {current ? <CircleDot className="h-6 w-6 text-brand-600" />
                      : active ? <CheckCircle2 className="h-6 w-6 text-brand-600" />
                      : <Circle className="h-6 w-6 text-slate-300" />}
                    <span className={`mt-1 text-[11px] font-medium ${active ? 'text-slate-700' : 'text-slate-400'}`}>
                      {s.replace(/_/g, ' ')}
                    </span>
                  </div>
                  {i < LIFECYCLE.length - 1 && (
                    <div className={`mx-2 mb-4 h-0.5 w-10 sm:w-16 ${idx > i ? 'bg-brand-500' : 'bg-slate-200'}`} />
                  )}
                </div>
              )
            })}
          </div>
          {additionalInfo && (
            <p className="mt-3 rounded-lg bg-orange-50 px-3 py-2 text-xs text-orange-700">
              The authority requested additional information — see the timeline below.
            </p>
          )}
        </div>

        {/* Details */}
        <div className="card p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Details</p>
          <div className="mt-2 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            <Field k="Authority" v={c.department} />
            <Field k="Jurisdiction" v={c.jurisdiction || '—'} />
            <Field k="Category" v={c.category.replace(/_/g, ' ')} />
            <Field k="Submitted" v={c.submitted_at ? new Date(c.submitted_at).toLocaleString() : '—'} />
          </div>
          {c.description && (
            <p className="mt-3 border-l-2 border-slate-300 pl-3 text-sm leading-relaxed text-slate-600">{c.description}</p>
          )}
          {c.unverified_fields?.length > 0 && (
            <div className="mt-3 rounded-lg bg-amber-50 p-3">
              <p className="text-xs font-semibold text-amber-700">Reported by you — not independently verified</p>
              <p className="mt-1 text-xs text-amber-600">{c.unverified_fields.join(', ')}</p>
            </div>
          )}
          <p className="mt-3 text-[11px] text-slate-400">
            All authority data is demo / mock government data — not a verified real institution.
          </p>
        </div>

        {/* Evidence */}
        {c.evidence.length > 0 && (
          <div className="card p-5">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Evidence</p>
            <div className="mt-2 space-y-2">
              {c.evidence.map((e) => (
                <div key={e.id} className="flex items-start gap-2 rounded-lg border border-slate-100 p-2.5">
                  <Paperclip className="mt-0.5 h-4 w-4 text-slate-400" />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium text-slate-700">{e.filename}</p>
                    {e.extracted_summary && (
                      <p className="text-xs text-slate-500">{e.extracted_summary} <span className="chip bg-amber-100 text-amber-700">AI-extracted — unverified</span></p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Timeline */}
        <div className="card p-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Timeline</p>
          <div className="mt-3 space-y-0">
            {c.events.map((e, i) => (
              <div key={e.id} className="relative flex gap-3 pb-5 last:pb-0">
                {i < c.events.length - 1 && <div className="absolute left-[9px] top-5 h-full w-0.5 bg-slate-200" />}
                <div className={`mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full ${
                  e.event_type === 'STATUS_UPDATED' && e.metadata?.source === 'user_pasted' ? 'bg-amber-100' : 'bg-brand-100'
                }`}>
                  <div className={`h-2 w-2 rounded-full ${
                    e.event_type === 'STATUS_UPDATED' && e.metadata?.source === 'user_pasted' ? 'bg-amber-500' : 'bg-brand-600'
                  }`} />
                </div>
                <div className="min-w-0">
                  <p className="text-sm font-medium text-slate-800">
                    {e.event_type === 'SUBMITTED' ? 'Complaint submitted'
                      : e.event_type === 'STATUS_UPDATED'
                      ? `Status: ${e.old_status?.replace(/_/g, ' ') ?? '—'} → ${e.new_status?.replace(/_/g, ' ')}`
                      : e.event_type.replace(/_/g, ' ')}
                  </p>
                  <p className="text-xs text-slate-500">
                    {new Date(e.created_at).toLocaleString()}
                    {e.metadata?.source === 'user_pasted' && ' · from a message you pasted — not independently verified'}
                    {e.metadata?.source === 'scheduler' && ' · detected automatically by follow-up check'}
                    {e.metadata?.source === 'seed' && ' · demo seed data'}
                  </p>
                </div>
              </div>
            ))}
            {!c.events.length && <p className="text-sm text-slate-400">No events recorded yet.</p>}
          </div>
        </div>
      </main>
    </div>
  )
}

function Field({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-dashed border-slate-100 pb-1">
      <span className="shrink-0 text-xs uppercase tracking-wide text-slate-400">{k}</span>
      <span className="truncate text-right text-sm font-medium text-slate-800">{v}</span>
    </div>
  )
}
