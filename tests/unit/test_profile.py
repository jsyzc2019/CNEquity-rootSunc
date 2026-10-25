"""load_profile: what could be known about each security on each date, and why not."""

from datetime import date, datetime, timezone

import polars as pl
import pytest

from cnequity.config import Config
from cnequity.domain.schemas import DATASET_SCHEMAS
from cnequity.query.profile import ProfileError, load_profile
from cnequity.storage.revisions import RevisionStore

S, DELISTED, NEW = "600519.SH", "000406.SZ", "688999.SH"
EARLY = datetime(2024, 4, 1, tzinfo=timezone.utc)  # observed in real time
LATE = datetime(2026, 10, 1, tzinfo=timezone.utc)  # recovered by a backfill


def _write(cfg, dataset, rows, partition, value):
    root = cfg.curated_root / dataset / f"{partition}={value}"
    root.mkdir(parents=True, exist_ok=True)
    pl.DataFrame(rows, schema=DATASET_SCHEMAS[dataset]).write_parquet(root / "part.parquet")
    RevisionStore(cfg.meta_root, cfg.curated_root, cfg.derived_root).commit(
        dataset,
        run_id=f"seed-{dataset}",
        changed_files=sorted((cfg.curated_root / dataset).rglob("*.parquet")),
        schema_version=1,
        contract_fingerprint="contract",
    )


def _meta(source, fetched):
    return {"source": source, "data_version": "v1", "fetched_at": fetched}


@pytest.fixture
def lake(tmp_path):
    cfg = Config(data_root=tmp_path / "lake")
    inst = cfg.curated_root / "instruments"
    inst.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "symbol": S,
                "name": "x",
                "exchange": "SH",
                "asset_type": "stock",
                "list_date": date(2001, 8, 27),
                "delist_date": None,
                "prev_symbol": None,
                **_meta("t", EARLY),
            },
            {
                "symbol": DELISTED,
                "name": "y",
                "exchange": "SZ",
                "asset_type": "stock",
                "list_date": date(1996, 6, 28),
                "delist_date": date(2006, 4, 21),
                "prev_symbol": None,
                **_meta("t", EARLY),
            },
            {
                "symbol": NEW,
                "name": "z",
                "exchange": "SH",
                "asset_type": "stock",
                "list_date": date(2024, 6, 3),
                "delist_date": None,
                "prev_symbol": None,
                **_meta("t", EARLY),
            },
        ],
        schema=DATASET_SCHEMAS["instruments"],
    ).write_parquet(inst / "part.parquet")
    RevisionStore(cfg.meta_root, cfg.curated_root, cfg.derived_root).commit(
        "instruments",
        run_id="seed",
        changed_files=[inst / "part.parquet"],
        schema_version=1,
        contract_fingerprint="contract",
    )

    def fsi(period, value, announced, source, fetched):
        return {
            "symbol": S,
            "report_period": period,
            "statement_type": "income",
            "item_code": "net_profit",
            "item_value": value,
            "announce_date": announced,
            **_meta(source, fetched),
        }

    _write(
        cfg,
        "financial_statement_items",
        [
            fsi("2023Q4", 100.0, date(2024, 3, 30), "eastmoney", EARLY),
            # 2023Q4 restated in May: as_of after it sees the new figure.
            fsi("2023Q4", 90.0, date(2024, 5, 20), "eastmoney_backfill", LATE),
            fsi("2024Q1", 30.0, date(2024, 4, 27), "eastmoney_backfill", LATE),
        ],
        "report_period",
        "2024",
    )
    _write(
        cfg,
        "trading_status",
        [
            {
                "symbol": S,
                "trade_date": date(2024, 4, 26),
                "is_trading": True,
                "status": "normal",
                "risk_warning": None,
                **_meta("derived_traded", LATE),
            },
        ],
        "trade_date",
        "2024-04",
    )
    return cfg


def _value(frame, field, as_of, symbol=S):
    row = frame.filter(
        (pl.col("field") == field) & (pl.col("as_of") == as_of) & (pl.col("symbol") == symbol)
    ).row(0, named=True)
    return row


def test_the_latest_visible_period_wins_and_restatements_apply_from_their_date(lake):
    days = [date(2024, 4, 26), date(2024, 4, 30), date(2024, 5, 31)]
    p = load_profile(["fsi:net_profit"], [S], days, config=lake)
    before = _value(p, "fsi:net_profit", days[0])
    assert (before["value_num"], before["value_str"], before["field_date"]) == (
        100.0,
        "2023Q4",
        date(2023, 12, 31),
    )
    assert before["pit_quality"] == "strict"  # first-hand and observed by 2024-04-01
    q1 = _value(p, "fsi:net_profit", days[1])
    assert (q1["value_num"], q1["pit_quality"]) == (30.0, "reconstructed")
    # The 2023Q4 restatement does not displace the newer 2024Q1 period.
    assert _value(p, "fsi:net_profit", days[2])["value_num"] == 30.0


def test_strict_mode_keeps_only_first_hand_rows_observed_in_time(lake):
    p = load_profile(["fsi:net_profit"], [S], [date(2024, 4, 30)], pit_mode="strict", config=lake)
    row = _value(p, "fsi:net_profit", date(2024, 4, 30))
    assert (row["value_num"], row["pit_quality"]) == (100.0, "strict")


def test_missing_values_say_why(lake):
    days = [date(2024, 3, 1), date(2024, 4, 26)]
    p = load_profile(
        ["fsi:net_profit", "status.st", "holders.count", "listed"],
        [S, DELISTED, NEW],
        days,
        config=lake,
    )
    assert _value(p, "fsi:net_profit", days[0])["missing_reason"] == "outside_coverage"
    assert _value(p, "status.st", days[1])["missing_reason"] == "value_unknown"
    assert _value(p, "holders.count", days[1])["missing_reason"] == "outside_coverage"
    gone = _value(p, "fsi:net_profit", days[1], DELISTED)
    assert (gone["value_num"], gone["missing_reason"]) == (None, "after_delisting")
    assert _value(p, "fsi:net_profit", days[1], NEW)["missing_reason"] == "before_listing"
    listed = _value(p, "listed", days[1], NEW)
    assert (listed["value_num"], listed["missing_reason"]) == (0.0, None)


def test_old_values_are_returned_marked_stale(lake):
    p = load_profile(["status.trading"], [S], [date(2024, 6, 28)], config=lake)
    row = _value(p, "status.trading", date(2024, 6, 28))
    assert (row["value_num"], row["age_days"], row["missing_reason"]) == (1.0, 63, "stale")


def test_unknown_fields_are_rejected(lake):
    with pytest.raises(ProfileError, match="unknown profile field"):
        load_profile(["industry.citic.l1"], [S], [date(2024, 4, 26)], config=lake)
