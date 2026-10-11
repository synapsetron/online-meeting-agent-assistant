import { describe, expect, it } from "vitest";
import { captionGrowth } from "./caption-growth";

describe("captionGrowth", () => {
  it("returns only the appended words when the row grows", () => {
    expect(captionGrowth("так ну зараз подивимося", "так ну зараз подивимося чи буде вона")).toEqual({
      kind: "growth",
      text: "чи буде вона",
    });
  });

  it("ignores casing and punctuation revisions of earlier words", () => {
    expect(captionGrowth("так ну зараз подивимося", "Так, ну зараз подивимося.")).toEqual({ kind: "same" });
    expect(captionGrowth("так ну зараз подивимося", "Так, ну зараз подивимося, чи буде")).toEqual({
      kind: "growth",
      text: "чи буде",
    });
  });

  it("does not repeat text when an earlier word was corrected", () => {
    const emitted = "чи буде вона транскрбіровать то що я кажу";
    const current = "чи буде вона транскрибувати то що я кажу чи ні";
    expect(captionGrowth(emitted, current)).toEqual({ kind: "growth", text: "чи ні" });
  });

  it("handles a revision that changes the number of earlier words", () => {
    const emitted = "воно якось технологію просто дропнуло";
    const current = "воно як ось технологію просто дропнуло короче";
    expect(captionGrowth(emitted, current)).toEqual({ kind: "growth", text: "короче" });
  });

  it("continues by word count when the last emitted words were revised", () => {
    expect(captionGrowth("один два три чотири пять", "один два три чотири п'ятий шість")).toEqual({
      kind: "growth",
      text: "шість",
    });
  });

  it("treats unrelated text as a new utterance", () => {
    expect(captionGrowth("добрий день усім", "переходимо до бюджету")).toEqual({
      kind: "new",
      text: "переходимо до бюджету",
    });
  });
});
