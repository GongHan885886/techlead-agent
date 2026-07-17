"""Efficiency dashboard - FastAPI backend."""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import sqlite3
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import settings

DEMO_DB_PATH = str(Path(__file__).parent.parent / "storage" / "demo.db")

app = FastAPI(title="TechLead 人效看板")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


def get_db(demo: bool = False):
    path = DEMO_DB_PATH if demo else settings.db_path
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


# ── Problem radar ──
@app.get("/api/problems")
def problems(demo: bool = Query(False)):
    conn = get_db(demo)
    cur = conn.cursor()
    problems_list = []

    # 1. High blocker count
    cur.execute("""
        SELECT developer_name, blocker_count, total_issues
        FROM developer_profiles
        WHERE blocker_count > 5
        ORDER BY blocker_count DESC
    """)
    for row in cur.fetchall():
        problems_list.append({
            "type": "blocker_overload", "severity": "critical",
            "title": f"{row['developer_name']} Blocker 过多",
            "detail": f"累计 {row['blocker_count']} 个 Blocker（共 {row['total_issues']} 个问题），远高于团队正常水平",
            "action": "安排 1on1 沟通，检查是否有技术债或资源不足问题",
            "developer": row['developer_name'], "metric": row['blocker_count'],
        })

    # 2. Delivery efficiency anomaly
    cur.execute(f"""
        SELECT json_extract(metadata, '$.developer') as dev, AVG(metric_value) as avg_days
        FROM team_metrics
        WHERE metric_type='avg_delivery_days'
          AND timestamp > datetime('now', '-30 days')
        GROUP BY dev
    """)
    dev_delivery = {r['dev']: r['avg_days'] for r in cur.fetchall() if r['dev']}
    if dev_delivery:
        team_avg = sum(dev_delivery.values()) / len(dev_delivery)
        for dev, avg in sorted(dev_delivery.items(), key=lambda x: -x[1]):
            if avg > team_avg * 1.3:
                problems_list.append({
                    "type": "efficiency_anomaly", "severity": "warning",
                    "title": f"{dev} 交付周期偏长",
                    "detail": f"平均 {avg:.1f} 天，团队均值 {team_avg:.1f} 天（↑ {(avg/team_avg-1)*100:.0f}%）",
                    "action": "Review 该开发者的需求拆分粒度，是否存在阻塞依赖",
                    "developer": dev, "metric": round(avg, 1),
                })

    # 3. Quality anomaly
    cur.execute(f"""
        SELECT json_extract(metadata, '$.developer') as dev, AVG(metric_value) as avg_rate
        FROM team_metrics
        WHERE metric_type='defect_rate'
          AND timestamp > datetime('now', '-30 days')
        GROUP BY dev
    """)
    dev_defect = {r['dev']: r['avg_rate'] for r in cur.fetchall() if r['dev']}
    if dev_defect:
        team_avg = sum(dev_defect.values()) / len(dev_defect)
        for dev, avg in sorted(dev_defect.items(), key=lambda x: -x[1]):
            if avg > team_avg * 1.5:
                problems_list.append({
                    "type": "quality_anomaly", "severity": "warning",
                    "title": f"{dev} 缺陷率偏高",
                    "detail": f"缺陷率 {avg:.2f} 分/天，团队均值 {team_avg:.2f}（↑ {(avg/team_avg-1)*100:.0f}%）",
                    "action": "CR 阶段加强对该开发者代码的审查，确认是否为新增需求导致的短期波动",
                    "developer": dev, "metric": round(avg, 2),
                })

    # 4. CR throughput declining
    cur.execute(f"""
        SELECT timestamp, metric_value
        FROM team_metrics
        WHERE metric_type='cr_throughput'
          AND timestamp > datetime('now', '-14 days')
        ORDER BY timestamp
    """)
    tp_rows = cur.fetchall()
    if len(tp_rows) >= 4:
        mid = len(tp_rows) // 2
        first_half = [r['metric_value'] for r in tp_rows[:mid]]
        second_half = [r['metric_value'] for r in tp_rows[mid:]]
        avg1 = sum(first_half) / len(first_half)
        avg2 = sum(second_half) / len(second_half)
        if avg2 < avg1 * 0.7:
            problems_list.append({
                "type": "cr_slowdown", "severity": "warning",
                "title": "CR 吞吐量下降",
                "detail": f"近 7 天日均 CR {avg2:.1f} 次，较之前 {avg1:.1f} 次下降 {(1-avg2/avg1)*100:.0f}%",
                "action": "排查是否有团队阻塞（上线压力/需求变更），必要时拉通全员 CR 时间",
                "developer": None, "metric": round(avg2, 1),
            })

    # 5. CR turnaround time
    cur.execute(f"""
        SELECT AVG(metric_value) as avg_hours
        FROM team_metrics
        WHERE metric_type='cr_turnaround'
          AND timestamp > datetime('now', '-7 days')
    """)
    row = cur.fetchone()
    avg_turnaround = row['avg_hours'] if row and row['avg_hours'] else 0
    if avg_turnaround > 12:
        problems_list.append({
            "type": "slow_review", "severity": "info",
            "title": "CR 平均周转时间过长",
            "detail": f"平均 {avg_turnaround:.1f} 小时（> 12 小时），等待时间影响交付节奏",
            "action": "建议设 CR SLA：普通 MR 8 小时内响应，紧急 MR 4 小时内",
            "developer": None, "metric": round(avg_turnaround, 1),
        })

    # 6. Hot issue types
    cur.execute(f"""
        SELECT issue_type, COUNT(*) as cnt
        FROM developer_issues
        WHERE severity='blocker' AND created_at > datetime('now', '-30 days')
        GROUP BY issue_type
        ORDER BY cnt DESC
        LIMIT 3
    """)
    for row in cur.fetchall():
        problems_list.append({
            "type": "hot_issue_type", "severity": "info",
            "title": f"高频问题类型：{row['issue_type']}",
            "detail": f"近 30 天出现 {row['cnt']} 次 Blocker，需要团队层面对齐规范",
            "action": "在周会安排专题分享，更新团队编码规范文档",
            "developer": None, "metric": row['cnt'],
        })

    conn.close()

    severity_order = {"critical": 0, "warning": 1, "info": 2}
    problems_list.sort(key=lambda p: (severity_order.get(p['severity'], 9), -p['metric']))

    return {
        "problems": problems_list,
        "total": len(problems_list),
        "critical_count": sum(1 for p in problems_list if p['severity'] == 'critical'),
        "warning_count": sum(1 for p in problems_list if p['severity'] == 'warning'),
        "info_count": sum(1 for p in problems_list if p['severity'] == 'info'),
    }


