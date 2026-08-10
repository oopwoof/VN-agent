import LegacyShell from './shell/LegacyShell'
import WorkbenchShell from './shell/WorkbenchShell'
import { useShellVariant } from './shell/useShellVariant'

export default function App() {
  const variant = useShellVariant()
  return variant === 'v2' ? <WorkbenchShell /> : <LegacyShell />
}
