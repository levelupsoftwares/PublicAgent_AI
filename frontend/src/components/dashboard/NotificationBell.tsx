import { useEffect, useRef, useState } from 'react'
import { Bell } from 'lucide-react'
import { api, Notification } from '../../api/client'

export default function NotificationBell() {
  const [items, setItems] = useState<Notification[]>([])
  const [open, setOpen] = useState(false)
  const [since, setSince] = useState<string | undefined>(undefined)
  const seen = useRef<Set<string>>(new Set())
  const [toast, setToast] = useState<Notification | null>(null)

  useEffect(() => {
    let stop = false
    const poll = async () => {
      try {
        const list = await api.notifications(since)
        if (stop) return
        if (list.length) {
          setItems((prev) => {
            const merged = [...list, ...prev.filter((p) => !list.some((l) => l.id === p.id))]
            return merged.slice(0, 50)
          })
          for (const n of list) {
            if (!seen.current.has(n.id)) {
              seen.current.add(n.id)
              setToast(n)
              setTimeout(() => setToast((t) => (t?.id === n.id ? null : t)), 6500)
            }
          }
          const latest = list[0].created_at
          setSince(latest)
        }
      } catch { /* ignore polling errors */ }
    }
    poll()
    const t = setInterval(poll, 6000)
    return () => { stop = true; clearInterval(t) }
  }, [since])

  const unread = items.filter((n) => !n.read).length

  return (
    <div className="relative">
      <button
        className="btn-secondary relative !px-2.5 !py-1.5 !min-h-0"
        onClick={async () => {
          setOpen((v) => !v)
          if (!open && unread) {
            try {
              await api.markRead(items.filter((n) => !n.read).map((n) => n.id))
              setItems((prev) => prev.map((n) => ({ ...n, read: true })))
            } catch { /* ignore */ }
          }
        }}
        title="Notifications"
      >
        <Bell className="h-4 w-4" />
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 grid h-4 min-w-4 place-items-center rounded-full bg-rose-500 px-1 text-[10px] font-bold text-white">
            {unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 z-50 mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-lg">
          <p className="border-b border-slate-100 px-4 py-2.5 text-sm font-semibold text-slate-700">Notifications</p>
          <div className="scroll-thin max-h-80 overflow-y-auto">
            {items.length === 0 && <p className="px-4 py-6 text-center text-xs text-slate-400">Nothing yet — status changes will appear here.</p>}
            {items.map((n) => (
              <div key={n.id} className="border-b border-slate-50 px-4 py-3">
                <p className="text-xs font-semibold text-slate-800">{n.title}</p>
                <p className="mt-0.5 text-xs leading-relaxed text-slate-500">{n.body}</p>
                <p className="mt-1 text-[10px] text-slate-400">{new Date(n.created_at).toLocaleString()}</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {toast && (
        <div className="fixed right-4 top-16 z-50 w-80 animate-[fadeIn_.2s_ease-out] rounded-xl border border-brand-200 bg-white p-4 shadow-xl">
          <p className="text-xs font-bold text-brand-700">{toast.title}</p>
          <p className="mt-1 text-xs text-slate-600">{toast.body}</p>
        </div>
      )}
    </div>
  )
}
