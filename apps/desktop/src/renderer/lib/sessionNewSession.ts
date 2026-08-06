export function shouldCreateNewSession(currentSessionEmpty: boolean): boolean {
  return !currentSessionEmpty;
}
