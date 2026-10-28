"""F35 — AI Assistant accuracy evaluation.

Generates ~200 deterministic questions from simulation state (people, shelters,
fleet, dams, flood risk, and unknown people), evaluates answers through the AI
assistant with and without the grounding filter (ablation), and saves
the benchmark to models/ai_eval_v1.json.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agents.dialogue import _fact_numbers, grounded
from backend.config import get_settings
from backend.services import ai_assistant
from backend.services.dam_risk import list_dams

MODELS_DIR = ROOT / "models"
OUTPUT_FILE = MODELS_DIR / "ai_eval_v1.json"

_NUM_RE = re.compile(r"\d+(?:\.\d+)?")
REFUSAL_PHRASES = [
    "could not find",
    "not found",
    "no information",
    "unknown",
    "cannot find",
    "not in this run",
    "missing",
]

# Realistic reference state for Delhi simulation
REFERENCE_STATE: dict[str, Any] = {
    "status": "running",
    "scenario": "heavy_rainfall",
    "city": "delhi",
    "tick": 42,
    "current": {
        "flood_probability": 0.68,
        "rainfall_rate_mm_h": 45.2,
        "river_level_m": 205.45,
    },
    "history": [
        {"rainfall_mm": 110.0, "river_m": 205.15, "dam_m": 200.2},
        {"rainfall_mm": 125.0, "river_m": 205.45, "dam_m": 201.0},
    ],
    "multi_agent": {
        "tier_label": "CRITICAL",
        "agents": [
            {"name": "Rescue Agent", "action": "Dispatched Unit 3 to Geeta Colony"},
            {"name": "Flood Risk Agent", "action": "Monitoring Yamuna gauge rise"},
        ],
        "messages": [
            {"from_name": "Flood Risk Agent", "text": "River level exceeded warning threshold 205.33 m"},
        ],
    },
    "citizens": [
        {
            "citizen_name": "Priya Sharma",
            "age": 29,
            "people": 3,
            "lat": 28.651,
            "lon": 77.262,
            "water_level_note": "knee-deep",
            "vulnerability": "standard",
            "ops_status": "en_route",
            "unit_name": "Ambulance Unit 1",
            "unit_role": "ambulance",
            "unit_base_name": "Central Fire Station",
            "driver_accepted": True,
            "accepted_at": "2026-10-08T10:00:05+00:00",
            "shelter_name": "Talkatora Indoor Stadium",
            "route_to_person": {"km": 4.2, "sim_minutes": 18.0, "method": "qaoa-flood"},
            "route_to_shelter": {"km": 6.1, "sim_minutes": 22.0},
            "timestamps": {"queued": "2026-10-08T10:00:00+00:00", "accepted": "2026-10-08T10:00:05+00:00"},
        },
        {
            "citizen_name": "Amit Verma",
            "age": 68,
            "people": 1,
            "lat": 28.665,
            "lon": 77.235,
            "water_level_note": "chest-deep",
            "vulnerability": "elderly",
            "ops_status": "assigned",
            "unit_name": "Rescue Boat 1",
            "unit_role": "boat",
            "unit_base_name": "Yamuna Depot",
            "driver_accepted": True,
            "shelter_name": "Thyagaraj Stadium",
            "route_to_person": {"km": 3.0, "sim_minutes": 12.0},
            "timestamps": {"queued": "2026-10-08T10:02:00+00:00"},
        },
        {
            "citizen_name": "Sunita Devi",
            "age": 34,
            "people": 4,
            "lat": 28.618,
            "lon": 77.212,
            "water_level_note": "ankle-deep",
            "vulnerability": "children",
            "ops_status": "rescued",
            "unit_name": "Ambulance Unit 2",
            "unit_role": "ambulance",
            "unit_base_name": "South Fire Station",
            "driver_accepted": True,
            "shelter_name": "Talkatora Indoor Stadium",
            "timestamps": {"queued": "2026-10-08T09:40:00+00:00", "rescued": "2026-10-08T10:05:00+00:00"},
        },
        {
            "citizen_name": "Kavita Rao",
            "age": 42,
            "people": 2,
            "lat": 28.632,
            "lon": 77.275,
            "water_level_note": "knee-deep",
            "vulnerability": "standard",
            "ops_status": "queued",
            "unit_name": None,
            "shelter_name": None,
            "timestamps": {"queued": "2026-10-08T10:10:00+00:00"},
        },
        {
            "citizen_name": "Mohammad Irfan",
            "age": 55,
            "people": 5,
            "lat": 28.640,
            "lon": 77.250,
            "water_level_note": "waist-deep",
            "vulnerability": "medical",
            "ops_status": "to_shelter",
            "unit_name": "Ambulance Unit 3",
            "unit_role": "ambulance",
            "unit_base_name": "Central Fire Station",
            "driver_accepted": True,
            "shelter_name": "Thyagaraj Stadium",
            "route_to_shelter": {"km": 5.4, "sim_minutes": 19.5},
            "timestamps": {"queued": "2026-10-08T09:55:00+00:00"},
        },
    ],
    "fleet_board": {
        "ambulances": [
            {"name": "Ambulance Unit 1", "status": "busy", "job": {"citizen_name": "Priya Sharma", "stage": "en_route"}},
            {"name": "Ambulance Unit 2", "status": "free"},
            {"name": "Ambulance Unit 3", "status": "busy", "job": {"citizen_name": "Mohammad Irfan", "stage": "to_shelter"}},
            {"name": "Ambulance Unit 4", "status": "free"},
            {"name": "Ambulance Unit 5", "status": "free"},
            {"name": "Ambulance Unit 6", "status": "free"},
            {"name": "Ambulance Unit 7", "status": "free"},
            {"name": "Ambulance Unit 8", "status": "free"},
            {"name": "Ambulance Unit 9", "status": "free"},
            {"name": "Ambulance Unit 10", "status": "free"},
        ],
        "ambulances_free": 8,
        "ambulances_busy": 2,
        "ambulances_total": 10,
        "waiting_for_ambulance": [],
        "rescue_units_active": [],
    },
    "shelter_allocation": [
        {
            "name": "Talkatora Indoor Stadium",
            "capacity": 1200,
            "seats_left": 1150,
            "allocated_this_run": 7,
            "delivered_this_run": 4,
        },
        {
            "name": "Thyagaraj Stadium",
            "capacity": 850,
            "seats_left": 820,
            "allocated_this_run": 6,
            "delivered_this_run": 0,
        },
    ],
}

FAKE_NAMES = [
    "Rajesh Kumar",
    "Ananya Bose",
    "Vikram Malhotra",
    "Siddharth Sen",
    "Deepa Menon",
    "Rohan Deshmukh",
    "Alok Mukherjee",
    "Neha Chawla",
    "Gaurav Tiwari",
    "Pooja Hegde",
    "Manish Pandey",
    "Meera Pillai",
]


def generate_evaluation_questions(
    state: dict[str, Any],
    dams: list[dict[str, Any]],
    seed: int = 42,
    target_count: int = 200,
) -> list[dict[str, Any]]:
    """Generate ~200 diverse questions grounded in simulation state."""
    rng = random.Random(seed)
    questions: list[dict[str, Any]] = []

    citizens = state.get("citizens", [])
    shelters = state.get("shelter_allocation", [])
    fleet = state.get("fleet_board", {})
    prob = state.get("current", {}).get("flood_probability")
    dams_sample = dams[:5] if dams else []

    # 1. Real Citizen Questions (~70 questions)
    person_templates = [
        ("What is the status of {name}?", "stage", lambda c: c.get("ops_status")),
        ("Where is {name} right now?", "stage", lambda c: c.get("ops_status")),
        ("How many people are with {name}?", "people", lambda c: str(c.get("people"))),
        ("What is the age of {name}?", "age", lambda c: str(c.get("age"))),
        ("Which unit is assigned to {name}?", "unit", lambda c: c.get("unit_name") or "none"),
        ("Which shelter is {name} heading to?", "shelter", lambda c: c.get("shelter_name") or "none"),
        ("What is the water level for {name}?", "water", lambda c: c.get("water_level_note")),
        ("What priority or vulnerability does {name} have?", "vuln", lambda c: c.get("vulnerability")),
        ("Has {name}'s driver accepted?", "accepted", lambda c: "accepted" if c.get("driver_accepted") else "no"),
        ("What is the route distance to {name} in km?", "km", lambda c: str(c.get("route_to_person", {}).get("km") or "unknown")),
        ("How many minutes will it take to reach {name}?", "min", lambda c: str(c.get("route_to_person", {}).get("sim_minutes") or "unknown")),
        ("Give me the current dispatch details for {name}.", "stage", lambda c: c.get("ops_status")),
    ]

    for c in citizens:
        name = c["citizen_name"]
        for tmpl, q_type, val_fn in person_templates:
            val = val_fn(c)
            questions.append({
                "id": f"q_person_{len(questions)+1:03d}",
                "category": "person",
                "question": tmpl.format(name=name),
                "target_entity": name,
                "expected_fact": str(val),
                "expected_refusal": False,
                "key_numbers": [float(m) for m in _NUM_RE.findall(str(val))] if val else [],
            })

    # 2. Unknown Person Questions (Refusal / Hallucination resistance, ~50 questions)
    unknown_templates = [
        "Where is {fake}?",
        "What is the status of {fake}?",
        "Which shelter was {fake} taken to?",
        "Give me the full report on {fake}.",
        "Has {fake} been rescued yet?",
    ]
    for fake in FAKE_NAMES:
        for tmpl in unknown_templates:
            questions.append({
                "id": f"q_unknown_{len(questions)+1:03d}",
                "category": "unknown_person",
                "question": tmpl.format(fake=fake),
                "target_entity": fake,
                "expected_fact": "not found",
                "expected_refusal": True,
                "key_numbers": [],
            })

    # 3. Fleet Questions (~36 questions)
    free_amb = fleet.get("ambulances_free", 0)
    busy_amb = fleet.get("ambulances_busy", 0)
    tot_amb = fleet.get("ambulances_total", 0)

    fleet_q_templates = [
        ("How many ambulances are free?", str(free_amb), [float(free_amb)]),
        ("How many ambulances are busy?", str(busy_amb), [float(busy_amb)]),
        ("What is the total number of ambulances in the fleet?", str(tot_amb), [float(tot_amb)]),
        ("How many ambulances are available right now?", str(free_amb), [float(free_amb)]),
        ("Are all ambulances busy?", "no" if free_amb > 0 else "yes", []),
        ("Tell me the fleet status and how many ambulances are free.", f"{free_amb} of {tot_amb}", [float(free_amb), float(tot_amb)]),
    ]
    for _ in range(6):
        for q_txt, exp, nums in fleet_q_templates:
            questions.append({
                "id": f"q_fleet_{len(questions)+1:03d}",
                "category": "fleet",
                "question": q_txt,
                "target_entity": "fleet",
                "expected_fact": exp,
                "expected_refusal": False,
                "key_numbers": nums,
            })

    # 4. Shelter Questions (~36 questions)
    for s in shelters:
        s_name = s["name"]
        cap = s["capacity"]
        left = s["seats_left"]
        delivered = s["delivered_this_run"]
        shelter_q_templates = [
            (f"How many seats are left at {s_name}?", str(left), [float(left)]),
            (f"What is the capacity of {s_name}?", str(cap), [float(cap)]),
            (f"How many people have reached {s_name}?", str(delivered), [float(delivered)]),
        ]
        for _ in range(6):
            for q_txt, exp, nums in shelter_q_templates:
                questions.append({
                    "id": f"q_shelter_{len(questions)+1:03d}",
                    "category": "shelter",
                    "question": q_txt,
                    "target_entity": s_name,
                    "expected_fact": exp,
                    "expected_refusal": False,
                    "key_numbers": nums,
                })

    # 5. Dam Questions (~30 questions)
    for d in dams_sample:
        d_name = d["name"]
        fill = d.get("fill_percentage")
        st = d.get("state")
        cap_tmc = d.get("live_capacity_tmc")
        dam_q_templates = [
            (f"What is the fill percentage of {d_name}?", str(fill), [float(fill)] if fill is not None else []),
            (f"Which state is {d_name} located in?", st or "unknown", []),
        ]
        if cap_tmc is not None:
            dam_q_templates.append((f"What is the capacity of {d_name} in TMC?", str(cap_tmc), [float(cap_tmc)]))
        for _ in range(2):
            for q_txt, exp, nums in dam_q_templates:
                questions.append({
                    "id": f"q_dam_{len(questions)+1:03d}",
                    "category": "dam",
                    "question": q_txt,
                    "target_entity": d_name,
                    "expected_fact": exp,
                    "expected_refusal": False,
                    "key_numbers": nums,
                })

    # 6. Overall Flood Risk & Weather (~24 questions)
    risk_q_templates = [
        ("What is the current flood probability?", str(prob), [float(prob)] if prob else []),
        ("What is the flood risk right now?", "critical" if prob and prob > 0.6 else "standard", []),
        ("What is the multi-agent tier label?", "CRITICAL", []),
        ("How many total citizens have sent an SOS?", str(len(citizens)), [float(len(citizens))]),
    ]
    for _ in range(6):
        for q_txt, exp, nums in risk_q_templates:
            questions.append({
                "id": f"q_risk_{len(questions)+1:03d}",
                "category": "flood_risk",
                "question": q_txt,
                "target_entity": "risk",
                "expected_fact": exp,
                "expected_refusal": False,
                "key_numbers": nums,
            })

    rng.shuffle(questions)
    while len(questions) < target_count:
        dup = dict(rng.choice(questions))
        dup["id"] = f"q_dup_{len(questions)+1:03d}"
        questions.append(dup)
    if len(questions) > target_count:
        questions = questions[:target_count]
    return questions


def score_answer(
    q: dict[str, Any],
    answer_text: str,
    facts_text: str,
) -> dict[str, Any]:
    """Score one model response against expected fact and grounding constraints."""
    text_lower = (answer_text or "").lower()
    facts_nums = _fact_numbers(facts_text)

    # Number verification
    ans_nums = [float(m) for m in _NUM_RE.findall(answer_text or "")]
    all_numbers_grounded = True
    hallucinated_numbers = []
    for n in ans_nums:
        # Check against facts with rounding tolerance
        decimals = len(str(n).split(".")[1]) if "." in str(n) else 0
        tol = 0.5 * 10 ** (-decimals) + 1e-9
        if not any(abs(n - f) <= tol for f in facts_nums):
            all_numbers_grounded = False
            hallucinated_numbers.append(n)

    # Refusal check
    is_refusal = any(ph in text_lower for ph in REFUSAL_PHRASES)

    expected_refusal = q["expected_refusal"]
    expected_fact = str(q.get("expected_fact") or "").lower()

    if expected_refusal:
        correct = is_refusal and len(hallucinated_numbers) == 0
        verdict = "refused_correctly" if is_refusal else "hallucinated_entity"
    else:
        if is_refusal:
            correct = False
            verdict = "false_refusal"
        else:
            # Check if expected fact keywords or key numbers appear
            key_num_match = all(
                any(abs(kn - an) <= 1e-2 for an in ans_nums)
                for kn in q.get("key_numbers", [])
            )
            fact_keyword_match = expected_fact in text_lower or (
                q["category"] == "person" and (
                    expected_fact.replace("_", " ") in text_lower
                    or expected_fact in text_lower
                )
            )
            fact_matched = key_num_match if q.get("key_numbers") else fact_keyword_match

            if hallucinated_numbers:
                correct = False
                verdict = "hallucinated_numbers"
            elif fact_matched:
                correct = True
                verdict = "correct"
            else:
                correct = False
                verdict = "wrong_fact"

    return {
        "verdict": verdict,
        "correct": correct,
        "is_refusal": is_refusal,
        "all_numbers_grounded": all_numbers_grounded,
        "hallucinated_numbers": hallucinated_numbers,
    }


async def evaluate_assistant(
    questions: list[dict[str, Any]],
    state: dict[str, Any],
    dams: list[dict[str, Any]],
    groq_api_key: str,
    primary_model: str,
    max_eval_items: int = 200,
) -> dict[str, Any]:
    """Run full evaluation with grounding filter and without (ablation)."""
    settings = get_settings()

    eval_subset = questions[:max_eval_items]
    results_with_grounding: list[dict[str, Any]] = []
    results_without_grounding: list[dict[str, Any]] = []

    print(f"Running evaluation on {len(eval_subset)} questions...")

    for i, q in enumerate(eval_subset):
        q_text = q["question"]

        # Production path: answer() enforces grounding filter and falls back to rules if ungrounded
        resp_prod = await ai_assistant.answer(q_text, state, dams, enforce_grounding=True)
        ans_prod = resp_prod.get("answer", "")
        facts_text = "\n".join(resp_prod.get("facts", []))

        score_prod = score_answer(q, ans_prod, facts_text)
        results_with_grounding.append({
            "id": q["id"],
            "category": q["category"],
            "question": q_text,
            "answer": ans_prod,
            "source": resp_prod.get("source"),
            **score_prod,
        })

        # Ablation path: raw LLM answer directly without grounding filter
        resp_raw = await ai_assistant.answer(q_text, state, dams, enforce_grounding=False)
        ans_raw = resp_raw.get("answer", "")
        score_raw = score_answer(q, ans_raw, facts_text)
        results_without_grounding.append({
            "id": q["id"],
            "category": q["category"],
            "question": q_text,
            "answer": ans_raw,
            "source": resp_raw.get("source"),
            **score_raw,
        })

        await asyncio.sleep(0.05)

        if (i + 1) % 20 == 0 or (i + 1) == len(eval_subset):
            print(f"Evaluated {i + 1}/{len(eval_subset)} questions...")

    # Aggregates
    def aggregate(scores: list[dict[str, Any]]) -> dict[str, Any]:
        tot = len(scores)
        correct_count = sum(1 for s in scores if s["correct"])
        grounded_count = sum(1 for s in scores if s["all_numbers_grounded"])
        hallucinated_count = sum(1 for s in scores if s["hallucinated_numbers"])
        refusal_tot = sum(1 for s in scores if s["category"] == "unknown_person")
        refusal_correct = sum(
            1 for s in scores if s["category"] == "unknown_person" and s["is_refusal"]
        )

        by_cat: dict[str, Any] = {}
        for s in scores:
            c = s["category"]
            if c not in by_cat:
                by_cat[c] = {"total": 0, "correct": 0, "grounded": 0}
            by_cat[c]["total"] += 1
            if s["correct"]:
                by_cat[c]["correct"] += 1
            if s["all_numbers_grounded"]:
                by_cat[c]["grounded"] += 1

        for c, data in by_cat.items():
            t = data["total"]
            data["accuracy_pct"] = round((data["correct"] / t) * 100, 1) if t else 0
            data["grounded_pct"] = round((data["grounded"] / t) * 100, 1) if t else 0

        return {
            "total_questions": tot,
            "accuracy_pct": round((correct_count / tot) * 100, 1) if tot else 0,
            "grounded_pct": round((grounded_count / tot) * 100, 1) if tot else 0,
            "hallucination_rate_pct": round((hallucinated_count / tot) * 100, 1) if tot else 0,
            "refusal_accuracy_pct": round((refusal_correct / refusal_tot) * 100, 1) if refusal_tot else 100.0,
            "by_category": by_cat,
        }

    summary_prod = aggregate(results_with_grounding)
    summary_raw = aggregate(results_without_grounding)

    report = {
        "name": "ai_eval_v1",
        "title": "AI Assistant Accuracy and Groundedness Evaluation",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "model": primary_model,
        "seed": 42,
        "total_questions": len(eval_subset),
        "with_grounding": summary_prod,
        "without_grounding_ablation": summary_raw,
        "sample_evaluations": results_with_grounding[:12],
        "notes": [
            f"Evaluated against Groq model {primary_model} with seed 42.",
            "Grounded verification rule: every emitted figure must trace to real facts.",
            "Refusal evaluation tests unknown entities to ensure no fictitious reports are invented.",
        ],
    }

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate AI assistant accuracy and grounding.")
    parser.add_argument("--seed", type=int, default=42, help="Seed for deterministic questions")
    parser.add_argument("--limit", type=int, default=200, help="Number of questions to evaluate")
    parser.add_argument("--out", type=str, default=str(OUTPUT_FILE), help="Output JSON filepath")
    args = parser.parse_args()

    settings = get_settings()
    key = (settings.groq_api_key or "").strip()
    if not key:
        print("ERROR: GROQ_API_KEY is not set in .env. As per F35 spec, evaluation requires the real Groq key and stops without it.")
        sys.exit(1)

    dams = list_dams()
    questions = generate_evaluation_questions(REFERENCE_STATE, dams, seed=args.seed, target_count=args.limit)

    primary_model = settings.groq_model or "openai/gpt-oss-20b"
    report = asyncio.run(
        evaluate_assistant(
            questions=questions,
            state=REFERENCE_STATE,
            dams=dams,
            groq_api_key=key,
            primary_model=primary_model,
            max_eval_items=args.limit,
        )
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"\nSaved evaluation report to {out_path}")
    print(f"Accuracy with grounding filter: {report['with_grounding']['accuracy_pct']}%")
    print(f"Grounded rate with grounding:   {report['with_grounding']['grounded_pct']}%")
    print(f"Accuracy without grounding:      {report['without_grounding_ablation']['accuracy_pct']}%")
    print(f"Grounded rate without grounding: {report['without_grounding_ablation']['grounded_pct']}%")
    print(f"Refusal accuracy:                {report['with_grounding']['refusal_accuracy_pct']}%")


if __name__ == "__main__":
    main()
