import { describe, expect, it } from "vitest";
import { DICT, LANGS, makeT, smsHref, smsNumber, smsText } from "./phonePages.js";

describe("F24 phone-page languages", () => {
  it("every key exists in every language, with the same list lengths", () => {
    const keys = Object.keys(DICT.en);
    for (const lang of Object.keys(LANGS)) {
      for (const k of keys) {
        expect(DICT[lang][k], `${lang}.${k}`).toBeDefined();
        if (Array.isArray(DICT.en[k])) expect(DICT[lang][k]).toHaveLength(DICT.en[k].length);
      }
    }
  });

  it("only English is marked reviewed; the others carry the unreviewed note", () => {
    for (const [k, v] of Object.entries(LANGS)) {
      expect(v.reviewed).toBe(k === "en");
      if (k !== "en") expect(DICT[k].unreviewed.length).toBeGreaterThan(5);
    }
  });

  it("fills placeholders and falls back to English", () => {
    expect(makeT("hi")("loc_found", { m: 12 })).toContain("12");
    expect(makeT("xx")("title")).toBe("Ask for rescue");
  });

  it("builds the exact SMS text the backend parser expects", () => {
    // Same string as EXAMPLE in backend/tests/test_sms_parse.py
    expect(smsText({ lat: 28.651, lon: 77.262, people: 3, water: "chest-deep", medical: "critical", name: "  Meena   Devi " })).toBe(
      "SOS 28.65100,77.26200 P3 WCHEST MCRITICAL Meena Devi"
    );
    expect(smsHref("+0000", "a b")).toBe("sms:+0000?body=a%20b");
  });

  it("has no SMS number unless configured", () => {
    expect(smsNumber()).toBeNull();
  });
});
