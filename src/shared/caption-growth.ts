/**
 * Meet keeps appending to one caption row while a person talks, and it also
 * revises words it has already shown (casing, punctuation, corrected words).
 * Given the row text we already emitted and the row text now, work out what
 * is genuinely new so the same speech is never emitted twice.
 */
export type CaptionGrowth =
  | { kind: "same" } // nothing new (identical, or only earlier words were revised)
  | { kind: "growth"; text: string } // the row continued; `text` is the new part
  | { kind: "new"; text: string }; // unrelated text: a new utterance in the same row

/** How far the end of the emitted text may have shifted because of revisions. */
const ANCHOR_SLACK_WORDS = 3;

function normalize(word: string): string {
  return word.toLowerCase().replace(/[^\p{L}\p{N}]+/gu, "");
}

function splitWords(text: string): string[] {
  return text.split(/\s+/).filter(Boolean);
}

export function captionGrowth(emitted: string, current: string): CaptionGrowth {
  const oldWords = splitWords(emitted);
  const newWords = splitWords(current);
  const oldNorm = oldWords.map(normalize);
  const newNorm = newWords.map(normalize);

  if (oldNorm.join(" ") === newNorm.join(" ")) return { kind: "same" };

  const result = (from: number): CaptionGrowth => {
    const text = newWords.slice(from).join(" ");
    return text ? { kind: "growth", text } : { kind: "same" };
  };

  // Find where the already-emitted text ends inside the current text by
  // locating its last few words near the expected position.
  for (const size of [3, 2, 1]) {
    if (size > oldNorm.length) continue;
    const tail = oldNorm.slice(-size).join(" ");
    const expected = oldNorm.length - size;
    const highest = Math.min(newNorm.length - size, expected + ANCHOR_SLACK_WORDS);
    const lowest = Math.max(0, expected - ANCHOR_SLACK_WORDS);
    for (let start = highest; start >= lowest; start--) {
      if (newNorm.slice(start, start + size).join(" ") === tail) return result(start + size);
    }
  }

  // The tail itself was revised: still the same utterance if most of the
  // beginning matches; then continue by word count.
  let common = 0;
  while (common < oldNorm.length && common < newNorm.length && oldNorm[common] === newNorm[common]) {
    common++;
  }
  if (common >= Math.ceil(oldNorm.length / 2)) return result(oldNorm.length);

  return { kind: "new", text: current };
}
