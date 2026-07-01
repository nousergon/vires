import { useEffect, useState } from 'react'
import type { WeightUnit } from '../lib/api'
import { calculatePlates, DEFAULT_BAR_WEIGHT } from '../lib/plates'
import { Sheet } from './ui'

/** Plate breakdown for a target barbell weight — defaults the target to the set's current weight. */
export default function PlateCalculatorSheet({
  open,
  onClose,
  unit,
  initialWeight,
}: {
  open: boolean
  onClose: () => void
  unit: WeightUnit
  initialWeight?: number | null
}) {
  const [target, setTarget] = useState(initialWeight?.toString() ?? '')
  const [bar, setBar] = useState(DEFAULT_BAR_WEIGHT[unit].toString())

  // Reseed from the calling row's weight each time the sheet opens.
  useEffect(() => {
    if (!open) return
    setTarget(initialWeight?.toString() ?? '')
    setBar(DEFAULT_BAR_WEIGHT[unit].toString())
  }, [open, initialWeight, unit])

  const targetNum = target === '' ? 0 : Number(target)
  const barNum = bar === '' ? 0 : Number(bar)
  const { perSide, remainder } = calculatePlates(targetNum, barNum, unit)

  return (
    <Sheet open={open} onClose={onClose} title="Plate calculator">
      <div className="flex gap-3">
        <label className="flex-1 text-xs text-slate-400">
          Target ({unit})
          <input
            type="number"
            inputMode="decimal"
            value={target}
            onChange={(e) => setTarget(e.target.value)}
            className="mt-1 w-full rounded-lg bg-slate-800 px-2 py-2 text-center outline-none focus:ring-1 focus:ring-amber-500"
          />
        </label>
        <label className="flex-1 text-xs text-slate-400">
          Bar ({unit})
          <input
            type="number"
            inputMode="decimal"
            value={bar}
            onChange={(e) => setBar(e.target.value)}
            className="mt-1 w-full rounded-lg bg-slate-800 px-2 py-2 text-center outline-none focus:ring-1 focus:ring-amber-500"
          />
        </label>
      </div>

      <div className="mt-4">
        <p className="text-xs uppercase text-slate-500">Per side</p>
        {targetNum <= barNum ? (
          <p className="mt-1 text-sm text-slate-400">Bar only — no plates needed.</p>
        ) : perSide.length === 0 ? (
          <p className="mt-1 text-sm text-slate-400">No plates fit; adjust target or bar weight.</p>
        ) : (
          <div className="mt-1 flex flex-wrap gap-1.5">
            {perSide.map((plate, i) => (
              <span
                key={i}
                className="rounded-lg bg-amber-500 px-2.5 py-1 text-sm font-semibold text-slate-950"
              >
                {plate}
              </span>
            ))}
          </div>
        )}
        {remainder > 0 && (
          <p className="mt-2 text-xs text-slate-500">
            {remainder} {unit}/side can't be made from standard plates.
          </p>
        )}
      </div>
    </Sheet>
  )
}
