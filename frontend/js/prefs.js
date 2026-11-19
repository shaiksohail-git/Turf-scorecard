/** Local scorer preferences (no account required in Phase 1). */

const SCORER_KEY = "gully-scorer-name";

export function scorerName() {
  try {
    return (localStorage.getItem(SCORER_KEY) || "").trim() || "scorer";
  } catch {
    return "scorer";
  }
}

export function saveScorerName(name) {
  const clean = String(name || "").trim().slice(0, 64);
  try {
    if (clean) localStorage.setItem(SCORER_KEY, clean);
    else localStorage.removeItem(SCORER_KEY);
  } catch {
    /* ignore storage failures */
  }
  return clean || "scorer";
}
