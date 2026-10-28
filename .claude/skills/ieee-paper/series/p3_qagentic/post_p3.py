"""p3_v2.json -> nums.tex, tab_twin.tex, tab_city.tex, fig_city.pdf (P3 runtime-assurance paper).
Every directional claim in paper.tex is asserted here; result sentences are generated from the data.
usage: post_p3.py <work> <out>"""
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

WORK, OUT = Path(sys.argv[1]), Path(sys.argv[2])
j = json.loads((WORK / "p3_v2.json").read_text(encoding="utf-8"))
# city data were rebuilt after the first city run: the whole city study is re-run on a frozen snapshot
# (exp_p3_city2.py) and every city number below comes from that one run; the twin part is unchanged.
C2F = WORK / "p3_city2.json"
CITY2 = json.loads(C2F.read_text(encoding="utf-8")) if C2F.exists() else None
if CITY2:
    j["city"] = CITY2["city"]
cfg = j["config"]
M = {}


def put(k, v):
    M[k] = v


pct = lambda xs: 100 * float(np.mean(xs)) if len(xs) else float("nan")
T = j["twin"]
put("Shots", str(cfg["shots"]))
put("Batch", str(cfg["batch"]))
put("TwinSeeds", str(len({r["seed"] for r in T})))
put("TwinEvents", str(len(T)))
put("TwinInfeasible", str(sum(not r["feasible"] for r in T)))

# ---------------- twin table
trow, tw = [], {}
for key, lab in (("qaoa_fixed", "QAOA, 64 shots"), ("qaoa_adaptive", "QAOA, adaptive"),
                 ("sa_fixed", "SA, 64 shots"), ("sa_adaptive", "SA, adaptive")):
    d = [x for r in T for x in r["draws"][key]]
    feas = [x for r in T for x in r["draws"][key] if r["feasible"]]
    v = {"unsafe": pct([x["raw_invalid"] for x in d]), "valid": pct([x["sampler_found"] for x in feas]),
         "opt": pct([x["optimal"] for x in feas]), "shots": float(np.mean([x["shots_used"] for x in d])),
         "false": pct([x["uncert_false_escalation"] for x in feas]),
         "cert_false": sum(x["cert_false_escalation"] for x in d), "cert_missed": sum(x["cert_missed_escalation"] for x in d)}
    tw[key] = v
    trow.append(f"{lab} & {v['unsafe']:.1f} & {v['valid']:.1f} & {v['opt']:.1f} & {v['shots']:.1f} & {v['false']:.1f}\\\\")
(OUT / "tab_twin.tex").write_text("\n".join(trow), encoding="utf-8")
put("TwinRawQ", f"{tw['qaoa_fixed']['unsafe']:.1f}")
put("TwinRawSA", f"{tw['sa_fixed']['unsafe']:.1f}")
assert all(v["cert_false"] == 0 and v["cert_missed"] == 0 for v in tw.values()), "certified loop: no false/missed escalation"
# every infeasible event escalated by the certified loop, every feasible one dispatched
for r in T:
    for key in tw:
        for x in r["draws"][key]:
            assert x["cert_escalate"] == (not r["feasible"]), "certified escalation exactly when infeasible"
milp_tw = [r["milp_ms"] for r in T]
enum_tw = [r["enum_ms"] for r in T]
put("TwinMilpMs", f"{np.median(milp_tw):.1f}")
put("TwinEnumMs", f"{np.median(enum_tw):.1f}")
put("TwinQaoaS", f"{np.median([r['qaoa_train_ms'] for r in T]) / 1000:.1f}")
fe = [r for r in T if r["feasible"]]
low_pf = [r for r in fe if r["pfeas_qaoa"] < 0.5]
put("TwinLowPfeas", str(len(low_pf)))
q, s = tw["qaoa_fixed"], tw["sa_fixed"]
assert max(v["false"] for v in tw.values()) == 0, "text: greedy found a plan whenever the sampler did not"
assert float(M["TwinMilpMs"]) < 50 and float(M["TwinQaoaS"]) * 1000 > 100 * float(M["TwinMilpMs"]), \
    "text: MILP costs milliseconds, QAOA training seconds"
put("TwinText", (
    f"Dispatching the most frequent sample unchecked would have been unsafe in {q['unsafe']:.1f}\\% of event draws for QAOA "
    f"and {s['unsafe']:.1f}\\% for simulated annealing. These include the {M['TwinInfeasible']} infeasible events, where "
    f"any answer a sampler gives is wrong. The verified loop dispatched no invalid plan, escalated every infeasible event "
    f"and no feasible one, and dispatched an optimal plan in {q['opt']:.1f}\\% (QAOA) and {s['opt']:.1f}\\% (annealing) of "
    f"feasible draws. At this size the uncertified loop also behaved well ({q['false']:.1f}\\% and {s['false']:.1f}\\% false "
    f"escalations), because the greedy rule found a plan whenever the sampler did not. The MILP took a median of "
    f"{M['TwinMilpMs']}~ms against {M['TwinEnumMs']}~ms for full enumeration, while one QAOA training took "
    f"{M['TwinQaoaS']}~s of simulation."))

