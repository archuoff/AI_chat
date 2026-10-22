import clsx from 'clsx'

/** JLR wordmark (from logo-black-2025.svg), drawn in currentColor so it works on dark and light backgrounds. */
export function JlrLogo({ className, title = 'JLR' }: { className?: string; title?: string }) {
  return (
    <svg viewBox="0 0 1206.22 1060.95" className={className} fill="currentColor" role="img" aria-label={title}>
      <path d="M49.61,1060.95c74.53-47.23,123.68-132.76,123.68-225.26L173.24,0h-96.12v831.77c0,34.55-8.01,67.28-24.29,94.54-13.76,21.3-31.86,40.71-52.84,55.01l49.61,79.64Z" />
      <polygon points="465.45 803.57 465.45 0 369.33 0 369.33 897.13 907.61 897.13 849.94 803.57 465.45 803.57" />
      <path d="M1178.03,247.35C1178.03,108.94,1057.56,0,921.7,0h-260.17v93.56h261.45c91,0,156.36,70.49,156.36,153.79s-65.36,157.64-156.36,157.64h-262.73v93.56h194.8l248.63,398.58h102.53l-249.91-401.14c121.75-15.38,221.72-108.94,221.72-248.63Z" />
    </svg>
  )
}

/** App mark: JLR logo on the Tata Technologies electric-blue tile. */
export function AppMark({ size = 40, className }: { size?: number; className?: string }) {
  return (
    <span
      className={clsx('bg-tt-electric-gradient inline-flex shrink-0 items-center justify-center text-white shadow-[0_8px_22px_-8px_rgba(0,0,179,0.8)]', className)}
      style={{ width: size, height: size, borderRadius: size * 0.28 }}
    >
      <JlrLogo className="w-[58%]" />
    </span>
  )
}

/** Sidebar brand: "JLR Knowledge Partner" with "Tata Technologies" underneath. */
export function Brand() {
  return (
    <div className="flex items-center gap-3">
      <JlrLogo className="h-[30px] w-auto shrink-0 text-white" />
      <div className="h-8 w-px bg-white/20" />
      <div className="leading-tight">
        <div className="font-display text-[15px] font-bold text-white">Knowledge Partner</div>
        <div className="mt-0.5 font-display text-[9.5px] font-bold tracking-[0.26em] text-tt-teal-tint">TATA TECHNOLOGIES</div>
      </div>
    </div>
  )
}
