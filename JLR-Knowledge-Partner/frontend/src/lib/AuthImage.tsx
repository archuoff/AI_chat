import clsx from 'clsx'
import { ImageOff } from 'lucide-react'
import { useEffect, useState } from 'react'
import { api } from './api'

// object URLs per picture, kept for the session (thumbnails are small; the same picture shows in several places)
const cache = new Map<string, Promise<string>>()

function load(id: string, thumb: boolean): Promise<string> {
  const key = `${id}:${thumb}`
  let p = cache.get(key)
  if (!p) {
    p = api.imageBlob(id, thumb).then((b) => URL.createObjectURL(b))
    p.catch(() => cache.delete(key))
    cache.set(key, p)
  }
  return p
}

/** <img> for a document picture: the API needs the Bearer token, so the file is fetched, not linked. */
export function AuthImage({ id, thumb = true, alt, className }: { id: string; thumb?: boolean; alt: string; className?: string }) {
  const [src, setSrc] = useState<string | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let live = true
    setSrc(null)
    setFailed(false)
    load(id, thumb).then(
      (u) => live && setSrc(u),
      () => live && setFailed(true),
    )
    return () => {
      live = false
    }
  }, [id, thumb])

  if (failed)
    return (
      <span className={clsx('flex items-center justify-center bg-tt-mist text-tt-slate/50', className)}>
        <ImageOff size={18} />
      </span>
    )
  if (!src) return <span className={clsx('block animate-pulse bg-tt-mist', className)} />
  return <img src={src} alt={alt} className={className} draggable={false} />
}
