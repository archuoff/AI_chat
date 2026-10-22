// Prepare chat image attachments in the browser: downscale big photos before upload (faster, cheaper
// vision tokens) and make a small thumbnail for the conversation view.
export type Attachment = { id: string; full: string; thumb: string; name: string }

export const MAX_ATTACHMENTS = 4
const MAX_SIDE = 1600
const THUMB_SIDE = 360
const ACCEPTED = ['image/png', 'image/jpeg', 'image/webp', 'image/gif']

const readDataUrl = (file: Blob) =>
  new Promise<string>((resolve, reject) => {
    const r = new FileReader()
    r.onload = () => resolve(String(r.result))
    r.onerror = () => reject(r.error)
    r.readAsDataURL(file)
  })

async function scaled(bitmap: ImageBitmap, maxSide: number, type: string, quality: number): Promise<string> {
  const k = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height))
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(bitmap.width * k)
  canvas.height = Math.round(bitmap.height * k)
  const ctx = canvas.getContext('2d')!
  if (type === 'image/jpeg') {
    ctx.fillStyle = '#fff' // transparent PNG -> white background
    ctx.fillRect(0, 0, canvas.width, canvas.height)
  }
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
  return canvas.toDataURL(type, quality)
}

export async function prepareImage(file: File): Promise<Attachment> {
  if (!ACCEPTED.includes(file.type)) throw new Error(`${file.name}: only PNG, JPEG, WebP or GIF images`)
  const bitmap = await createImageBitmap(file)
  const small = Math.max(bitmap.width, bitmap.height) <= MAX_SIDE
  // keep crisp originals for small PNG drawings/screenshots; re-encode everything else as JPEG
  const full =
    small && file.size <= 1.5 * 1024 * 1024 && file.type !== 'image/gif'
      ? await readDataUrl(file)
      : await scaled(bitmap, MAX_SIDE, 'image/jpeg', 0.86)
  const thumb = await scaled(bitmap, THUMB_SIDE, 'image/jpeg', 0.8)
  bitmap.close()
  return { id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`, full, thumb, name: file.name || 'pasted image' }
}

export const imageFiles = (list: FileList | File[] | null | undefined) =>
  Array.from(list ?? []).filter((f) => f.type.startsWith('image/'))