# ---------------- city table
C = j["city"]
# HiGHS status 1 = 60 s time limit: no plan and no proof. exp_p3_v2.py stored these as feasible=False, which an
# escalation cannot claim as certified. exp_p3_timeout.py re-solves exactly these instances with a longer limit.
TO = [r for r in C if r["milp_status"] == 1]
put("CityTimeout", str(len(TO)))
put("CityLimitS", "60")
assert all(r["milp_status"] in (0, 2) for r in C if r not in TO), "every other MILP ended optimal or proved infeasible"
if TO:
    lj = CITY2["timeout"] if CITY2 else json.loads((WORK / "p3_timeout.json").read_text(encoding="utf-8"))
    lr = {(r["city"], r["G"], r["tight"], r["k"]): r for r in lj["rows"]}
    put("LongLimitS", f"{lj['limit_s']:.0f}")
    for r in TO:
        L = lr[(r["city"], r["G"], r["tight"], r["k"])]
        r["long_status"], r["long_ms"] = L["milp_status"], L["milp_ms"]
        r["feasible"] = L["milp_status"] == 0
        for x in r["draws"]["fixed"] + r["draws"]["adaptive"]:
            x["uncert_false_escalation"] = x["uncert_escalate"] and r["feasible"]
    assert len({(r["G"], r["tight"]) for r in TO}) == 1, "text: all time-outs in one cell"
    put("TimeoutG", str(TO[0]["G"]))
    put("TimeoutDemand", f"{int(TO[0]['tight'] * 100)}")
    put("TimeoutSettled", str(sum(r["long_status"] in (0, 2) for r in TO)))
    put("TimeoutFeasible", str(sum(r["long_status"] == 0 for r in TO)))
    put("TimeoutInfeasible", str(sum(r["long_status"] == 2 for r in TO)))
    settled = [r["long_ms"] / 1000 for r in TO if r["long_status"] in (0, 2)]
    put("TimeoutMaxS", f"{max(settled):.0f}" if settled else "--")
    put("TimeoutMinS", f"{min(settled):.0f}" if settled else "--")
put("CityN", str(len(C)))
put("CityMinVars", str(min(r["G"] * r["S"] for r in C)))
put("CityMaxVars", str(max(r["G"] * r["S"] for r in C)))
crow, cv = [], {}
for G in sorted({r["G"] for r in C}):
    for tight in sorted({r["tight"] for r in C}):
        rr = [r for r in C if r["G"] == G and r["tight"] == tight]
        fz = [r for r in rr if r["feasible"]]
        dr = [x for r in fz for x in r["draws"]["fixed"]]
        alld = [x for r in rr for x in r["draws"]["fixed"]]
        solved = [r for r in rr if r not in TO]
        v = {"n": len(rr), "nfeas": len(fz), "valid": pct([x["sampler_found"] for x in dr]),
             "unsafe": pct([x["raw_invalid"] for x in alld]), "false": pct([x["uncert_false_escalation"] for x in dr]),
             "milp_max": max(r["milp_ms"] for r in solved) / 1000, "n_to": len(rr) - len(solved)}
        cv[(G, tight)] = v
        f1 = lambda x: "--" if x != x else f"{x:.1f}"  # no solvable instance in this cell
        tmax = f"{v['milp_max']:.2f}" + (f"$^\\dagger$" if v["n_to"] else "")
        crow.append(f"{G} & {G * 10} & {int(tight * 100)}\\% & {v['nfeas']}/{v['n']} & {f1(v['valid'])} & {v['unsafe']:.1f} & "
                    f"{f1(v['false'])} & {tmax}\\\\")
