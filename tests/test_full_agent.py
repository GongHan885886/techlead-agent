#!/usr/bin/env python3
"""
Full end-to-end test for TechLead Agent with mocked external APIs.

Covers:
1. scan             - Daily scan (TAPD + GitLab)
2. review-design    - Design review routing (orchestrator decides which agent)
3. review-mr        - Code review routing
4. profile          - Learning advisor (error book analysis)
5. weekly-report    - Weekly summary
6. intent           - Orchestrator intent recognition
7. cache            - File / LLM / HTTP cache core functions
8. persistence      - Disk-backed cache
"""

import asyncio
import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["OPENAI_API_KEY"] = "test-key-for-mock"
os.environ["LLM_MODEL"] = "gpt-4o-mock"
os.environ["CACHE_ENABLED"] = "true"

from tools.memory_store import init_db, record_issue, record_team_metric
from tools.cache_manager import get_cache_manager

# === Reset & seed DB ===
import sqlite3
from config import settings
db = settings.db_path
if os.path.exists(db):
    os.remove(db)
init_db()

SEED = [
    ("张三", "transaction", "blocker", "文件上传",
     "private 方法使用 @Transactional 失效", "改为 public"),
    ("张三", "transaction", "warning", "交易系统",
     "同类内部调用事务不回滚", "注入自身Bean"),
    ("张三", "logging", "warning", "支付", "缺少业务ID日志", "添加 orderId"),
    ("李四", "multithread", "blocker", "订单查询",
     "HashMap 并发读写异常", "改用 ConcurrentHashMap"),
    ("王五", "sql", "warning", "报表", "大表全表扫描", "添加索引"),
]
for dev, it, sev, sc, desc, sug in SEED:
    record_issue(developer_name=dev, issue_type=it, severity=sev,
                 scenario=sc, description=desc, suggestion=sug, source="code_review")
record_team_metric("avg_delivery_days", 4.5, "days", {"developer": "张三"})
record_team_metric("avg_delivery_days", 3.2, "days", {"developer": "李四"})
record_team_metric("defect_rate", 2.1, "score/day", {"developer": "张三"})

from agents.orchestrator import OrchestratorAgent


def mock_llm(content="ok"):
    mc = MagicMock()
    mc.message.content = content
    mc.message.function_call = None
    r = MagicMock()
    r.choices = [mc]
    r.usage = MagicMock(prompt_tokens=100, completion_tokens=50, total_tokens=150)
    r.model = "gpt-4o-m"
    return r


