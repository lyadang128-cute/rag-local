"""
RAG Evaluation Script

Measures:
  Retrieval — Hit Rate, MRR, Recall@K, Precision@K
  Generation — Faithfulness, Answer Relevance (via ragas, if available)
  Latency  — per-stage timing

Usage:
  cd backend
  python -m eval.evaluate --kb-name default
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.core.embedder import Embedder
from app.core.generator import Generator
from app.core.retriever import Retriever
from app.core.reranker import Reranker

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("eval")

EVAL_DIR = Path(__file__).parent
TEST_SET_PATH = EVAL_DIR / "test_set.json"
TOPK = settings.rerank_top_k


@dataclass
class EvalSample:
    question: str
    ground_truth: str
    relevant_patterns: list[str]
    relevant_doc: str = ""
    # Populated during eval
    hits: list = field(default_factory=list)
    answer: str = ""
    hit_rank: int = -1  # 0-based rank of first relevant hit, -1 = miss
    latencies: dict[str, float] = field(default_factory=dict)


def _is_relevant(chunk_text: str, patterns: list[str]) -> bool:
    """Check if chunk text contains any of the relevant patterns."""
    for p in patterns:
        if p in chunk_text:
            return True
    return False


async def run_eval(kb_name: str = "default") -> list[EvalSample]:
    """Run the full evaluation pipeline."""
    embedder = Embedder()
    retriever = Retriever()
    reranker = Reranker()
    generator = Generator()

    with open(TEST_SET_PATH, encoding="utf-8") as f:
        samples_raw = json.load(f)

    samples = [EvalSample(**s) for s in samples_raw]

    print(f"\n{'='*60}")
    print(f"  RAG Evaluation — {len(samples)} questions")
    print(f"  KB: {kb_name}  |  top_k: {TOPK}  |  min_score: {settings.min_score}")
    print(f"  Embed: {settings.embed_mode} ({settings.embed_dim}D)")
    print(f"{'='*60}\n")

    for idx, s in enumerate(samples, 1):
        print(f"[{idx}/{len(samples)}] {s.question}")

        # ── Step 1: Embed ──
        t0 = time.perf_counter()
        qv = await embedder.embed_query(s.question)
        s.latencies["embed"] = round(time.perf_counter() - t0, 3)

        # ── Step 2: Hybrid search ──
        t0 = time.perf_counter()
        try:
            hits = await retriever.hybrid_search(qv, s.question, top_k=TOPK, kb_name=kb_name)
        except Exception:
            hits = await retriever.search(qv, top_k=TOPK, kb_name=kb_name)
        s.latencies["retrieve"] = round(time.perf_counter() - t0, 3)

        # ── Find first relevant rank ──
        for rank, h in enumerate(hits):
            if _is_relevant(h.text, s.relevant_patterns):
                s.hit_rank = rank
                break
        s.hits = hits

        # ── Step 3: Filter + Rerank ──
        t0 = time.perf_counter()
        candidates = [h for h in hits if h.score >= settings.min_score]
        if candidates and len(candidates) > TOPK:
            try:
                texts = [h.text for h in candidates]
                metas = [
                    {"filename": h.filename, "text": h.text, "chapter_title": h.chapter_title}
                    for h in candidates
                ]
                sorted_texts, _, _ = await reranker.filter_and_sort(
                    s.question, texts, metas, top_k=TOPK
                )
                contexts = sorted_texts
            except Exception:
                contexts = [h.text for h in candidates[:TOPK]]
        else:
            contexts = [h.text for h in candidates[:TOPK]]
        s.latencies["rerank"] = round(time.perf_counter() - t0, 3)

        # ── Step 4: Generate ──
        t0 = time.perf_counter()
        full = ""
        async for token in generator.generate(s.question, contexts, []):
            full += token
        s.answer = full.strip()
        s.latencies["generate"] = round(time.perf_counter() - t0, 3)

        # Report
        rel = "HIT" if s.hit_rank >= 0 else "MISS"
        rank_str = f"rank={s.hit_rank+1}" if s.hit_rank >= 0 else "-"
        print(f"    [{rel}] {rank_str}  |  embed={s.latencies['embed']}s"
              f"  retrieve={s.latencies['retrieve']}s  rerank={s.latencies['rerank']}s"
              f"  generate={s.latencies['generate']}s  answer_len={len(s.answer)}")

        await asyncio.sleep(0.5)  # avoid hammering the API

    await generator.close()
    return samples


def compute_metrics(samples: list[EvalSample]) -> dict:
    """Compute retrieval metrics."""
    n = len(samples)
    total_relevant = n  # assuming at least 1 relevant doc per question

    # Hit Rate: fraction of questions where at least 1 relevant chunk retrieved
    hits_at_k = {1: 0, 3: 0, 5: 0}
    reciprocal_ranks = []
    precision_sums = {1: 0.0, 5: 0.0}
    recall_sums = {1: 0.0, 5: 0.0}

    for s in samples:
        rank = s.hit_rank
        if rank >= 0:
            reciprocal_ranks.append(1.0 / (rank + 1))
            for k in hits_at_k:
                if rank < k:
                    hits_at_k[k] += 1
            # Precision@K: among top K, how many are relevant
            for k in precision_sums:
                relevant_in_topk = sum(
                    1 for h in s.hits[:k] if _is_relevant(h.text, s.relevant_patterns)
                )
                precision_sums[k] += relevant_in_topk / k
                recall_sums[k] += min(relevant_in_topk, 1) / 1  # binary: found or not
        else:
            reciprocal_ranks.append(0.0)

    metrics = {
        "total_questions": n,
        "hit_rate@1": round(hits_at_k[1] / n, 3),
        "hit_rate@3": round(hits_at_k[3] / n, 3),
        "hit_rate@5": round(hits_at_k[5] / n, 3),
        "mrr": round(sum(reciprocal_ranks) / n, 3),
        "precision@1": round(precision_sums[1] / n, 3),
        "precision@5": round(precision_sums[5] / n, 3),
        "recall@5": round(recall_sums[5] / n, 3),
    }
    return metrics


def compute_latency(samples: list[EvalSample]) -> dict:
    """Aggregate latency stats."""
    stages = ["embed", "retrieve", "rerank", "generate"]
    result = {}
    for stage in stages:
        vals = [s.latencies.get(stage, 0) for s in samples]
        result[stage] = {
            "avg": round(sum(vals) / len(vals), 3),
            "max": round(max(vals), 3),
            "min": round(min(vals), 3),
        }
    total_avgs = [sum(s.latencies.get(st, 0) for st in stages) for s in samples]
    result["total_avg"] = round(sum(total_avgs) / len(total_avgs), 3)
    return result


def print_report(samples: list[EvalSample], metrics: dict, latency: dict):
    """Pretty-print the evaluation report."""

    print(f"\n{'='*60}")
    print("  RETRIEVAL METRICS")
    print(f"{'='*60}")
    for k, v in metrics.items():
        print(f"  {k:<18s} : {v}")

    print(f"\n{'='*60}")
    print("  LATENCY (seconds)")
    print(f"{'='*60}")
    for stage, stats in latency.items():
        if stage == "total_avg":
            print(f"  {'total (avg)':<18s} : {stats}s")
        else:
            print(f"  {stage:<18s} : avg={stats['avg']}s  min={stats['min']}s  max={stats['max']}s")

    print(f"\n{'='*60}")
    print("  PER-QUESTION DETAIL")
    print(f"{'='*60}")
    for idx, s in enumerate(samples, 1):
        status = f"rank={s.hit_rank+1}" if s.hit_rank >= 0 else "MISS"
        preview = s.answer[:300].replace("\n", " ")
        print(f"\n  [{idx}] {s.question}")
        print(f"      Status: {status}")
        print(f"      Answer: {preview}{'...' if len(s.answer) > 300 else ''}")

    # ── Ragas generation metrics ──
    try:
        from ragas import evaluate as ragas_evaluate
        from ragas.metrics import faithfulness, answer_relevancy
        from datasets import Dataset
        from langchain_openai import ChatOpenAI

        print(f"\n{'='*60}")
        print("  GENERATION METRICS (ragas)")
        print(f"{'='*60}")

        eval_llm = ChatOpenAI(
            model=settings.deepseek_chat_model,
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )

        ragas_data = {
            "question": [s.question for s in samples],
            "answer": [s.answer for s in samples],
            "contexts": [[h.text for h in s.hits[:TOPK]] for s in samples],
            "ground_truth": [s.ground_truth for s in samples],
        }
        dataset = Dataset.from_dict(ragas_data)
        result = ragas_evaluate(
            dataset, metrics=[faithfulness, answer_relevancy], llm=eval_llm
        )
        print(f"  Faithfulness      : {result['faithfulness']:.3f}")
        print(f"  Answer Relevance  : {result['answer_relevancy']:.3f}")
    except ImportError:
        print(f"\n  [install ragas + langchain-openai for generation metrics]")
    except Exception as e:
        print(f"\n  [ragas evaluation skipped: {e}]")

    print(f"\n{'='*60}\n")


def save_results(samples: list[EvalSample], metrics: dict, latency: dict):
    """Save detailed results to JSON."""
    results = {
        "metrics": metrics,
        "latency": latency,
        "details": []
    }
    for s in samples:
        results["details"].append({
            "question": s.question,
            "status": f"rank={s.hit_rank+1}" if s.hit_rank >= 0 else "MISS",
            "answer": s.answer,
            "ground_truth": s.ground_truth,
            "hit_rank": s.hit_rank,
            "latencies": s.latencies,
        })

    out_path = EVAL_DIR / "results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n  Results saved to: {out_path}")


async def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--kb-name", default="default")
    args = parser.parse_args()

    samples = await run_eval(args.kb_name)
    metrics = compute_metrics(samples)
    latency = compute_latency(samples)
    print_report(samples, metrics, latency)
    save_results(samples, metrics, latency)


if __name__ == "__main__":
    asyncio.run(main())
