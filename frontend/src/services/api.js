import axios from "axios";

const api = axios.create({
  baseURL: "",
  timeout: 45000,
});

function isTransientNetwork(err) {
  const code = err?.code || "";
  const msg = String(err?.message || err?.toString?.() || "").toLowerCase();
  return (
    code === "ERR_NETWORK" ||
    code === "ECONNABORTED" ||
    msg.includes("network") ||
    msg.includes("network_changed") ||
    msg.includes("failed to fetch") ||
    msg.includes("timeout")
  );
}

api.interceptors.response.use(
  (res) => res,
  async (err) => {
    const cfg = err.config || {};
    cfg.__retryCount = cfg.__retryCount || 0;
    if (cfg.__retryCount < 2 && isTransientNetwork(err)) {
      cfg.__retryCount += 1;
      await new Promise((r) => setTimeout(r, 350 * cfg.__retryCount));
      return api.request(cfg);
    }
    return Promise.reject(err);
  }
);

export async function getJson(url, fallbackMessage = "DATA UNAVAILABLE") {
  try {
    const { data } = await api.get(url);
    return data;
  } catch (err) {
    return { available: false, message: `${fallbackMessage}: ${err.message}` };
  }
}

export async function postJson(url, body) {
  const { data } = await api.post(url, body);
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
  const res = await fetch(`/api/rescue-desk/person/${caseId}/report.pdf`);
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
  const res = await fetch(`/api/simulation/person-report.pdf?name=${q}`);
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
  const res = await fetch("/api/simulation/report.pdf");
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
