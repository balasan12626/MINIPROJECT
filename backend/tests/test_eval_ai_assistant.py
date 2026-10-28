"""F35 — Tests for AI Assistant accuracy evaluation script."""

from scripts.eval_ai_assistant import (
    REFERENCE_STATE,
    generate_evaluation_questions,
    score_answer,
)
from backend.services.dam_risk import list_dams


def test_question_generator_is_deterministic_with_seed():
    dams = list_dams()
    q1 = generate_evaluation_questions(REFERENCE_STATE, dams, seed=42, target_count=50)
    q2 = generate_evaluation_questions(REFERENCE_STATE, dams, seed=42, target_count=50)
    assert len(q1) == len(q2) == 50
    assert [q["id"] for q in q1] == [q["id"] for q in q2]
    assert [q["question"] for q in q1] == [q["question"] for q in q2]


def test_question_generator_covers_categories():
    dams = list_dams()
    questions = generate_evaluation_questions(REFERENCE_STATE, dams, seed=123, target_count=200)
    assert len(questions) == 200
    categories = {q["category"] for q in questions}
    assert {"person", "unknown_person", "fleet", "shelter", "dam", "flood_risk"} <= categories


def test_score_grounded_answer():
    q = {
        "id": "q1",
        "category": "fleet",
        "question": "How many ambulances are free?",
        "target_entity": "fleet",
        "expected_fact": "8",
        "expected_refusal": False,
        "key_numbers": [8.0],
    }
    facts_text = "Ambulances: 8 of 10 free, 2 on jobs."
    answer = "There are 8 ambulances currently free."
    score = score_answer(q, answer, facts_text)
    assert score["correct"] is True
    assert score["all_numbers_grounded"] is True
    assert score["verdict"] == "correct"
    assert len(score["hallucinated_numbers"]) == 0


def test_score_hallucinated_number():
    q = {
        "id": "q2",
        "category": "fleet",
        "question": "How many ambulances are free?",
        "target_entity": "fleet",
        "expected_fact": "8",
        "expected_refusal": False,
        "key_numbers": [8.0],
    }
    facts_text = "Ambulances: 8 of 10 free, 2 on jobs."
    # Emits 42 which does not exist in facts
    answer = "There are 42 ambulances currently free."
    score = score_answer(q, answer, facts_text)
    assert score["correct"] is False
    assert score["all_numbers_grounded"] is False
    assert score["verdict"] == "hallucinated_numbers"
    assert 42.0 in score["hallucinated_numbers"]


def test_score_correct_refusal_for_unknown_person():
    q = {
        "id": "q3",
        "category": "unknown_person",
        "question": "Where is Rajesh Kumar?",
        "target_entity": "Rajesh Kumar",
        "expected_fact": "not found",
        "expected_refusal": True,
        "key_numbers": [],
    }
    facts_text = "Status: running. Overall: 5 citizens."
    answer = "I could not find that person in this run's SOS list."
    score = score_answer(q, answer, facts_text)
    assert score["correct"] is True
    assert score["is_refusal"] is True
    assert score["verdict"] == "refused_correctly"


def test_score_hallucinated_entity_for_unknown_person():
    q = {
        "id": "q4",
        "category": "unknown_person",
        "question": "Where is Rajesh Kumar?",
        "target_entity": "Rajesh Kumar",
        "expected_fact": "not found",
        "expected_refusal": True,
        "key_numbers": [],
    }
    facts_text = "Status: running. Overall: 5 citizens."
    # Fabricating a story for a non-existent person
    answer = "Rajesh Kumar is at Talkatora Stadium with 2 family members."
    score = score_answer(q, answer, facts_text)
    assert score["correct"] is False
    assert score["is_refusal"] is False
    assert score["verdict"] == "hallucinated_entity"