(OUT / "tab_city.tex").write_text("\n".join(crow), encoding="utf-8")
Gs = sorted({r["G"] for r in C})
allf = [x for r in C if r["feasible"] for x in r["draws"]["fixed"]]
put("CityFalseEsc", f"{pct([x['uncert_false_escalation'] for x in allf]):.1f}")
put("CitySAFoundEight", f"{pct([x['sampler_found'] for r in C if r['feasible'] and r['G'] == Gs[0] for x in r['draws']['fixed']]):.1f}")
put("CitySAFoundThirtyTwo", f"{pct([x['sampler_found'] for r in C if r['feasible'] and r['G'] == Gs[-1] for x in r['draws']['fixed']]):.1f}")
put("MilpMaxS", f"{max(r['milp_ms'] for r in C if r not in TO) / 1000:.1f}")
put("CitySettled", str(len(C) - len(TO)))
put("CityInfeasible", str(sum(not r["feasible"] for r in C)))
assert all(r["milp_ms"] < 60_000 for r in C if r not in TO), "time-outs are exactly the status-1 runs"
put("EightTightFeas", str(cv[(Gs[0], 0.9)]["nfeas"]))
assert cv[(Gs[0], 0.9)]["nfeas"] < 0.25 * cv[(Gs[0], 0.9)]["n"], "text: few 8-group instances at 90% demand had a valid plan"
assert all(v["unsafe"] > 50 for v in cv.values()), "text: unsafe in most calls at every size"
assert float(M["CitySAFoundEight"]) > float(M["CitySAFoundThirtyTwo"]), "text: sampler valid rate falls with size"
assert float(M["CityFalseEsc"]) > 0, "text: uncertified loop escalates solvable cases"
tight_hi = [x["uncert_false_escalation"] for r in C if r["feasible"] and r["tight"] == max(r2["tight"] for r2 in C)
            for x in r["draws"]["fixed"]]
tight_lo = [x["uncert_false_escalation"] for r in C if r["feasible"] and r["tight"] == min(r2["tight"] for r2 in C)
            for x in r["draws"]["fixed"]]
put("CityFalseTight", f"{pct(tight_hi):.1f}")
put("CityFalseLoose", f"{pct(tight_lo):.1f}")
gg = [r["greedy_gap_pct"] for r in C if r["feasible"] and r["greedy_gap_pct"] is not None]
put("CityGreedyGap", f"{np.median(gg):.1f}")
assert float(M["CityFalseLoose"]) < float(M["CityFalseTight"]), "text: false escalation comes from tight capacity"
if TO:
    to_txt = (f"The other {M['CityTimeout']}, all with {M['TimeoutG']} groups at {M['TimeoutDemand']}\\% demand, hit the "
              f"{M['CityLimitS']}~s limit with neither a plan nor a proof, so the loop would have escalated them without a "
              f"certificate. ")
    if M["TimeoutSettled"] == M["CityTimeout"]:
        assert M["TimeoutFeasible"] == M["CityTimeout"], "text: every time-out had a plan"
        to_txt += (f"Given up to {M['LongLimitS']}~s, the solver found an optimal plan for all {M['CityTimeout']} in at "
                   f"most {M['TimeoutMaxS']}~s, one of them in {M['TimeoutMinS']}~s, so solve times vary with machine "
                   f"load. Treating a time-out as proof of infeasibility would have sent solvable cases to a human.")
    else:
        to_txt += (f"A {M['LongLimitS']}~s limit settled {M['TimeoutSettled']} of them ({M['TimeoutFeasible']} with a "
                   f"plan, {M['TimeoutInfeasible']} proved infeasible).")
else:
    DL = 5
    slow = [r for r in C if r["milp_ms"] > DL * 1000]
    put("CityTimeout", "0")
    put("DeadlineS", str(DL))
    put("DeadlineN", str(len(slow)))
    put("MilpSlowS", f"{max(r['milp_ms'] for r in C) / 1000:.1f}")
    assert slow and all(r["feasible"] for r in slow), "text: every instance slower than the deadline had a plan"
    to_txt = (f"No solve reached the {M['CityLimitS']}~s limit; the slowest took {M['MilpSlowS']}~s. A {DL}~s deadline, "
              f"short enough to re-plan within one radio cycle, would have stopped {len(slow)} instances with neither "
              f"a plan nor a proof, and every one of them had a valid plan. A time-out must therefore be reported as "
              f"unknown, never as infeasible.")
put("CityText", (
    f"As the problem grew from {Gs[0]} to {Gs[-1]} groups, simulated annealing produced a valid plan in "
    f"{M['CitySAFoundEight']}\\% and then {M['CitySAFoundThirtyTwo']}\\% of calls on solvable instances; Section~\\ref{{sec:viol}} shows that "
    f"at this scale most samples were not even complete assignments. "
    f"Dispatching the top sample unchecked would have been unsafe in most calls at every size. With 8 groups at 90\\% demand "
    f"each group is about as large as the free seats of an average shelter, and only {M['EightTightFeas']} of 60 "
    f"instances had a valid plan. "
    f"The uncertified loop escalated {M['CityFalseEsc']}\\% of solvable cases overall ({M['CityFalseTight']}\\% at 90\\% "
    f"demand, {M['CityFalseLoose']}\\% at 60\\%), because the greedy rule also fails when capacity is tight. Where the "
    f"greedy rule did find a plan, its median cost was {M['CityGreedyGap']}\\% above the optimum. Within the "
    f"{M['CityLimitS']}~s limit the MILP settled {M['CitySettled']} of the {M['CityN']} instances, finding the optimal plan "
    f"or proving that none exists, in at most {M['MilpMaxS']}~s. " + to_txt))

