import json
import logging

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse, StreamingResponse

from app.config import settings
from app.core.embedder import Embedder
from app.core.generator import Generator
from app.core.qa_memory import find_similar as qa_find_similar
from app.core.qa_memory import save as qa_save
from app.core.qa_memory import search as qa_search
from app.core.qa_memory import stats as qa_stats
from app.core.retriever import Retriever, SearchHit
from app.core.reranker import Reranker
from app.models.schemas import ChatRequest, CorrectionRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])


def _get_embedder() -> Embedder:
    return Embedder()


def _get_retriever() -> Retriever:
    return Retriever()


def _get_generator() -> Generator:
    return Generator()


def _get_reranker() -> Reranker:
    return Reranker()


def _sse(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"



@router.post("")
async def chat(
    req: ChatRequest,
    embedder: Embedder = Depends(_get_embedder),
    retriever: Retriever = Depends(_get_retriever),
    generator: Generator = Depends(_get_generator),
    reranker: Reranker = Depends(_get_reranker),
):
    # Step 0 — Handle /correct command: update the answer for the last user question
    if req.question.strip().startswith("/correct"):
        corrected_answer = req.question.strip()[len("/correct"):].strip()
        if not corrected_answer:
            async def _err_stream():
                yield _sse("chunk", json.dumps({"content": "用法：/correct <正确答案>，例如 /correct 最强者是庞纬"}, ensure_ascii=False))
                yield _sse("done", "{}")
            return StreamingResponse(_err_stream(), media_type="text/event-stream")

        # Find the last user question from chat history (before this /correct command)
        target_question = None
        for msg in reversed(req.history):
            if msg.role == "user" and not msg.content.strip().startswith("/correct"):
                target_question = msg.content
                break

        if target_question:
            qv_correct = await embedder.embed_query(target_question)
            await qa_save(target_question, corrected_answer, qv_correct, req.kb_name, overwrite=True)
            logger.info(f"/correct: matched via history '{target_question[:30]}...' -> '{corrected_answer[:40]}...'")
            msg = f"已更新记忆！\n原问题：{target_question}\n新答案：{corrected_answer}"
        else:
            # Fallback: search for the most similar question in existing memory
            qv_correct = await embedder.embed_query(corrected_answer)
            similar = await qa_find_similar(qv_correct, req.kb_name)
            if similar:
                best_q, best_sim = similar
                await qa_save(best_q, corrected_answer, qv_correct, req.kb_name, overwrite=True)
                msg = f"已更新记忆！\n匹配到：{best_q}\n新答案：{corrected_answer}"
            else:
                msg = "没有找到可纠正的记忆记录。请先问一个问题，得到答案后再用 /correct 纠正。"

        async def _ok_stream():
            yield _sse("chunk", json.dumps({"content": msg}, ensure_ascii=False))
            yield _sse("done", "{}")
        return StreamingResponse(_ok_stream(), media_type="text/event-stream")

    # Step 1 — QA memory lookup: if a similar question was corrected before,
    # return the memorized answer directly, bypassing the RAG pipeline.
    qv_mem = await embedder.embed_query(req.question)
    memory_hit = await qa_search(qv_mem, req.kb_name)
    if memory_hit:
        memorized_answer, sim_score = memory_hit
        logger.info(f"QA memory hit (similarity={sim_score:.3f}), returning memorized answer")

        async def memory_stream():
            sources_json = json.dumps(
                {"items": [{"filename": "[已矫正记忆]", "text": memorized_answer, "score": sim_score, "chapter": ""}]},
                ensure_ascii=False,
            )
            yield _sse("sources", sources_json)
            yield _sse("chunk", json.dumps({"content": memorized_answer}, ensure_ascii=False))
            yield _sse("done", "{}")

        return StreamingResponse(memory_stream(), media_type="text/event-stream")

    # Step 1 — Query rewriting for better recall on large collections
    rewrites = [req.question]
    if not req.fast_mode:
        rewrite_prompt = f"""将以下问题改写为2-3个不同的搜索短语，用于在小说中查找相关内容。\n问题：{req.question}\n\n只输出搜索短语，每行一个，不要编号："""
        gen = Generator()
        try:
            raw = ""
            async for token in gen.generate(rewrite_prompt, [], []):
                raw += token
            for line in raw.strip().split("\n"):
                line = line.strip().lstrip("-0123456789.、) ").strip()
                if line and len(line) > 2:
                    rewrites.append(line)
            rewrites = list(dict.fromkeys(rewrites))[:4]  # dedupe, max 4 variants
        except Exception:
            logger.warning("Query rewriting failed, using original question only", exc_info=True)
        finally:
            await gen.close()

    # Step 2 — Search with all query variants, then merge & dedupe
    seen_ids: set[str] = set()
    all_hits: list = []
    per_query = max(30, settings.recall_top_k // len(rewrites))

    for q in rewrites:
        try:
            qv = await embedder.embed_query(q)
            hits = await retriever.hybrid_search(qv, q, top_k=per_query, kb_name=req.kb_name)
        except Exception:
            logger.warning(f"Search failed for variant: {q[:30]}", exc_info=True)
            continue
        for h in hits:
            if h.chunk_id not in seen_ids:
                seen_ids.add(h.chunk_id)
                all_hits.append(h)

    hits = sorted(all_hits, key=lambda h: h.score, reverse=True)[:settings.recall_top_k]
    logger.info(f"Multi-query: {len(rewrites)} variants → {len(all_hits)} unique hits → {len(hits)} final")

    # Step 2 — Filter by minimum relevance score
    candidates = [h for h in hits if h.score >= settings.min_score]

    # Step 3 — Cross-Encoder reranking
    if candidates and len(candidates) > settings.rerank_top_k:
        try:
            doc_texts = [h.text for h in candidates]
            doc_metas = [
                {"filename": h.filename, "score": h.score, "metadata": h.metadata}
                for h in candidates
            ]
            sorted_texts, sorted_metas, sorted_scores = await reranker.filter_and_sort(
                req.question, doc_texts, doc_metas, top_k=settings.rerank_top_k
            )
            relevant_hits = []
            for text, meta, score in zip(sorted_texts, sorted_metas, sorted_scores):
                relevant_hits.append(
                    SearchHit(
                        chunk_id=meta.get("chunk_id", ""),
                        doc_id=meta.get("doc_id", ""),
                        filename=meta.get("filename", ""),
                        text=text,
                        score=score,
                        prev_text=meta.get("prev_text", ""),
                        next_text=meta.get("next_text", ""),
                        chapter_title=meta.get("chapter_title", ""),
                        metadata=meta.get("metadata", {}),
                    )
                )
        except Exception:
            logger.warning("Reranking failed, using raw search results", exc_info=True)
            relevant_hits = candidates[: settings.rerank_top_k]
    else:
        relevant_hits = candidates[: settings.rerank_top_k]

    # ── Relevance label helper ──────────────────────────────────────
    def _relevance_label(score: float) -> str:
        if score >= 0.7:
            return "【高度相关】"
        elif score >= 0.4:
            return "【相关】"
        else:
            return "【部分相关】"

    # Build expanded contexts (chunk + its neighbors for narrative continuity)
    contexts = []
    for h in relevant_hits:
        # Build a rich header with relevance and context info
        header_parts = [_relevance_label(h.score)]
        if hasattr(h, "chapter_title") and h.chapter_title:
            header_parts.append(f"[章节：{h.chapter_title}]")
        if hasattr(h, "filename") and h.filename:
            fname = h.filename
            if len(fname) > 60:
                fname = fname[:57] + "..."
            header_parts.append(f"[文件：{fname}]")
        header = "".join(header_parts)

        parts = []
        if hasattr(h, "prev_text") and h.prev_text:
            parts.append(h.prev_text)
        parts.append(h.text)
        if hasattr(h, "next_text") and h.next_text:
            parts.append(h.next_text)
        body = "\n".join(parts)
        contexts.append(header + "\n" + body)

    history_dicts = [h.model_dump() for h in req.history]

    async def event_stream():
        sources_json = json.dumps(
            {
                "items": [
                    {"filename": h.filename, "text": h.text, "score": h.score,
                     "chapter": h.chapter_title}
                    for h in relevant_hits
                ]
            },
            ensure_ascii=False,
        )
        yield _sse("sources", sources_json)

        full_answer = ""
        async for token in generator.generate(req.question, contexts, history_dicts):
            full_answer += token
            yield _sse("chunk", json.dumps({"content": token}, ensure_ascii=False))

        yield _sse("done", "{}")

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/correct")
async def correct(
    req: CorrectionRequest,
    embedder: Embedder = Depends(_get_embedder),
):
    """Save a corrected answer to QA memory.

    After calling this endpoint, future similar questions will return
    the memorized answer directly without going through the RAG pipeline.
    """
    qv = await embedder.embed_query(req.question)
    await qa_save(req.question, req.answer, qv, req.kb_name, overwrite=True)
    return {"code": 0, "message": "ok", "data": {"question": req.question}}


@router.get("/memory/stats")
async def memory_stats(kb_name: str = "default"):
    """Return QA memory statistics."""
    s = qa_stats(kb_name)
    return {"code": 0, "message": "ok", "data": s}
