import axios from "axios";
import { getAuthToken } from "./auth.js";
import { apiUrl, resolveApiOrigin } from "./apiOrigin.js";

const api = axios.create({
  baseURL: resolveApiOrigin(),
  timeout: 25000,
});

api.interceptors.request.use((config) => {
  const token = getAuthToken();
  if (token) {
    config.headers = config.headers || {};
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

function isTransientNetwork(err) {
  const code = err?.code || "";
  const msg = String(err?.message || err?.toString?.() || "").toLowerCase();
  return (
    code === "ERR_NETWORK" ||
    msg.includes("network") ||
    msg.includes("network_changed") ||
    msg.includes("failed to fetch")
  );
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const status = err?.response?.status;
    const cfg = err.config || {};
    const method = String(cfg.method || "get").toLowerCase();
    // Never retry auth failures, timeouts, or mutating POSTs — that caused 5+ min "Launching…" hangs
    if (status === 401 || status === 403 || err?.code === "ECONNABORTED" || method !== "get") {
      return Promise.reject(err);
    }
    cfg.__retryCount = cfg.__retryCount || 0;
    if (cfg.__retryCount < 1 && isTransientNetwork(err)) {
      cfg.__retryCount += 1;
      await new Promise((r) => setTimeout(r, 400));
      return api.request(cfg);
    }
    return Promise.reject(err);
  }
);

export async function loginOperator(username, password) {
  const { data } = await api.post("/api/auth/login", { username, password }, { timeout: 15000 });
  return data;
}

export async function getJson(url, fallbackMessage = "DATA UNAVAILABLE") {
  try {
    const { data } = await api.get(url);
    return data;
  } catch (err) {
    return { available: false, message: `${fallbackMessage}: ${err.message}` };
  }
}

export async function postJson(url, body) {
  const { data } = await api.post(url, body, { timeout: 30000 });
  return data;
}

export const fetchHealth = () => getJson("/api/health");
export const fetchLivePipeline = () => getJson("/api/pipeline/live");
export async function refreshLive() {
  try {
    return await postJson("/api/pipeline/refresh", {});
  } catch {
    return fetchLivePipeline();
  }
}
export const fetchIncidents = () => getJson("/api/incidents");
export const fetchIncident = (id) => getJson(`/api/incidents/${id}`);
export const fetchAgents = () => getJson("/api/agents/status");
export const fetchAgentEvents = () => getJson("/api/agents/events");
export const fetchPolicy = () => getJson("/api/policy");
export const fetchShelters = () => getJson("/api/shelters");
export const fetchRoutes = () => getJson("/api/routes");
export const fetchModels = () => getJson("/api/ml/models");
export const fetchMlBenchmark = () => getJson("/api/ml/benchmark");
export const fetchMetrics = () => getJson("/api/metrics");
export const fetchScenarios = () => getJson("/api/simulation/scenarios");
export const fetchSimState = () => getJson("/api/simulation/state");
export const fetchAlgorithmArena = () => getJson("/api/simulation/algorithm-arena");
export const fetchVoiceAgentStatus = () => getJson("/api/voice-agent/status");
export const startVoiceAgent = (context = {}) => postJson("/api/voice-agent/start", { context });
export async function voiceAgentTurn(text, history = [], context = {}) {
  const { data } = await api.post("/api/voice-agent/turn", { text, history, context });
  return data;
}
export const startSimulation = (body) => postJson("/api/simulation/start", body);
export const pauseSimulation = () => postJson("/api/simulation/pause", {});
export const resumeSimulation = () => postJson("/api/simulation/resume", {});
export const resetSimulation = () => postJson("/api/simulation/reset", {});
export const reviewIncident = (body) => postJson("/api/policy/review", body);
export const optimizeEvac = (body) => postJson("/api/optimization/evacuation", body || {});
export const optBenchmark = () => postJson("/api/optimization/benchmark", {});
export const sendSos = (body) => postJson("/api/emergency/sos", body);
export const fetchTeams = () => getJson("/api/rescue/teams");
export const fetchEmergencies = () => getJson("/api/emergency");
export const fetchSources = () => getJson("/api/sources");
export const fetchClusters = () => getJson("/api/emergency/clusters");
export const fetchConversation = (mode = "live") => getJson(`/api/agents/conversation?mode=${mode}`);
export const overrideSimulation = (body) => postJson("/api/simulation/override", body);
export const sendSimulationSos = (body) => postJson("/api/simulation/sos", body);
export const confirmRescue = (rescued, mode = "simulation") => postJson("/api/rescue/outcome", { rescued, mode });
export const setSimFeatures = (features) => postJson("/api/simulation/features", { features });
export const forceDispatch = () => postJson("/api/simulation/force-dispatch", {});
export const askSimAgent = (question) => postJson("/api/simulation/ask-agent", { question });
export const setSimChecklist = (checklist) => postJson("/api/simulation/checklist", { checklist });
export const fetchMlExplain = (rainfall) =>
  getJson(rainfall != null ? `/api/ml/explain?rainfall_24h_mm=${rainfall}` : "/api/ml/explain");

export const fetchRescueDesk = () => getJson("/api/rescue-desk/state");
export const rescueSos = (body) => postJson("/api/rescue-desk/sos", body);
export const syncRescueFromSim = () => postJson("/api/rescue-desk/sync-simulation", {});
export const rescueAdminShare = (case_id) => postJson("/api/rescue-desk/admin/share", { case_id });
export const rescueAmbulanceAction = (case_id, ambulance_id, action) =>
  postJson("/api/rescue-desk/ambulance/action", { case_id, ambulance_id, action });
export const rescueShelterConfirm = (case_id, accept = true) =>
  postJson("/api/rescue-desk/shelter/confirm", { case_id, accept });
export const rescueRescued = (case_id, rescued = true) =>
  postJson("/api/rescue-desk/rescued", { case_id, rescued });
export const resetRescueDesk = () => postJson("/api/rescue-desk/reset", {});

export async function downloadPersonReport(caseId) {
  const token = getAuthToken();
  const res = await fetch(apiUrl(`/api/rescue-desk/person/${caseId}/report.pdf`), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Person report unavailable");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `person_${caseId}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadSimPersonReport(citizenName) {
  const q = encodeURIComponent(String(citizenName || "").trim());
  const token = getAuthToken();
  const res = await fetch(apiUrl(`/api/simulation/person-report.pdf?name=${q}`), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) {
    let detail = "Person report unavailable";
    try {
      const err = await res.json();
      detail = err.detail || detail;
    } catch {
      detail = `${detail} (HTTP ${res.status})`;
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `person_${String(citizenName).replace(/\s+/g, "_")}.pdf`;
  a.click();
  URL.revokeObjectURL(url);
}

export async function downloadSimReport() {
  const token = getAuthToken();
  const res = await fetch(apiUrl("/api/simulation/report.pdf"), {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error("Report unavailable");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "after_action_report.pdf";
  a.click();
  URL.revokeObjectURL(url);
}

export function formatUnavailable(value, suffix = "") {
  if (value === null || value === undefined || value === "") return "DATA UNAVAILABLE";
  return `${value}${suffix}`;
}

/* —— IEEE HQRL simulation demo (/simulation only) —— */
export const hqrlState = () => getJson("/api/simulation/hqrl/state");
export const hqrlConfigure = (body) => postJson("/api/simulation/hqrl/configure", body);
export const hqrlStart = () => postJson("/api/simulation/hqrl/start", {});
export const hqrlReset = () => postJson("/api/simulation/hqrl/reset", {});
export const hqrlInjectClosure = (road_id = null) =>
  postJson("/api/simulation/hqrl/inject-closure", { road_id });
export const hqrlInjectConflict = () => postJson("/api/simulation/hqrl/inject-conflict", {});
export const hqrlInjectShelterFull = (shelter_id = null) =>
  postJson("/api/simulation/hqrl/inject-shelter-full", { shelter_id });
export const hqrlReplan = () => postJson("/api/simulation/hqrl/replan", {});
export const hqrlAccept = () => postJson("/api/simulation/hqrl/accept", {});
export const hqrlReject = () => postJson("/api/simulation/hqrl/reject", {});
export const hqrlFailures = (failures) => postJson("/api/simulation/hqrl/failures", { failures });
export const hqrlBenchmark = (body = { n_scenarios: 30, seed: 42 }) =>
  postJson("/api/simulation/hqrl/benchmark", body);
export const hqrlAblation = (body = { n_scenarios: 20, seed: 42 }) =>
  postJson("/api/simulation/hqrl/ablation", body);
export const hqrlPaperPack = () => getJson("/api/simulation/hqrl/paper-pack");
export async function hqrlExportDownload() {
  const res = await fetch(apiUrl("/api/simulation/hqrl/export"));
  if (!res.ok) throw new Error("Export unavailable");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "hqrl_synthetic_results.json";
  a.click();
  URL.revokeObjectURL(url);
}
export async function hqrlExportCsv() {
  const res = await fetch(apiUrl("/api/simulation/hqrl/export.csv"));
  if (!res.ok) throw new Error("CSV export unavailable");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "hqrl_benchmark_table.csv";
  a.click();
  URL.revokeObjectURL(url);
}
export async function hqrlExportTex() {
  const res = await fetch(apiUrl("/api/simulation/hqrl/export.tex"));
  if (!res.ok) throw new Error("LaTeX export unavailable");
  const blob = await res.blob();
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "hqrl_table.tex";
  a.click();
  URL.revokeObjectURL(url);
}
