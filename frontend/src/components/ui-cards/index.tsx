import { ReactNode } from 'react'
import {
  AlertTriangle, BadgeCheck, CheckCircle2, ChevronRight, Compass, FileSignature,
  FileText, HelpCircle, Info, Link2, Megaphone, Paperclip, ShieldAlert, XCircle,
} from 'lucide-react'
import { Message } from '../../api/client'

// ---------------------------------------------------------------- helpers
const ICONS: Record<string, any> = {
  compass: Compass, 'file-signature': FileSignature, megaphone: Megaphone, 'help-circle': HelpCircle,
}

export function CardShell({
  title, subtitle, children, tone = 'default', icon,
}: {
  title?: string; subtitle?: string; children: ReactNode; tone?: 'default' | 'warn' | 'danger' | 'success'; icon?: ReactNode
}) {
  const toneCls =
    tone === 'danger' ? 'border-rose-200 bg-rose-50'
    : tone === 'warn' ? 'border-amber-200 bg-amber-50'
    : tone === 'success' ? 'border-brand-200 bg-brand-50'
    : 'border-slate-200 bg-white'
  return (
    <div className={`card overflow-hidden ${toneCls}`}>
      {(title || subtitle) && (
        <div className="flex items-start gap-2 border-b border-slate-200/70 px-4 py-3">
          {icon}
          <div>
            {title && <p className="text-sm font-semibold text-slate-800">{title}</p>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
        </div>
      )}
      <div className="px-4 py-3">{children}</div>
    </div>
  )
}

function MockBadge() {
  return <span className="chip bg-slate-200 text-slate-600">Demo / mock government data</span>
}
function UnverifiedBadge() {
  return <span className="chip bg-amber-100 text-amber-700">Unverified</span>
}

// ---------------------------------------------------------------- cards
function OptionsCard({ card, onAction }: CardProps) {
  return (
    <CardShell title={card.title} subtitle={card.subtitle}>
      <div className="grid gap-2 sm:grid-cols-2">
        {card.options.map((o: any) => {
          const Icon = ICONS[o.icon] || Info
          return (
            <button
              key={o.id}
              onClick={() => onAction({ type: 'option', option: o.id })}
              className="group flex items-start gap-3 rounded-lg border border-slate-200 p-3 text-left transition hover:border-brand-400 hover:bg-brand-50/60"
            >
              <span className="grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-slate-100 text-slate-600 group-hover:bg-brand-100 group-hover:text-brand-700">
                <Icon className="h-4 w-4" />
              </span>
              <span className="min-w-0">
                <span className="flex items-center gap-1 text-sm font-semibold text-slate-800">
                  {o.label} <ChevronRight className="h-3.5 w-3.5 opacity-0 transition group-hover:opacity-60" />
                </span>
                <span className="mt-0.5 block text-xs leading-relaxed text-slate-500">{o.description}</span>
              </span>
            </button>
          )
        })}
      </div>
      {card.authority?.name && (
        <p className="mt-3 flex flex-wrap items-center gap-2 text-xs text-slate-500">
          Likely authority: <strong className="text-slate-700">{card.authority.name}</strong>
          <MockBadge />
        </p>
      )}
    </CardShell>
  )
}

function GuidanceCard({ card }: CardProps) {
  return (
    <CardShell title={card.title} icon={<Compass className="mt-0.5 h-4 w-4 text-brand-600" />}>
      <div className="space-y-3">
        {card.sections.map((s: any, i: number) => (
          <div key={i}>
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">{s.heading}</p>
            <p className="mt-1 text-sm leading-relaxed text-slate-700">{s.body}</p>
          </div>
        ))}
      </div>
      <p className="mt-3 rounded-lg bg-slate-50 px-3 py-2 text-[11px] leading-relaxed text-slate-500">
        {card.disclaimer}
      </p>
    </CardShell>
  )
}

function SourceCitationCard({ card }: CardProps) {
  if (!card.sources?.length) return null
  return (
    <div className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2">
      <p className="flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
        <Link2 className="h-3 w-3" /> Sources
      </p>
      <ul className="mt-1 space-y-0.5">
        {card.sources.map((s: any, i: number) => (
          <li key={i} className="truncate text-xs text-slate-600">
            • {s.title} <span className="text-slate-400">({s.source_ref})</span>
          </li>
        ))}
      </ul>
      {card.note && <p className="mt-1 text-[11px] text-slate-400">{card.note}</p>}
    </div>
  )
}

function InformationRequestCard({ card, onAction }: CardProps) {
  return (
    <CardShell title={card.title} subtitle={card.note} icon={<FileText className="mt-0.5 h-4 w-4 text-brand-600" />}>
      {card.progress && (
        <div className="mb-3">
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200">
            <div
              className="h-full rounded-full bg-brand-500 transition-all"
              style={{ width: `${Math.round(((card.progress.provided || 0) / Math.max(card.progress.total, 1)) * 100)}%` }}
            />
          </div>
          <p className="mt-1 text-[11px] text-slate-400">
            {card.progress.provided}/{card.progress.total} fields collected
          </p>
        </div>
      )}
      <div className="space-y-3">
        {card.questions.map((q: any) => (
          <div key={q.field} className="rounded-lg border border-slate-200 p-3">
            <p className="text-sm font-medium text-slate-800">
              {q.label}
              {!q.required && <span className="ml-2 chip bg-slate-100 text-slate-500">Optional</span>}
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              <button className="btn-primary !py-1.5 !min-h-0 text-xs" onClick={() => onAction(null, q.field, q.type)}>
                Answer
              </button>
              {q.allow_skip && (
                <button className="btn-secondary !py-1.5 !min-h-0 text-xs" onClick={() => onAction({ type: 'skip', field: q.field })}>
                  [Skip]
                </button>
              )}
            </div>
          </div>
        ))}
      </div>
    </CardShell>
  )
}

function ValidationIssuesCard({ card }: CardProps) {
  return (
    <CardShell title={card.title} tone="warn" icon={<AlertTriangle className="mt-0.5 h-4 w-4 text-amber-600" />}>
      <ul className="space-y-1.5">
        {card.issues.map((i: any, idx: number) => (
          <li key={idx} className="flex items-center gap-2 text-sm text-slate-700">
            <XCircle className="h-4 w-4 shrink-0 text-amber-500" />
            <span><strong>{i.label}</strong> — {String(i.issue).replace(/_/g, ' ')}</span>
          </li>
        ))}
      </ul>
    </CardShell>
  )
}

function ComplaintReviewCard({ card, onAction }: CardProps) {
  return (
    <CardShell title={card.title} subtitle={card.warning} icon={<FileSignature className="mt-0.5 h-4 w-4 text-brand-600" />}>
      <div className="space-y-3">
        <div className="rounded-lg bg-slate-50 p-3">
          <p className="text-xs uppercase tracking-wide text-slate-400">Complaint</p>
          <p className="mt-1 text-sm font-medium text-slate-800">{card.complaint.category.replace(/_/g, ' ')}</p>
          <p className="text-xs text-slate-500">{card.complaint.department}</p>
          {card.complaint.description && (
            <p className="mt-2 border-l-2 border-slate-300 pl-2 text-sm text-slate-600">{card.complaint.description}</p>
          )}
        </div>
        <div className="grid gap-x-4 gap-y-1.5 sm:grid-cols-2">
          {card.fields.map((f: any) => (
            <div key={f.field} className="flex items-baseline justify-between gap-2 border-b border-dashed border-slate-100 pb-1 text-sm">
              <span className="shrink-0 text-slate-500">{f.label}</span>
              <span className={`text-right font-medium ${f.skipped ? 'text-slate-400 italic' : 'text-slate-800'}`}>{f.value}</span>
            </div>
          ))}
        </div>
        {card.unverified_fields?.length > 0 && (
          <div className="rounded-lg bg-amber-50 p-3">
            <p className="flex items-center gap-1.5 text-xs font-semibold text-amber-700">
              <AlertTriangle className="h-3.5 w-3.5" /> Reported by you — not independently verified
            </p>
            <p className="mt-1 text-xs text-amber-600">{card.unverified_fields.join(', ')}</p>
          </div>
        )}
        {card.evidence?.length > 0 && (
          <div className="space-y-1">
            {card.evidence.map((e: any, i: number) => (
              <p key={i} className="flex items-center gap-2 text-xs text-slate-600">
                <Paperclip className="h-3.5 w-3.5" /> {e.filename}
                {e.summary && <span className="text-slate-400">— {e.summary}</span>}
              </p>
            ))}
          </div>
        )}
        <p className="flex items-center gap-2 text-[11px] text-slate-400"><MockBadge /> {card.labels?.mock}</p>
        <div className="flex flex-wrap gap-2 pt-1">
          <button className="btn-primary" onClick={() => onAction({ type: 'confirm', value: true })}>
            <BadgeCheck className="h-4 w-4" /> Confirm &amp; Submit
          </button>
          <button className="btn-secondary" onClick={() => onAction({ type: 'confirm', value: false })}>
            Go Back
          </button>
        </div>
      </div>
    </CardShell>
  )
}

function StatusCard({ card }: CardProps) {
  return (
    <CardShell title={card.title} tone="success" icon={<CheckCircle2 className="mt-0.5 h-4 w-4 text-brand-600" />}>
      <div className="flex flex-wrap items-center gap-3">
        <div>
          <p className="text-2xl font-bold tracking-tight text-slate-900">{card.reference_number}</p>
          <p className="text-sm text-slate-500">
            Status: <span className="font-semibold text-brand-700">{card.status_display}</span>
            {card.department && <> · {card.department}</>}
          </p>
        </div>
      </div>
      {card.tracking?.active && (
        <p className="mt-2 text-xs text-slate-500">
          Follow-up tracking active — next check in ~{Math.round((card.tracking.interval_seconds || 0) / 60)} min.
        </p>
      )}
      <p className="mt-2 text-[11px] text-slate-400">{card.note}</p>
    </CardShell>
  )
}

function GovMessageAnalysisCard({ card }: CardProps) {
  const verified = card.verification === 'verified'
  const notFound = card.verification === 'not_found'
  return (
    <CardShell
      title="Government message — analysis"
      subtitle={card.verification_label || (card.looks_government ? 'Looks like an official message' : 'Does not look official')}
      tone={verified ? 'success' : card.looks_government ? 'default' : 'warn'}
      icon={<ShieldAlert className={`mt-0.5 h-4 w-4 ${verified ? 'text-brand-600' : 'text-amber-600'}`} />}
    >
      <div className="space-y-2 text-sm">
        <Row k="Reference" v={card.reference_number || '— not found —'} />
        <Row k="Extracted status" v={card.status_display || (card.extracted_status?.replace(/_/g, ' ') ?? 'uncertain')} />
        {card.required_action && <Row k="Suggested action" v={card.required_action} />}
        {card.confidence != null && <Row k="Confidence" v={`${Math.round(card.confidence * 100)}%`} />}
      </div>
      <p className="mt-3 flex flex-wrap items-center gap-2 text-[11px] text-slate-500">
        {verified ? (
          <span className="chip bg-brand-100 text-brand-700">Corroborated by (mock) status API</span>
        ) : (
          <UnverifiedBadge />
        )}
        {notFound && <span className="chip bg-rose-100 text-rose-700">No matching complaint in your account</span>}
        <span>Derived from a message you pasted — not independently verified.</span>
      </p>
    </CardShell>
  )
}

function EmergencyCard({ card }: CardProps) {
  return (
    <CardShell title={card.title} tone="danger" icon={<AlertTriangle className="mt-0.5 h-4 w-4 text-rose-600" />}>
      <p className="text-sm leading-relaxed text-rose-800">{card.body}</p>
      <a href={`tel:${card.helpline.number}`} className="btn mt-3 w-full bg-rose-600 text-white hover:bg-rose-700">
        Call {card.helpline.label}: {card.helpline.number}
      </a>
      <ul className="mt-3 list-disc space-y-1 pl-5 text-xs text-rose-700">
        {card.actions.map((a: string, i: number) => <li key={i}>{a}</li>)}
      </ul>
    </CardShell>
  )
}

function NoticeCard({ card }: CardProps) {
  const tone = card.level === 'error' ? 'danger' : card.level === 'warn' ? 'warn' : 'default'
  return (
    <CardShell title={card.title} tone={tone as any} icon={<Info className="mt-0.5 h-4 w-4 text-slate-500" />}>
      <p className="text-sm text-slate-700">{card.body}</p>
    </CardShell>
  )
}

function Row({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-dashed border-slate-100 pb-1">
      <span className="shrink-0 text-xs uppercase tracking-wide text-slate-400">{k}</span>
      <span className="text-right font-medium text-slate-800">{v}</span>
    </div>
  )
}

interface CardProps {
  card: any
  onAction: (action: { type: string; option?: string; field?: string; value?: boolean } | null, field?: string, type?: string) => void
}

const RENDERERS: Record<string, (props: CardProps) => JSX.Element | null> = {
  options: OptionsCard,
  guidance: GuidanceCard,
  source_citations: SourceCitationCard,
  information_request: InformationRequestCard,
  validation_issues: ValidationIssuesCard,
  review: ComplaintReviewCard,
  status: StatusCard,
  gov_message_analysis: GovMessageAnalysisCard,
  emergency: EmergencyCard,
  notice: NoticeCard,
}

export function StructuredCardView({ card, onAction }: { card: any; onAction: CardProps['onAction'] }) {
  const Renderer = RENDERERS[card?.type]
  if (!Renderer) return null
  return <Renderer card={card} onAction={onAction} />
}
