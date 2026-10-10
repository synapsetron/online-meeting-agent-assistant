/** Number of `--ma-speaker-N` colors defined in styles.css (light and dark). */
const PALETTE_SIZE = 8;

const assigned = new Map<string, number>();

/**
 * CSS color for a speaker: the same speaker always gets the same color, and
 * colors are handed out in order of first appearance so the first eight
 * speakers are all different.
 */
export function speakerColor(speakerId: string): string {
  let index = assigned.get(speakerId);
  if (index === undefined) {
    index = assigned.size % PALETTE_SIZE;
    assigned.set(speakerId, index);
  }
  return `var(--ma-speaker-${index + 1})`;
}

/** Start a new meeting with a fresh color assignment. */
export function resetSpeakerColors(): void {
  assigned.clear();
}
