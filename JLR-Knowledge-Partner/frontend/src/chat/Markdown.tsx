import { memo } from 'react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

type Props = { text: string; onCite?: (n: number) => void; streaming?: boolean }

/** Renders answer markdown; [n] citations become clickable chips. */
export const AnswerMarkdown = memo(function AnswerMarkdown({ text, onCite, streaming }: Props) {
  const linked = text.replace(/\[(\d{1,3})\](?!\()/g, '[$1](#cite-$1)')
  return (
    <div className={streaming ? 'md caret' : 'md'}>
      <Markdown
        remarkPlugins={[remarkGfm]}
        components={{
          a({ href, children }) {
            const m = href?.match(/^#cite-(\d+)$/)
            if (m) {
              const n = Number(m[1])
              return (
                <button type="button" className="cite" onClick={() => onCite?.(n)} title={`Show source ${n}`}>
                  {n}
                </button>
              )
            }
            return (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            )
          },
          table({ children }) {
            return (
              <div className="table-wrap">
                <table>{children}</table>
              </div>
            )
          },
        }}
      >
        {linked}
      </Markdown>
    </div>
  )
})