# ── Overview ──
@app.get("/api/overview")
def overview(demo: bool = Query(False)):
    conn = get_db(demo)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(DISTINCT developer_name) FROM developer_issues")
    dev_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT target) FROM review_history WHERE review_type='design_review'")
    story_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(DISTINCT target) FROM review_history WHERE review_type='code_review'")
    mr_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM developer_issues WHERE created_at > datetime('now', '-30 days')")
    issue_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM developer_issues WHERE severity='blocker' AND created_at > datetime('now', '-30 days')")
    blocker_count = cur.fetchone()[0]
    cur.execute("""
        SELECT COUNT(*) FILTER (WHERE result='pass') AS passed, COUNT(*) AS total
        FROM review_history WHERE created_at > datetime('now', '-30 days')
    """)
    row = cur.fetchone()
    pass_rate = round(row["passed"] / row["total"] * 100, 1) if row["total"] > 0 else 0
    conn.close()
    return {"developers": dev_count, "stories": story_count, "mrs": mr_count,
            "issues_30d": issue_count, "blockers_30d": blocker_count, "pass_rate": pass_rate}


# ── Developer list ──
@app.get("/api/developers")
def developers(demo: bool = Query(False)):
    conn = get_db(demo)
    cur = conn.cursor()
    cur.execute("""
        SELECT developer_name, total_issues, blocker_count, warning_count,
               top_issue_types, tier, last_updated
        FROM developer_profiles ORDER BY total_issues DESC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Developer detail ──
@app.get("/api/developers/{name}")
def developer_detail(name: str, days: int = Query(30), demo: bool = Query(False)):
    conn = get_db(demo)
    cur = conn.cursor()
    cur.execute("SELECT * FROM developer_profiles WHERE developer_name=?", (name,))
    profile = cur.fetchone()
    cur.execute(f"""
        SELECT issue_type, severity, description, scenario, source, mr_id, created_at
        FROM developer_issues
        WHERE developer_name=? AND created_at > datetime('now', '-{days} days')
        ORDER BY created_at DESC LIMIT 50
    """, (name,))
    issues = [dict(r) for r in cur.fetchall()]
    cur.execute(f"""
        SELECT issue_type, severity, COUNT(*) as count
        FROM developer_issues
        WHERE developer_name=? AND created_at > datetime('now', '-{days} days')
        GROUP BY issue_type, severity ORDER BY count DESC
    """, (name,))
    breakdown = [dict(r) for r in cur.fetchall()]
    cur.execute("""
        SELECT review_type, target, result, blocker_count, warning_count, created_at
        FROM review_history
        WHERE reviewer=? AND created_at > datetime('now', '-30 days')
        ORDER BY created_at DESC
    """, (name,))
    reviews = [dict(r) for r in cur.fetchall()]
    conn.close()
    return {"profile": dict(profile) if profile else None, "issues": issues,
            "breakdown": breakdown, "reviews": reviews}


# ── Trends ──
@app.get("/api/trends")
def trends(days: int = Query(60), demo: bool = Query(False)):
    conn = get_db(demo)
    cur = conn.cursor()

    cur.execute(f"""
        SELECT timestamp, metric_value, metadata FROM team_metrics
        WHERE metric_type='avg_delivery_days' AND timestamp > datetime('now', '-{days} days')
        ORDER BY timestamp
    """)
    delivery_rows = cur.fetchall()
    cur.execute(f"""
        SELECT timestamp, metric_value, metadata FROM team_metrics
        WHERE metric_type='defect_rate' AND timestamp > datetime('now', '-{days} days')
        ORDER BY timestamp
    """)
    defect_rows = cur.fetchall()
    cur.execute(f"""
        SELECT timestamp, metric_value FROM team_metrics
        WHERE metric_type='cr_throughput' AND timestamp > datetime('now', '-{days} days')
        ORDER BY timestamp
    """)
    throughput_rows = cur.fetchall()
    cur.execute(f"""
        SELECT timestamp, metric_value FROM team_metrics
        WHERE metric_type='cr_turnaround' AND timestamp > datetime('now', '-{days} days')
        ORDER BY timestamp
    """)
    turnaround_rows = cur.fetchall()
    conn.close()

    def group_by_dev(rows):
        groups = {}
        for r in rows:
            meta = json.loads(r["metadata"]) if r["metadata"] else {}
            dev = meta.get("developer", "team")
            if dev not in groups:
                groups[dev] = {"dates": [], "values": []}
            groups[dev]["dates"].append(r["timestamp"][:10])
            groups[dev]["values"].append(r["metric_value"])
        return groups

    return {
        "avg_delivery_days": group_by_dev(delivery_rows),
        "defect_rate": group_by_dev(defect_rows),
        "cr_throughput": {"dates": [r["timestamp"][:10] for r in throughput_rows],
                          "values": [r["metric_value"] for r in throughput_rows]},
        "cr_turnaround": {"dates": [r["timestamp"][:10] for r in turnaround_rows],
                          "values": [r["metric_value"] for r in turnaround_rows]},
    }


# ── Team composition ──
@app.get("/api/team-composition")
def team_composition(demo: bool = Query(False)):
    conn = get_db(demo)
    cur = conn.cursor()
    cur.execute("SELECT developer_name, total_issues, blocker_count, tier FROM developer_profiles ORDER BY total_issues DESC")
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Review stats ──
@app.get("/api/review-stats")
def review_stats(days: int = Query(30), demo: bool = Query(False)):
    conn = get_db(demo)
    cur = conn.cursor()
    cur.execute(f"""
        SELECT review_type, result, COUNT(*) as count
        FROM review_history WHERE created_at > datetime('now', '-{days} days')
        GROUP BY review_type, result
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]



