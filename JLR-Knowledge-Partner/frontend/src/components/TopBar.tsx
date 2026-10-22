import clsx from 'clsx'
import { Menu, PanelRightClose, PanelRightOpen } from 'lucide-react'

type Props = {
  title: string
  subtitle?: string
  onMenu: () => void
  onToggleSources?: () => void
  sourcesOpen?: boolean
}

export function TopBar({ title, subtitle, onMenu, onToggleSources, sourcesOpen }: Props) {
  return (
    <header className={clsx("flex shrink-0 items-center gap-3 border-b border-tt-line/70 bg-white px-4 sm:px-6", subtitle ? "h-[64px]" : "h-[56px]")}>
      <button className="rounded-lg p-2 text-tt-navy hover:bg-tt-mist lg:hidden" onClick={onMenu} aria-label="Open menu">
        <Menu size={20} />
      </button>
      <div className="min-w-0 flex-1">
        <h1 className={clsx("truncate font-display font-bold text-tt-navy", subtitle ? "text-[17px]" : "text-[15.5px]")}>{title}</h1>
        {subtitle && <p className="truncate text-[12.5px] text-tt-slate/80">{subtitle}</p>}
      </div>
      {onToggleSources && (
        <button
          onClick={onToggleSources}
          className={clsx(
            'inline-flex items-center gap-2 rounded-xl px-3 py-2 text-[13px] font-semibold transition',
            sourcesOpen ? 'bg-tt-electric/[0.07] text-tt-electric hover:bg-tt-electric/[0.12]' : 'text-tt-navy ring-1 ring-tt-line hover:bg-tt-mist',
          )}
          aria-label={sourcesOpen ? 'Hide sources' : 'Show sources'}
          title={sourcesOpen ? 'Hide sources' : 'Show sources'}
        >
          {sourcesOpen ? <PanelRightClose size={17} /> : <PanelRightOpen size={17} />}
          <span className="hidden sm:inline">Sources</span>
        </button>
      )}
    </header>
  )
}
