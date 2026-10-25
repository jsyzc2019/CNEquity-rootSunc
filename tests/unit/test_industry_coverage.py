"""cne verify --industry: snapshots against listed stocks, industries against the previous snapshot."""

from datetime import date, datetime, timezone

import polars as pl
import pytest

from cnequity.config import Config
from cnequity.domain.schemas import DATASET_SCHEMAS
from cnequity.quality.industry_coverage import industry_coverage_report
from cnequity.storage.revisions import RevisionStore

D1, D2, D3 = date(2026, 8, 31), date(2026, 9, 30), date(2026, 10, 30)
FETCHED = datetime(2026, 11, 1, tzinfo=timezone.utc)
STOCKS = [f"6000{i:02d}.SH" for i in range(12)]


def _commit(cfg, dataset):
    root = cfg.curated_root / dataset
    RevisionStore(cfg.meta_root, cfg.curated_root, cfg.derived_root).commit(
        dataset,
        run_id="seed",
        changed_files=sorted(root.rglob("*.parquet")),
        schema_version=1,
        contract_fingerprint="contract",
    )


def _member(symbol, day, l3, *, system="eastmoney", version="v2"):
    l1, l2 = l3[:1] + "00", l3[:2] + "0"
    return {
        "symbol": symbol,
        "classification_system": system,
        "industry_code": l3,
        "industry_name": l3,
        "l1_code": l1,
        "l1_name": l1,
        "l2_code": l2,
        "l2_name": l2,
        "l3_code": l3,
        "l3_name": l3,
        "as_of_date": day,
        "source": system,
        "data_version": version,
        "fetched_at": FETCHED,
    }


def _lake(tmp_path, rows):
    cfg = Config(data_root=tmp_path / "lake")
    inst = cfg.curated_root / "instruments"
    inst.mkdir(parents=True)
    pl.DataFrame(
        [
            {
                "symbol": s,
                "name": s,
                "exchange": "SH",
                "asset_type": "stock",
                "list_date": date(2020, 1, 1),
                "delist_date": None,
                "prev_symbol": None,
                "source": "t",
                "data_version": "v1",
                "fetched_at": FETCHED,
            }
            for s in STOCKS
        ],
        schema=DATASET_SCHEMAS["instruments"],
    ).write_parquet(inst / "part.parquet")
    _commit(cfg, "instruments")
    frame = pl.DataFrame(rows, schema=DATASET_SCHEMAS["industry_members"])
    for (day,), part in frame.partition_by("as_of_date", as_dict=True).items():
        root = cfg.curated_root / "industry_members" / f"as_of_date={day}"
        root.mkdir(parents=True)
        part.write_parquet(root / "part.parquet")
    _commit(cfg, "industry_members")
    return cfg


def _snapshot(day, *, codes=None, drop=(), **kw):
    codes = codes or {s: ("111" if i < 6 else "122") for i, s in enumerate(STOCKS)}
    return [_member(s, day, codes[s], **kw) for s in STOCKS if s not in drop]


def test_a_complete_stable_classification_reports_no_gaps(tmp_path):
    cfg = _lake(tmp_path, _snapshot(D1) + _snapshot(D2))
    report = industry_coverage_report(cfg, today=D2)
    em = report["systems"]["eastmoney"]
    assert report["state"] == "complete"
    assert em["coverage_min"] == 1.0
    assert em["industries_by_level"] == {"L1": 1, "L2": 2, "L3": 2}
    assert em["days_since_last"] == 0


def test_missing_members_and_a_vanished_industry_are_gaps(tmp_path):
    # On D2 the whole 122 industry is gone: six listed stocks have no row.
    cfg = _lake(tmp_path, _snapshot(D1) + _snapshot(D2, drop=STOCKS[6:]))
    em = industry_coverage_report(cfg, today=D2)["systems"]["eastmoney"]
    gap = em["coverage_gaps"][0]
    assert (gap["as_of_date"], gap["missing"], gap["coverage"]) == ("2026-09-30", 6, 0.5)
    assert gap["missing_sample"] == STOCKS[6:]
    vanished = {(d["level"], d["industry_code"]) for d in em["industry_drops"]}
    assert vanished == {("L2", "120"), ("L3", "122")}


def test_v1_snapshots_are_partial_and_not_compared(tmp_path):
    # A v1 snapshot holds one random level per stock, so its counts move
    # without any change in the market; it must not read as a drop.
    v1 = [{**r, "l2_code": None, "l3_code": None, "data_version": "v1"} for r in _snapshot(D1)]
    cfg = _lake(tmp_path, v1 + _snapshot(D2))
    em = industry_coverage_report(cfg, today=D2)["systems"]["eastmoney"]
    assert em["partial_level_snapshots"]["count"] == 1
    assert em["industry_drops"] == []


@pytest.mark.parametrize("moved", [3, 8])
def test_a_taxonomy_replacement_is_reported_apart_from_drops(tmp_path, moved):
    renumbered = {
        s: ("911" if i < moved else ("111" if i < 6 else "122")) for i, s in enumerate(STOCKS)
    }
    cfg = _lake(tmp_path, _snapshot(D2, system="sw") + _snapshot(D3, codes=renumbered, system="sw"))
    sw = industry_coverage_report(cfg, today=D3)["systems"]["sw"]
    if moved == 8:
        assert [r["as_of_date"] for r in sw["reclassifications"]] == ["2026-10-30"]
        assert sw["industry_drops"] == []
    else:
        # An ordinary reassignment: 111 keeps half its members, not a drop.
        assert sw["reclassifications"] == []
        assert sw["industry_drops"] == []
