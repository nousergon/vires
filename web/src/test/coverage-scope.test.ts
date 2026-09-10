// The coverage gate's *scope* is asserted here, not only its number.
//
// repository-baseline-policy.md §4.2 C5: the way a coverage gate stops being
// honest is by narrowing what it measures rather than by lowering the
// number — which reads as an improvement in every report. Measured on
// symposion, removing one flag moved the reported figure from 34.76% to
// 92.36% with no new test code.
//
// vires' frontend uses vitest + the v8 provider, not coverage.py, so the
// honest-scope flag is `coverage.all: true` (report on every file `include`
// matches, not only files a test imported) rather than a `--cov=<package>`
// target. These tests assert what a passing suite cannot otherwise notice:
//
// * `all: true` is set (C1) — without it, an untested file is simply absent
//   from the denominator instead of counting as 0% covered;
// * `include` names the whole `src` tree (C1), never a narrower subdirectory;
// * exactly one `thresholds` block is enforced (C2), at/above the pinned
//   ratchet, and it is never lowered to pass a change (C3);
// * `exclude` matches a pinned, individually-justified list — a future PR
//   widening it silently shrinks the denominator without this test noticing
//   the change in words;
// * every `.ts`/`.tsx` source file under `src/` is inside `include` or on the
//   pinned exclude list — nothing is invisible to the gate by a different
//   kind of omission.

import { describe, expect, it } from 'vitest'
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { dirname, join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const HERE = dirname(fileURLToPath(import.meta.url))
const WEB_ROOT = join(HERE, '..', '..')
const CONFIG_PATH = join(WEB_ROOT, 'vitest.config.ts')
const SRC_ROOT = join(WEB_ROOT, 'src')
const CONFIG_TEXT = readFileSync(CONFIG_PATH, 'utf-8')

// The floors may be RAISED here as coverage improves. Lowering any of them is
// a policy amendment (repository-baseline-policy.md §4.2 C3), not a code
// change.
const MINIMUM_THRESHOLDS = { statements: 70, branches: 65, functions: 63, lines: 72 }

// Individually justified in vitest.config.ts's coverage.exclude comment.
// Widening this set is a scope decision, not a drive-by coverage bump —
// update the comment there and this list together.
const EXPECTED_EXCLUDE = new Set([
  'src/**/*.test.{ts,tsx}',
  'src/test/**',
  'src/main.tsx',
  'src/vite-env.d.ts',
])

function listSourceFiles(dir: string): string[] {
  const out: string[] = []
  for (const name of readdirSync(dir)) {
    const full = join(dir, name)
    const st = statSync(full)
    if (st.isDirectory()) {
      out.push(...listSourceFiles(full))
    } else if (/\.(ts|tsx)$/.test(name)) {
      out.push(relative(WEB_ROOT, full).split('\\').join('/'))
    }
  }
  return out
}

// Isolate the `coverage: { ... }` object specifically — `test:` also has its
// own top-level `include` (test-file discovery), and a bare regex on the
// whole file would match that one instead of coverage.include.
const COVERAGE_BLOCK_MATCH = CONFIG_TEXT.match(/coverage:\s*\{([^]*?)\n\s{4}\},/)
if (!COVERAGE_BLOCK_MATCH) {
  throw new Error('could not isolate the coverage: {...} block in vitest.config.ts')
}
const COVERAGE_BLOCK = COVERAGE_BLOCK_MATCH[1]

describe('coverage measurement scope', () => {
  it('reports on every included file, not only files a test happened to import', () => {
    expect(COVERAGE_BLOCK).toMatch(/\ball:\s*true\b/)
  })

  it('measures the whole src tree, never a narrower path', () => {
    const match = COVERAGE_BLOCK.match(/include:\s*\[([^\]]*)\]/)
    expect(match).not.toBeNull()
    const entries = (match![1].match(/'([^']*)'/g) ?? []).map((s: string) => s.slice(1, -1))
    expect(entries.sort()).toEqual(['src/**/*.ts', 'src/**/*.tsx'].sort())
  })

  it('enforces exactly one thresholds block at or above the pinned ratchet', () => {
    const match = COVERAGE_BLOCK.match(/thresholds:\s*\{([^}]*)\}/)
    expect(match).not.toBeNull()
    const body = match![1]
    for (const [key, floor] of Object.entries(MINIMUM_THRESHOLDS)) {
      const m = body.match(new RegExp(`${key}:\\s*(\\d+)`))
      expect(m, `thresholds.${key} must be present`).not.toBeNull()
      const value = Number(m![1])
      expect(
        value,
        `thresholds.${key}=${value} is below the ratchet ${floor}. A floor is ` +
          'raised as coverage improves and never lowered to make a change pass ' +
          '(repository-baseline-policy.md §4.2 C3).',
      ).toBeGreaterThanOrEqual(floor)
    }
  })

  it('excludes only the pinned, individually-justified set', () => {
    const match = COVERAGE_BLOCK.match(/exclude:\s*\[([^\]]*)\]/)
    expect(match).not.toBeNull()
    const entries = new Set((match![1].match(/'([^']*)'/g) ?? []).map((s: string) => s.slice(1, -1)))
    const added = [...entries].filter((e) => !EXPECTED_EXCLUDE.has(e))
    const removed = [...EXPECTED_EXCLUDE].filter((e) => !entries.has(e))
    expect(
      added,
      'coverage exclude gained unreviewed entries — each excluded path removes ' +
        'files from the denominator, raising the reported figure without adding ' +
        'a test. Update EXPECTED_EXCLUDE here alongside a justification comment ' +
        'in vitest.config.ts if this is deliberate.',
    ).toEqual([])
    expect(removed, 'coverage exclude lost tracked entries').toEqual([])
  })

  it('has no source file outside the measured src tree', () => {
    // Every .ts/.tsx file under src/ matches the `include` glob by
    // construction (src/**/*.ts, src/**/*.tsx) — this guards against a
    // future include narrowed to a subdirectory, which the second test above
    // would also catch, but this walks the real filesystem rather than the
    // config text.
    const files = listSourceFiles(SRC_ROOT)
    const stray = files.filter((f) => !f.startsWith('src/'))
    expect(stray).toEqual([])
  })
})
