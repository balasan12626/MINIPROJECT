// Capture the three UI screenshots for section 4.14 with headless Chrome (no npm installs).
// Needs backend on :8000 and Vite on :5173. Usage: node screenshots.mjs <workDir>
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";

const WORK = process.argv[2] || join(tmpdir(), "aquasentinel-report");
const FIG = join(WORK, "fig");
mkdirSync(FIG, { recursive: true });
const BASE = "http://127.0.0.1:5173";
const CHROME = process.env.CHROME_PATH || "C:/Program Files/Google/Chrome/Application/chrome.exe";
const PORT = 9333;
const profile = join(tmpdir(), "cdp-profile-aqua");
mkdirSync(profile, { recursive: true });
const chrome = spawn(CHROME, ["--headless=new", `--remote-debugging-port=${PORT}`, `--user-data-dir=${profile}`,
  "--window-size=1600,1000", "--hide-scrollbars", "--force-device-scale-factor=1", "about:blank"], { stdio: "ignore" });
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

let target;
for (let i = 0; i < 80 && !target; i++) {
  try { target = (await (await fetch(`http://127.0.0.1:${PORT}/json`)).json()).find((t) => t.type === "page"); } catch {}
  if (!target) await sleep(250);
}
const ws = new WebSocket(target.webSocketDebuggerUrl);
await new Promise((r) => ws.addEventListener("open", r));
let id = 0;
const pending = new Map();
ws.addEventListener("message", (ev) => { const m = JSON.parse(ev.data); if (pending.has(m.id)) { pending.get(m.id)(m); pending.delete(m.id); } });
const send = (method, params = {}) => new Promise((res) => { const i = ++id; pending.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const js = async (e) => (await send("Runtime.evaluate", { expression: e, awaitPromise: true, returnByValue: true })).result?.result?.value;
const go = async (path, wait) => { await send("Page.navigate", { url: BASE + path }); await sleep(wait); };
const click = async (label) => console.log(await js(`(() => { const w=${JSON.stringify(label.toLowerCase())};
  const b=[...document.querySelectorAll('button,a,[role=button]')].find(e=>(e.innerText||'').toLowerCase().includes(w));
  if(!b) return 'NOT FOUND: '+w; b.scrollIntoView({block:'center'}); b.click(); return 'clicked: '+w; })()`));
const scrollToText = async (text, offset = 120) => js(`(() => { const el=[...document.querySelectorAll('h2,h3,h4,div,span')]
  .find(e=>e.childElementCount===0 && (e.innerText||'').trim().toLowerCase()===${JSON.stringify(text.toLowerCase())});
  if(!el) return false; window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - ${offset}); return true; })()`);
const shot = async (name) => { await sleep(600); const r = await send("Page.captureScreenshot", { format: "png" });
  writeFileSync(join(FIG, name), Buffer.from(r.result.data, "base64")); console.log("saved", join(FIG, name)); };

await send("Page.enable");
await send("Emulation.setDeviceMetricsOverride", { width: 1600, height: 1000, deviceScaleFactor: 1, mobile: false });

// Figure 4.6 – Command Center with live data
await go("/", 15000);
await js("window.scrollTo(0,0)");
await shot("ui_command_center.png");

// Figure 4.7 – Simulation Lab after RUN SCENARIO (Heavy Rainfall), result cards + Dam Monitor
await go("/simulation", 6000);
await click("heavy rainfall");
await sleep(2500);
await click("run scenario");
await sleep(35000);
// top of the result cards ("RESERVOIR RISK" is the first card) just under the sticky header
if (!(await scrollToText("Reservoir risk", 140))) await js("window.scrollTo(0, 3240)");
await shot("ui_simulation.png");

// Figure 4.8 – Rescue Route after pulling the simulation residents into the desk
await go("/rescue", 6000);
await click("pull from simulation");
await sleep(20000);
await js("window.scrollTo(0, 460)");
await shot("ui_rescue.png");

ws.close();
chrome.kill();
process.exit(0);