# ---------------- shot budget
ad = [x for r in T for k in ("qaoa_adaptive", "sa_adaptive") for x in r["draws"][k]]
fx = [x for r in T for k in ("qaoa_fixed", "sa_fixed") for x in r["draws"][k]]
put("AdaptShots", f"{np.mean([x['shots_used'] for x in ad]):.1f}")
same = 0
tot = 0
for r in T:
    for smp in ("qaoa", "sa"):
        for a_, f_ in zip(r["draws"][f"{smp}_adaptive"], r["draws"][f"{smp}_fixed"]):
            tot += 1
            same += (a_["tool"] in ("milp", "escalate")) == (f_["tool"] in ("milp", "escalate")) and \
                a_["cert_escalate"] == f_["cert_escalate"]
put("AdaptSame", f"{100 * same / tot:.1f}")
put("AdaptOptQ", f"{tw['qaoa_adaptive']['opt']:.1f}")
put("FixedOptQ", f"{tw['qaoa_fixed']['opt']:.1f}")
put("AdaptOptSA", f"{tw['sa_adaptive']['opt']:.1f}")
put("FixedOptSA", f"{tw['sa_fixed']['opt']:.1f}")
cad = [x["shots_used"] for r in C for x in r["draws"]["adaptive"]]
put("CityAdaptShots", f"{np.mean(cad):.1f}")
assert same == tot, "abstract/text: adaptive budget took the same escalation decision in every draw"
assert tw["qaoa_fixed"]["opt"] - tw["qaoa_adaptive"]["opt"] > 10, "text: QAOA loses optimality with the adaptive budget"
assert abs(tw["sa_fixed"]["opt"] - tw["sa_adaptive"]["opt"]) < 1, "text: annealing does not"
assert tw["sa_fixed"]["opt"] == tw["sa_fixed"]["valid"] == tw["sa_adaptive"]["opt"], "text: every valid SA sample optimal"
assert float(M["CityAdaptShots"]) > float(M["AdaptShots"]), "text: adaptive rule saves less at city scale than on the twin"
assert np.ceil(np.log(0.01) / np.log(1 - 0.05)) == 90, "text: q=0.05, eps=0.01 needs 90 shots"
put("ShotText", (
    f"With the adaptive budget the twin loop used {M['AdaptShots']} shots per event on average instead of {cfg['shots']} "
    f"and took the same escalation decision in every draw. Plan quality did change for QAOA: it dispatched an optimal plan in "
    f"{M['AdaptOptQ']}\\% of feasible draws against {M['FixedOptQ']}\\% with the full budget, because the loop keeps the "
    f"cheapest valid sample of the first successful batch rather than of all {cfg['shots']} shots. Annealing dispatched an "
    f"optimal plan whenever it found a valid one, with either budget, so its rate stayed at {M['AdaptOptSA']}\\%. At city scale "
    f"the adaptive rule used {M['CityAdaptShots']} shots per call, more than on the twin, because valid samples are rarer there."))
assert 90 > cfg["shots"]
assert float(M["AdaptShots"]) < cfg["shots"], "text: adaptive budget uses fewer shots"

# ---------------- twin results by event
EV = ["initial", "R5 closed", "surge", "closure", "A failed", "B failed"]
erow, ev = [], {}
for e, name in enumerate(EV):
    R = [r for r in T if r["event"] == e]
    F = [r for r in R if r["feasible"]]
    v = {"inf": len(R) - len(F), "n": len(R),
         "uq": pct([x["raw_invalid"] for r in R for x in r["draws"]["qaoa_fixed"]]),
         "us": pct([x["raw_invalid"] for r in R for x in r["draws"]["sa_fixed"]]),
         "oq": pct([x["optimal"] for r in F for x in r["draws"]["qaoa_fixed"]]),
         "os": pct([x["optimal"] for r in F for x in r["draws"]["sa_fixed"]])}
    ev[e] = v
    erow.append(f"E{e} {name} & {v['inf']}/{v['n']} & {v['uq']:.1f} & {v['us']:.1f} & {v['oq']:.1f} & {v['os']:.1f}\\\\")