# ── API: Requirements/stories progress ──
@app.get("/api/requirements")
def requirements(demo: bool = Query(False)):
    """Return requirements with progress, risk, and status."""
    conn = get_db(demo)
    cur = conn.cursor()
    cur.execute("""
        SELECT id, title, owner, status, progress, priority,
               begin_date, due_date, risk, blocked, story_type, updated_at
        FROM stories
        ORDER BY
            CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 ELSE 2 END,
            CASE risk WHEN '高' THEN 0 WHEN '中' THEN 1 WHEN '低' THEN 2 ELSE 3 END,
            progress ASC
    """)
    rows = cur.fetchall()
    conn.close()
    return [dict(r) for r in rows]

# ── Serve dashboard pages ──
def _render_dashboard(demo_mode: bool = False) -> str:
    html_path = Path(__file__).parent / "templates" / "dashboard.html"
    html = html_path.read_text(encoding="utf-8")
    if demo_mode:
        # Inject demo mode flag before the first <script>
        html = html.replace(
            "const API = '';",
            "const API = '';\nconst DEMO_MODE = true;",
            1
        )
    else:
        html = html.replace(
            "const API = '';",
            "const API = '';\nconst DEMO_MODE = false;",
            1
        )
    return html


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _render_dashboard()


@app.get("/demo", response_class=HTMLResponse)
def dashboard_demo():
    return _render_dashboard()



