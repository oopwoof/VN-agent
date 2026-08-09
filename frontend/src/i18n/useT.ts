import useStore from '../store'
import { dict, type TKey } from './dict'

/** Translate a UI-chrome key using the language currently in the store.
 *  Falls back to the Chinese string if a key is somehow missing from the
 *  active language, so a gap shows up as the wrong language rather than as
 *  a blank button. */
export function useT(): (key: TKey) => string {
  const lang = useStore(s => s.lang)
  return (key: TKey) => dict[lang][key] ?? dict.zh[key]
}