(OUT / "tab_event.tex").write_text("\n".join(erow), encoding="utf-8")
fq = pct([x["raw_invalid"] for r in T if r["feasible"] for x in r["draws"]["qaoa_fixed"]])
fs = pct([x["raw_invalid"] for r in T if r["feasible"] for x in r["draws"]["sa_fixed"]])
put("TwinRawFeasQ", f"{fq:.1f}")
put("TwinRawFeasSA", f"{fs:.1f}")
put("EvFiveInf", str(ev[5]["inf"]))
put("EvFourQ", f"{ev[4]['uq']:.1f}")
put("EvFourSA", f"{ev[4]['us']:.1f}")
assert max(ev[e]["uq"] for e in (0, 1)) == 0 and max(ev[e]["us"] for e in (0, 1)) <= 1.0, "text: E0/E1 nearly never unsafe"
assert all(ev[e]["inf"] == 0 for e in range(5)), "text: only E5 has infeasible events"
assert all(ev[e]["uq"] > ev[e]["us"] for e in (2, 3, 4)), "text: QAOA top sample unsafe more often than SA after E2"
assert ev[2]["uq"] < ev[3]["uq"] < ev[4]["uq"], "text: unsafe rate grows as the disruption accumulates"
put("EventText", (
    f"In the initial state and after the first road closure "
    f"the most frequent sample was almost always valid. The risk appeared once capacity became tight: after the shelter "
    f"surge, a second closure and the failure of shelter A, the unsafe rate of QAOA rose from {ev[2]['uq']:.1f}\\% to "
    f"{M['EvFourQ']}\\%, and that of annealing from {ev[2]['us']:.1f}\\% to {M['EvFourSA']}\\%. After shelter B also "
    f"failed, {M['EvFiveInf']} of 30 events had no valid plan at all. Counting solvable events only, unverified dispatch "
    f"would still have been unsafe in {M['TwinRawFeasQ']}\\% (QAOA) and {M['TwinRawFeasSA']}\\% (annealing) of draws."))

# ---------------- why the top sample is invalid (exp_p3_viol.py re-run, checked draw for draw against p3_v2.json)
VJ = json.loads((WORK / "p3_viol.json").read_text(encoding="utf-8"))
if CITY2:  # city classes come from the same run as the city tables
    VJ["city"] = [{"city": r["city"], "G": r["G"], "tight": r["tight"], "k": r["k"],
                   "sa": [{"cls": c["cls"], "raw_invalid": c["top_unsafe"]} for c in r["cap"]]} for r in CITY2["city"]]
tkey = {(r["seed"], r["event"]): r for r in T}
for v in VJ["twin"]:
    r = tkey[(v["seed"], v["event"])]
    for smp in ("qaoa", "sa"):
        assert [c["raw_invalid"] for c in v[smp]] == [x["raw_invalid"] for x in r["draws"][f"{smp}_fixed"]], \
            "violation re-run reproduces the twin draws"
ckey = {(r["city"], r["G"], r["tight"], r["k"]): r for r in C}
same_inst = same_draw = n_draw = 0
for v in VJ["city"]:
    r = ckey[(v["city"], v["G"], v["tight"], v["k"])]
    a, b = [c["raw_invalid"] for c in v["sa"]], [x["raw_invalid"] for x in r["draws"]["fixed"]]
    same_inst += a == b
    same_draw += sum(p == q for p, q in zip(a, b))
    n_draw += len(a)
# floating-point order in the vectorised annealer can flip an acceptance at the boundary: report, do not hide
assert same_inst >= 0.99 * len(C), "violation re-run reproduces the city draws"
put("ReproInst", str(same_inst))
put("ReproDrawPct", f"{100 * same_draw / n_draw:.1f}")
assert len(VJ["twin"]) == len(T) and len(VJ["city"]) == len(C)
CLS = ["onehot", "forbidden", "pair", "blind"]
vrow, vv = [], {}
groups = [("Twin, QAOA", [c for v in VJ["twin"] for c in v["qaoa"]]),
          ("Twin, SA", [c for v in VJ["twin"] for c in v["sa"]])] + \
         [(f"City, SA, $G={G}$", [c for v in VJ["city"] if v["G"] == G for c in v["sa"]]) for G in Gs]
for lab, cs in groups:
    bad = [c["cls"] for c in cs if c["cls"] != "valid"]
    assert len(bad) == sum(c["raw_invalid"] for c in cs), "class 'valid' exactly when raw_invalid is false"
    sh = {k: 100 * bad.count(k) / len(bad) if bad else float("nan") for k in CLS}
    vv[lab] = {"n": len(bad), **sh}
    vrow.append(f"{lab} & {len(bad)} & " + " & ".join(f"{sh[k]:.1f}" for k in CLS) + "\\\\")
