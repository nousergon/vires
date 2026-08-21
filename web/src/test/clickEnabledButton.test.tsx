import { describe, expect, it, vi } from 'vitest'
import { render } from '@testing-library/react'
import { useState } from 'react'
import { clickEnabledButton } from './utils'

/**
 * The guard has to be shown to FAIL, or it is not a guard (vires-ops#77).
 *
 * The defect `clickEnabledButton` exists to convert into a loud failure is that
 * `fireEvent.click` on a `disabled` button is a SILENT no-op — React does not
 * fire `onClick`, nothing throws, and the test fails several lines later as
 * "the handler was never called", which reads as a product defect rather than a
 * test that acted too early.
 */
describe('clickEnabledButton', () => {
  it('clicks a button that is already enabled', async () => {
    const onClick = vi.fn()
    render(<button onClick={onClick}>Save</button>)
    await clickEnabledButton('Save')
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('waits for a button that starts disabled and becomes enabled', async () => {
    const onClick = vi.fn()
    function Delayed() {
      const [ready, setReady] = useState(false)
      // Enable on the next macrotask, the shape of the real race: the element
      // the test waited on is present before the button is clickable.
      setTimeout(() => setReady(true), 10)
      return (
        <button disabled={!ready} onClick={onClick}>
          Save
        </button>
      )
    }
    render(<Delayed />)
    await clickEnabledButton('Save')
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('FAILS naming the button when it never enables, instead of clicking into silence', async () => {
    const onClick = vi.fn()
    render(
      <button disabled onClick={onClick}>
        Save
      </button>,
    )
    await expect(clickEnabledButton('Save')).rejects.toThrow(/still disabled/)
    // The point of the whole helper: without it this handler is silently never
    // called and the failure surfaces somewhere else entirely.
    expect(onClick).not.toHaveBeenCalled()
  })

  it('fails when no button carries that accessible name', async () => {
    render(<button>Save</button>)
    await expect(clickEnabledButton('Update objective')).rejects.toThrow()
  })
})
