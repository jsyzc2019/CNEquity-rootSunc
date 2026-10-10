"""Repairs of stored data, each published as a new retained revision."""

from __future__ import annotations

import json

import click

from cnequity.cli._root import cli
from cnequity.cli._shared import _cfg, config_option


def _emit(value: dict) -> None:
    click.echo(json.dumps(value, indent=2, ensure_ascii=False, default=str))


@cli.group()
def repair():
    """修复已存数据：默认只预览，--apply 核验后发布并保留旧版本。"""


@repair.command("missing-values")
@click.argument("dataset", type=click.Choice(["valuation_metrics", "index_constituents"]))
@config_option
@click.option("--apply", is_flag=True, help="将缺失值占位零改为空值并发布新版本；默认只预览。")
def missing_values(dataset: str, config_path: str, apply: bool):
    """修正估值占位零及东财、国证缺失的指数权重，保留旧版本。"""
    from cnequity.storage.repairs.missing_values import repair_missing_values

    _emit(repair_missing_values(_cfg(config_path), dataset, apply=apply))


@repair.command("financial-announcements")
@config_option
@click.option("--apply", is_flag=True, help="追加明确标记的原始公告日重建版本；默认只预览。")
def financial_announcements(config_path: str, apply: bool):
    """依据 LICO 原始公告日补财报重建版本，保留实际公告版本及旧湖版本。"""
    from cnequity.storage.repairs.financial_announcements import repair_financial_announcements

    _emit(repair_financial_announcements(_cfg(config_path), apply=apply))


@repair.command("daily-bar-coverage")
@config_option
@click.option(
    "--apply", is_flag=True, help="按已提交数据结清北交所整日欠账和已证明的上市前欠账；默认只预览。"
)
def daily_bar_coverage(config_path: str, apply: bool):
    """复查北交所整日欠账及上市前欠账，只按已提交且不矛盾的证据结清。"""
    from cnequity.storage.repairs.daily_bar_coverage import repair_daily_bar_coverage

    _emit(repair_daily_bar_coverage(_cfg(config_path), apply=apply))


@repair.command("fund-factors")
@config_option
@click.option(
    "--apply", is_flag=True, help="按已记录的拆分、转增条款发布修正因子，保留旧版本；默认只预览。"
)
def fund_factors(config_path: str, apply: bool):
    """补入 ETF/LOF 因子漏掉的份额折算，保留其他来源台阶及现金分红口径。"""
    from cnequity.storage.repairs.fund_factors import repair_fund_factors

    _emit(repair_fund_factors(_cfg(config_path), apply=apply))


@repair.command("fund-listing-dates")
@config_option
@click.option("--apply", is_flag=True, help="归档交易所目录并发布缺失的基金上市日期；默认只预览。")
def fund_listing_dates(config_path: str, apply: bool):
    """从交易所当前 ETF/LOF 目录补上市日期；预览也会请求来源。"""
    from cnequity.storage.repairs.fund_listing_dates import repair_fund_listing_dates

    _emit(repair_fund_listing_dates(_cfg(config_path), apply=apply))


@repair.command("layout")
@click.argument("dataset")
@config_option
@click.option("--apply", is_flag=True, help="写入并发布新版本；默认只输出计划。")
def layout(dataset: str, config_path: str, apply: bool):
    """把分区数据集根目录或错误键目录里的文件并入登记分区。

    \b
    同一主键的多份观察只在非空值完全一致时互补填空；有冲突的键按规范规则整行取一份。
    重复键的全部原始观察写入 _quarantine 作为证据，旧版本继续保留。
    """
    from cnequity.storage.repairs.layout import LayoutRepairError, repair_layout

    try:
        _emit(repair_layout(_cfg(config_path), dataset.lower(), apply=apply))
    except LayoutRepairError as exc:
        raise click.ClickException(str(exc)) from exc


@repair.command("valuation-basis")
@config_option
@click.option("--apply", is_flag=True, help="写入并发布新版本；默认只输出计划。")
def valuation_basis(config_path: str, apply: bool):
    """统一 valuation_metrics 的市盈率与市值口径。

    \b
    push2 动态市盈率移入 pe_dynamic；Baostock 流通市值由成交均价口径换算为收盘价口径，
    无法核对的保留原值并标注 vwap 口径；总市值按 share_structure 当日有效总股本重建，
    无股本记录的保留年末股本估算并标注。已有口径的行不重算。
    """
    from cnequity.storage.repairs.valuation_basis import repair_valuation_basis

    _emit(repair_valuation_basis(_cfg(config_path), apply=apply))


@repair.command("corporate-action-gaps")
@config_option
@click.option("--apply", is_flag=True, help="向 Baostock 补取并发布新版本；默认只离线输出计划。")
def corporate_action_gaps(config_path: str, apply: bool):
    """补上新浪与 Baostock 因子都有台阶、湖里却没有记录的除权事件。

    \b
    依据最近一次 `cne derive adj_factor_source` 的证据。附近 10 天内已有、但日期错开的
    记录，若其条款能解释该台阶，就移到台阶日；其余按证券和年份向 Baostock 取分红，
    只收除权日正是台阶日、且条款能解释台阶的行。解释不了的保持缺口，不会凭空补。
    """
    from cnequity.storage.repairs.corporate_action_gaps import repair_corporate_action_gaps

    _emit(repair_corporate_action_gaps(_cfg(config_path), apply=apply))


