"""P1 revision experiments -> <work>/p1_v2.json (additive; p1.json is not touched).

Same 30 instances as exp_p1.py (seed 42 + 17 i, R5 closed, Shelter A +50 %, G = 4, 12 qubits).
  seeds     - depth-progressive training p = 1..4 with 5 optimiser seeds per instance for
              X/mean, XY/mean and XY/CVaR. Seed k = 0 reproduces the run in p1.json exactly.
              Trained angles are stored for the transfer study.
  grover    - Grover-mixer QAOA over the one-hot subspace (same start state as XY), mean and CVaR.
  penalty   - X mixer with the penalty weight scaled by lambda in {0.25, 0.5, 2} (lambda = 1 is p1.json).
  sa        - simulated annealing with 20 restarts x 200 sweeps.
  exactness - Proposition 1 condition per instance (pairwise encoding exact).
usage: .venv\\Scripts\\python.exe exp_p1_v2.py <work>
"""
import itertools
import json
import sys
import time
from multiprocessing import Pool
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
sys.path[:0] = [str(ROOT), str(HERE.parent), str(HERE)]
import qaoa_sim as Q  # noqa: E402
from exp_p1 import disrupted  # noqa: E402

N_INST, G, SEEDS = 30, 4, 5
DEPTHS = (1, 2, 3, 4)


class GroverQaoa(Q.Qaoa):
    """Grover mixer U_M(beta) = I + (e^{-i beta} - 1)|s><s|, |s> = W_3^{(x)G} (uniform one-hot plans)."""

    def __init__(self, inst, diag, alpha=1.0):
        super().__init__(inst, "xy", diag, alpha=alpha)
        self.kind = "grover"

    def state(self, theta):
        p = len(theta) // 2
        psi = self.psi0.copy()
        s = self.psi0
        for k in range(p):
            psi *= np.exp(-1j * theta[k] * self.hn)
            psi += (np.exp(-1j * theta[p + k]) - 1.0) * np.vdot(s, psi) * s
        return psi


def load(i):
    inst = Q.instance_from_engine(disrupted(42 + 17 * i), G)
    d = Q.diagonals(inst, Q.bit_table(3 * G))
    ex = Q.exact_solve(inst)
    return inst, d, ex


def train(qa, opt, feas, seed):
    rng = np.random.default_rng(seed)
    warm, out = None, []
    for p in DEPTHS:
        nf0 = qa.nfev
        th, _ = qa.optimise(p, rng, restarts=2, warm=warm)
        warm = th
        pr = np.abs(qa.state(th)) ** 2
        out.append({"p": p, "popt": float(pr[opt].sum()), "pfeas": float(pr[feas].sum()),
                    "nfev": qa.nfev - nf0, "theta": [float(x) for x in th]})
    return out


def job(args):
    """One (instance, task) unit of work."""
    i, task = args
    inst, d, ex = load(i)
    if not np.isfinite(ex["obj"]):
        return {"i": i, "task": task, "feasible_instance": False}
    opt = d["obj"] <= ex["obj"] + 1e-6
    feas = d["feas"]
    t0 = time.perf_counter()
    res = {"i": i, "task": task, "feasible_instance": True}
    if task.startswith("seed"):
        _, kind, alpha, k = task.split(":")
        qa = Q.Qaoa(inst, kind, d, alpha=float(alpha))
        res["runs"] = train(qa, opt, feas, i + 10007 * int(k))
    elif task.startswith("grover"):
        alpha = float(task.split(":")[1])
        res["runs"] = train(GroverQaoa(inst, d, alpha=alpha), opt, feas, i)
    elif task.startswith("penalty"):
        lam = float(task.split(":")[1])
        dd = dict(d)
        viol = (d["h_qubo"] - _lin_s(inst, d)) / d["P"]
        dd["h_qubo"] = _lin_s(inst, d) + lam * d["P"] * viol
        res["runs"] = train(Q.Qaoa(inst, "x", dd), opt, feas, i)
        res["qubo_exact"] = bool(opt[int(np.argmin(dd["h_qubo"]))])
    elif task == "sa":
        rng = np.random.default_rng(5000 + i)
        sa = Q.simulated_annealing(inst, d, rng, restarts=20, sweeps=200)
        res.update({"sa_opt": bool(opt[sa["k"]]), "sa_feas": bool(feas[sa["k"]]), "sa_ms": sa["ms"]})
    elif task == "exact":
        res.update(exactness(inst, d, opt))
    res["sec"] = time.perf_counter() - t0
    return res


def _lin_s(inst, d):
    bits = Q.bit_table(3 * G).reshape(-1, G, 3).astype(np.float64)
    return np.einsum("kgs,gs->k", bits, Q.shifted_cost(inst))


def exactness(inst, d, opt):
    """Proposition 1: if, for every shelter s, every set of >= 3 groups allowed at s whose pairs all
    fit also fits as a whole, the zero-penalty one-hot set equals the feasible set and the QUBO
    minimiser is a true optimum."""
    cond = True
    for s in range(inst["S"]):
        allowed = [g for g in range(inst["G"]) if not inst["forb"][g, s]]
        for r in range(3, len(allowed) + 1):
            for T in itertools.combinations(allowed, r):
                pairs_ok = all(inst["sizes"][a] + inst["sizes"][b] <= inst["rem"][s]
                               for a, b in itertools.combinations(T, 2))
                if pairs_ok and sum(inst["sizes"][g] for g in T) > inst["rem"][s]:
                    cond = False
    zero = d["onehot"] & (d["h_xy"] <= d["P"] - 1.0 + 1e-9)  # one-hot, no penalised term
    return {"cond": cond, "zero_eq_feas": bool(np.array_equal(zero, d["feas"])),
            "qubo_exact": bool(opt[int(np.argmin(d["h_qubo"]))])}


if __name__ == "__main__":
    work = Path(sys.argv[1] if len(sys.argv) > 1 else ".")
    work.mkdir(parents=True, exist_ok=True)
    tasks = []
    for i in range(N_INST):
        tasks += [(i, "exact"), (i, "sa"), (i, "grover:1.0"), (i, "grover:0.1")]
        tasks += [(i, f"penalty:{lam}") for lam in (0.25, 0.5, 2.0)]
        tasks += [(i, f"seed:{kind}:{a}:{k}") for kind, a in (("x", 1.0), ("xy", 1.0), ("xy", 0.1))
                  for k in range(SEEDS)]
    t0 = time.time()
    out = []
    with Pool(4) as pool:
        for n, r in enumerate(pool.imap_unordered(job, tasks), 1):
            out.append(r)
            if n % 25 == 0:
                print(f"{n}/{len(tasks)} done, {time.time() - t0:.0f}s", flush=True)
    out.sort(key=lambda r: (r["i"], r["task"]))
    (work / "p1_v2.json").write_text(json.dumps({"n_inst": N_INST, "seeds": SEEDS, "results": out}),
                                     encoding="utf-8")
    print("wrote", work / "p1_v2.json", f"{time.time() - t0:.0f}s")