(OUT / "tab_viol.tex").write_text("\n".join(vrow), encoding="utf-8")
tq, ts = vv["Twin, QAOA"], vv["Twin, SA"]
cl = [vv[f"City, SA, $G={G}$"] for G in Gs]
assert tq["blind"] > 90 and ts["blind"] > 90, "text: twin failures are penalty-free overloads"
assert cl[0]["onehot"] < cl[1]["onehot"] < cl[2]["onehot"] and cl[2]["onehot"] == 100, "text: one-hot breaks grow to all"
assert cl[0]["blind"] > cl[1]["blind"] > cl[2]["blind"], "text: penalty-free share falls with size"
assert max(v["pair"] for v in vv.values()) < 1, "text: penalised overloads almost never on top"
assert max(v["onehot"] for v in (tq,)) == 0, "text: XY mixer keeps one-hot"
put("ViolBlindQ", f"{tq['blind']:.1f}")
put("ViolBlindSA", f"{ts['blind']:.1f}")
put("ViolBlindEight", f"{cl[0]['blind']:.1f}")
put("ViolOnehotEight", f"{cl[0]['onehot']:.1f}")
put("ViolOnehotSixteen", f"{cl[1]['onehot']:.1f}")
put("ViolText", (
    f"On the twin,{M['ViolBlindQ']}\\% of the unsafe QAOA samples and {M['ViolBlindSA']}\\% of the annealing samples "
    f"overfilled a shelter although every pair of groups in it fitted, so the QUBO assigned them no penalty at all. "
    f"Overloads with a penalized pair almost never reached the top, and the XY mixer never broke the one-hot rule. At "
    f"city scale the picture changes: the annealer, run for a fixed 40 sweeps, left groups with no shelter or with several "
    f"in {M['ViolOnehotEight']}\\% of unsafe samples at {Gs[0]} groups, {M['ViolOnehotSixteen']}\\% at {Gs[1]} and all of "
    f"them at {Gs[-1]}, while penalty-free overloads fell from {M['ViolBlindEight']}\\% to none. A small instance fails "
    f"through the encoding and a large one through the search, and the verifier catches both. " +
    ("The twin re-run that produced these classes reproduced the original flags in every draw; the city classes come "
     "from the same run as the city tables."
     if CITY2 else
     f"The re-run that produced these classes reproduced the original flags in every twin draw and in {M['ReproInst']} "
     f"of {len(C)} city instances ({M['ReproDrawPct']}\\% of draws); we attribute the few differences to "
     f"floating-point ordering in the vectorized annealer.")))
assert "sweeps=40), G, S)" in (HERE_SRC := (Path(__file__).parent / "exp_p3_v2.py").read_text(encoding="utf-8")), \
    "text: city annealer runs 40 sweeps"

# ---------------- trace of one twin episode (seed chosen by rule: most events handled by the greedy fallback)
seeds = sorted({r["seed"] for r in T})
n_greedy = lambda sd: sum(any(x["tool"] == "greedy" for x in r["draws"]["qaoa_fixed"]) for r in T if r["seed"] == sd)
tsd = max(seeds, key=lambda sd: (n_greedy(sd), -sd))
TOOL = {"sampler": "sampler", "greedy": "greedy", "milp": "MILP", "escalate": "escalate"}
trow, tr = [], {}
for r in sorted([r for r in T if r["seed"] == tsd], key=lambda r: r["event"]):
    d = r["draws"]["qaoa_fixed"]
    tools = {}
    for x in d:
        tools[x["tool"]] = tools.get(x["tool"], 0) + 1
    gaps = [x["gap_pct"] for x in d if x["gap_pct"] is not None and x["tool"] != "escalate"]
    tr[r["event"]] = {"pf": r["pfeas_qaoa"], "uns": sum(x["raw_invalid"] for x in d), "tools": tools,
                      "opt": sum(bool(x["optimal"]) for x in d), "gap": max(gaps) if gaps else None}
    v = tr[r["event"]]
    tl = ", ".join(f"{TOOL[k]} {n}" for k, n in sorted(tools.items(), key=lambda kv: -kv[1]))
    gs = "--" if v["gap"] is None else f"{v['gap']:.1f}"
    trow.append(f"E{r['event']} {EV[r['event']]} & {'yes' if r['feasible'] else 'no'} & {v['pf']:.2f} & {v['uns']}/10 & "
                f"{tl} & {gs}\\\\")
(OUT / "tab_trace.tex").write_text("\n".join(trow), encoding="utf-8")
put("TraceSeedNo", str(tsd))
put("TracePfTwo", f"{tr[2]['pf']:.2f}")
put("TracePfThree", f"{tr[3]['pf']:.2f}")
put("TraceGreedyGap", f"{max(v['gap'] for v in tr.values() if v['gap'] is not None):.1f}")
assert tr[0]["pf"] > 0.9 and tr[1]["pf"] > 0.9 and tr[2]["pf"] < 0.1 and tr[3]["pf"] < 0.1, "text: QAOA valid mass collapses"
assert tr[3]["tools"] == {"greedy": 10}, "text: greedy carried E3 in every draw"
assert tr[5]["tools"] == {"escalate": 10} and not [r for r in T if r["seed"] == tsd and r["event"] == 5][0]["feasible"], \
    "text: E5 escalated with certificate"
assert all(v["uns"] == 10 for e, v in tr.items() if e >= 2), "text: top sample unsafe in every draw from E2 on"
assert tr[2]["tools"].get("sampler", 0) > 0, "text: verifier found a rare valid sample after the surge"

