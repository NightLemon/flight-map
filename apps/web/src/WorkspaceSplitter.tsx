type Props = { width: number; onWidth: (width: number) => void }

export function WorkspaceSplitter({ width, onWidth }: Props) {
  const adjust = (next: number) => onWidth(Math.max(320, Math.min(window.innerWidth - 650, next)))
  return <div className="workspace-splitter" role="separator" aria-label="调整地图与航图宽度" aria-orientation="vertical"
    aria-valuenow={Math.round(width)} aria-valuemin={320} aria-valuemax={Math.max(320, window.innerWidth - 650)} tabIndex={0}
    onPointerDown={(event) => { event.currentTarget.setPointerCapture(event.pointerId); event.preventDefault() }}
    onPointerMove={(event) => { if (event.currentTarget.hasPointerCapture(event.pointerId)) adjust(window.innerWidth - event.clientX - 22) }}
    onPointerUp={(event) => event.currentTarget.releasePointerCapture(event.pointerId)}
    onKeyDown={(event) => {
      if (event.key === 'ArrowLeft' || event.key === 'ArrowRight') { event.preventDefault(); adjust(width + (event.key === 'ArrowLeft' ? 24 : -24)) }
      if (event.key === 'Home') { event.preventDefault(); adjust(320) }
      if (event.key === 'End') { event.preventDefault(); adjust(window.innerWidth - 650) }
    }}><span /></div>
}
