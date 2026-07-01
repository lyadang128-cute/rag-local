"""
RAG 系统压力测试工具

用法:
  cd backend
  python -m eval.stress_test --users 50 --rounds 10

测试项目:
  1. 并发搜索 — 模拟多人同时查询
  2. API 延迟分布 — P50/P90/P99
  3. 错误率
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from dataclasses import dataclass, field

import httpx

BASE_URL = "http://127.0.0.1:9090/api/v1"

# 预置测试问题（覆盖不同部门的知识点）
TEST_QUERIES = [
    "员工试用期是多久",
    "如何申请年休假",
    "五险一金的缴纳比例",
    "Git commit 规范是什么",
    "API 接口响应格式要求",
    "绩效考核的等级划分",
    "客户分级标准是什么",
    "售后问题P0级别的响应时间",
    "新员工入职需要提交哪些材料",
    "迟到的扣款标准",
    "销售提成比例怎么算",
    "数据库索引规范",
    "离职流程是什么",
    "测试覆盖率要求",
    "客户投诉处理时效",
]


@dataclass
class Stats:
    """聚合统计"""
    total: int = 0
    success: int = 0
    errors: int = 0
    latencies: list[float] = field(default_factory=list)

    @property
    def error_rate(self) -> float:
        return self.errors / self.total if self.total else 0

    def percentile(self, p: float) -> float:
        if not self.latencies:
            return 0
        sorted_lat = sorted(self.latencies)
        idx = int(len(sorted_lat) * p / 100)
        return sorted_lat[min(idx, len(sorted_lat) - 1)]

    def report(self):
        print(f"  总请求: {self.total}")
        print(f"  成功: {self.success}  |  失败: {self.errors}  |  错误率: {self.error_rate:.1%}")
        print(f"  平均延迟: {sum(self.latencies)/len(self.latencies)*1000:.0f}ms" if self.latencies else "  平均延迟: N/A")
        print(f"  P50: {self.percentile(50)*1000:.0f}ms  |  P90: {self.percentile(90)*1000:.0f}ms  |  P99: {self.percentile(99)*1000:.0f}ms")
        print(f"  最快: {min(self.latencies)*1000:.0f}ms  |  最慢: {max(self.latencies)*1000:.0f}ms" if self.latencies else "")


async def login(client: httpx.AsyncClient, username: str, pwd: str) -> str | None:
    """登录并返回 JWT token"""
    try:
        resp = await client.post(
            f"{BASE_URL}/auth/login",
            json={"username": username, "password": pwd},
        )
        if resp.status_code == 200:
            return resp.json()["data"]["token"]
    except Exception:
        pass
    return None


async def search_one(client: httpx.AsyncClient, query: str, token: str | None, kb_name: str | None) -> tuple[bool, float]:
    """执行一次搜索，返回 (成功, 耗时秒)"""
    t0 = time.perf_counter()
    try:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        body = {"query": query, "top_k": 5}
        if kb_name:
            body["kb_name"] = kb_name
        resp = await client.post(
            f"{BASE_URL}/search",
            json=body,
            headers=headers,
            timeout=30,
        )
        elapsed = time.perf_counter() - t0
        return resp.status_code == 200, elapsed
    except Exception:
        return False, time.perf_counter() - t0


async def test_concurrent_search(users: int, rounds: int, token: str | None):
    """并发搜索测试：users 个虚拟用户，每人发 rounds 次请求"""
    print(f"\n{'='*60}")
    print(f"  并发搜索测试 — {users} 用户 × {rounds} 轮 = {users * rounds} 次请求")
    print(f"{'='*60}")

    stats = Stats()
    sem = asyncio.Semaphore(users)

    async def worker(uid: int):
        nonlocal stats
        async with httpx.AsyncClient() as client:
            for r in range(rounds):
                async with sem:
                    query = TEST_QUERIES[(uid + r) % len(TEST_QUERIES)]
                    ok, elapsed = await search_one(client, query, token, None)
                    stats.total += 1
                    if ok:
                        stats.success += 1
                    else:
                        stats.errors += 1
                    stats.latencies.append(elapsed)
                await asyncio.sleep(0.05)  # slight gap between rounds

    t0 = time.perf_counter()
    tasks = [worker(i) for i in range(users)]
    await asyncio.gather(*tasks)
    total_time = time.perf_counter() - t0

    print(f"\n  总耗时: {total_time:.1f}s  |  QPS: {stats.total/total_time:.1f}")
    stats.report()


async def test_ramp_up(token: str | None):
    """逐步增压测试：从 5 并发逐步加到 100"""
    print(f"\n{'='*60}")
    print(f"  逐步增压测试 — 5 → 10 → 25 → 50 → 100 并发")
    print(f"{'='*60}")

    for users in [5, 10, 25, 50, 100]:
        stats = Stats()
        sem = asyncio.Semaphore(users)

        async def worker(uid):
            nonlocal stats
            async with httpx.AsyncClient() as client:
                async with sem:
                    query = TEST_QUERIES[uid % len(TEST_QUERIES)]
                    ok, elapsed = await search_one(client, query, token, None)
                    stats.total += 1
                    if ok:
                        stats.success += 1
                    else:
                        stats.errors += 1
                    stats.latencies.append(elapsed)

        t0 = time.perf_counter()
        await asyncio.gather(*[worker(i) for i in range(users)])
        elapsed = time.perf_counter() - t0

        avg_lat = (sum(stats.latencies) / len(stats.latencies) * 1000) if stats.latencies else 0
        print(f"  {users:>3} 并发 | QPS: {users/elapsed:5.1f} | 平均: {avg_lat:5.0f}ms | P99: {stats.percentile(99)*1000:5.0f}ms | 错误: {stats.errors}")


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--users", type=int, default=20, help="并发用户数（默认20）")
    parser.add_argument("--rounds", type=int, default=5, help="每用户请求轮次（默认5）")
    parser.add_argument("--ramp", action="store_true", help="执行逐步增压测试")
    args = parser.parse_args()

    print(f"{'='*60}")
    print(f"  RAG 系统压力测试")
    print(f"  目标: {BASE_URL}")
    print(f"{'='*60}")

    # Check backend alive
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get("http://127.0.0.1:9090/health", timeout=5)
            print(f"  [OK] 后端运行中 (status={resp.status_code})")
        except Exception:
            print(f"  [FAIL] 后端未响应，请先启动后端")
            return

    # Try login (soft fail — search still works without auth for public KBs)
    token = None
    async with httpx.AsyncClient() as client:
        token = await login(client, "testadmin", "1234")
    if token:
        print(f"  [OK] Admin 登录成功 (token={token[:20]}...)")
    else:
        print(f"  [WARN] 无可用登录账号，将以匿名模式测试")

    # Test 1: Concurrent search
    await test_concurrent_search(args.users, args.rounds, token)

    # Test 2: Ramp-up (optional)
    if args.ramp:
        await test_ramp_up(token)

    print(f"\n{'='*60}")
    print(f"  压力测试完成")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    asyncio.run(main())