# ---------------- uncertainty: bootstrap over events / instances (draws of one event are not independent)
from scipy.stats import wilcoxon  # noqa: E402

rng = np.random.default_rng(2026)


def boot(units, f, n=2000):
    """95% percentile interval of f over units resampled with replacement."""
    idx = rng.integers(len(units), size=(n, len(units)))
    v = np.sort([f([units[i] for i in row]) for row in idx])
    return v[int(0.025 * n)], v[int(0.975 * n) - 1]


unsafe_of = lambda key: (lambda rs: pct([x["raw_invalid"] for r in rs for x in r["draws"][key]]))
for key, name in (("qaoa_fixed", "Q"), ("sa_fixed", "SA")):
    lo, hi = boot(T, unsafe_of(key))
    put(f"TwinRaw{name}Lo", f"{lo:.1f}")
    put(f"TwinRaw{name}Hi", f"{hi:.1f}")
fe_ev = [r for r in T if r["feasible"]]
uq = np.array([np.mean([x["raw_invalid"] for x in r["draws"]["qaoa_fixed"]]) for r in fe_ev])
us = np.array([np.mean([x["raw_invalid"] for x in r["draws"]["sa_fixed"]]) for r in fe_ev])
put("PairQWorse", str(int((uq > us).sum())))
put("PairSAWorse", str(int((us > uq).sum())))
put("PairTie", str(int((uq == us).sum())))
put("PairN", str(len(fe_ev)))
pw = wilcoxon(uq, us).pvalue
mant, ex = f"{pw:.1e}".split("e")
put("PairP", f"{mant}\\times10^{{{int(ex)}}}" if pw < 1e-3 else f"{pw:.3f}")
cf = [r for r in C if r["feasible"]]
lo, hi = boot(cf, lambda rs: pct([x["uncert_false_escalation"] for r in rs for x in r["draws"]["fixed"]]))
put("CityFalseLo", f"{lo:.1f}")
put("CityFalseHi", f"{hi:.1f}")
assert lo > 0, "text: false escalation interval above zero"
assert pw < 0.01 and (uq > us).sum() > (us > uq).sum(), "text: QAOA top sample unsafe more often, significant"
put("StatText", (
    f"Resampling events gives 95\\% intervals of {M['TwinRawQLo']}--{M['TwinRawQHi']}\\% for QAOA and "
    f"{M['TwinRawSALo']}--{M['TwinRawSAHi']}\\% for annealing. On the {M['PairN']} solvable events, the top QAOA sample "
    f"was unsafe more often than the top annealing sample in {M['PairQWorse']} events and less often in "
    f"{M['PairSAWorse']} (Wilcoxon signed-rank $p={M['PairP']}$), so the difference is consistent across events and not an effect of a few draws."))

# ---------------- city results by city
RE = CITY2["reach"] if CITY2 else json.loads((WORK / "p3_reach.json").read_text(encoding="utf-8"))
ccrow, cc = [], {}
for city in sorted({r["city"] for r in C}, key=lambda c: -sum(r["feasible"] for r in C if r["city"] == c)):
    R = [r for r in C if r["city"] == city]
    F = [r for r in R if r["feasible"]]
    v = {"nf": len(F), "n": len(R), "valid": pct([x["sampler_found"] for r in F for x in r["draws"]["fixed"]]),
         "unsafe": pct([x["raw_invalid"] for r in R for x in r["draws"]["fixed"]]),
         "false": pct([x["uncert_false_escalation"] for r in F for x in r["draws"]["fixed"]]),
         "greedy": pct([r["greedy_valid"] for r in F]),
         "milp": float(np.median([r["milp_ms"] for r in R])) / 1000, "cut": RE[city]["zones_cut_off"]}
    cc[city] = v
    ccrow.append(f"{city.capitalize()} & {v['nf']}/{v['n']} & {v['valid']:.1f} & {v['unsafe']:.1f} & {v['false']:.1f} & "
                 f"{v['greedy']:.1f} & {v['milp']:.2f}\\\\")
