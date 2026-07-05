import { useQuery } from '@tanstack/react-query'
import { api, type ProgramSummary } from '../lib/api'
import ConstraintsPanel from './ConstraintsPanel'
import AilmentsPanel from './AilmentsPanel'
import { Button } from './ui'

/** Coach tab — strategy summary, constraints, and ailment episodes. */
export default function CoachSummaryView({
  programs,
  onGenerateCoach,
  onModifyProgram,
  onChanged,
}: {
  programs: ProgramSummary[]
  onGenerateCoach: () => void
  onModifyProgram: (p: { id: number; name: string }) => void
  onChanged: () => void
}) {
  const { data: active } = useQuery({
    queryKey: ['active-objective'],
    queryFn: api.activeObjective,
  })
  const activeProgram =
    programs.find((p) => p.status === 'active') ??
    (active?.active_program
      ? {
          id: active.active_program.program_id,
          name: active.active_program.name,
          coach_summary: active.active_program.coach_summary,
          status: 'active' as const,
          goal_text: null,
          objective_id: null,
          start_date: null,
          end_date: null,
          planned_count: 0,
          completed_count: 0,
        }
      : null)

  const summary =
    activeProgram?.coach_summary ?? active?.active_program?.coach_summary ?? null

  return (
    <div className="space-y-6">
      <section>
        <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
          Coach&apos;s strategy
        </h2>
        {summary ? (
          <div className="rounded-xl border border-slate-800 bg-slate-800/40 p-3">
            {activeProgram && (
              <div className="mb-2 text-xs text-slate-500">
                {activeProgram.name}
                {activeProgram.end_date && ` · ends ${activeProgram.end_date}`}
                {activeProgram.planned_count > 0 &&
                  ` · ${activeProgram.completed_count}/${activeProgram.planned_count} done`}
              </div>
            )}
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-slate-300">{summary}</p>
            {activeProgram && (
              <div className="mt-3 flex gap-2">
                <Button variant="secondary" onClick={() => onModifyProgram({ id: activeProgram.id, name: activeProgram.name })}>
                  Modify plan
                </Button>
              </div>
            )}
          </div>
        ) : (
          <div className="rounded-xl border border-dashed border-slate-700 p-4 text-center">
            <p className="text-sm text-slate-400">No active plan yet.</p>
            <Button className="mt-3" onClick={onGenerateCoach}>
              ✨ Generate plan
            </Button>
          </div>
        )}
      </section>

      <AilmentsPanel onChanged={onChanged} />

      <ConstraintsPanel constraints={active?.constraints ?? []} onChanged={onChanged} compact />
    </div>
  )
}
