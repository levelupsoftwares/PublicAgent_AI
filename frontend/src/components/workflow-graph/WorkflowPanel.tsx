import { useCallback, useEffect, useMemo, useState } from 'react'
import {
  Background, Controls, MarkerType, ReactFlow,
  type Edge, type Node,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { Activity, Radio, X } from 'lucide-react'
import { WorkflowEvent } from '../../api/client'

export const PRIMARY_SEQUENCE = [
  'REQUEST_RECEIVED', 'INTENT_IDENTIFIED', 'AUTHORITY_IDENTIFIED', 'OFFICIAL_DATA_RETRIEVED',
  'REQUIREMENTS_IDENTIFIED', 'OPTIONS_PRESENTED', 'GUIDANCE_PROVIDED', 'INFORMATION_REQUESTED',
  'INFORMATION_VALIDATED', 'COMPLAINT_PREPARED', 'AWAITING_CONFIRMATION', 'COMPLAINT_SUBMITTED',
  'REFERENCE_RECEIVED', 'FOLLOWUP_SCHEDULED',
]

export const GOV_SEQUENCE = [
  'REQUEST_RECEIVED', 'AUTHORITY_IDENTIFIED', 'OFFICIAL_DATA_RETRIEVED', 'STATUS_UPDATED',
]

const NODE_LABELS: Record<string, string> = {
  REQUEST_RECEIVED: 'Request received',
  INTENT_IDENTIFIED: 'Issue classified',
  AUTHORITY_IDENTIFIED: 'Authority identified',
  OFFICIAL_DATA_RETRIEVED: 'Official data retrieved (RAG)',
  REQUIREMENTS_IDENTIFIED: 'Requirements identified',
  OPTIONS_PRESENTED: 'Options presented',
  GUIDANCE_PROVIDED: 'Guidance provided',
  INFORMATION_REQUESTED: 'Information requested',
  INFORMATION_VALIDATED: 'Information validated',
  COMPLAINT_PREPARED: 'Complaint prepared',
  AWAITING_CONFIRMATION: 'Awaiting confirmation',
  COMPLAINT_SUBMITTED: 'Complaint submitted',
  REFERENCE_RECEIVED: 'Reference received',
  FOLLOWUP_SCHEDULED: 'Follow-up scheduled',
  STATUS_UPDATED: 'Status updated',
}

function buildGraph(mode: 'primary' | 'gov', reached: Set<string>, current: string | null):
  { nodes: Node[]; edges: Edge[] } {
  const seq = mode === 'gov' ? GOV_SEQUENCE : PRIMARY_SEQUENCE
  const nodes: Node[] = []
  const edges: Edge[] = []
  const n = seq.length
  const colGap = 215
  const width = 190
  const height = 66

  seq.forEach((evt, i) => {
    const isCurrent = current === evt && !reached.has(evt) ||
      (current === evt && reached.has(evt)) // current is latest even if seen
    const done = reached.has(evt) && current !== evt
    const state = done ? 'done' : isCurrent ? 'current' : 'upcoming'
    const fill = state === 'done' ? '#065f46' : state === 'current' ? '#047857' : '#f1f5f9'
    const stroke = state === 'upcoming' ? '#cbd5e1' : '#047857'
    const textColor = state === 'upcoming' ? '#94a3b8' : '#ffffff'
    nodes.push({
      id: evt,
      position: { x: (i % 4) * colGap, y: Math.floor(i / 4) * (height + 34) + 14 },
      data: {
        label: (
          <div className="flex items-center gap-2 px-1" style={{ width: width - 24 }}>
            <span
              className="grid h-5 w-5 shrink-0 place-items-center rounded-full text-[10px] font-bold"
              style={{
                background: state === 'upcoming' ? '#e2e8f0' : 'rgba(255,255,255,.22)',
                color: textColor,
              }}
            >
              {state === 'done' ? '✓' : state === 'current' ? '●' : '○'}
            </span>
            <span className="text-[10.5px] font-semibold leading-tight" style={{ color: textColor }}>
              {NODE_LABELS[evt] || evt}
            </span>
          </div>
        ),
      },
      style: {
        background: fill, border: `1.5px solid ${stroke}`, borderRadius: 10,
        width, height, padding: 4, boxShadow: state === 'current' ? '0 0 0 3px rgba(16,185,129,.25)' : 'none',
      },
    })
    if (i > 0) {
      const prev = seq[i - 1]
      const active = reached.has(evt)
      edges.push({
        id: `${prev}->${evt}`, source: prev, target: evt, animated: active && !reached.has(seq[Math.min(seq.indexOf(evt) + 1, n - 1)]) && current === evt,
        style: { stroke: active ? '#10b981' : '#cbd5e1', strokeWidth: active ? 2 : 1.5 },
        markerEnd: { type: MarkerType.ArrowClosed, color: active ? '#10b981' : '#94a3b8', width: 14, height: 14 },
      })
    }
  })
  return { nodes, edges }
}

export default function WorkflowPanel({
  events, live, onClose,
}: {
  events: WorkflowEvent[]
  live: boolean
  onClose?: () => void
}) {
  // A pasted gov-message turn switches the visible sequence; we show whichever
  // sequence has more matching events this conversation (primary by default).
  const [mode, setMode] = useState<'primary' | 'gov'>('primary')

  const govHits = events.filter((e) => e.event_type === 'STATUS_UPDATED').length
  useEffect(() => {
    if (govHits > 0 && events.some((e) => e.event_type === 'COMPLAINT_SUBMITTED' || e.event_type === 'FOLLOWUP_SCHEDULED')) {
      setMode('primary')
    } else if (govHits > 0) {
      setMode('gov')
    }
  }, [govHits, events])

  const reached = useMemo(() => {
    const set = new Set<string>()
    for (const e of events) set.add(e.event_type)
    return set
  }, [events])

  const current = events.length ? events[events.length - 1].event_type : null
  const { nodes, edges } = useMemo(() => buildGraph(mode, reached, current), [mode, reached, current])

  const fitDone = useCallback((instance: any) => {
    setTimeout(() => instance?.fitView({ padding: 0.12, maxZoom: 1 }), 40)
  }, [])

  return (
    <div className="flex h-full flex-col bg-slate-900">
      <div className="flex items-center justify-between border-b border-slate-700 px-4 py-3">
        <div className="flex items-center gap-2 text-white">
          <Activity className="h-4 w-4 text-brand-400" />
          <div>
            <p className="text-sm font-semibold leading-tight">Agent workflow</p>
            <p className="text-[11px] text-slate-400">
              {mode === 'gov' ? 'Government-message graph' : 'Primary complaint graph'} · {reached.size}/{(mode === 'gov' ? GOV_SEQUENCE : PRIMARY_SEQUENCE).length} steps
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {live ? (
            <span className="chip bg-brand-500/15 text-brand-300">
              <Radio className="h-3 w-3 animate-pulse" /> live
            </span>
          ) : (
            <span className="chip bg-slate-700 text-slate-300">idle</span>
          )}
          {onClose && (
            <button className="btn-ghost !px-2 !min-h-0 text-slate-300 hover:bg-slate-800 lg:hidden" onClick={onClose}>
              <X className="h-4 w-4" />
            </button>
          )}
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          fitView
          proOptions={{ hideAttribution: true }}
          nodesDraggable={false}
          nodesConnectable={false}
          edgesFocusable={false}
          onInit={fitDone}
          className="bg-slate-900"
        >
          <Background color="#1e293b" gap={18} />
          <Controls showInteractive={false} className="!bottom-3 !left-3" />
        </ReactFlow>
      </div>
      <div className="border-t border-slate-700 px-4 py-2 text-[11px] text-slate-400">
        ✓ completed · ● current · ○ upcoming — driven by safe workflow events only
      </div>
    </div>
  )
}
