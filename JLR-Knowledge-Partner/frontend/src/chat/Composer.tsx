import clsx from 'clsx'
import { ArrowUp, Check, ChevronDown, ImagePlus, LoaderCircle, Paperclip, Square, X } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'
import { api } from '../lib/api'
import { DomainIcon, domainVisual } from '../lib/domains'
import { imageFiles, MAX_ATTACHMENTS, prepareImage, type Attachment } from '../lib/images'

// 'all' = every domain this user may query (the server enforces the user's allowed domains)
export type DomainScope = string

export function buildFilters(domain: DomainScope): Record<string, unknown> | null {
  return domain !== 'all' ? { domain } : null
}

type Props = {
  busy: boolean
  domain: DomainScope
  domainOptions: string[]
  onDomain: (d: DomainScope) => void
  onSend: (text: string, images: Attachment[]) => void
  onStop: () => void
}

export function Composer({ busy, domain, domainOptions, onDomain, onSend, onStop }: Props) {
  const [text, setText] = useState('')
  const [menu, setMenu] = useState<null | 'domain'>(null)
  const [images, setImages] = useState<Attachment[]>([])
  const [preparing, setPreparing] = useState(0)
  const [dragging, setDragging] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const ref = useRef<HTMLTextAreaElement>(null)
  const fileInput = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    el.style.height = '0px'
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`
    el.style.overflowY = el.scrollHeight > 180 ? 'auto' : 'hidden' // no scroll arrows until text really overflows
  }, [text])

  useEffect(() => {
    if (!error) return
    const t = setTimeout(() => setError(null), 4000)
    return () => clearTimeout(t)
  }, [error])

  const addFiles = async (files: File[]) => {
    if (!files.length) return
    const room = MAX_ATTACHMENTS - images.length
    if (room <= 0) {
      setError(`You can attach up to ${MAX_ATTACHMENTS} images`)
      return
    }
    if (files.length > room) setError(`Only ${room} more image${room === 1 ? '' : 's'} can be attached`)
    api.warmup()
    const take = files.slice(0, room)
    setPreparing((n) => n + take.length)
    for (const f of take) {
      try {
        const a = await prepareImage(f)
        setImages((cur) => (cur.length < MAX_ATTACHMENTS ? [...cur, a] : cur))
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setPreparing((n) => n - 1)
      }
    }
    ref.current?.focus()
  }

  const canSend = (text.trim() || images.length) && !preparing && !busy

  const submit = () => {
    if (!canSend) return
    onSend(text.trim(), images)
    setText('')
    setImages([])
  }

  return (
    <div className="mx-auto w-full max-w-3xl px-4 pb-5 sm:px-6">
      <div
        onDragOver={(e) => {
          if (Array.from(e.dataTransfer.items).some((i) => i.kind === 'file')) {
            e.preventDefault()
            setDragging(true)
          }
        }}
        onDragLeave={(e) => {
          if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false)
        }}
        onDrop={(e) => {
          e.preventDefault()
          setDragging(false)
          addFiles(imageFiles(e.dataTransfer.files))
        }}
        className={clsx(
          'relative rounded-[26px] border bg-white p-2.5 shadow-[0_10px_36px_-14px_rgba(0,27,91,0.22)] transition focus-within:border-tt-periwinkle/70 focus-within:shadow-[0_12px_40px_-12px_rgba(0,0,179,0.28)]',
          dragging ? 'border-tt-electric ring-4 ring-tt-electric/10' : 'border-tt-line',
        )}
      >
        {dragging && (
          <div className="pointer-events-none absolute inset-0 z-10 flex items-center justify-center rounded-[26px] bg-tt-electric/[0.05]">
            <span className="inline-flex items-center gap-2 rounded-xl bg-white px-3 py-1.5 text-[13px] font-semibold text-tt-electric shadow-card">
              <ImagePlus size={16} /> Drop images to attach
            </span>
          </div>
        )}

        {(images.length > 0 || preparing > 0) && (
          <div className="flex flex-wrap gap-2 px-2 pt-1.5 pb-1">
            {images.map((a) => (
              <div key={a.id} className="group relative h-16 w-16 overflow-hidden rounded-xl border border-tt-line bg-tt-mist">
                <img src={a.thumb} alt={a.name} className="h-full w-full object-cover" />
                <button
                  onClick={() => setImages((cur) => cur.filter((x) => x.id !== a.id))}
                  className="absolute top-1 right-1 flex h-5 w-5 items-center justify-center rounded-full bg-tt-navy/80 text-white opacity-0 transition group-hover:opacity-100 focus:opacity-100"
                  aria-label={`Remove ${a.name}`}
                >
                  <X size={12} />
                </button>
              </div>
            ))}
            {Array.from({ length: preparing }, (_, i) => (
              <div key={`p${i}`} className="flex h-16 w-16 items-center justify-center rounded-xl border border-dashed border-tt-line bg-tt-mist">
                <LoaderCircle size={16} className="animate-spin text-tt-electric" />
              </div>
            ))}
          </div>
        )}

        <textarea
          ref={ref}
          rows={1}
          value={text}
          onFocus={api.warmup}
          onChange={(e) => {
            setText(e.target.value)
            api.warmup()
          }}
          onPaste={(e) => {
            const files = imageFiles(e.clipboardData.files)
            if (files.length) {
              e.preventDefault()
              addFiles(files)
            }
          }}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              submit()
            }
          }}
          placeholder={
            images.length
              ? 'Ask about the image… (or just send it)'
              : domain === 'all'
                ? ''
                : `Ask the ${domainVisual(domain).label} knowledge base…`
          }
          className="block max-h-[180px] w-full resize-none bg-transparent px-3.5 pt-2.5 pb-1 text-[15px] leading-relaxed text-tt-ink outline-none placeholder:text-tt-slate/55"
        />
        <div className="flex items-center gap-1 px-1.5 pt-1">
          <button
            onClick={() => fileInput.current?.click()}
            disabled={images.length >= MAX_ATTACHMENTS}
            className="flex h-8 w-8 items-center justify-center rounded-lg text-tt-slate transition hover:bg-tt-mist hover:text-tt-electric disabled:opacity-40"
            title="Attach images (or paste / drag them in)"
            aria-label="Attach images"
          >
            <Paperclip size={17} />
          </button>
          <input
            ref={fileInput}
            type="file"
            accept="image/png,image/jpeg,image/webp,image/gif"
            multiple
            className="hidden"
            onChange={(e) => {
              addFiles(imageFiles(e.target.files))
              e.target.value = ''
            }}
          />
          <div className="relative">
            <button
              onClick={() => setMenu((m) => (m === 'domain' ? null : 'domain'))}
              className={clsx(
                'inline-flex items-center gap-1.5 rounded-lg py-1 pr-2 pl-1 text-[12.5px] font-semibold transition hover:bg-tt-mist',
                domain === 'all' ? 'text-tt-slate' : 'text-tt-navy',
              )}
            >
              <DomainIcon id={domain} size="sm" />
              {domainVisual(domain).label}
              <ChevronDown size={13} />
            </button>
            {menu === 'domain' && (
              <Menu onClose={() => setMenu(null)}>
                {domainOptions.map((d) => (
                  <button
                    key={d}
                    onClick={() => {
                      onDomain(d)
                      setMenu(null)
                    }}
                    className={clsx('flex w-full items-center gap-2 rounded-lg px-2.5 py-1.5 text-left text-[13px] transition', d === domain ? 'bg-tt-mist font-semibold text-tt-navy' : 'text-tt-ink hover:bg-tt-mist/70')}
                  >
                    <DomainIcon id={d} size="sm" />
                    <span className="flex-1">{domainVisual(d).label}</span>
                    {d === domain && <Check size={14} className="text-tt-electric" />}
                  </button>
                ))}
              </Menu>
            )}
          </div>
          {error ? (
            <span className="ml-auto truncate text-[11.5px] font-medium text-tt-ember">{error}</span>
          ) : (
            <span className="ml-auto hidden text-[11.5px] text-tt-slate/60 sm:block">Enter to send · Shift+Enter new line</span>
          )}
          {busy ? (
            <button onClick={onStop} className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-tt-navy text-white transition hover:bg-tt-midnight" aria-label="Stop">
              <Square size={13} fill="currentColor" />
            </button>
          ) : (
            <button
              onClick={submit}
              disabled={!canSend}
              className="bg-tt-electric-gradient flex h-9 w-9 shrink-0 items-center justify-center rounded-full text-white shadow-[0_8px_20px_-8px_rgba(0,0,179,0.8)] transition hover:scale-105 disabled:scale-100 disabled:opacity-35 disabled:shadow-none"
              aria-label="Send"
            >
              <ArrowUp size={18} strokeWidth={2.5} />
            </button>
          )}
        </div>
      </div>
      <p className="mt-2 text-center text-[11.5px] text-tt-slate/60">
        Answers are grounded in your indexed documents. Verify critical values against the cited source.
      </p>
    </div>
  )
}

function Menu({ children, onClose }: { children: React.ReactNode; onClose: () => void }) {
  return (
    <>
      <div className="fixed inset-0 z-10" onClick={onClose} />
      <div className="absolute bottom-full left-0 z-20 mb-2 w-56 rounded-xl border border-tt-line bg-white p-1 shadow-lift">{children}</div>
    </>
  )
}
