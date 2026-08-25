import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/** Dynamic RL + XAI panels — values only from backend HQRL state. */
export default function DynamicRlXaiPanel({ state }) {
  const rl = state?.rl_learning || {};
  const xai = state?.xai || {};
  const cands = state?.candidates || [];
  const mode = state?.data_mode || {};
  const bars = xai.feature_bars || [];
  const hist = (rl.reward_history || []).map((v, i) => ({ ep: i + 1, reward: Number(v) }));
  const candRows = cands.map((c) => ({
    name: c.id,
    score: Number(c.ppo_score) || 0,
    ok: c.qubo_pass || c.status === "FEASIBLE" || c.status === "SELECTED",
  }));
  const tip = { background: "#0c1c24", border: "1px solid #3a6a78", fontSize: 12, borderRadius: 8 };

  return (
    <div className="hqrl-panel">
      <h2>Reinforcement learning + explainable AI (live backend)</h2>
      <div className="hqrl-badge" style={{ marginBottom: 8 }}>
        {mode.mode || "DYNAMIC_BACKEND_ONLY"} · RL {mode.rl || "online"} · XAI {mode.xai || "online"}
      </div>
      <p className="hqrl-muted">{mode.label || "All values computed on the backend — not static UI text."}</p>

      <div className="hqrl-layout" style={{ marginTop: 8 }}>
        <div className="hqrl-panel">
          <h2>Online RL policy</h2>
          <div className="hqrl-kpi-row">
            <div className="hqrl-kpi"><span>Episodes</span><b>{rl.episodes ?? "—"}</b></div>
            <div className="hqrl-kpi"><span>Policy</span><b>v{rl.policy_version ?? "—"}</b></div>
            <div className="hqrl-kpi"><span>Last reward</span><b>{rl.last_reward ?? "—"}</b></div>
            <div className="hqrl-kpi"><span>Avg reward</span><b>{rl.avg_reward ?? "—"}</b></div>
          </div>
          <div className="hqrl-muted" style={{ marginTop: 6 }}>
            Weights · travel {rl.weights?.travel ?? "—"} · hazard {rl.weights?.hazard ?? "—"} · priority {rl.weights?.priority_bonus ?? "—"}
          </div>

          <h3>Reward history (area chart)</h3>
          <div style={{ height: 160, marginTop: 4 }}>
            {hist.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={hist} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,200,210,0.12)" />
                  <XAxis dataKey="ep" tick={{ fill: "#9eb8c2", fontSize: 10 }} />
                  <YAxis tick={{ fill: "#9eb8c2", fontSize: 10 }} />
                  <Tooltip contentStyle={tip} />
                  <Area type="monotone" dataKey="reward" stroke="#5ec8d8" fill="rgba(94,200,216,0.28)" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <span className="hqrl-muted">Run pipeline / replan to update rewards.</span>
            )}
          </div>

          <h3>Heuristic policy candidate scores (bars)</h3>
          <div style={{ height: 150 }}>
            {candRows.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={candRows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,200,210,0.12)" />
                  <XAxis dataKey="name" tick={{ fill: "#9eb8c2", fontSize: 10 }} />
                  <YAxis tick={{ fill: "#9eb8c2", fontSize: 10 }} />
                  <Tooltip contentStyle={tip} />
                  <Bar dataKey="score" radius={[4, 4, 0, 0]}>
                    {candRows.map((c, i) => (
                      <Cell key={i} fill={c.ok ? "#3ecf8e" : "#e85d6c"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <span className="hqrl-muted">No candidates yet.</span>
            )}
          </div>
          {cands.map((c) => (
            <div key={c.id} className="hqrl-muted" style={{ marginBottom: 2 }}>
              <b>{c.id}</b> · {c.label} · {c.status}
            </div>
          ))}
        </div>

        <div className="hqrl-panel">
          <h2>Explainable decision (backend attributions)</h2>
          {xai.error ? <div className="unavailable">{xai.error}</div> : null}
          <div className="hqrl-mono" style={{ marginBottom: 8 }}>
{`Selected: ${xai.selected_label || "—"}
Risk: ${xai.risk || "—"} · Rel: ${xai.reliability_score ?? "—"}
Method: ${xai.method || "—"}
Computed: ${xai.computed_at || "—"}`}
          </div>
          <h3>Feature contributions</h3>
          <div style={{ height: Math.max(180, bars.length * 28) }}>
            {bars.length ? (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={bars} layout="vertical" margin={{ top: 4, right: 12, left: 8, bottom: 4 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,200,210,0.12)" />
                  <XAxis type="number" tick={{ fill: "#9eb8c2", fontSize: 10 }} />
                  <YAxis type="category" dataKey="feature" width={120} tick={{ fill: "#9eb8c2", fontSize: 9 }} />
                  <Tooltip contentStyle={tip} />
                  <Bar dataKey="contribution" radius={[0, 4, 4, 0]}>
                    {bars.map((b, i) => (
                      <Cell key={i} fill={b.contribution >= 0 ? "#3ecf8e" : "#e85d6c"} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <p className="hqrl-muted">No attribution bars yet — run start / replan.</p>
            )}
          </div>
          <h3>Why selected</h3>
          <ul className="hqrl-check">
            {(xai.why_selected || []).map((w) => (
              <li key={w} className="pass">✓ {w}</li>
            ))}
          </ul>
          <h3>Rejected (backend)</h3>
          <ul className="hqrl-check">
            {(xai.rejected || []).map((r) => (
              <li key={`${r.id}-${r.reason}`} className="fail">✗ {r.id}: {r.reason}</li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}
