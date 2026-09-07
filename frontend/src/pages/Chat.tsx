import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  Landmark, LayoutDashboard, MessageSquarePlus, Paperclip, PanelRightOpen, Send, ShieldCheck, X,
} from 'lucide-react'
import { api, ChatAction, Message, Notification, WorkflowEvent } from '../api/client'
import { useAuth } from '../state/AuthContext'
import { StructuredCardView } from '../components/ui-cards'
import WorkflowPanel from '../components/workflow-graph/WorkflowPanel'
import NotificationBell from '../components/dashboard/NotificationBell'

export default function Chat() {
  const { conversationId } = useParams()
  const navigate = useNavigate()
  const { user } = useAuth()

  const [messages, setMessages] = useState<Message[]>([])
  const [events, setEvents] = useState<WorkflowEvent[]>([])
  const [input, setInput] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [convId, setConvId] = useState<string | null>(conversationId || null)
  const [conversations, setConversations] = useState<{ id: string; title: string | null; updated_at: string }[]>([])
  const [showWorkflow, setShowWorkflow] = useState(false)
  const [pendingQuestion, setPendingQuestion] = useState<{ field: string; label: string; type: string } | null>(null)
  const [uploadInfo, setUploadInfo] = useState<string>('')
  const bottomRef = useRef<HTMLDivElement>(null)
  const fileRef = useRef<HTMLInputElement>(null)

  const loadConversations = useCallback(() => {
    api.conversations().then(setConversations).catch(() => {})
  }, [])

  // Load a conversation's history + events
  useEffect(() => {
    if (!conversationId) {
      setMessages([])
      setEvents([])
      setConvId(null)
      return
    }
    setConvId(conversationId)
    api.conversationMessages(conversationId).then((msgs) => {
      setMessages(msgs)
      const evs: WorkflowEvent[] = []
      for (const m of msgs) for (const e of m.workflow_events || []) evs.push(e)
      setEvents(evs)
    }).catch(() => setError('Could not load conversation'))
    api.conversationEvents(conversationId).then((r) => {
      if (r.events.length) setEvents(r.events)
    }).catch(() => {})
    loadConversations()
  }, [conversationId, loadConversations])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, busy])

  const send = async (content: string, action?: ChatAction, displayOverride?: string) => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      const r = await api.chat(convId, content, action)
      setConvId(r.conversation_id)
      setMessages((prev) => [
        ...prev,
        ...(displayOverride
          ? [{ id: `local-${Date.now()}`, role: 'user' as const, content: displayOverride, created_at: new Date().toISOString() }]
          : []),
        ...r.messages,
      ])
      setEvents((prev) => [...prev, ...r.workflow_events])
      setPendingQuestion(null)
      setInput('')
      if (!conversationId) {
        navigate(`/chat/${r.conversation_id}`, { replace: true })
      }
      loadConversations()
    } catch (err: any) {
      setError(err?.message || 'Request failed')
    } finally {
      setBusy(false)
    }
  }

  const submitText = async (e?: React.FormEvent) => {
    e?.preventDefault()
    const text = input.trim()
    if (!text || busy) return
    // optimistic user bubble
    setMessages((prev) => [...prev, { id: `local-${Date.now()}`, role: 'user', content: text, created_at: new Date().toISOString() }])
    if (pendingQuestion) {
      // The backend re-asks; we simply send text — the agent extracts fields.
      setPendingQuestion(null)
    }
    await send(text)
  }

  const onCardAction = async (action: any, field?: string, type?: string) => {
    if (action === null && field) {
      // "Answer" button on an information request → focus the composer for that field
      setPendingQuestion({ field, label: field, type: type || 'text' })
      return
    }
    if (!action) return
    const labels: Record<string, string> = {
      option_file: 'File a Formal Complaint', option_report: 'Report the Incident',
      option_understand: 'Understand My Options', option_not_sure: "I'm Not Sure What To Do",
    }
    let display: string | undefined
    if (action.type === 'option') display = labels[`option_${action.option}`]
    if (action.type === 'skip') display = 'Skipped that field'
    if (action.type === 'confirm') display = action.value ? 'Confirm & Submit' : 'Go back'
    await send('', action as ChatAction, display)
  }

  const onUpload = async (file: File) => {
    setUploadInfo(`Uploading ${file.name}…`)
    try {
      const r = await api.uploadEvidence(file, convId)
      setUploadInfo(`${file.name} — ${r.label}`)
      setMessages((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}`, role: 'user',
          content: `📎 Attached: ${file.name}`, created_at: new Date().toISOString(),
          structured_payload: {
            type: 'notice', level: 'info', title: `Attachment: ${file.name}`,
            body: r.extracted_summary || 'Stored. AI extraction unavailable — nothing was inferred.',
          },
        } as any,
      ])
      setTimeout(() => setUploadInfo(''), 6000)
    } catch (err: any) {
      setUploadInfo('')
      setError(err?.message || 'Upload failed')
    }
  }

  return (
    <div className="flex h-screen flex-col bg-slate-100">
      {/* Top bar */}
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-2.5">
        <div className="flex items-center gap-3">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600 text-white">
            <Landmark className="h-5 w-5" />
          </div>
          <div>
            <p className="text-sm font-bold leading-tight text-slate-900">PublicAgent AI</p>
            <p className="text-[11px] text-slate-400">Demo data only — no real complaints are filed</p>
          </div>
        </div>
        <div className="flex items-center gap-1.5">
          <NotificationBell />
          <Link to="/dashboard" className="btn-secondary !py-1.5 !min-h-0 text-xs">
            <LayoutDashboard className="h-4 w-4" /> My Complaints
          </Link>
          <button
            className="btn-secondary !py-1.5 !min-h-0 text-xs xl:hidden"
            onClick={() => setShowWorkflow((v) => !v)}
          >
            <PanelRightOpen className="h-4 w-4" /> Workflow
          </button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        {/* Left: conversations */}
        <aside className="hidden w-60 shrink-0 flex-col border-r border-slate-200 bg-white md:flex">
          <div className="p-3">
            <button
              className="btn-primary w-full !py-2 text-xs"
              onClick={() => { navigate('/chat'); setMessages([]); setEvents([]); setConvId(null) }}
            >
              <MessageSquarePlus className="h-4 w-4" /> New conversation
            </button>
          </div>
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto px-2 pb-3">
            <p className="px-2 pb-1 pt-2 text-[11px] font-semibold uppercase tracking-wide text-slate-400">History</p>
            {conversations.map((c) => (
              <button
                key={c.id}
                onClick={() => navigate(`/chat/${c.id}`)}
                className={`mb-1 w-full rounded-lg px-3 py-2 text-left text-sm transition ${
                  c.id === convId ? 'bg-brand-50 text-brand-800' : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <span className="line-clamp-2 leading-snug">{c.title || 'Conversation'}</span>
              </button>
            ))}
            {!conversations.length && (
              <p className="px-2 py-4 text-xs text-slate-400">No conversations yet — describe a problem to start.</p>
            )}
          </div>
          <div className="border-t border-slate-100 p-3">
            <p className="flex items-center gap-1.5 text-[11px] text-slate-400">
              <ShieldCheck className="h-3.5 w-3.5 text-brand-600" /> Logged in as {user?.name}
            </p>
          </div>
        </aside>

        {/* Center: chat */}
        <main className="flex min-w-0 flex-1 flex-col">
          <div className="scroll-thin min-h-0 flex-1 overflow-y-auto">
            <div className="mx-auto max-w-3xl space-y-4 px-4 py-6">
              {!messages.length && (
                <WelcomeCard onExample={(t) => send(t)} />
              )}
              {messages.map((m) => <MessageRow key={m.id} m={m} onAction={onCardAction} />)}
              {busy && (
                <div className="flex gap-2 px-1">
                  <span className="h-2 w-2 animate-bounce rounded-full bg-brand-500" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-brand-500 [animation-delay:120ms]" />
                  <span className="h-2 w-2 animate-bounce rounded-full bg-brand-500 [animation-delay:240ms]" />
                </div>
              )}
              <div ref={bottomRef} />
            </div>
          </div>

          {/* Composer */}
          <div className="border-t border-slate-200 bg-white px-4 py-3">
            {error && (
              <p className="mx-auto mb-2 max-w-3xl rounded-lg bg-rose-50 px-3 py-2 text-xs text-rose-700">{error}</p>
            )}
            {uploadInfo && (
              <p className="mx-auto mb-2 max-w-3xl rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">{uploadInfo}</p>
            )}
            <form onSubmit={submitText} className="mx-auto flex max-w-3xl items-end gap-2">
              <input
                ref={fileRef} type="file" className="hidden" accept=".jpg,.jpeg,.png,.pdf"
                onChange={(e) => {
                  const f = e.target.files?.[0]
                  if (f) onUpload(f)
                  e.target.value = ''
                }}
              />
              <button
                type="button" className="btn-secondary !px-3" title="Attach evidence (JPG/PNG/PDF, ≤10MB)"
                onClick={() => fileRef.current?.click()}
              >
                <Paperclip className="h-4 w-4" />
              </button>
              <textarea
                className="max-h-32 min-h-[44px] flex-1 resize-none rounded-xl border border-slate-300 px-3.5 py-2.5 text-sm focus:border-brand-500 focus:outline-none"
                placeholder={pendingQuestion ? `Answering: ${pendingQuestion.label} — type your answer…` : 'Describe your problem, answer a question, or paste a government SMS…'}
                value={input}
                rows={1}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === 'Enter' && !e.shiftKey) submitText(e as any)
                }}
              />
              <button type="submit" className="btn-primary !px-4" disabled={busy || !input.trim()}>
                <Send className="h-4 w-4" />
              </button>
            </form>
            <p className="mx-auto mt-1.5 max-w-3xl text-[11px] text-slate-400">
              The agent never files anything without your explicit confirmation. Guidance is
              informational only — not legal advice.
            </p>
          </div>
        </main>

        {/* Right: workflow panel */}
        <aside className="hidden w-[340px] shrink-0 xl:block">
          <WorkflowPanel events={events} live={busy} />
        </aside>
        {showWorkflow && (
          <div className="fixed inset-0 z-40 flex xl:hidden">
            <div className="flex-1 bg-black/40" onClick={() => setShowWorkflow(false)} />
            <div className="relative w-[88vw] max-w-sm">
              <WorkflowPanel events={events} live={busy} onClose={() => setShowWorkflow(false)} />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function MessageRow({ m, onAction }: { m: Message; onAction: any }) {
  if (m.role === 'user') {
    return (
      <div className="flex justify-end">
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-brand-600 px-4 py-2.5 text-sm text-white shadow-sm">
          {m.content}
        </div>
      </div>
    )
  }
  return (
    <div className="flex flex-col items-start gap-2">
      {m.content && (
        <div className="max-w-[92%] rounded-2xl rounded-bl-md border border-slate-200 bg-white px-4 py-2.5 text-sm leading-relaxed text-slate-800 shadow-sm">
          {m.content}
        </div>
      )}
      {m.structured_payload && (
        <div className="w-full max-w-[92%]">
          <StructuredCardView card={m.structured_payload} onAction={onAction} />
        </div>
      )}
    </div>
  )
}

function WelcomeCard({ onExample }: { onExample: (text: string) => void }) {
  return (
    <div className="card p-6">
      <h2 className="text-lg font-bold text-slate-900">Hi — I'm your PublicAgent.</h2>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">
        Tell me what happened in your own words. I'll figure out what kind of issue it is,
        which authority typically handles it, and what your options are — I never file
        anything without your explicit confirmation.
      </p>
      <div className="mt-4 space-y-2">
        <p className="text-xs font-semibold uppercase tracking-wide text-slate-400">Try an example</p>
        {[
          'A police officer misbehaved with me.',
          'My electricity bill is wildly inflated and the meter seems faulty.',
        ].map((t) => (
          <button
            key={t}
            onClick={() => onExample(t)}
            className="w-full rounded-lg border border-slate-200 px-3 py-2.5 text-left text-sm text-slate-700 transition hover:border-brand-400 hover:bg-brand-50/50"
          >
            “{t}”
          </button>
        ))}
      </div>
    </div>
  )
}
