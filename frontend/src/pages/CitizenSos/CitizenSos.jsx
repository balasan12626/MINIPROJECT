import { useCallback, useEffect, useMemo, useState } from "react";
import { Circle, MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { fetchCities, fetchSosStatus, sendPublicSos } from "../../services/api.js";
import { registerPhoneOffline } from "../../utils/offlinePages.js";
import "../DriverApp/driverApp.css";
import { WATER_CODES, smsHref, smsNumber, smsText, usePhoneLang } from "../../i18n/phonePages.js";
import LangPicker from "../../i18n/LangPicker.jsx";


const TICKET_KEY = "aq_sos_ticket";
const POLL_MS = 5000;
const MAX_SIDE = 1600;
const TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const TILE_ATTR = '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';
// Map opens on central Delhi only so a citizen without GPS can place the pin.
const START = [28.62, 77.23];
const WATER = WATER_CODES;
// F21: injured / critical callers are taken to the nearest hospital (triage first).
export const MEDICAL = [
  ["none", "No one is hurt"],
  ["injured", "Someone is injured"],
  ["critical", "Someone is badly hurt / unconscious"],
];
const STEPS = [
  ["queued", "Waiting"],
  ["en_route", "Unit on the way"],
  ["to_shelter", "Going to shelter"],
  ["rescued", "Safe"],
];

const PIN = L.divIcon({ className: "sos-pin-wrap", html: '<div class="sos-pin">📍</div>', iconSize: [32, 32], iconAnchor: [16, 30] });

const store = {
  get() {
    try {
      return window.localStorage.getItem(TICKET_KEY);
    } catch {
      return null;
    }
  },
  set(v) {
    try {
      if (v) window.localStorage.setItem(TICKET_KEY, v);
      else window.localStorage.removeItem(TICKET_KEY);
    } catch {
      /* private mode: status just won't survive a refresh */
    }
  },
};

// ---- offline outbox (F15): one SOS kept on the phone until it can be sent ----
const OUTBOX_KEY = "aq_sos_outbox";
const MAX_QUEUED_PHOTO = 1_500_000; // data-URL bytes; bigger photos are dropped from the queued copy

const outbox = {
  get() {
    try {
      const raw = window.localStorage.getItem(OUTBOX_KEY);
      return raw ? JSON.parse(raw) : null;
    } catch {
      return null;
    }
  },
  set(v) {
    try {
      if (v) window.localStorage.setItem(OUTBOX_KEY, JSON.stringify(v));
      else window.localStorage.removeItem(OUTBOX_KEY);
    } catch {
      /* storage full / private mode: the SOS stays in memory only */
    }
  },
};

function toForm(p, blob) {
  const form = new FormData();
  form.append("name", p.name);
  if (p.age != null) form.append("age", String(p.age));
  form.append("people", String(p.people));
  form.append("water", p.water);
  if (p.medical && p.medical !== "none") form.append("medical", p.medical);
  form.append("lat", String(p.lat));
  form.append("lon", String(p.lon));
  if (p.accuracy_m != null) form.append("accuracy_m", String(p.accuracy_m));
  if (blob) form.append("photo", blob, "photo.jpg");
  return form;
}

async function queueOffline(payload, blob) {
  let photo = null;
  if (blob && typeof FileReader !== "undefined") {
    photo = await new Promise((ok) => {
      const r = new FileReader();
      r.onload = () => ok(String(r.result));
      r.onerror = () => ok(null);
      r.readAsDataURL(blob);
    });
    if (photo && photo.length > MAX_QUEUED_PHOTO) photo = null;
  }
  outbox.set({ payload, photo, photo_dropped: Boolean(blob && !photo) });
}

/** Shrink a phone photo to ≤ 1600 px JPEG before upload (EXIF is also
 * stripped server-side). Falls back to the original file. */
async function shrink(file) {
  if (!file || typeof document === "undefined" || typeof URL.createObjectURL !== "function") return file;
  try {
    const url = URL.createObjectURL(file);
    const img = await new Promise((ok, bad) => {
      const i = new Image();
      i.onload = () => ok(i);
      i.onerror = bad;
      i.src = url;
    });
    URL.revokeObjectURL(url);
    const k = Math.min(1, MAX_SIDE / Math.max(img.width, img.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(img.width * k);
    canvas.height = Math.round(img.height * k);
    canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise((ok) => canvas.toBlob(ok, "image/jpeg", 0.85));
    return blob || file;
  } catch {
    return file;
  }
}

function PinPicker({ onPick, fix }) {
  const map = useMapEvents({ click: (e) => onPick([e.latlng.lat, e.latlng.lng], null) });
  // Jump to a fresh GPS fix (not on every drag / tap).
  useEffect(() => {
    if (fix) map.setView(fix.pos, fix.zoom, { animate: false });
  }, [fix, map]);
  return null;
}

/** F31: family members who get this link can see where this person is — nobody else. */
export function findLink(ticket) {
  const origin = typeof window !== "undefined" ? window.location.origin : "";
  return `${origin}/find?t=${ticket}`;
}

function ShareTicket({ ticket, t }) {
  const [done, setDone] = useState("");
  const link = findLink(ticket);
  async function copy() {
    try {
      await navigator.clipboard.writeText(link);
      setDone("Link copied.");
    } catch {
      setDone("Copy failed — share the link below by hand.");
    }
  }
  return (
    <div className="sos-share">
      <button type="button" className="drv-btn" onClick={copy}>
        {t("share")}
      </button>
      <p className="drv-muted">
        {t("share_note")} <code>{link}</code> {done}
      </p>
    </div>
  );
}

export function SosStatus({ ticket, onNew, t: tIn }) {
  const t = tIn || ((k) => ({ your_sos: "YOUR SOS", steps: STEPS.map((s) => s[1]), stay: "Stay where you are if it is safe. This page updates every 5 seconds.", another: "Send another SOS", safe_at: "Safe at", shelter: "Shelter", share: "🔗 Share with family", share_note: "Only people with this link can see your status:" })[k]);
  const [st, setSt] = useState(null);
  const [err, setErr] = useState("");
  useEffect(() => {
    let alive = true;
    let timer;
    const tick = async () => {
      try {
        const d = await fetchSosStatus(ticket);
        if (alive) {
          setSt(d);
          setErr("");
        }
      } catch (e) {
        if (alive)
          setErr(e?.response?.status === 404 ? "This SOS is no longer in a live operation." : "Connection lost — retrying…");
      }
      if (alive) timer = setTimeout(tick, POLL_MS);
    };
    tick();
    return () => {
      alive = false;
      clearTimeout(timer);
    };
  }, [ticket]);

  const at = st ? Math.max(0, STEPS.findIndex(([k]) => k === (st.stage === "assigned" ? "queued" : st.stage))) : 0;
  return (
    <section className="drv-card">
      <p className="drv-kicker">{t("your_sos")}</p>
      <h2>{st?.stage_text || "Sending…"}</h2>
      <ol className="sos-steps">
        {STEPS.map(([k], i) => (
          <li key={k} className={i < at || (st?.stage === "rescued" && i === at) ? "is-done" : i === at ? "is-now" : ""}>
            {t("steps")[i]}
          </li>
        ))}
      </ol>
      {st?.unit ? (
        <p>
          {st.unit_role === "ambulance" ? "🚑" : "🚒"} <b>{st.unit}</b>
          {st.eta_min != null ? ` · route time ${st.eta_min} min` : ""}
        </p>
      ) : null}
      {st?.shelter ? (
        <p>
          🏠 {t("shelter")}: <b>{st.shelter}</b>
        </p>
      ) : null}
      {st?.safe_at ? (
        <p>
          {st.safe_at.kind === "hospital" ? "🏥" : "✅"} {t("safe_at")} <b>{st.safe_at.name}</b>
          {st.safe_at.lat != null ? (
            <>
              {" "}
              ·{" "}
              <a href={`https://www.openstreetmap.org/?mlat=${st.safe_at.lat}&mlon=${st.safe_at.lon}#map=16/${st.safe_at.lat}/${st.safe_at.lon}`} target="_blank" rel="noreferrer">
                map
              </a>
            </>
          ) : null}
        </p>
      ) : null}
      {st?.waiting_reason ? <p className="drv-muted">{st.waiting_reason}</p> : null}
      {err ? <p className="drv-banner is-error">{err}</p> : null}
      <p className="drv-muted">{t("stay")}</p>
      {onNew ? <ShareTicket ticket={ticket} t={t} /> : null}
      {onNew ? (
        <button type="button" className="link-btn" onClick={onNew}>
          {t("another")}
        </button>
      ) : null}
    </section>
  );
}

/** F4 — public phone page (/sos). Posts to POST /api/public/sos; the person
 * then appears in the live run at `queued` and follows the normal pipeline. */
export default function CitizenSos() {
  const [lang, setLang, t] = usePhoneLang();
  const sms = smsNumber();
  // F15: cache this page's shell so it opens again without signal.
  useEffect(() => {
    registerPhoneOffline();
  }, []);
  const [ticket, setTicket] = useState(() => store.get());
  const [name, setName] = useState("");
  const [age, setAge] = useState("");
  const [people, setPeople] = useState("1");
  const [water, setWater] = useState(WATER[1]);
  const [medical, setMedical] = useState("none");
  const [pos, setPos] = useState(null); // [lat, lon]
  const [acc, setAcc] = useState(null); // metres
  const [locNote, setLocNote] = useState("");
  const [locating, setLocating] = useState(false);
  const [fix, setFix] = useState(null);
  // F7: without GPS the pin starts in the city of the live operation.
  const [start, setStart] = useState(START);
  useEffect(() => {
    let alive = true;
    Promise.resolve()
      .then(() => fetchCities())
      .then((res) => {
        const c = (res?.cities || []).find((x) => x.id === res?.active);
        if (alive && c?.center?.length === 2) setStart(c.center);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);
  const [photo, setPhoto] = useState(null);
  const [error, setError] = useState("");
  const [sending, setSending] = useState(false);
  const [queued, setQueued] = useState(() => outbox.get());

  // F15: send a queued SOS as soon as the phone is back online (and on load).
  useEffect(() => {
    let busy = false;
    const flush = async () => {
      const item = outbox.get();
      if (!item || busy || (typeof navigator !== "undefined" && navigator.onLine === false)) return;
      busy = true;
      try {
        const blob = item.photo ? await (await fetch(item.photo)).blob() : null;
        const res = await sendPublicSos(toForm(item.payload, blob));
        outbox.set(null);
        setQueued(null);
        store.set(res.ticket);
        setTicket(res.ticket);
      } catch (err) {
        if (err?.response) {
          // the server answered with a refusal: stop retrying, tell the person
          outbox.set(null);
          setQueued(null);
          setError(`Your saved SOS could not be delivered: ${err.response.data?.detail || `HTTP ${err.response.status}`}`);
        }
      } finally {
        busy = false;
      }
    };
    flush();
    window.addEventListener("online", flush);
    const id = setInterval(flush, 15000);
    return () => {
      window.removeEventListener("online", flush);
      clearInterval(id);
    };
  }, []);

  const pick = useCallback((p, accuracy) => {
    setPos(p);
    setAcc(accuracy);
  }, []);

  function locate() {
    setLocNote("");
    if (typeof navigator === "undefined" || !navigator.geolocation) {
      setLocNote(t("loc_unsupported"));
      if (!pos) setPos(start);
      return;
    }
    setLocating(true);
    navigator.geolocation.getCurrentPosition(
      (g) => {
        setLocating(false);
        const here = [g.coords.latitude, g.coords.longitude];
        pick(here, Math.round(g.coords.accuracy));
        setFix({ pos: here, zoom: g.coords.accuracy < 300 ? 16 : 13 });
        setLocNote(t("loc_found", { m: Math.round(g.coords.accuracy) }));
      },
      (e) => {
        setLocating(false);
        if (!pos) setPos(start);
        setLocNote(
          e?.code === 1 ? t("loc_denied") : t("loc_failed")
        );
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  }

  const markerEvents = useMemo(
    () => ({
      dragend: (e) => {
        const ll = e.target.getLatLng();
        pick([ll.lat, ll.lng], null);
      },
    }),
    [pick]
  );

  async function submit(e) {
    e.preventDefault();
    setError("");
    if (!name.trim()) return setError(t("err_name"));
    const n = Number(people);
    if (!Number.isInteger(n) || n < 1 || n > 50) return setError(t("err_people"));
    if (age !== "" && (Number(age) < 0 || Number(age) > 120)) return setError(t("err_age"));
    if (!pos) return setError(t("err_pos"));
    const payload = {
      name: name.trim(),
      age: age === "" ? null : Number(age),
      people: n,
      water,
      medical,
      lat: pos[0],
      lon: pos[1],
      accuracy_m: acc,
      saved_at: new Date().toISOString(),
    };
    setSending(true);
    let blob = null;
    try {
      if (photo) blob = await shrink(photo);
      // F15: no signal → keep the SOS on this phone and send it when the network returns.
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        await queueOffline(payload, blob);
        setQueued(outbox.get());
        return;
      }
      const res = await sendPublicSos(toForm(payload, blob));
      store.set(res.ticket);
      setTicket(res.ticket);
    } catch (err) {
      const code = err?.response?.status;
      const detail = err?.response?.data?.detail;
      if (!err?.response) {
        // network failure (no HTTP answer at all): queue it rather than lose it
        await queueOffline(payload, blob);
        setQueued(outbox.get());
        return;
      }
      setError(
        code === 409
          ? t("err_409")
          : code === 429
            ? t("err_429")
            : typeof detail === "string"
              ? detail
              : t("err_send")
      );
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="drv-page">
      <header className="drv-head">
        <div>
          <p className="drv-kicker">AQUASENTINEL · FLOOD SOS</p>
          <h1>{t("title")}</h1>
        </div>
      </header>
      <LangPicker lang={lang} setLang={setLang} t={t} />

      {queued && !ticket ? (
        <p className="drv-banner is-ok" role="status">
          {t("offline")} ({queued.payload?.name}, {queued.payload?.people})
          {queued.photo_dropped ? " (The photo was too large to keep offline and will not be sent.)" : ""}
        </p>
      ) : null}

      {ticket ? (
        <SosStatus
          ticket={ticket}
          t={t}
          onNew={() => {
            store.set(null);
            setTicket(null);
          }}
        />
      ) : (
        <form className="drv-card" onSubmit={submit} noValidate>
          <label className="drv-field">
            {t("name")}
            <input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} autoComplete="name" />
          </label>
          <div className="drv-row">
            <label className="drv-field">
              {t("age")}
              <input type="number" inputMode="numeric" min="0" max="120" value={age} onChange={(e) => setAge(e.target.value)} />
            </label>
            <label className="drv-field">
              {t("people")}
              <input type="number" inputMode="numeric" min="1" max="50" value={people} onChange={(e) => setPeople(e.target.value)} />
            </label>
          </div>
          <label className="drv-field">
            {t("water")}
            <select value={water} onChange={(e) => setWater(e.target.value)}>
              {WATER.map((w, i) => (
                <option key={w} value={w}>
                  {t("water_opts")[i]}
                </option>
              ))}
            </select>
          </label>

          <label className="drv-field">
            {t("injured")}
            <select value={medical} onChange={(e) => setMedical(e.target.value)}>
              {MEDICAL.map(([v], i) => (
                <option key={v} value={v}>
                  {t("med_opts")[i]}
                </option>
              ))}
            </select>
          </label>

          <button type="button" className="drv-btn sos-locate" onClick={locate} disabled={locating}>
            {locating ? t("locating") : t("locate")}
          </button>
          {locNote ? <p className="drv-muted">{locNote}</p> : null}
          {pos ? (
            <MapContainer center={pos} zoom={acc && acc < 300 ? 16 : 13} className="drv-map">
              <TileLayer attribution={TILE_ATTR} url={TILE_URL} maxZoom={19} />
              <PinPicker onPick={pick} fix={fix} />
              {acc ? <Circle center={pos} radius={acc} pathOptions={{ color: "#3b82f6", weight: 1, fillOpacity: 0.12 }} /> : null}
              <Marker position={pos} icon={PIN} draggable eventHandlers={markerEvents} />
            </MapContainer>
          ) : null}

          <label className="drv-field">
            {t("photo")}
            <input type="file" accept="image/*" capture="environment" onChange={(e) => setPhoto(e.target.files?.[0] || null)} />
          </label>

          {error ? <p className="drv-banner is-error">{error}</p> : null}
          <button type="submit" className="drv-btn reject" disabled={sending}>
            {sending ? t("sending") : t("send")}
          </button>
          {sms ? (
            <>
              <a
                className={`drv-btn sos-sms${pos ? "" : " is-disabled"}`}
                href={pos ? smsHref(sms, smsText({ lat: pos[0], lon: pos[1], people: Number(people) || 1, water, medical, name })) : undefined}
                aria-disabled={!pos}
                onClick={(e) => {
                  if (!pos) {
                    e.preventDefault();
                    setError(t("err_pos"));
                  }
                }}
              >
                {t("sms")}
              </a>
              <p className="drv-muted">{t("sms_note")}</p>
            </>
          ) : null}
          <p className="drv-foot">{t("foot")}</p>
        </form>
      )}
    </div>
  );
}
