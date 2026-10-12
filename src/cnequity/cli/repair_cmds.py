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


@repair.command("fund-volume")
@config_option
@click.option("--apply", is_flag=True, help="核验后替换整行并发布新版本，保留旧版。")
@click.option(
    "--refresh-sources", is_flag=True, help="归档官方历史 K 线及必要的独立金额证据；默认离线回放。"
)
@click.option("--max-symbols", type=click.IntRange(min=1), default=16, show_default=True)
def fund_volume(config_path: str, apply: bool, refresh_sources: bool, max_symbols: int):
    """修复零成交量、正成交额的沪深场内基金；须与官方日线价格及金额一致。"""
    from cnequity.storage.repairs.fund_volume import repair_fund_volume

    try:
        _emit(
            repair_fund_volume(
                _cfg(config_path),
                apply=apply,
                refresh_sources=refresh_sources,
                max_symbols=max_symbols,
            )
        )
    except (ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc


@repair.command("financial-originals")
@config_option
@click.option("--symbols", help="股票代码，逗号分隔。")
@click.option("--all-stocks", is_flag=True, help="使用湖中股票目录；与 --symbols 二选一。")
@click.option("--after", help="接续上一批 next_cursor（YEAR:SYMBOL）；失败项可不带游标重试。")
@click.option(
    "--quarter",
    type=click.Choice(["Q1", "Q2", "Q3", "Q4"]),
    default="Q4",
    show_default=True,
    help="报告期；Q2 为半年报，Q4 为年报，利润和现金流只恢复年初至期末累计数。",
)
@click.option("--start-year", type=click.IntRange(min=2001), default=2016, show_default=True)
@click.option("--end-year", type=click.IntRange(min=2001), default=2024, show_default=True)
@click.option("--max-reports", type=click.IntRange(min=1), default=16, show_default=True)
@click.option(
    "--reparse", is_flag=True, help="重新解析已有原文报告；内容未变的行保留原始观测时间。"
)
@click.option(
    "--refresh-sources",
    is_flag=True,
    help="从巨潮取完整公告查询和原始定期报告；默认回放已归档来源。",
)
@click.option("--apply", is_flag=True, help="追加可核实的原文当期数，保留既有版本及真实采集时间。")
def financial_originals(
    config_path: str,
    symbols: str | None,
    all_stocks: bool,
    after: str | None,
    quarter: str,
    start_year: int,
    end_year: int,
    max_reports: int,
    reparse: bool,
    refresh_sources: bool,
    apply: bool,
):
    """从原始定期报告恢复合并报表科目；不使用比较期数，不把今天采集伪装成历史观测。"""
    from cnequity.cli._shared import comma_values
    from cnequity.storage.repairs.financial_originals import repair_financial_originals

    try:
        _emit(
            repair_financial_originals(
                _cfg(config_path),
                symbols=comma_values(symbols, "--symbols") if symbols else None,
                all_stocks=all_stocks,
                after=after,
                quarter=int(quarter[-1]),
                start_year=start_year,
                end_year=end_year,
                max_reports=max_reports,
                reparse=reparse,
                refresh_sources=refresh_sources,
                apply=apply,
            )
        )
    except (ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc


@repair.command("daily-bar-coverage")
@config_option
@click.option(
    "--apply", is_flag=True, help="按已提交数据结清北交所整日欠账和已证明的上市前欠账；默认只预览。"
)
def daily_bar_coverage(config_path: str, apply: bool):
    """复查北交所整日欠账及上市前欠账，只按已提交且不矛盾的证据结清。"""
    from cnequity.storage.repairs.daily_bar_coverage import repair_daily_bar_coverage

    _emit(repair_daily_bar_coverage(_cfg(config_path), apply=apply))


@repair.command("fund-no-print")
@config_option
@click.option(
    "--apply", is_flag=True, help="保存基金竞价日线覆盖证据并结清对应欠账；不生成日线或停牌行。"
)
@click.option(
    "--refresh-sources", is_flag=True, help="向沪深交易所取历史基金报表；默认离线回放已留存报表。"
)
@click.option(
    "--max-sessions",
    type=click.IntRange(min=1),
    default=32,
    show_default=True,
    help="每批最多核对的欠账交易日。",
)
def fund_no_print(config_path: str, apply: bool, refresh_sources: bool, max_sessions: int):
    """用沪深交易所明确的基金竞价日线覆盖证据核对欠账；正常可交易不等于当日有竞价成交。"""
    from cnequity.storage.repairs.fund_no_print import repair_fund_no_print

    _emit(
        repair_fund_no_print(
            _cfg(config_path),
            apply=apply,
            refresh_sources=refresh_sources,
            max_sessions=max_sessions,
        )
    )


@repair.command("fund-factors")
@config_option
@click.option(
    "--apply", is_flag=True, help="按已记录的拆分、转增条款发布修正因子，保留旧版本；默认只预览。"
)
def fund_factors(config_path: str, apply: bool):
    """补入 ETF/LOF 因子漏掉的份额折算，保留其他来源台阶及现金分红口径。"""
    from cnequity.storage.repairs.fund_factors import repair_fund_factors

    _emit(repair_fund_factors(_cfg(config_path), apply=apply))


@repair.command("adj-factors")
@config_option
@click.option("--apply", is_flag=True, help="应用可确定的因子修正并保留旧版本；未解决项只作提示。")
@click.option("--refresh-sources", is_flag=True, help="联网补取独立因子证据；默认仅使用本地缓存。")
@click.option("--symbols", default=None, help="逗号分隔的证券代码；默认分批检查历史问题。")
@click.option("--start", default=None, help="待修事件起点（YYYY-MM-DD）；累计影响延续到其后。")
@click.option("--end", default=None, help="待修事件终点（YYYY-MM-DD）；累计影响延续到其后。")
@click.option(
    "--max-symbols",
    default=100,
    type=click.IntRange(min=1),
    show_default=True,
    help="每批最多检查的证券数；应用后保存历史进度。",
)
@click.option("--plan", default=None, help="应用指定预览的计划标识；输入变化时要求重新预览。")
def adj_factors(config_path, apply, refresh_sources, symbols, start, end, max_symbols, plan):
    """统一修复股票因子与 ETF/LOF 份额折算；默认离线预览并保存计划。"""
    from cnequity.cli._shared import comma_values, parse_date_option
    from cnequity.storage.repairs.adj_factors import repair_adj_factors

    try:
        _emit(
            repair_adj_factors(
                _cfg(config_path),
                apply=apply,
                refresh_sources=refresh_sources,
                symbols=comma_values(symbols, "--symbols"),
                start=parse_date_option(start, "--start"),
                end=parse_date_option(end, "--end"),
                max_symbols=max_symbols,
                plan_id=plan,
            )
        )
    except (ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc


@repair.command("fund-listing-dates")
@config_option
@click.option("--apply", is_flag=True, help="归档交易所目录并发布缺失的基金上市日期；默认只预览。")
def fund_listing_dates(config_path: str, apply: bool):
    """从交易所当前 ETF/LOF 目录补上市日期；预览也会请求来源。"""
    from cnequity.storage.repairs.fund_listing_dates import repair_fund_listing_dates

    _emit(repair_fund_listing_dates(_cfg(config_path), apply=apply))


@repair.command("index-snapshots")
@config_option
@click.option(
    "--indices", default=None, help="指数代码，逗号分隔；默认沪深300、科创50、深证成指、创业板指。"
)
@click.option("--apply", is_flag=True, help="按文件实际日期替换完整指数快照，保留旧版本。")
@click.option("--refresh-sources", is_flag=True, help="取官方成分和权重文件；默认离线回放。")
def index_snapshots(config_path: str, indices: str | None, apply: bool, refresh_sources: bool):
    """恢复可取得的官方带日期成分与真实权重；不向过去倒推，也不跨日期填权重。"""
    from cnequity.cli._shared import comma_values
    from cnequity.storage.repairs.index_snapshots import repair_index_snapshots

    try:
        _emit(
            repair_index_snapshots(
                _cfg(config_path),
                indices=comma_values(indices, "--indices"),
                apply=apply,
                refresh_sources=refresh_sources,
            )
        )
    except (ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc


@repair.command("index-history")
@config_option
@click.option(
    "--index-symbol",
    type=click.Choice(["399001.SZ", "000688.SH"]),
    default="399001.SZ",
    show_default=True,
    help="选择已核验的历史成分目录。",
)
@click.option(
    "--apply", is_flag=True, help="替换已核验区间的完整成分历史，保留官方带日期权重及旧版本。"
)
@click.option(
    "--refresh-sources", is_flag=True, help="补采目录中未归档的官方历史附件；默认离线回放。"
)
def index_history(config_path: str, index_symbol: str, apply: bool, refresh_sources: bool):
    """回放已核验的深证成指或科创50历史公告；每次生效日保存完整名单，未知历史权重为空。"""
    from cnequity.storage.repairs.index_history import repair_index_history

    try:
        _emit(
            repair_index_history(
                _cfg(config_path),
                index_symbol=index_symbol,
                apply=apply,
                refresh_sources=refresh_sources,
            )
        )
    except (ValueError, RuntimeError) as exc:
        raise click.ClickException(str(exc)) from exc


@repair.command("stock-listing-dates")
@config_option
@click.option("--apply", is_flag=True, help="发布官方 IPO 日历证实的股票上市日期；保留旧版本。")
@click.option("--refresh-sources", is_flag=True, help="联网取巨潮 IPO 日历；默认回放已归档来源。")
@click.option("--max-sessions", type=click.IntRange(min=1), default=32, show_default=True)
@click.option(
    "--event-date",
    multiple=True,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    help="额外回放指定日的官方上市事件，可重复；不要求证券已有日线。",
)
def stock_listing_dates(
    config_path: str, apply: bool, refresh_sources: bool, max_sessions: int, event_date: tuple
):
    """补官方日历证实的股票上市日期；首根日线或显式日期只定位请求。"""
    from cnequity.storage.repairs.stock_listing_dates import repair_stock_listing_dates

    _emit(
        repair_stock_listing_dates(
            _cfg(config_path),
            apply=apply,
            refresh_sources=refresh_sources,
            max_sessions=max_sessions,
            event_dates=tuple(day.date() for day in event_date),
        )
    )


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
