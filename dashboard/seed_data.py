"""Seed realistic mock data with 优秀/普通/较差 tier classification."""
import sqlite3
import uuid
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

TIERS = {
    "张三": "优秀",   # top performer
    "李四": "优秀",   # top performer
    "王五": "普通",   # average
    "赵六": "普通",   # average
    "陈七": "较差",   # struggling
}

def seed():
    conn = sqlite3.connect(settings.db_path)
    cursor = conn.cursor()
    now = datetime.now()
    devs = list(TIERS.keys())
    issue_types = ["transaction", "multithread", "logging", "api", "sql", "security"]
    severities = ["blocker", "warning", "info"]

    # ── developer_issues ──
    cursor.execute("DELETE FROM developer_issues")
    for dev in devs:
        tier = TIERS[dev]
        # Different tiers get different issue counts and severity mixes
        if tier == "优秀":
            num_issues = 6
            blocker_pct = 0.05   # very few blockers
            warning_pct = 0.30
        elif tier == "普通":
            num_issues = 15
            blocker_pct = 0.15   # some blockers
            warning_pct = 0.40
        else:  # 较差
            num_issues = 28
            blocker_pct = 0.30   # lots of blockers
            warning_pct = 0.45

        for idx in range(num_issues):
            itype = issue_types[idx % len(issue_types)]
            r = idx / num_issues
            if r < blocker_pct:
                severity = "blocker"
            elif r < blocker_pct + warning_pct:
                severity = "warning"
            else:
                severity = "info"

            days_ago = idx * 2 + 2  # spread across last ~60 days
            if days_ago > 60:
                days_ago = 60
            created = (now - timedelta(days=days_ago)).isoformat()
            issue_id = f"issue_{uuid.uuid4().hex[:8]}"

            type_label = {"transaction":"事务","multithread":"多线程","logging":"日志",
                          "api":"API","sql":"SQL","security":"安全"}
            description = f"{type_label[itype]}问题 #{idx+1}"
            if severity == "blocker":
                description += "（严重）"

            cursor.execute(
                "INSERT INTO developer_issues "
                "(id, developer_name, issue_type, severity, scenario, description, "
                " suggestion, source, mr_id, story_id, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (issue_id, dev, itype, severity, "file-upload",
                 description, "Should follow team best practices",
                 "code_review", str(100 + idx), f"story_{idx}", created),
            )
    print("  [OK] developer_issues")

    # ── developer_profiles ──
    cursor.execute("DELETE FROM developer_profiles")
    for dev in devs:
        tier = TIERS[dev]
        if tier == "优秀":
            total, blockers, warnings = 6, 0, 2
            types = [("api", 2), ("logging", 2), ("sql", 1), ("transaction", 1)]
        elif tier == "普通":
            total, blockers, warnings = 15, 2, 6
            types = [("transaction", 5), ("multithread", 4), ("logging", 3), ("sql", 2), ("api", 1)]
        else:
            total, blockers, warnings = 28, 8, 13
            types = [("transaction", 10), ("multithread", 7), ("logging", 5), ("security", 3), ("api", 2), ("sql", 1)]

        top_types = json.dumps([{"type": t, "count": c} for t, c in types[:4]])
        cursor.execute(
            "INSERT OR REPLACE INTO developer_profiles "
            "(developer_name, total_issues, blocker_count, warning_count, "
            " top_issue_types, tier, last_updated) "
            "VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)",
            (dev, total, blockers, warnings, top_types, tier),
        )
    print("  [OK] developer_profiles")

    # ── review_history ──
    cursor.execute("DELETE FROM review_history")
    idx = 0
    for dev in devs:
        tier = TIERS[dev]
        if tier == "优秀":
            num_reviews = 10
            pass_rate = 0.9
        elif tier == "普通":
            num_reviews = 7
            pass_rate = 0.6
        else:
            num_reviews = 5
            pass_rate = 0.3

        for i in range(num_reviews):
            idx += 1
            review_id = f"review_{uuid.uuid4().hex[:8]}"
            rtype = "code_review" if i % 3 != 0 else "design_review"
            target = f"MR!{100 + idx}" if rtype == "code_review" else f"DS-{100 + idx}"
            passed = i < num_reviews * pass_rate
            bc = 0 if passed else (1 if tier != "较差" else 2)
            wc = 0 if passed else (1 + (i % 2))
            created = (now - timedelta(days=i * 2)).isoformat()
            cursor.execute(
                "INSERT INTO review_history "
                "(id, review_type, reviewer, target, result, "
                " blocker_count, warning_count, suggestion_count, details, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (review_id, rtype, dev, target,
                 "pass" if passed else "fail",
                 bc, wc, i % 4,
                 json.dumps({"focus": "transaction,logging"}), created),
            )
    print("  [OK] review_history")

    # ── team_metrics ──
    cursor.execute("DELETE FROM team_metrics")
    for day_offset in range(60):
        day = now - timedelta(days=59 - day_offset)
        ts = day.isoformat()

        for dev in devs:
            tier = TIERS[dev]
            mid = f"metric_{uuid.uuid4().hex[:8]}"
            if tier == "优秀":
                base = 7 + (day_offset % 5) * 0.2        # 7-8 days
                defect_base = 0.5 + (day_offset % 10) * 0.03  # 0.5-0.8
            elif tier == "普通":
                base = 10 + (day_offset % 8) * 0.3       # 10-12 days
                defect_base = 1.5 + (day_offset % 12) * 0.04 # 1.5-2.0
            else:
                base = 15 + (day_offset % 10) * 0.4      # 15-19 days
                defect_base = 3.0 + (day_offset % 15) * 0.05 # 3.0-3.7

            cursor.execute(
                "INSERT INTO team_metrics VALUES (?, ?, ?, ?, ?, ?)",
                (mid, "avg_delivery_days", round(base, 1),
                 "days", ts, json.dumps({"developer": dev})),
            )

            mid = f"metric_{uuid.uuid4().hex[:8]}"
            cursor.execute(
                "INSERT INTO team_metrics VALUES (?, ?, ?, ?, ?, ?)",
                (mid, "defect_rate", round(defect_base, 2),
                 "score/day", ts, json.dumps({"developer": dev})),
            )

        # CR throughput: gradually improving
        mid = f"metric_{uuid.uuid4().hex[:8]}"
        throughput = 2 + (day_offset // 10)  # 2 -> 7 over 60 days
        cursor.execute(
            "INSERT INTO team_metrics VALUES (?, ?, ?, ?, ?, ?)",
            (mid, "cr_throughput", throughput,
             "reviews", ts, "{}"),
        )

        # CR turnaround: improving over time
        mid = f"metric_{uuid.uuid4().hex[:8]}"
        turnaround = max(3, 12 - day_offset * 0.15)  # 12h -> 3h over 60 days
        cursor.execute(
            "INSERT INTO team_metrics VALUES (?, ?, ?, ?, ?, ?)",
            (mid, "cr_turnaround", round(turnaround, 1),
             "hours", ts, "{}"),
        )
    print("  [OK] team_metrics")

    # ── stories (requirements) ──
    cursor.execute("DELETE FROM stories")
    stories_data = [
        ["ST-001", "文件上传功能优化", "张三", "已完成", 100, "P0", "2026-06-02", "2026-06-17", "无", 0, "需求"],
        ["ST-002", "订单列表查询性能优化", "李四", "已完成", 100, "P1", "2026-06-07", "2026-06-22", "无", 0, "需求"],
        ["ST-003", "支付链路优化", "王五", "进行中", 75, "P0", "2026-06-22", "2026-07-25", "低", 0, "需求"],
        ["ST-004", "用户权限管理系统", "张三", "进行中", 60, "P0", "2026-06-27", "2026-07-30", "中", 0, "需求"],
        ["ST-005", "消息推送服务重构", "赵六", "进行中", 40, "P1", "2026-07-02", "2026-08-06", "高", 0, "需求"],
        ["ST-006", "数据看板前端开发", "王五", "进行中", 30, "P1", "2026-07-07", "2026-08-11", "中", 0, "需求"],
        ["ST-007", "日志采集系统升级", "陈七", "进行中", 20, "P2", "2026-07-09", "2026-08-21", "高", 1, "需求"],
        ["ST-008", "API 网关统一接入", "李四", "进行中", 55, "P0", "2026-06-29", "2026-07-27", "中", 0, "需求"],
        ["ST-009", "缓存层优化", "陈七", "进行中", 15, "P2", "2026-07-12", "2026-08-14", "高", 0, "需求"],
        ["ST-010", "自动化测试覆盖率提升", "赵六", "已完成", 100, "P1", "2026-06-17", "2026-07-12", "无", 0, "优化"],
        ["ST-011", "数据库读写分离", "张三", "进行中", 45, "P0", "2026-07-02", "2026-07-31", "高", 0, "需求"],
        ["ST-012", "通知中心集成飞书", "李四", "待开始", 0, "P2", "2026-07-20", "2026-08-21", "无", 0, "需求"],
        ["ST-013", "搜索服务 ES 升级", "赵六", "进行中", 10, "P1", "2026-06-12", "2026-07-12", "高", 1, "需求"],
        ["ST-014", "部署流水线优化", "王五", "进行中", 80, "P1", "2026-07-05", "2026-07-16", "中", 0, "优化"],
        ["ST-015", "监控告警系统对接", "陈七", "进行中", 25, "P2", "2026-06-27", "2026-07-27", "中", 0, "需求"],
    ]
    for s in stories_data:
        cursor.execute(
            "INSERT OR REPLACE INTO stories (id, title, owner, status, progress, priority, begin_date, due_date, risk, blocked, story_type) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            s
        )
    # Also update the review_history design_review targets to match story IDs
    print("  [OK] stories")

    conn.commit()
    conn.commit()
    conn.close()
    print(f"\n[DONE] Demo data seeded")
    print(f"  Tiers: {json.dumps(TIERS, ensure_ascii=False)}")


if __name__ == "__main__":
    seed()