@repair.command("orphan-symbols")
@config_option
@click.option("--apply", is_flag=True, help="核验后发布新版本；默认只输出计划。")
def orphan_symbols(config_path: str, apply: bool):
    """删除 daily_bars 里从未出现的证券在 adj_factors 与 corporate_actions 中的行。

    \b
    这类行没有可复权的价格：早年作为净值序列误入的场外基金（519xxx）行情已清理，
    因子和分红却留了下来；未采集行情的上市基金也在其列。它们只会被报成因子与公司行为矛盾。
    按数据集各发布一个新版本，旧版本保留，可按版本读取。
    """
    from cnequity.storage.repairs.orphan_symbols import repair_orphan_symbols

    _emit(repair_orphan_symbols(_cfg(config_path), apply=apply))


@repair.command("stale-suspensions")
@config_option
@click.option("--apply", is_flag=True, help="核验后发布新版本；默认只输出计划。")
def stale_suspensions(config_path: str, apply: bool):
    """删除已被实际成交日线否定的推断停牌（trading_status 中 derived_bar_gap 来源的行）。

    \b
    这类行由缺失的日线推断而来；某次运行漏抓了行情时，缺口会被误记为停牌。
    行情补齐后，同一天有成交的日线即证明该行错误。独立来源的停牌记录不受影响。
    """
    from cnequity.storage.repairs.orphan_symbols import repair_stale_derived_suspensions

    _emit(repair_stale_derived_suspensions(_cfg(config_path), apply=apply))


@repair.command("status-outages")
@config_option
@click.option("--start", required=True, help="窗口起点（YYYY-MM-DD）。")
@click.option("--end", required=True, help="窗口终点（YYYY-MM-DD）。")
@click.option("--apply", is_flag=True, help="核验后发布新版本；默认只输出计划。")
def status_outages(config_path: str, start: str, end: str, apply: bool):
    """按现行规则重建东财中断期间的 trading_status 缓存行（eastmoney_cached）。

    \b
    旧规则会沿用缓存自己写的行，长假会让缓存过期，并把没有记录的证券记成停牌。
    窗口内的缓存行全部删除；主源当天没有答复的交易所里，没有其他记录的证券沿用
    前 5 个交易日内最近的一手记录，保留原抓取时间，Baostock 历史与日线缺口推断的停牌
    仍优先。没有一手记录的证券不写行。
    """
    from datetime import date

    from cnequity.storage.repairs.status_outages import repair_status_outages

    try:
        window = date.fromisoformat(start), date.fromisoformat(end)
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc
    _emit(repair_status_outages(_cfg(config_path), start=window[0], end=window[1], apply=apply))


@repair.command("status-listing-window")
@config_option
@click.option("--apply", is_flag=True, help="核验后发布新版本；默认只输出计划。")
def status_listing_window(config_path: str, apply: bool):
    """删除 trading_status 中落在证券上市日之前、或没有退市记录支撑的行。

    \b
    旧版合并曾把尚无日线的新证券推断为退市，状态步骤随后在它们上市后的头几个
    交易日写入 derived_delisted；东财也会把尚未上市的代码报成正常交易。
    derived_delisted 行只在当前 instruments 仍记有不早于上市日、且不晚于该行的
    退市日时保留；上市日之前的行一律删除，除非日线在上市日之前就有成交。不补写行。
    """
    from cnequity.storage.repairs.status_listing_window import repair_status_listing_window

    _emit(repair_status_listing_window(_cfg(config_path), apply=apply))


@repair.command("status-traded")
@config_option
@click.option(
    "--start",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="成交状态补缺起点（YYYY-MM-DD）。",
)
@click.option(
    "--end",
    required=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="成交状态补缺终点（YYYY-MM-DD）。",
)
@click.option("--apply", is_flag=True, help="核验后发布新版本；默认只输出计划。")
def status_traded(config_path: str, start, end, apply: bool):
    """用实际成交日线补缺失状态键，ST 保持未知。

    \b
    只补已知上市期间、成交量大于零且没有状态行的股票/ETF 键，来源为 derived_traded。
    不覆盖已有状态，不把无成交日期解释为停牌，不生成 ST 覆盖凭证。
    默认预览不写湖；--apply 重新核对当前版本后发布，保留旧版本。
    """
    from cnequity.storage.repairs.status_traded import repair_status_traded

    if end < start:
        raise click.BadParameter("--end 必须晚于或等于 --start")
    _emit(repair_status_traded(_cfg(config_path), start=start.date(), end=end.date(), apply=apply))


@repair.command("misdated-valuation")
@config_option
@click.option(
    "--apply", is_flag=True, help="向东财 datacenter 取数并发布新版本；默认只离线输出计划。"
)
def misdated_valuation(config_path: str, apply: bool):
    """替换 valuation_metrics 中盖错交易日的 push2 快照行。

    \b
    push2 快照不带日期，只描述抓取时最近一个已收盘的交易日。抓取时刻对应的交易日
    与行上日期不一致的行，--apply 时删除，并在同一版本中换成东财 datacenter
    按日期发布的估值；datacenter 没有的键不再保留错误的行。
    """
    from cnequity.storage.repairs.valuation_snapshots import repair_misdated_valuation

    _emit(repair_misdated_valuation(_cfg(config_path), apply=apply))
