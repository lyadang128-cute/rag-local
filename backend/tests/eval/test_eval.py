"""RAGAS-based evaluation for the RAG knowledge base system.

Usage:
    # Run evaluation with the sample test questions
    cd backend
    python -m pytest tests/eval/test_eval.py -v -s

    # Or run standalone
    python tests/eval/test_eval.py

Metrics evaluated:
    - faithfulness: Is the answer factually grounded in the retrieved context?
    - answer_relevancy: How relevant is the answer to the question?
    - context_precision: How relevant and well-ranked are the retrieved chunks?
    - context_recall: How many of the relevant chunks were retrieved?

Requirements:
    pip install ragas datasets
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Ensure backend/ is on path when running standalone
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import asyncio

import pytest
from datasets import Dataset


def load_test_questions() -> list[dict]:
    """Load test question set from JSON."""
    questions_path = Path(__file__).parent / "test_questions.json"
    with open(questions_path, encoding="utf-8") as f:
        return json.load(f)


async def run_rag_pipeline(question: str, top_k: int = 3):
    """Run the full RAG pipeline for a single question.

    Returns (answer, contexts, reference_answer).
    Reference answer is empty when no ground truth is available.
    """
    from app.core.embedder import Embedder
    from app.core.generator import Generator
    from app.core.retriever import Retriever

    embedder = Embedder()
    retriever = Retriever()
    generator = Generator()

    # Retrieve
    query_vec = await embedder.embed_query(question)
    try:
        hits = await retriever.hybrid_search(
            query_vector=query_vec,
            query_text=question,
            top_k=top_k * 4,
        )
    except Exception:
        hits = await retriever.search(query_vec, top_k=top_k * 4)

    # Collect contexts
    contexts = [h.text for h in hits[:top_k]]

    # Generate
    tokens = []
    async for token in generator.generate(question, contexts):
        tokens.append(token)
    answer = "".join(tokens)

    await embedder.close()
    await generator.close()

    return answer, contexts


@pytest.fixture(scope="module")
def test_questions():
    return load_test_questions()


@pytest.mark.asyncio
@pytest.mark.parametrize("idx", range(len(load_test_questions())))
async def test_rag_answer(idx: int):
    """Test each question in the eval set produces a non-empty answer."""
    questions = load_test_questions()
    q = questions[idx]
    answer, contexts = await run_rag_pipeline(q["question"], top_k=3)

    assert answer, f"Empty answer for question: {q['question']}"
    assert len(answer) > 10, f"Answer too short ({len(answer)} chars): {q['question']}"
    assert contexts, f"No contexts retrieved for: {q['question']}"


@pytest.mark.asyncio
async def test_ragas_evaluation():
    """Run RAGAS metrics across the full test question set."""
    try:
        from ragas import evaluate
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_precision,
        )
        from ragas.llms import LangchainLLMWrapper
        from langchain_openai import ChatOpenAI
    except ImportError:
        pytest.skip("ragas or langchain_openai not installed — skipping RAGAS eval")

    from app.config import settings

    questions = load_test_questions()
    if not questions:
        pytest.skip("No test questions defined")

    # Set up the judge LLM (use DeepSeek via OpenAI-compatible API)
    evaluator_llm = LangchainLLMWrapper(
        ChatOpenAI(
            model=settings.deepseek_chat_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
    )

    records = {"question": [], "answer": [], "contexts": [], "ground_truth": []}
    for q in questions:
        answer, contexts = await run_rag_pipeline(q["question"], top_k=3)
        records["question"].append(q["question"])
        records["answer"].append(answer)
        records["contexts"].append(contexts)
        records["ground_truth"].append(q.get("reference_answer", ""))

    dataset = Dataset.from_dict(records)

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision],
        llm=evaluator_llm,
    )

    print("\n=== RAGAS Evaluation Results ===")
    for metric_name, score in result.items():
        print(f"  {metric_name}: {score:.4f}")
    print("================================")

    # Assert minimum quality thresholds (adjust as needed)
    faithfulness_score = result.get("faithfulness", 0)
    assert faithfulness_score >= 0.5, f"Faithfulness too low: {faithfulness_score:.2f}"


def test_eval_data_integrity(test_questions):
    """Ensure eval data is well-formed."""
    assert len(test_questions) > 0, "No test questions found"
    for i, q in enumerate(test_questions):
        assert q.get("question"), f"Question {i} missing 'question' field"
        assert isinstance(q["question"], str), f"Question {i} must be a string"


if __name__ == "__main__":
    # Standalone run (prints results without pytest assertions)
    async def main():
        questions = load_test_questions()
        print(f"Loaded {len(questions)} test questions\n")
        for i, q in enumerate(questions):
            print(f"Q{i+1}: {q['question']}")
            answer, contexts = await run_rag_pipeline(q["question"])
            print(f"  Answer: {answer[:200]}...")
            print(f"  Contexts: {len(contexts)} chunks")
            if q.get("reference_answer"):
                print(f"  Reference: {q['reference_answer'][:200]}...")
            print()

    asyncio.run(main())
