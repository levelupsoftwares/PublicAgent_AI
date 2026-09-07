// Typed API client — same-origin (dev: Vite proxy; prod: FastAPI serves dist/).
export interface User {
  id: string
  name: string
  email: string
  phone?: string | null
}

export interface WorkflowEvent {
  event_type: string
  timestamp: string
  payload: Record<string, unknown>
}

export interface Message {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  structured_payload?: StructuredCard | null
  workflow_events?: WorkflowEvent[] | null
  created_at: string
}

export interface StructuredCard {
  type: string
  [key: string]: any
}

export interface ChatAction {
  type: 'option' | 'skip' | 'confirm' | 'cancel'
  option?: string
  field?: string
  value?: boolean
}

export interface Complaint {
  id: string
  reference_number: string | null
  category: string
  department: string
  jurisdiction: string | null
  status: string
  description: string
  structured_fields: Record<string, any>
  unverified_fields: string[]
  submitted_at: string | null
  updated_at: string
  next_check_at: string | null
}

export interface ComplaintEvent {
  id: string
  event_type: string
  old_status: string | null
  new_status: string | null
  metadata: Record<string, any>
  created_at: string
}

export interface ComplaintDetail extends Complaint {
  events: ComplaintEvent[]
  evidence: { id: string; filename: string; content_type: string; extracted_summary: string | null; created_at: string }[]
}

export interface Notification {
  id: string
  complaint_id: string | null
  title: string
  body: string
  read: boolean
  created_at: string
}

export interface ConversationSummary {
  id: string
  title: string | null
  complaint_id: string | null
  created_at: string
  updated_at: string
}

const TOKEN_KEY = 'publicagent_token'

export function getToken(): string | null {
  return localStorage.getItem(TOKEN_KEY)
}
export function setToken(t: string | null) {
  if (t) localStorage.setItem(TOKEN_KEY, t)
  else localStorage.removeItem(TOKEN_KEY)
}

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' }
  const token = getToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  const resp = await fetch(path, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  })
  if (resp.status === 401) {
    setToken(null)
    throw new ApiError(401, 'Session expired — please log in again.')
  }
  if (!resp.ok) {
    let detail = `${resp.status} ${resp.statusText}`
    try {
      const data = await resp.json()
      if (data?.detail) detail = typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail)
    } catch { /* ignore */ }
    throw new ApiError(resp.status, detail)
  }
  return resp.json() as Promise<T>
}

export const api = {
  // auth
  demoLogin: () => request<{ access_token: string; user: User }>('POST', '/api/auth/demo-login'),
  login: (email: string, password: string) =>
    request<{ access_token: string; user: User }>('POST', '/api/auth/login', { email, password }),
  register: (name: string, email: string, password: string, phone?: string) =>
    request<{ access_token: string; user: User }>('POST', '/api/auth/register', { name, email, password, phone }),

  // chat
  chat: (conversationId: string | null, content: string, action?: ChatAction) =>
    request<{ conversation_id: string; messages: Message[]; workflow_events: WorkflowEvent[]; agent_phase: string }>(
      'POST', '/api/chat', { conversation_id: conversationId, content, action }),
  conversations: () => request<ConversationSummary[]>('GET', '/api/conversations'),
  conversationMessages: (id: string) => request<Message[]>('GET', `/api/conversations/${id}/messages`),
  conversationEvents: (id: string) =>
    request<{ conversation_id: string; events: WorkflowEvent[]; agent_state: Record<string, any> }>(
      'GET', `/api/conversations/${id}/events`),

  // complaints
  complaints: () => request<Complaint[]>('GET', '/api/complaints'),
  complaint: (id: string) => request<ComplaintDetail>('GET', `/api/complaints/${id}`),

  // evidence
  uploadEvidence: async (file: File, conversationId: string | null) => {
    const form = new FormData()
    form.append('file', file)
    if (conversationId) form.append('conversation_id', conversationId)
    const headers: Record<string, string> = {}
    const token = getToken()
    if (token) headers['Authorization'] = `Bearer ${token}`
    const resp = await fetch('/api/evidence', { method: 'POST', headers, body: form })
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}))
      throw new ApiError(resp.status, data?.detail || 'Upload failed')
    }
    return resp.json() as Promise<{ id: string; filename: string; extracted_summary: string | null; label: string }>
  },

  // gov message
  analyzeGovMessage: (text: string) =>
    request<Record<string, any>>('POST', '/api/gov-message/analyze', { text }),

  // notifications
  notifications: (since?: string) =>
    request<Notification[]>('GET', `/api/notifications${since ? `?since=${encodeURIComponent(since)}` : ''}`),
  markRead: (ids: string[]) => request<{ marked: number }>('POST', '/api/notifications/mark-read', { ids }),

  // demo
  advanceStatus: (payload: { complaint_id?: string; reference_number?: string }) =>
    request<{ force_advance: Record<string, any>; scheduler_run: Record<string, any> }>(
      'POST', '/api/demo/advance-status', payload),
}
