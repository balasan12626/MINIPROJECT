import json, os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.family"] = "Times New Roman"
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths as P
SP = P.WORK.as_posix() + "/"
OUT = SP + "fig/"
os.makedirs(OUT, exist_ok=True)
ROOT = P.ROOT.as_posix() + "/"
EDGE = "#1f2a44"


def box(ax, x, y, w, h, text, fc="#ffffff", fs=11, bold=False):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08", fc=fc, ec=EDGE, lw=1.3))
    ax.text(x + w / 2, y + h / 2, text, ha="center", va="center", fontsize=fs, fontweight="bold" if bold else "normal")


def arrow(ax, x1, y1, x2, y2, text=None, both=False):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="<|-|>" if both else "-|>", color=EDGE, lw=1.3))
    if text:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + 0.12, text, fontsize=9, ha="center", style="italic")


def canvas(w, h, y0=0):
    fig, ax = plt.subplots(figsize=(w, h))
    ax.set_xlim(0, w)
    ax.set_ylim(y0, h + y0)
    ax.axis("off")
    return fig, ax


def save(fig, name):
    fig.savefig(OUT + name, dpi=200, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# 1 Architecture -------------------------------------------------------------
fig, ax = canvas(12, 13.6, y0=-0.5)
ax.text(6, 12.95, "AquaSentinel - Overall System Architecture", ha="center", fontsize=15, fontweight="bold")
bands = [(11.0, 1.7, "#e8f0fe", "PRESENTATION LAYER"), (9.2, 1.4, "#fff4e5", "COMMUNICATION LAYER"),
         (3.0, 5.9, "#e9f7ef", "APPLICATION LAYER - FastAPI backend (Python)"), (1.2, 1.5, "#fdecea", "DATA LAYER"),
         (-0.45, 1.4, "#f3e8fd", "EXTERNAL SOURCES")]
for y, h, c, t in bands:
    ax.add_patch(FancyBboxPatch((0.2, y), 11.6, h, boxstyle="round,pad=0.02,rounding_size=0.1", fc=c, ec="#9aa5b8", lw=1))
    ax.text(0.4, y + h - 0.22, t, fontsize=10, fontweight="bold", color="#33415c")
for i, t in enumerate(["Live Command\nCenter  (/)", "Live Response\n(/response)", "Simulation Lab\n(/simulation)", "Rescue Route\n(/rescue)"]):
    box(ax, 0.5 + i * 2.85, 11.1, 2.55, 1.0, t, fs=10.5)
ax.text(7.0, 12.48, "React 19 + Vite | React Router | Leaflet | Recharts | ScenarioContext", ha="center", fontsize=9.5, color="#33415c")
box(ax, 1.0, 9.35, 4.6, 0.9, "REST API (Axios, JSON)\n/api/* endpoints", fs=10.5)
box(ax, 6.4, 9.35, 4.6, 0.9, "WebSocket hub  /ws\nheartbeat + typed events", fs=10.5)
arrow(ax, 3.3, 11.1, 3.3, 10.25, both=True)
arrow(ax, 8.7, 11.1, 8.7, 10.25, both=True)
arrow(ax, 3.3, 9.35, 3.3, 8.45, both=True)
arrow(ax, 8.7, 9.35, 8.7, 8.45, both=True)
box(ax, 0.5, 7.45, 3.5, 1.0, "API routers\nlive, ml, simulation, hqrl,\nemergency, rescue, dams, voice", fs=9.5)
box(ax, 4.25, 7.45, 3.5, 1.0, "Shared pipeline\nrun_pipeline(mode, observations)", fs=10, bold=True, fc="#d7ecdf")
box(ax, 8.0, 7.45, 3.5, 1.0, "Security\nJWT, CORS, SlowAPI,\nsecurity headers", fs=9.5)
mods = [("Data\nnormalisation", 0.5), ("Feature\nengine", 2.4), ("ML prediction\nRF / XGB / v2 / v4", 4.3),
        ("Operational\nrisk engine", 6.2), ("Decision\npolicy", 8.1), ("Agent\ngraph", 10.0)]
for t, x in mods:
    box(ax, x, 5.95, 1.6, 1.05, t, fs=9.5)
for i in range(len(mods) - 1):
    arrow(ax, mods[i][1] + 1.6, 6.47, mods[i + 1][1], 6.47)
arrow(ax, 6.0, 7.45, 6.0, 7.0)
mods2 = [("Shelter\nengine", 0.5), ("Route engine\nDijkstra/A*/Yen", 2.4), ("QUBO optimiser\nGreedy/SA/QAOA", 4.3),
         ("SOS K-means +\nvulnerable-first", 6.2), ("Rescue stage\nmachine", 8.1), ("Digital twin\nsimulation", 10.0)]
for t, x in mods2:
    box(ax, x, 4.45, 1.6, 1.05, t, fs=9.2)
for i in range(len(mods2) - 1):
    arrow(ax, mods2[i][1] + 1.6, 4.97, mods2[i + 1][1], 4.97)
arrow(ax, 10.8, 5.95, 10.8, 5.5)
box(ax, 0.5, 3.2, 3.6, 0.9, "XAI: TreeSHAP +\nIsolation Forest change monitor", fs=9.5)
box(ax, 4.3, 3.2, 3.4, 0.9, "HQRL benchmark engine\nPPO + QUBO + simulated QAOA", fs=9.5)
box(ax, 7.9, 3.2, 3.6, 0.9, "LLM agents: Groq agent radio,\nGemini voice SOS, PDF report", fs=9.5)
box(ax, 0.5, 1.35, 3.4, 0.95, "MongoDB (Motor)\nobservations, agent_events,\nincidents, audit logs", fs=9.5)
box(ax, 4.3, 1.35, 3.4, 0.95, "Model artefacts (.pkl / .json)\nRF, XGB, v2/v3, v4", fs=9.5)
box(ax, 8.1, 1.35, 3.4, 0.95, "Datasets (training only)\nINDOFLOODS, CAMELS-IND", fs=9.5)
arrow(ax, 2.2, 3.2, 2.2, 2.3, both=True)
arrow(ax, 6.0, 2.3, 6.0, 3.2)
arrow(ax, 9.8, 2.3, 9.8, 3.2)
for i, t in enumerate(["Open-Meteo\nweather + flood API", "OpenWeather\n(optional key)", "OpenStreetMap\nmap tiles", "Groq / Gemini\nLLM APIs"]):
    box(ax, 0.5 + i * 2.85, -0.3, 2.55, 0.85, t, fs=9.5)
save(fig, "fig_architecture.png")

# 2 Workflow -----------------------------------------------------------------
fig, ax = canvas(9.5, 12.6)
steps = [("START: live tick (every 90 s) or\nsimulation tick", ""), ("SENSE: fetch weather, rainfall,\nriver / dam stage", ""),
         ("Normalise data and build features\n(T1d-T10d rainfall analogue)", ""), ("PREDICT: ML probability +\noperational risk engine", ""),
         ("Data, model and system\ngates healthy?", "d"), ("REASON: agent graph emits\nWEATHER, DAM, FLOOD_RISK events", ""),
         ("DECIDE: policy band\nMONITOR / HUMAN REVIEW / AUTO", "d"), ("OPTIMISE: shelter scoring, flood-aware\nroutes, QUBO assignment", ""),
         ("RESPOND: dispatch teams, rescue stage\nmachine, WebSocket push to UI", ""), ("STORE: snapshot and audit log\nin MongoDB", "")]
y = 11.6
pos = []
for t, k in steps:
    box(ax, 1.0, y, 5.2, 0.85, t, fs=10.5, fc="#fff4e5" if k else "#ffffff", bold=bool(k))
    pos.append(y)
    y -= 1.22
for i in range(len(pos) - 1):
    arrow(ax, 3.6, pos[i], 3.6, pos[i + 1] + 0.85)
arrow(ax, 6.2, pos[4] + 0.42, 6.9, pos[4] + 0.42)
ax.text(6.95, pos[4] + 0.42, "No: mark UNAVAILABLE,\nhold automation", fontsize=9.5, va="center")
arrow(ax, 6.2, pos[6] + 0.42, 6.9, pos[6] + 0.42)
ax.text(6.95, pos[6] + 0.42, "Review: operator\napproves / rejects (JWT)", fontsize=9.5, va="center")
save(fig, "fig_workflow.png")

# 3 Rescue stages --------------------------------------------------------------
fig, ax = canvas(13, 3.2)
st = [("queued", "admin triage,\nvulnerable-first"), ("assigned", "crew mobilises\nat unit base"),
      ("en_route", "base to person\n(flood-aware route)"), ("to_shelter", "person to shelter\n(route recomputed)"), ("rescued", "terminal state")]
for i, (s, d) in enumerate(st):
    x = 0.3 + i * 2.6
    box(ax, x, 1.4, 2.0, 0.9, s, fs=12, bold=True, fc="#e9f7ef" if s == "rescued" else "#e8f0fe")
    ax.text(x + 1.0, 0.8, d, ha="center", va="center", fontsize=9.5)
    if i < 4:
        arrow(ax, x + 2.0, 1.85, x + 2.6, 1.85)
ax.text(6.5, 2.85, "Per-person rescue stage machine (stage length = route travel time)", ha="center", fontsize=11.5, fontweight="bold")
save(fig, "fig_stages.png")

# 4 HQRL pipeline ----------------------------------------------------------------
fig, ax = canvas(13, 3.6)
hs = ["Road graph +\nflood / closures", "PPO policy\nTop-K route\ncandidates", "QUBO encoding\nclosure, capacity,\nvehicles, access",
      "Solver\nsimulated QAOA /\nclassical fallback", "Deterministic\nvalidation\nchecklist", "XAI explanation +\nhuman-in-the-loop\ngate"]
for i, t in enumerate(hs):
    x = 0.2 + i * 2.15
    box(ax, x, 0.8, 1.85, 1.6, t, fs=10, fc="#f3e8fd" if i in (2, 3) else "#ffffff")
    if i < 5:
        arrow(ax, x + 1.85, 1.6, x + 2.15, 1.6)
ax.text(6.5, 3.0, "HQRL evacuation routing pipeline", ha="center", fontsize=12, fontweight="bold")
ax.text(6.5, 0.3, "Replanning is triggered by flood-closure and shelter-full events; no quantum speed-up is claimed.", ha="center", fontsize=9.5, style="italic")
save(fig, "fig_hqrl.png")

# 5 Deployment -------------------------------------------------------------------
fig, ax = canvas(11, 4.4)
ax.add_patch(FancyBboxPatch((0.2, 0.3), 10.6, 3.6, boxstyle="round,pad=0.02", fc="#f7f9fc", ec="#9aa5b8"))
ax.text(0.45, 3.6, "docker compose (local machine or VPS)", fontsize=10.5, fontweight="bold")
box(ax, 0.6, 1.3, 2.8, 1.6, "frontend container\nVite build served\nby nginx", fs=10)
box(ax, 4.1, 1.3, 2.8, 1.6, "backend container\nUvicorn + FastAPI\n:8000  (/api, /ws)", fs=10)
box(ax, 7.6, 1.3, 2.8, 1.6, "mongo:7 container\ndatabase\nflood_response", fs=10)
arrow(ax, 3.4, 2.1, 4.1, 2.1, "proxy")
arrow(ax, 6.9, 2.1, 7.6, 2.1)
ax.text(5.5, 0.65, "Browser -> nginx -> /api and /ws proxied to backend; API keys stay server-side in .env", ha="center", fontsize=9.5, style="italic")
save(fig, "fig_deploy.png")

# 6 ML v1 --------------------------------------------------------------------------
ev = json.load(open(ROOT + "models/evaluation.json"))
keys = ["accuracy", "precision", "recall", "f1", "roc_auc"]
lab = ["Accuracy", "Precision", "Recall", "F1-score", "ROC-AUC"]
x = np.arange(len(keys))
fig, ax = plt.subplots(figsize=(8, 4))
for i, (m, c, n) in enumerate([("random_forest", "#2f5d9e", "Random Forest"), ("xgboost", "#d0802f", "XGBoost")]):
    v = [ev[m][k] for k in keys]
    bars = ax.bar(x + (i - 0.5) * 0.36, v, 0.36, color=c, label=n)
    for r, val in zip(bars, v):
        ax.text(r.get_x() + r.get_width() / 2, val + 0.01, f"{val:.3f}", ha="center", fontsize=8.5)
ax.set_xticks(x, lab)
ax.set_ylim(0, 1)
ax.set_ylabel("Score (held-out 910 events)")
ax.legend(frameon=False)
ax.spines[["top", "right"]].set_visible(False)
ax.set_title("V1 INDOFLOODS severe-flood classifiers - test metrics", fontsize=12)
save(fig, "fig_ml_v1.png")

# 7 V4 candidates ------------------------------------------------------------------
e4 = json.load(open(ROOT + "models/flood_evaluation_v4.json"))
names = list(e4["candidates"])
series = [("balanced_accuracy", "#2f5d9e", "Balanced accuracy"), ("roc_auc", "#3c8d5a", "ROC-AUC"), ("pr_auc", "#d0802f", "PR-AUC")]
x = np.arange(len(names))
fig, ax = plt.subplots(figsize=(10, 4.2))
for i, (k, c, n) in enumerate(series):
    ax.bar(x + (i - 1) * 0.27, [e4["candidates"][nm]["validation"][k] for nm in names], 0.27, color=c, label=n)
ax.set_xticks(x, [n.replace("_", "\n") for n in names], fontsize=9)
ax.set_ylim(0.6, 1.0)
ax.legend(frameon=False, ncol=3, loc="upper left")
ax.spines[["top", "right"]].set_visible(False)
ax.set_title("V4 CAMELS-IND 3-day flood forecast - validation (2009-2014) comparison", fontsize=12)
save(fig, "fig_ml_v4.png")

# 8 Confusion matrix -------------------------------------------------------------
t = e4["test"]["unseen_gauges_2015_2020"]["model"]
cm = np.array([[t["tn"], t["fp"]], [t["fn"], t["tp"]]])
fig, ax = plt.subplots(figsize=(4.8, 4))
ax.imshow(cm, cmap="Blues")
for i in range(2):
    for j in range(2):
        ax.text(j, i, f"{cm[i, j]:,}", ha="center", va="center", fontsize=13, color="white" if cm[i, j] > 20000 else "black")
ax.set_xticks([0, 1], ["Pred: no flood", "Pred: flood"])
ax.set_yticks([0, 1], ["Actual: no flood", "Actual: flood"])
ax.set_title("V4 confusion matrix - unseen gauges 2015-2020", fontsize=11)
save(fig, "fig_cm_v4.png")

# 9 HQRL bench ----------------------------------------------------------------------
d = json.load(open(SP + "hqrl.json"))
tb = d["bench"]["table"]
m = [r["method"] for r in tb]
fig, axs = plt.subplots(1, 2, figsize=(11, 4))
axs[0].barh(m, [r["safe_evacuation_pct"] for r in tb], color="#3c8d5a")
axs[0].set_xlim(80, 101)
axs[0].set_title("Safe evacuation (%)")
axs[0].invert_yaxis()
axs[1].barh(m, [r["clearance_time_min"] for r in tb], color="#2f5d9e")
axs[1].set_xlim(15, 18.5)
axs[1].set_title("Mean clearance time (min)")
axs[1].invert_yaxis()
axs[1].set_yticklabels([])
for a in axs:
    a.spines[["top", "right"]].set_visible(False)
fig.suptitle("HQRL benchmark - 30 synthetic scenarios, seed 42", fontsize=12)
save(fig, "fig_hqrl_bench.png")
print("done", sorted(os.listdir(OUT)))
