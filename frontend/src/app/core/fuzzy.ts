// Lightweight client-side fuzzy matching — replaces Python rapidfuzz.
// Dice-coefficient (bigram) similarity, scaled 0-100, with token-aware variants.

function norm(s: string): string {
  return (s || '').toLowerCase().trim().replace(/\s+/g, ' ');
}

function bigrams(s: string): Map<string, number> {
  const m = new Map<string, number>();
  for (let i = 0; i < s.length - 1; i++) {
    const g = s.substr(i, 2);
    m.set(g, (m.get(g) || 0) + 1);
  }
  return m;
}

function dice(a: string, b: string): number {
  a = a.replace(/\s/g, ''); b = b.replace(/\s/g, '');
  if (!a.length || !b.length) return 0;
  if (a === b) return 100;
  const ba = bigrams(a), bb = bigrams(b);
  let inter = 0, total = 0;
  for (const [g, c] of ba) { total += c; if (bb.has(g)) inter += Math.min(c, bb.get(g)!); }
  for (const c of bb.values()) total += c;
  return Math.round((2 * inter / total) * 100);
}

function sortTokens(s: string): string {
  return norm(s).split(' ').sort().join(' ');
}

export function tokenSortRatio(a: string, b: string): number {
  return dice(sortTokens(a), sortTokens(b));
}

export function tokenSetRatio(a: string, b: string): number {
  const sa = Array.from(new Set(norm(a).split(' '))).sort().join(' ');
  const sb = Array.from(new Set(norm(b).split(' '))).sort().join(' ');
  return dice(sa, sb);
}

export function partialRatio(a: string, b: string): number {
  a = norm(a); b = norm(b);
  if (!a || !b) return 0;
  const [short, long] = a.length <= b.length ? [a, b] : [b, a];
  if (long.includes(short)) return 100;
  return dice(a, b);
}

export interface ScoreInput {
  name?: string; gender?: string; age_band?: string; state?: string; language?: string; description?: string;
}
export interface Candidate {
  name?: string; gender?: string; age_band?: string; state?: string; language?: string; description?: string;
}

/** Weighted multi-field score mirroring app.py (returns score + human reasons). */
export function scoreMatch(q: ScoreInput, c: Candidate): { score: number; reasons: string[] } {
  let score = 0;
  const reasons: string[] = [];

  if (q.name && c.name) {
    const ns = tokenSortRatio(q.name, c.name);
    if (ns > 60) { score += ns * 0.35; reasons.push(`Name: ${Math.round(ns)}%`); }
  }
  if (q.state && c.state && q.state.toLowerCase() === c.state.toLowerCase()) {
    score += 15; reasons.push('State match');
  }
  if (q.language && c.language && q.language.toLowerCase() === c.language.toLowerCase()) {
    score += 10; reasons.push('Language match');
  }
  if (q.description && c.description) {
    const ds = tokenSetRatio(q.description, c.description);
    if (ds > 40) { score += ds * 0.25; reasons.push(`Description: ${Math.round(ds)}%`); }
  }
  if (q.age_band && c.age_band && q.age_band === c.age_band) {
    score += 10; reasons.push('Age match');
  }
  return { score: Math.round(score * 10) / 10, reasons };
}
