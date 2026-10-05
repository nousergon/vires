import { describe, expect, it } from 'vitest'
import { canonicalRedirect } from './canonicalHost'

const loc = (hostname: string, pathname = '/app/', search = '', hash = '') => ({ hostname, pathname, search, hash })

describe('canonicalRedirect', () => {
  it('sends the EC2 origin hostname to the canonical host, keeping path, query and hash', () => {
    expect(canonicalRedirect(loc('vires-app.nousergon.ai', '/app/login', '?error=INVALID_TOKEN', '#x'))).toBe(
      'https://vires.nousergon.ai/app/login?error=INVALID_TOKEN#x',
    )
  })

  it('leaves the canonical host alone (the Worker-proxied path never loops)', () => {
    expect(canonicalRedirect(loc('vires.nousergon.ai'))).toBeNull()
  })

  it('leaves local dev alone', () => {
    expect(canonicalRedirect(loc('localhost'))).toBeNull()
    expect(canonicalRedirect(loc('127.0.0.1'))).toBeNull()
  })
})
