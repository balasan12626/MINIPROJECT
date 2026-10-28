import { LANGS } from "./phonePages.js";

/** F24: language picker for the phone pages (remembered on this phone). */
export default function LangPicker({ lang, setLang, t }) {
  return (
    <div className="phone-lang">
      <label>
        {t("lang")}{" "}
        <select value={lang} onChange={(e) => setLang(e.target.value)} aria-label="Language">
          {Object.entries(LANGS).map(([k, v]) => (
            <option key={k} value={k}>
              {v.name}
            </option>
          ))}
        </select>
      </label>
      {!LANGS[lang]?.reviewed ? <p className="drv-muted">{t("unreviewed")}</p> : null}
    </div>
  );
}
