import { describe, expect, it } from "vitest";
import { speakerColor } from "./speaker-colors";

describe("speakerColor", () => {
  it("is stable per speaker and distinct for the first eight speakers", () => {
    const ids = Array.from({ length: 8 }, (_, i) => `speaker-${i}`);
    const colors = ids.map(speakerColor);
    expect(new Set(colors).size).toBe(8);
    expect(ids.map(speakerColor)).toEqual(colors);
    expect(speakerColor("speaker-8")).toBe(colors[0]); // palette wraps around
  });
});
