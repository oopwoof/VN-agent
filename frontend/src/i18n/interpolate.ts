/** Substitute `{name}` placeholders in a dictionary string.
 *
 *  Deliberately tiny and dependency-free: the chat log only ever needs a
 *  handful of slots (a story title, a job id, a scene name, an error string),
 *  and an ICU-grade formatter would be several kB of runtime for that.
 *
 *  A placeholder with no matching variable is left verbatim, so a missing
 *  `tvar` shows up as a visible `{title}` instead of silently becoming
 *  "undefined" or an empty hole.
 */
export function interpolate(
  template: string,
  vars?: Record<string, string | number>,
): string {
  if (!vars) return template
  return template.replace(/\{(\w+)\}/g, (match, name: string) =>
    Object.prototype.hasOwnProperty.call(vars, name) ? String(vars[name]) : match,
  )
}