(OUT / "tab_bycity.tex").write_text("\n".join(ccrow), encoding="utf-8")
cut = [c for c in cc if cc[c]["cut"] > 0]
assert cut == ["kolkata"] and RE["kolkata"]["zones_cut_off"] == 1, "text: closures cut off one Kolkata zone only"
assert cc["kolkata"]["nf"] < 10 and all(cc[c]["nf"] >= 40 for c in cc if c != "kolkata"), "text: Kolkata mostly infeasible"
worst = max((c for c in cc if c != "kolkata"), key=lambda c: cc[c]["false"])
put("KolFeas", str(cc["kolkata"]["nf"]))
put("WorstCity", worst.capitalize())
put("WorstFalse", f"{cc[worst]['false']:.1f}")
put("WorstGreedy", f"{cc[worst]['greedy']:.1f}")
put("MinUnsafeCity", f"{min(v['unsafe'] for v in cc.values()):.1f}")
assert cc[worst]["greedy"] == min(cc[c]["greedy"] for c in cc if c != "kolkata"), "text: worst city = weakest greedy"
put("ByCityText", (
    f"Unverified dispatch was unsafe in at least "
    f"{M['MinUnsafeCity']}\\% of calls in every city. In Kolkata the three closures cut one of the six zones off from "
    f"every shelter, so any instance with a group there has no valid plan, and only {M['KolFeas']} of 60 were solvable. "
    f"{M['WorstCity']} had the most false escalations ({M['WorstFalse']}\\%) and the weakest greedy rule, which found a "
    f"plan in {M['WorstGreedy']}\\% of its solvable instances. The failures of the uncertified loop therefore depend on "
    f"the city network as well as on the problem size."))

# ---------------- second revision: usual-practice baselines, exact solver first, longer annealer
import post_p3_r2  # noqa: E402

R2 = post_p3_r2.extend(put, WORK, OUT, T, C, CITY2)

# ---------------- figure
plt.rcParams.update({"font.family": "serif", "font.serif": ["Times New Roman"], "font.size": 8,
                     "pdf.fonttype": 42, "ps.fonttype": 42})
fig, ax = plt.subplots(figsize=(3.45, 1.9))
for tight, ls in ((0.6, "-"), (0.9, "--")):
    ax.plot(Gs, [cv[(G, tight)]["valid"] for G in Gs], "o" + ls, color="0.1", ms=3, lw=0.9,
            label=f"valid sample, demand {int(tight * 100)}%")
    ax.plot(Gs, [cv[(G, tight)]["false"] for G in Gs], "s" + ls, color="0.55", ms=3, lw=0.9,
            label=f"false escalation, demand {int(tight * 100)}%")
ax.set_xticks(Gs)
ax.set_xlabel("groups $G$ (10 shelters)")
ax.set_ylabel("% of calls")
ax.set_ylim(-3, 103)
ax.grid(lw=0.3)
ax.legend(fontsize=5.6, frameon=False, loc="upper right")
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_city.pdf")

# MILP certificate time against size; time-outs drawn at the limit with their re-run time
fig, ax = plt.subplots(figsize=(3.45, 1.75))
jit = np.random.default_rng(1)
for feas, mk, col, lab in ((True, "o", "0.15", "plan found"), (False, "^", "0.6", "proved infeasible")):
    rr = [r for r in C if r not in TO and r["feasible"] == feas]
    ax.scatter([r["G"] * r["S"] * (1 + jit.uniform(-0.08, 0.08)) for r in rr], [r["milp_ms"] / 1000 for r in rr],
               s=5, marker=mk, facecolors="none", edgecolors=col, lw=0.5, label=lab)
if TO:
    xs = [r["G"] * r["S"] for r in TO]
    ax.scatter(xs, [60] * len(TO), s=22, marker="x", color="0", lw=0.8, label=f"time-out at {M['CityLimitS']} s")
    ax.scatter(xs, [r["long_ms"] / 1000 for r in TO], s=14, marker="*", color="0", lw=0.3, label="same, re-run")
ax.axhline(60, color="0.4", lw=0.5, ls=":")
if not TO:
    ax.axhline(5, color="0.2", lw=0.6, ls=":")
ax.set_xscale("log")
ax.set_yscale("log")
ax.set_xticks(sorted({r["G"] * r["S"] for r in C}))
ax.set_xticklabels([str(v) for v in sorted({r["G"] * r["S"] for r in C})])
ax.minorticks_off()
ax.set_xlabel("binary variables $G\\times S$")
ax.set_ylabel("MILP time (s)")
ax.set_ylim(top=5e3)
ax.grid(lw=0.3)
ax.legend(fontsize=5.6, frameon=False, loc="upper left", ncol=2)
fig.tight_layout(pad=0.3)
fig.savefig(OUT / "fig_milp.pdf")
med = {G: float(np.median([r["milp_ms"] for r in C if r["G"] == G and r not in TO])) / 1000 for G in Gs}
put("MilpMedEight", f"{med[Gs[0]]:.2f}")
put("MilpMedThirtyTwo", f"{med[Gs[-1]]:.2f}")
assert med[Gs[0]] < med[Gs[1]] < med[Gs[-1]], "text: median MILP time grows with size"
assert med[Gs[-1]] < 1, "text: median certificate under a second at district scale"

with open(OUT / "nums.tex", "w", encoding="utf-8") as f:
    for k, v in M.items():
        f.write(f"\\newcommand{{\\{k}}}{{{v}}}\n")
print("p3 nums:", len(M))
