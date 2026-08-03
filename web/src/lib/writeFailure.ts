// One place where a failed write becomes visible to the user.
//
// Every mutating call in this app went through an un-awaited, un-caught
// `await api.x(...)` inside an onClick. When the API is unreachable — or
// wedged, which is what happened on 2026-08-03 when vires.service sat pinned
// at its cgroup MemoryHigh and answered nothing for ~18 minutes — the promise
// rejects, React drops it as an unhandled rejection, and the button simply
// does nothing. Reads kept rendering from the service worker's NetworkFirst
// cache, so the app looked alive while every tap was silently discarded.
//
// A swallowed write is the failure mode the fleet's fail-loud rule exists to
// prevent, and it is worse here than a crash: the user re-taps, assumes the
// set logged, and finds out at the end of the session that it did not.
//
// `alert` rather than a toast because it is what the two pre-existing failure
// paths in this codebase already use (HistoryPage, SessionDetailSheet) and it
// cannot itself be missed mid-set. Upgrading to a non-blocking toast is a
// single-call-site change from here, which is the reason this helper exists at
// all rather than an `alert` inlined at each of the twelve write sites.
export function reportWriteFailure(action: string, err: unknown): void {
  const raw = err instanceof Error ? err.message : String(err)
  // req() formats errors as "<status>: <detail>"; the status is noise here.
  const detail = raw.replace(/^\d+:\s*/, '')
  console.error(`vires: ${action} failed`, err)
  alert(`Couldn't ${action}: ${detail}\n\nNothing was saved — try again.`)
}

// Run a write and surface its failure instead of dropping it. Returns true when
// the write landed, so callers can skip follow-on state changes on failure.
export async function withWriteFailure(action: string, fn: () => Promise<unknown>): Promise<boolean> {
  try {
    await fn()
    return true
  } catch (err) {
    reportWriteFailure(action, err)
    return false
  }
}
