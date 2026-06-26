/**
 * Frontend mirror of _sanitize_exc_for_ui() in miqi/execution/orchestrator.py.
 *
 * Applies the same sanitization to error messages before they are displayed in
 * the renderer UI: truncate at 300 chars, strip absolute paths, URLs, and long
 * Base64-like tokens.  The server-side logger retains the full exception; this
 * function is only for user-visible error text.
 */

/** Maximum length for a user-visible error message. */
const MAX_LEN = 300

/**
 * Matches http(s) URLs.
 * Applied BEFORE the path regex so URLs are replaced as a whole unit,
 * rather than having their path segments fragmented into [path] markers.
 */
const RE_URL = /https?:\/\/[^\s"'<>]{1,200}/g

/**
 * Matches Unix / Windows absolute paths.
 * E.g. /home/user/file.py, C:\Users\test\data.json, \\?\C:\foo\bar
 *
 * Applied AFTER the URL regex so we never see path segments inside URLs.
 *
 * Three alternatives (longest-first so UNC wins over drive-letter):
 *   1) UNC:  \\?\X:\dir\...\file
 *   2) Windows drive:  X:\dir\...\file
 *   3) Unix absolute:  /dir/.../file
 */
const RE_PATH =
  /(?:\\\\\?\\[A-Za-z]:[\\/](?:[^\s"'<>|:]+[\\/])*[^\s"'<>|:]+)|(?:[A-Za-z]:[\\/](?:[^\s"'<>|:]+[\\/])*[^\s"'<>|:]+)|(?:\/(?:[^\s"'<>|:]+[\/])*[^\s"'<>|:]+)/g

/** Matches long Base64-like tokens (40+ contiguous base64 chars). */
const RE_TOKEN = /\b[A-Za-z0-9+/=]{40,}\b/g

export function sanitizeUiMessage(raw: string): string {
  if (!raw) return ''

  let s = raw
  // 1) Truncate first (same order as Python _sanitize_exc_for_ui)
  if (s.length > MAX_LEN) {
    s = s.slice(0, MAX_LEN) + '…' // horizontal ellipsis (one char)
  }
  // 2) Strip URLs before paths (avoids path regex fragmenting URL segments)
  s = s.replace(RE_URL, '[url]')
  // 3) Strip paths
  s = s.replace(RE_PATH, '[path]')
  // 4) Strip long tokens
  s = s.replace(RE_TOKEN, '[token]')

  return s
}
