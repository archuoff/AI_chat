import clsx from 'clsx'
import { ArrowDown } from 'lucide-react'
import { AnimatePresence, motion } from 'motion/react'
import { memo, useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { api, streamChat } from '../lib/api'
import { storage, uid } from '../lib/storage'
import type { Attachment } from '../lib/images'
import { useMedia } from '../lib/useMedia'
import type { UIMessage } from '../lib/types'
import { buildFilters, Composer, type DomainScope } from './Composer'
import { MessageView } from './MessageView'
import { SourcesPanel } from './SourcesPanel'
import { Welcome } from './Welcome'

type Props = {
  sessionId: string
  onTouched: (sessionId: string, firstQuestion: string) => void
  sourcesOpen: boolean
  onSourcesOpen: (open: boolean) => void
}

export const ChatView = memo(function ChatView({ sessionId, onTouched, sourcesOpen, onSourcesOpen }: Props) {
  const [messages, setMessages] = useState<UIMessage[]>([])
  const [busy, setBusy] = useState(false)
  const [domain, setDomain] = useState<DomainScope>('all')
  const [domainOptions, setDomainOptions] = useState<string[]>(['all'])

  useEffect(() => {
    api.domains().then((ds) => setDomainOptions(['all', ...ds.map((d) => d.id).filter((id) => id !== 'unassigned')])).catch(() => {})
  }, [])
  const [activeMsg, setActiveMsg] = useState<string | null>(null)
  const [highlight, setHighlight] = useState<number | null>(null)
  const abortRef = useRef<AbortController | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)
  const pinnedRef = useRef(true)
  const [awayFromBottom, setAwayFromBottom] = useState(false)
  const wide = useMedia('(min-width: 1280px)')

  // load a conversation: local cache first (keeps sources), otherwise the server's memory
  useEffect(() => {
    abortRef.current?.abort()
    setBusy(false)
    setHighlight(null)
    setActiveMsg(null)
    const cached = storage.messages(sessionId)
    if (cached) {
      setMessages(cached.map((m) => ({ ...m, streaming: false })))
      return
    }
    setMessages([])
    let cancelled = false
    api
      .history(sessionId)
      .then((h) => {
        if (!cancelled && h.length) setMessages(h.map((m) => ({ id: uid(), role: m.role, content: m.content })))
      })
      .catch(() => {})
    return () => {
      cancelled = true
    }
  }, [sessionId])

  useEffect(() => {
    if (!busy && messages.length) storage.saveMessages(sessionId, messages)
  }, [busy, messages, sessionId])

  useEffect(() => {
    const el = scrollRef.current
    if (!el) return
    if (messages.length === 0) el.scrollTo({ top: 0 })
    else if (pinnedRef.current) el.scrollTo({ top: el.scrollHeight })
  }, [messages])

  const panelMsg = useMemo(() => {
    const assistants = messages.filter((m) => m.role === 'assistant')
    return assistants.find((m) => m.id === activeMsg) ?? assistants[assistants.length - 1]
  }, [messages, activeMsg])

  const send = useCallback(
    async (typed: string, attachments: Attachment[] = []) => {
      if (busy) return
      const text = typed || (attachments.length ? 'What does this image show, and what do our documents say about it?' : '')
      if (!text) return
      const user: UIMessage = { id: uid(), role: 'user', content: typed, images: attachments.map((a) => a.thumb) }
      const asst: UIMessage = { id: uid(), role: 'assistant', content: '', streaming: true, steps: [] }
      setMessages((m) => [...m, user, asst])
      setActiveMsg(asst.id)
      setHighlight(null)
      setBusy(true)
      pinnedRef.current = true
      onTouched(sessionId, typed || 'Image question')
      const update = (fn: (m: UIMessage) => UIMessage) => setMessages((ms) => ms.map((m) => (m.id === asst.id ? fn(m) : m)))
      const ctrl = new AbortController()
      abortRef.current = ctrl
      const filters = buildFilters(domain)
      const started = performance.now()
      try {
        await streamChat(
          { session_id: sessionId, message: text, filters, images: attachments.map((a) => a.full) },
          (ev) => {
            if (ev.type === 'status') update((m) => ({ ...m, steps: [...(m.steps ?? []), { step: ev.step, message: ev.message }] }))
            else if (ev.type === 'token') update((m) => ({ ...m, content: m.content + ev.text }))
            else if (ev.type === 'reset') update((m) => ({ ...m, content: '' }))
            else if (ev.type === 'final')
              update((m) => ({
                ...m,
                content: ev.answer,
                sources: ev.sources,
                mode: ev.mode,
                intent: ev.intent,
                notices: ev.notices,
                timings: ev.timings,
                elapsedMs: performance.now() - started,
                streaming: false,
              }))
            else if (ev.type === 'error') update((m) => ({ ...m, error: ev.message, streaming: false }))
          },
          ctrl.signal,
        )
      } catch (e) {
        const aborted = e instanceof DOMException && e.name === 'AbortError'
        update((m) => ({
          ...m,
          streaming: false,
          error: aborted ? undefined : `Could not reach the assistant: ${(e as Error).message}`,
          notices: aborted ? ['Generation stopped.'] : m.notices,
        }))
      } finally {
        update((m) => ({ ...m, streaming: false }))
        setBusy(false)
        abortRef.current = null
      }
    },
    [busy, onTouched, domain, sessionId],
  )

  const cite = (msgId: string, n: number) => {
    setActiveMsg(msgId)
    setHighlight(n)
    onSourcesOpen(true)
  }

  const panel = <SourcesPanel sources={panelMsg?.sources ?? []} highlight={highlight} onClose={() => onSourcesOpen(false)} />

  return (
    <div className="flex min-h-0 flex-1">
      <div className={clsx('relative flex min-w-0 flex-1 flex-col', messages.length ? 'bg-[#fbfcff]' : 'bg-tt-canvas')}>
        <div
          ref={scrollRef}
          className="scrollbar-thin flex-1 overflow-y-auto"
          onScroll={(e) => {
            const el = e.currentTarget
            pinnedRef.current = el.scrollHeight - el.scrollTop - el.clientHeight < 120
            setAwayFromBottom(el.scrollHeight - el.scrollTop - el.clientHeight > 400)
          }}
        >
          {messages.length === 0 ? (
            <Welcome onAsk={send} domains={domainOptions.filter((d) => d !== 'all')} />
          ) : (
            <div className="mx-auto w-full max-w-[46rem] space-y-9 px-4 pt-8 pb-10 sm:px-6">
              {messages.map((m) => (
                <MessageView
                  key={m.id}
                  msg={m}
                  active={m.id === panelMsg?.id && m.role === 'assistant'}
                  onCite={(n) => cite(m.id, n)}
                  onShowSources={() => {
                    setActiveMsg(m.id)
                    setHighlight(null)
                    onSourcesOpen(true)
                  }}
                />
              ))}
            </div>
          )}
        </div>
        {awayFromBottom && messages.length > 0 && (
          <button
            onClick={() => {
              pinnedRef.current = true
              scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
            }}
            className="absolute bottom-[132px] left-1/2 z-10 flex h-9 w-9 -translate-x-1/2 items-center justify-center rounded-full border border-tt-line bg-white text-tt-navy shadow-lift transition hover:bg-tt-mist"
            aria-label="Jump to latest message"
            title="Jump to latest"
          >
            <ArrowDown size={17} />
          </button>
        )}
        <Composer
          busy={busy}
          domain={domain}
          domainOptions={domainOptions}
          onDomain={setDomain}
          onSend={send}
          onStop={() => abortRef.current?.abort()}
        />
      </div>

      {/* layout change is instant (animating width re-lays out the whole chat every frame) */}
      {wide && sourcesOpen && <aside className="w-[380px] shrink-0 border-l border-tt-line bg-white">{panel}</aside>}

      <AnimatePresence>
        {!wide && sourcesOpen && (
          <>
            <motion.div
              className="fixed inset-0 z-30 bg-tt-midnight/40 xl:hidden"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              onClick={() => onSourcesOpen(false)}
            />
            <motion.aside
              className="fixed inset-y-0 right-0 z-40 w-[min(400px,92vw)] bg-white shadow-2xl xl:hidden"
              initial={{ x: '100%' }}
              animate={{ x: 0 }}
              exit={{ x: '100%' }}
              transition={{ type: 'spring', damping: 30, stiffness: 300 }}
            >
              {panel}
            </motion.aside>
          </>
        )}
      </AnimatePresence>
    </div>
  )
})
