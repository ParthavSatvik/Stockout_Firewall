import { afterEach, expect, test } from "vitest";
import { act, cleanup, render, screen } from "@testing-library/react";
import { DICTIONARIES, I18nProvider, LANGUAGES, translate, useT, type TKey } from "./i18n";

afterEach(() => { cleanup(); localStorage.clear(); });

const en = DICTIONARIES.en;
const keys = Object.keys(en) as TKey[];
const placeholders = (s: string) => (s.match(/\{\w+\}/g) ?? []).sort().join(",");

test("every language has every key, non-empty, with the same placeholders", () => {
  for (const { code } of LANGUAGES) {
    const dict = DICTIONARIES[code];
    for (const k of keys) {
      expect(dict[k], `${code}.${k}`).toBeTruthy();
      expect(placeholders(dict[k]), `${code}.${k} placeholders`).toBe(placeholders(en[k]));
    }
  }
});

test("non-English dictionaries are actually translated (in their own script)", () => {
  const script: Record<string, RegExp> = { hi: /[ऀ-ॿ]/, kn: /[ಀ-೿]/, ta: /[஀-௿]/, te: /[ఀ-౿]/, bn: /[ঀ-৿]/ };
  for (const [code, re] of Object.entries(script)) {
    const dict = DICTIONARIES[code as keyof typeof DICTIONARIES];
    const native = keys.filter((k) => re.test(dict[k])).length;
    // Brand/product terms (PromiseGuard, Razorpay, WhatsApp, SKU) may stay in Latin script.
    expect(native / keys.length, code).toBeGreaterThan(0.95);
  }
});

test("interpolation keeps data values untouched", () => {
  expect(translate("kn", "sup.commitRelay", { qty: "40", rest: "60 kg" })).toBe("40 ಬದ್ಧತೆ + 60 kg ರಿಲೇ");
  expect(translate("hi", "order.title", { id: "a46b9063" })).toBe("ऑर्डर #a46b9063");
});

function Probe() {
  const { t, setLang, lang } = useT();
  return <div><p>{t("nav.commandCenter")}</p><p data-testid="lang">{lang}</p><button onClick={() => setLang("ta")}>switch</button></div>;
}

test("switching language re-renders, persists and sets <html lang>", () => {
  render(<I18nProvider><Probe /></I18nProvider>);
  expect(screen.getByText("Command Center")).toBeTruthy();
  act(() => screen.getByText("switch").click());
  expect(screen.getByText("கட்டளை மையம்")).toBeTruthy();
  expect(localStorage.getItem("stockout_firewall_lang")).toBe("ta");
  expect(document.documentElement.lang).toBe("ta");
  cleanup();
  render(<I18nProvider><Probe /></I18nProvider>);  // a reload keeps the choice
  expect(screen.getByTestId("lang").textContent).toBe("ta");
});

test("an unknown stored language falls back to English", () => {
  localStorage.setItem("stockout_firewall_lang", "xx");
  render(<I18nProvider><Probe /></I18nProvider>);
  expect(screen.getByTestId("lang").textContent).toBe("en");
});