class TestTechLeadAgent(unittest.TestCase):
    """Full integration tests with mocked APIs."""

    def setUp(self):
        get_cache_manager().clear_all()
        self._patch_llm()

    def tearDown(self):
        self._llm_patcher.stop()

    def _patch_llm(self):
        self._llm_patcher = patch("openai.OpenAI")
        mo = self._llm_patcher.start()
        mc = MagicMock()
        mc.create = MagicMock(return_value=mock_llm(
            "🔴 Blocker: [F001] 文件大小限制\n🟡 Warning: [F004] 存储方案"))
        mo.return_value.chat.completions = mc

    async def _run(self, message, extra=None, mock_tapd=False, mock_git=False):
        patches = []
        if mock_tapd:
            t = MagicMock()
            t.fetch_stories = AsyncMock(return_value=[
                {"id": "S1", "title": "文件上传", "owner": "张三",
                 "status": "进行中", "progress": 60,
                 "due_date": (datetime.now()+timedelta(days=1)).strftime("%Y-%m-%d"),
                 "begin_date": (datetime.now()-timedelta(days=10)).strftime("%Y-%m-%d"),
                 "modified": datetime.now().strftime("%Y-%m-%d"), "priority": "P0"}])
            t.fetch_bugs = AsyncMock(return_value=[])
            patches.append(("tools.tapd_client.get_tapd_client", lambda: t))
        if mock_git:
            g = MagicMock()
            g.fetch_mrs = AsyncMock(return_value=[
                {"id": 111, "iid": 111, "title": "feat: upload",
                 "author": "张三", "state": "opened", "draft": False,
                 "source_branch": "feat/up", "target_branch": "main",
                 "created_at": "2026-07-12T10:00:00Z",
                 "updated_at": "2026-07-14T08:00:00Z",
                 "web_url": "https://gitlab.example.com/mr/111",
                 "changes_count": 15, "additions": 450, "deletions": 30}])
            g.fetch_mr_diff = AsyncMock(return_value="--- a/X.java\n+++ b/X.java\n@@ -1 +1 @@\n-old\n+new")
            g.is_configured = MagicMock(return_value=True)
            patches.append(("tools.git_client.get_git_client", lambda: g))
        for target, factory in patches:
            patcher = patch(target, factory)
            patcher.start()
            self.addCleanup(patcher.stop)
        data = extra or {}
        data["message"] = message
        o = OrchestratorAgent()
        return await o.process(data)

    # ==================== Tests ====================

    def test_01_scan(self):
        """1. Scan — fetches TAPD stories + GitLab MRs via orchestrator."""
        async def t():
            r = await self._run("scan", mock_tapd=True, mock_git=True)
            self.assertEqual(r["intent"], "scan")
        asyncio.run(t())
        print("  ✅ scan: orchestrator routed correctly")

    def test_02_design_review(self):
        """2. Design review — orchestrator routes to deep_review."""
        async def t():
            r = await self._run("评审张三的方案", {"author": "张三", "scenario": "file-upload"})
            self.assertEqual(r["intent"], "deep_review")
        asyncio.run(t())
        print("  ✅ design_review: intent=deep_review")

    def test_03_code_review(self):
        """3. Code review — orchestrator routes to code_review."""
        async def t():
            r = await self._run("CR MR !111", {"mr_id": 111})
            self.assertEqual(r["intent"], "code_review")
        asyncio.run(t())
        print("  ✅ code_review: intent=code_review")

    def test_04_profile(self):
        """4. Profile — error book analysis with seeded data."""
        async def t():
            r = await self._run("查一下张三的错题", {"developer": "张三", "days": 30})
            self.assertEqual(r["intent"], "learning_advice")
            raw = r.get("raw_result", {})
            # raw result has nested profile
            profile = raw.get("profile", {})
            self.assertGreater(profile.get("total_issues", 0), 0,
                               f"Expected data for 张三, got profile={profile}")
            return r
        r = asyncio.run(t())
        raw = r.get("raw_result", {})
        profile = raw.get("profile", {})
        print(f"  ✅ profile: {profile.get('total_issues')} issues, "
              f"blockers={profile.get('blocker_count')}")

    def test_05_weekly_report(self):
        """5. Weekly report — delivery + team overview."""
        async def t():
            r = await self._run("生成周报", mock_tapd=True, mock_git=True)
            self.assertEqual(r["intent"], "weekly_report")
            self.assertIn("delivery", r)
            self.assertIn("team", r)
        asyncio.run(t())
        print("  ✅ weekly_report: intent=weekly_report")

    def test_06_intent_recognition(self):
        """6. Intent recognition — orchestrator._identify_intent."""
        o = OrchestratorAgent()
        cases = [
            ("scan",              "扫描今天的工作"),
            ("scan",              "扫描今天的 MR"),
            ("deep_review",       "评审张三的方案"),
            ("deep_review",       "方案评审"),
            ("code_review",       "CR MR !123"),
            ("code_review",       "帮我代码审查"),
            ("weekly_report",     "生成周报"),
            ("weekly_report",     "weekly"),
            ("learning_advice",   "错题"),
            ("learning_advice",   "张三的学习建议"),
            ("help",              "帮助"),
            ("unknown",           "天气不错"),
        ]
        for exp, msg in cases:
            self.assertEqual(o._identify_intent(msg), exp,
                             f"[{msg}] want {exp}, got {o._identify_intent(msg)}")
        print(f"  ✅ intent: {len(cases)} cases match")

    def test_07_cache_file(self):
        """7. File cache — rules cache on 2nd load."""
        from tools.rule_loader import load_rules
        c = get_cache_manager()
        c.clear_type("file")
        load_rules("file-upload")
        m1 = c.get_stats()["file_misses"]
        load_rules("file-upload")
        h2 = c.get_stats()["file_hits"]
        self.assertGreater(h2, 0)
        print(f"  ✅ cache_file: hits={h2}, misses={m1}")

    def test_08_cache_llm(self):
        """8. LLM cache — exact match only."""
        c = get_cache_manager()
        c.clear_type("llm")
        p = json.dumps([{"role": "system", "content": "x"}], sort_keys=True)
        self.assertIsNone(c.get_llm(p))
        c.set_llm(p, "resp")
        self.assertEqual(c.get_llm(p), "resp")
        self.assertIsNone(c.get_llm(p + "x"))
        print("  ✅ cache_llm: exact-match works")

    def test_09_cache_http(self):
        """9. HTTP cache — different params different cache."""
        c = get_cache_manager()
        c.clear_type("http")
        c.set_http("/api/test", {"ok": 1}, method="GET", params={"a": "1"})
        self.assertEqual(c.get_http("/api/test", "GET", params={"a": "1"}), {"ok": 1})
        self.assertIsNone(c.get_http("/api/test", "GET", params={"a": "2"}))
        print("  ✅ cache_http: params-isolated")

    def test_10_cache_persist(self):
        """10. Cache persistence — disk-backed."""
        c = get_cache_manager()
        c.clear_type("file")
        c.set_file("/tmp/ptest.yaml", {"x": "y"})
        from tools.cache_manager import CacheManager as CM
        c2 = CM()
        self.assertEqual(c2.get_file("/tmp/ptest.yaml"), {"x": "y"})
        print("  ✅ cache_persist: survives new instance")

    def test_11_cache_stats(self):
        """11. Cache statistics — hit/miss tracking."""
        c = get_cache_manager()
        c.clear_all()
        c.get_llm("p1")
        c.set_llm("p1", "r1")
        c.get_llm("p1")
        c.get_llm("p2")
        s = c.get_stats()
        self.assertEqual(s["llm_hits"], 1)
        self.assertEqual(s["llm_misses"], 2)
        hr = c.get_hit_rate("llm")
        self.assertAlmostEqual(hr["hit_rate"], 1/3)
        print(f"  ✅ stats: {hr['hit_rate']*100:.0f}% ({hr['hits']}h/{hr['misses']}m)")

    def test_12_rule_loader_valid(self):
        """12. All 14 rules load successfully."""
        from tools.rule_loader import load_rules, RULE_MAP
        failed = []
        for sc in sorted(RULE_MAP):
            try:
                r = load_rules(sc)
                self.assertIsNotNone(r)
                self.assertIn("checks", r)
            except Exception as e:
                failed.append(f"{sc}: {e}")
        self.assertEqual(len(failed), 0, f"Failed: {failed}")
        print(f"  ✅ rules: {len(RULE_MAP)} scenarios all loadable")


def main():
    suite = unittest.TestLoader().loadTestsFromTestCase(TestTechLeadAgent)
    runner = unittest.TextTestRunner(verbosity=0)
    result = runner.run(suite)

    print("\n" + "=" * 60)
    total = result.testsRun
    passed = total - len(result.failures) - len(result.errors)
    print(f"总计: {total} 测试 | 通过: {passed} | "
          f"失败: {len(result.failures)} | 错误: {len(result.errors)}")
    if result.wasSuccessful():
        print("🎉 全部通过!")
    else:
        for t, _ in result.failures + result.errors:
            print(f"  ❌ {t}")
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