# ── API: Developer radar (5-dimension profile, 0-100) ──
@app.get("/api/developer-radar")
def developer_radar(demo: bool = Query(False)):
    """Return 5-dimension radar scores per developer. Higher = better."""
    conn = get_db(demo)
    cur = conn.cursor()
    now = datetime.now(timezone.utc).astimezone()

    # Get all developers
    cur.execute("SELECT developer_name FROM developer_profiles")
    devs = [r["developer_name"] for r in cur.fetchall()]
    result = []

    for dev in devs:
        # 1. Design review pass rate
        cur.execute("""
            SELECT COUNT(*) FILTER (WHERE result='pass') AS passed, COUNT(*) AS total
            FROM review_history
            WHERE reviewer=? AND review_type='design_review'
              AND created_at > datetime('now', '-60 days')
        """, (dev,))
        row = cur.fetchone()
        design_pass_rate = (row["passed"] / row["total"] * 100) if row["total"] > 0 else 50

        # 2. Code review quality (inverse of blocker rate in code reviews)
        cur.execute("""
            SELECT COALESCE(SUM(blocker_count), 0) as total_blockers,
                   COUNT(*) as total_reviews
            FROM review_history
            WHERE reviewer=? AND review_type='code_review'
              AND created_at > datetime('now', '-60 days')
        """, (dev,))
        row = cur.fetchone()
        if row["total_reviews"] > 0:
            avg_blockers = row["total_blockers"] / row["total_reviews"]
            code_quality = max(0, 100 - avg_blockers * 30)
        else:
            code_quality = 50

        # 3. Defect rate (inverse, lower is better)
        cur.execute("""
            SELECT AVG(metric_value) as avg_rate
            FROM team_metrics
            WHERE metric_type='defect_rate'
              AND json_extract(metadata, '$.developer') = ?
              AND timestamp > datetime('now', '-30 days')
        """, (dev,))
        row = cur.fetchone()
        avg_defect = row["avg_rate"] if row and row["avg_rate"] else 0
        defect_score = max(0, min(100, 100 - avg_defect * 25))

        # 4. Delivery efficiency (inverse of delivery days)
        cur.execute("""
            SELECT AVG(metric_value) as avg_days
            FROM team_metrics
            WHERE metric_type='avg_delivery_days'
              AND json_extract(metadata, '$.developer') = ?
              AND timestamp > datetime('now', '-30 days')
        """, (dev,))
        row = cur.fetchone()
        avg_days = row["avg_days"] if row and row["avg_days"] else 14
        delivery_score = max(0, min(100, 100 - (avg_days - 5) * 8))

        # 5. CR responsiveness (inverse of turnaround time)
        cur.execute("""
            SELECT AVG(metric_value) as avg_hours
            FROM team_metrics
            WHERE metric_type='cr_turnaround'
              AND timestamp > datetime('now', '-30 days')
        """)
        row = cur.fetchone()
        avg_turnaround = row["avg_hours"] if row and row["avg_hours"] else 24
        # When they're the reviewer, their responsiveness is the team turnaround
        # For individual scoring, use the team average as a proxy
        responsiveness = max(0, min(100, 100 - avg_turnaround * 5))

        # Calculate overall score (weighted average)
        overall = round((
            design_pass_rate * 0.20 +
            code_quality * 0.25 +
            defect_score * 0.25 +
            delivery_score * 0.20 +
            responsiveness * 0.10
        ), 1)

        result.append({
            "developer": dev,
            "dimensions": {
                "技术方案评审": round(design_pass_rate, 1),
                "代码质量": round(code_quality, 1),
                "缺陷控制": round(defect_score, 1),
                "交付效率": round(delivery_score, 1),
                "CR响应": round(responsiveness, 1),
            },
            "overall": overall,
        })

    conn.close()
    return result


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7820)
