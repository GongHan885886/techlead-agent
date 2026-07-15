#!/usr/bin/env python3
"""TechLead Manager Agent - Main entry point.

Usage:
    python main.py scan
    python main.py review-design --author "张三" --scenario "file-upload"
    python main.py review-mr --mr-id "123"
    python main.py profile --developer "李四"
    python main.py help
"""

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

# Add project root to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from config import settings
from utils.logger import setup_logging, get_logger
from agents.orchestrator import OrchestratorAgent
from tools.memory_store import init_db
from tools.rule_loader import validate_rules_dir
from tools.cache_manager import get_cache_manager


# Initialize
setup_logging()
logger = get_logger(__name__)
console = Console()
app = typer.Typer(help="TechLead Manager Agent - 技术经理 AI 助手")


@app.callback()
def setup(verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging")):
    """Setup application."""
    if verbose:
        setup_logging(log_level="DEBUG")

    # Initialize database
    init_db()

    # Validate rules directory
    if not validate_rules_dir():
        console.print("[yellow]⚠️  Some rule files are missing. System will use mock data.[/yellow]")


@app.command()
def scan():
    """Scan daily tasks: pending designs, MRs, and TAPD risks."""
    console.print("\n[bold blue]📋 开始每日扫描...[/bold blue]\n")

    async def run_scan():
        orchestrator = OrchestratorAgent()
        result = await orchestrator.process({"message": "scan"})

        # Display results
        _display_scan_results(result)

        return result

    result = asyncio.run(run_scan())

    console.print(f"\n[green]✅ 扫描完成！[/green]")


@app.command()
def review_design(
    author: str = typer.Option(..., "--author", "-a", help="Design author name"),
    scenario: str = typer.Option(None, "--scenario", "-s", help="Design scenario"),
):
    """Review technical design document."""
    console.print(f"\n[bold blue]📄 开始评审 {author} 的方案...[/bold blue]\n")

    async def run_review():
        orchestrator = OrchestratorAgent()
        result = await orchestrator.process({
            "message": f"review design by {author}",
            "author": author,
            "scenario": scenario,
        })

        return result

    result = asyncio.run(run_review())

    if result.get("intent") == "deep_review":
        console.print(f"[yellow]🔧 Design reviewer agent - Full implementation pending[/yellow]")
    else:
        console.print(result.get("message", "No message"))


@app.command()
def review_mr(
    mr_id: str = typer.Option(..., "--mr-id", "-m", help="Merge request ID"),
    focus: str = typer.Option(None, "--focus", "-f", help="Review focus areas (comma-separated)"),
):
    """Review merge request code changes."""
    console.print(f"\n[bold blue]🔍 开始 CR MR !{mr_id}...[/bold blue]\n")

    focus_areas = focus.split(",") if focus else []

    async def run_review():
        orchestrator = OrchestratorAgent()
        result = await orchestrator.process({
            "message": f"CR MR !{mr_id}",
            "mr_id": int(mr_id),
            "focus_areas": focus_areas,
        })

        return result

    result = asyncio.run(run_review())

    if result.get("intent") == "code_review":
        _display_mr_results(result)
    else:
        console.print(result.get("message", "No message"))


@app.command()
def profile(
    developer: str = typer.Option(..., "--developer", "-d", help="Developer name"),
    days: int = typer.Option(30, "--days", help="Number of days to look back"),
):
    """Show developer's error profile and learning advice."""
    console.print(f"\n[bold blue]📚 查询 {developer} 的错题情况...[/bold blue]\n")

    async def run_profile():
        from agents.learning_advisor import LearningAdvisorAgent

        learning_agent = LearningAdvisorAgent()
        result = await learning_agent.process({"developer": developer, "days": days})

        return result

    result = asyncio.run(run_profile())

    if result.get("intent") == "learning_advice" and "error" not in result:
        # Display formatted report
        from agents.learning_advisor import LearningAdvisorAgent

        learning_agent = LearningAdvisorAgent()
        formatted_report = learning_agent.format_report(result)
        console.print(formatted_report)
    else:
        console.print(result.get("message", "No message"))


@app.command()
def weekly_report():
    """Generate weekly report."""
    console.print("\n[bold blue]📊 生成周报...[/bold blue]\n")

    async def run_report():
        orchestrator = OrchestratorAgent()
        result = await orchestrator.process({"message": "weekly report"})

        return result

    result = asyncio.run(run_report())

    if result.get("intent") == "weekly_report":
        delivery = result.get("delivery", {})
        team = result.get("team", {})

        # Display delivery tracking
        if delivery:
            from agents.delivery_tracker import DeliveryTrackerAgent

            delivery_agent = DeliveryTrackerAgent()
            formatted_report = delivery_agent.format_report(delivery)
            console.print(formatted_report)

        # Display team overview
        if team and team.get("common_issues"):
            console.print("\n[bold blue]👥 团队共性问题[/bold blue]\n")
            for issue in team["common_issues"][:5]:
                emoji = {"blocker": "🔴", "warning": "🟡", "info": "🟢"}.get(issue["severity"], "⚪")
                console.print(f"{emoji} {issue['type']}: {issue['count']} 次")
    else:
        console.print(result.get("message", "No message"))


@app.command()
def help_command():
    """Show available commands and usage."""
    help_text = """[bold blue]🤖 TechLead Agent 可用命令：[/bold blue]

[yellow]【每日扫描】[/yellow]
  main.py scan
  扫描今天所有需要关注的事情

[yellow]【方案评审】[/yellow]
  main.py review-design --author "张三" --scenario "file-upload"
  评审张三的文件上传方案

[yellow]【代码审查】[/yellow]
  main.py review-mr --mr-id "123" --focus "transaction,logging"
  CR MR !123，重点关注事务和日志

[yellow]【学习建议】[/yellow]
  main.py profile --developer "李四" --days 30
  查询李四最近30天的错题情况

[yellow]【周报】[/yellow]
  main.py weekly-report
  生成本周工作汇报

[yellow]【缓存管理】[/yellow]
  main.py status
  查看缓存统计和命中率

  main.py clear-cache [type]
  清除缓存（默认全部，可指定: file, http, llm, result）

[yellow]【配置】[/yellow]
  复制 .env.example 为 .env 并配置：
  - OPENAI_API_KEY: OpenAI API 密钥
  - TAPD_API_USER/PASSWORD: TAPD 账号
  - GITLAB_TOKEN: GitLab 访问令牌
"""
    console.print(help_text)


# Display helpers
def _display_scan_results(result: dict):
    """Display scan results in formatted output."""
    # Stories section
    stories = result.get("stories", [])
    high_risk = result.get("high_risk_stories", [])
    warning = result.get("warning_stories", [])

    console.print("[bold]📊 交付追踪报告[/bold]\n")

    # Risk table
    if high_risk or warning:
        table = Table(show_header=True, header_style="bold magenta")
        table.add_column("状态", style="red" if high_risk else "yellow")
        table.add_column("需求")
        table.add_column("负责人")
        table.add_column("进度")
        table.add_column("距提测")

        for story in high_risk:
            table.add_row("🔴", story["title"], story["owner"], f"{story['progress']}%", "紧急")

        for story in warning:
            table.add_row("🟡", story["title"], story["owner"], f"{story['progress']}%", "警告")

        console.print(table)
    else:
        console.print("[green]✅ 无高风险需求[/green]")

    console.print()

    # MRs section
    mrs = result.get("mrs", [])
    console.print(f"[bold]待处理 MR[/bold]: {len(mrs)} 个\n")

    if mrs:
        for mr in mrs[:5]:
            status_emoji = "⚠️" if mr["draft"] else "✅"
            console.print(f"{status_emoji} [link={mr['web_url']}]MR !{mr['iid']}[/link]: {mr['title']} by {mr['author']}")
    else:
        console.print("[green]✅ 无待处理 MR[/green]")


def _display_mr_results(result: dict):
    """Display MR review results."""
    blockers = result.get("blockers", [])
    warnings = result.get("warnings", [])
    suggestions = result.get("suggestions", [])

    console.print(f"\n[bold]🔍 CR 审查报告 - MR !{result.get('mr_id')}[/bold]\n")
    console.print(f"关注领域: {', '.join(result.get('focus_areas', []))}\n")

    # Findings summary
    passed = result.get("passed", False)
    if passed:
        console.print("[green bold]✅ 自检通过[/green bold]\n")
    else:
        console.print("[red bold]❌ 自检不通过[/red bold]\n")

    # Blockers
    if blockers:
        console.print("[red bold]🔴 Blocker（必须修复）：[/red bold]")
        for i, b in enumerate(blockers, 1):
            console.print(f"  {i}. {b['description']}")
        console.print()

    # Warnings
    if warnings:
        console.print("[yellow bold]🟡 Warning（建议修复）：[/yellow bold]")
        for i, w in enumerate(warnings, 1):
            console.print(f"  {i}. {w['description']}")
        console.print()

    # Suggestions
    if suggestions:
        console.print("[blue bold]💡 Suggestion（最佳实践）：[/blue bold]")
        for i, s in enumerate(suggestions, 1):
            console.print(f"  {i}. {s['description']}")
        console.print()

    # Summary
    console.print(f"[bold]统计[/bold]:")
    console.print(f"  - Blocker: {len(blockers)} 个")
    console.print(f"  - Warning: {len(warnings)} 个")
    console.print(f"  - Suggestion: {len(suggestions)} 个")

    if not passed:
        console.print("\n[yellow]⏳ 等待技术经理确认...[/yellow]")
        console.print("使用 'main.py confirm' 确认发送评论")


def _display_profile(developer: str, profile: dict, context: str, days: int):
    """Display developer profile and learning advice."""
    console.print(f"[bold blue]📚 【{developer}】的错题情况[/bold blue]\n")
    console.print(f"数据时间范围: 最近 {days} 天\n")

    # Stats
    console.print(f"[bold]📊 错题统计[/bold]:")
    console.print(f"  - 总问题数: {profile.get('total_issues', 0)} 个")
    console.print(f"  - Blocker: {profile.get('blocker_count', 0)} 个")
    console.print(f"  - Warning: {profile.get('warning_count', 0)} 个\n")

    # Top types
    if profile.get('type_breakdown'):
        console.print("[bold]🎯 高频问题类型[/bold]:")
        for item in profile['type_breakdown'][:5]:
            emoji = {"blocker": "🔴", "warning": "🟡", "info": "🟢"}.get(item['severity'], "⚪")
            console.print(f"  {emoji} {item['type']}: {item['count']} 次 {item['severity'].upper()}")
        console.print()

    # Learning context panel
    console.print(Panel(context.strip(), title="[bold]学习建议上下文[/bold]", border_style="blue"))


@app.command()
def confirm():
    """Confirm and execute pending tasks."""
    console.print("\n[bold blue]✓ 确认执行待处理任务...[/bold blue]\n")
    console.print("[yellow]⚠️  此功能需要先有挂起的任务（如 CR 评论待确认）[/yellow]")


@app.command()
def clear_cache(cache_type: str = "all"):
    """Clear cached data.

    Args:
        cache_type: Type of cache to clear (all, file, http, llm, result)
    """
    from tools.cache_manager import get_cache_manager

    console.print(f"\n[bold blue]🗑️  清除缓存...[/bold blue]\n")

    cache_manager = get_cache_manager()

    if cache_type == "all":
        cache_manager.clear_all()
        console.print("[green]✅ 已清除所有缓存[/green]")
    elif cache_type in ["file", "http", "llm", "result"]:
        cache_manager.clear_type(cache_type)
        console.print(f"[green]✅ 已清除 {cache_type} 缓存[/green]")
    else:
        console.print(f"[red]❌ 未知缓存类型: {cache_type}[/red]")
        console.print("可用类型: all, file, http, llm, result")


@app.command()
def status():
    """Show system status."""
    console.print("\n[bold blue]🔍 系统状态[/bold blue]\n")

    # Database status
    db_path = settings.db_path
    db_exists = Path(db_path).exists()
    console.print(f"[bold]数据库[/bold]: {db_path}")
    console.print(f"  状态: {'✅ 已初始化' if db_exists else '❌ 未初始化'}\n")

    # Rules status
    rules_valid = validate_rules_dir()
    console.print(f"[bold]规则文件[/bold]: {settings.rules_dir}")
    console.print(f"  状态: {'✅ 完整' if rules_valid else '⚠️  部分缺失'}\n")

    # Cache status
    console.print(f"[bold]缓存系统[/bold]:")
    cache_enabled = getattr(settings, 'cache_enabled', True)
    console.print(f"  启用: {'✅' if cache_enabled else '❌'}")
    if cache_enabled:
        cache_manager = get_cache_manager()
        stats = cache_manager.get_stats()
        console.print(f"  文件缓存命中: {stats['file_hits']} 次")
        console.print(f"  文件缓存未命中: {stats['file_misses']} 次")
        console.print(f"  HTTP 缓存命中: {stats['http_hits']} 次")
        console.print(f"  HTTP 缓存未命中: {stats['http_misses']} 次")

        # Show hit rates
        hit_rates = cache_manager.get_hit_rate()
        console.print(f"\n[bold]缓存命中率[/bold]:")
        for cache_type, rate in hit_rates.items():
            hit_rate_pct = rate['hit_rate'] * 100
            color = "green" if hit_rate_pct >= 80 else "yellow" if hit_rate_pct >= 50 else "red"
            console.print(f"  {cache_type.upper()}: {hit_rate_pct:.1f}% ({rate['hits']}/{rate['hits']+rate['misses']})")

    # Configuration status
    console.print(f"\n[bold]配置[/bold]:")
    console.print(f"  LLM 模型: {settings.llm_model}")
    console.print(f"  日志级别: {settings.log_level}")
    console.print(f"  追踪启用: {'✅' if settings.trace_enabled else '❌'}")


if __name__ == "__main__":
    app()