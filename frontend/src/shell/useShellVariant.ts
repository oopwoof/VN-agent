import { useState } from 'react'

export type ShellVariant = 'v1' | 'v2'

const STORAGE_KEY = 'vn-agent.shell'

// L5 cutover: v2 is now the default. ?shell=v1 still reaches the legacy
// shell until Task 15 removes it.
const DEFAULT_VARIANT: ShellVariant = 'v2'

function isVariant(value: string | null): value is ShellVariant {
  return value === 'v1' || value === 'v2'
}

function resolve(): ShellVariant {
  // URL wins and is sticky: ?shell=v1 is the one-parameter escape hatch, and
  // persisting it means the user does not have to re-append it on reload.
  const fromUrl = new URLSearchParams(window.location.search).get('shell')
  if (isVariant(fromUrl)) {
    try {
      window.localStorage.setItem(STORAGE_KEY, fromUrl)
    } catch {
      /* private mode / storage disabled — URL still applies for this load */
    }
    return fromUrl
  }

  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (isVariant(stored)) return stored
  } catch {
    /* ignore */
  }

  return DEFAULT_VARIANT
}

/** Which shell to render. Resolved once per mount — switching variants is a
 *  reload, which is what we want: the two shells do not share layout state. */
export function useShellVariant(): ShellVariant {
  const [variant] = useState<ShellVariant>(resolve)
  return variant
}
