"""What `cne init` says when it ends.

The full result is a machine record (phase receipts, per-batch outcomes,
fallback options) that ran to tens of thousands of lines for a full-market
lake. Printed raw it buried the one thing a first-time user needs: whether
the lake is usable and what to run next. That record is saved to a file;
the terminal gets the answer.
"""

from __future__ import annotations

import json
from pathlib import Path

from cnequity.cli.demo import MCP_GUIDE_URL

STEP_LABELS = {
    "instruments": "证券目录",
    "trading_calendar": "交易日历",
    "corporate_actions": "公司行为",
    "daily_bars": "日线",
    "index_bars": "指数日线",
    "trading_status": "交易状态",
    "compact": "入湖发布",
    "derive_adj_factors": "复权因子",
    "derive_industry_index": "行业指数",
    "audit": "质量审计",
    "trading_status_derive": "停牌派生",
}


def save_init_result(log_dir: Path, result: dict) -> Path | None:
    """Keep the full machine result next to the run's log; never fail over it."""
    path = Path(log_dir) / f"cne-init-{result.get('run_id', 'unknown')}.json"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(result, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
        )
    except OSError:
        return None
    return path


def _label(step: str) -> str:
    name = STEP_LABELS.get(step)
    return f"{name}（{step}）" if name else step


def render_init_summary(
    result: dict,
    *,
    config_arg: str,
    config_abs: Path,
    data_root: Path,
    log_path: Path | None,
    result_path: Path | None,
) -> list[str]:
    status = str(result.get("status", "failed"))
    run_id = result.get("run_id", "?")
    owed = [str(step) for step in result.get("owed_steps") or []]
    usable = status != "failed" or bool(result.get("lake_usable"))
    resume = f"cne init{config_arg}"

    lines = ["", "== 建湖结果 =="]
    if status != "failed" and not owed:
        lines.append(f"✓ 湖已建好，可以使用（run {run_id}）。")
    elif usable:
        lines.append(f"✓ 湖已建好，可以查询日线（run {run_id}）。")
        lines.append("  以下部分这次没有完成，多为数据源暂时不可用：")
        lines.extend(f"  - {_label(step)}" for step in owed)
        lines.append(f"  稍后重跑 `{resume}` 只补这些，已完成的部分不会重来。")
    else:
        lines.append(f"✗ 建湖还没完成（run {run_id}）。已下载的部分都已保存。")
        if owed:
            lines.append("  还差：" + "、".join(_label(step) for step in owed))
        lines.append(f"  网络或数据源恢复后重跑 `{resume}`，会从断点续跑。")
        lines.append("  看哪个数据源不通：cne sources probe" + config_arg)
    if log_path is not None:
        lines.append(f"  日志：{log_path}")
    if result_path is not None:
        lines.append(f"  完整结果（JSON）：{result_path}")

    if usable:
        lines += [
            "",
            "下一步：",
            f"  cne check{config_arg}          检查数据是否完整、可用",
            f"  cne serve{config_arg}          在浏览器里看湖",
            f"  cne run daily{config_arg}      每天运行一次保持更新",
            "",
            "Python：",
            "  from cnequity.query import load",
            f'  bars = load("daily_bars", symbols=["600519.SH"], data_root="{data_root}")',
            "",
            "接给 AI（只读 MCP，以 Claude Code 为例）：",
            f"  claude mcp add cnequity -- cne mcp --config {config_abs}",
            f"其他客户端的写法：{MCP_GUIDE_URL}",
        ]
    return lines
