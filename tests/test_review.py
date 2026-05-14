"""Task 10: HITL review CLI tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from xplane_gen.review import _validate_type, load_resolved_decisions, run_review


def _make_item(building_type: str = "generic", confidence: float = 0.5) -> dict:
    return {
        "building_type": building_type,
        "height_m": 8.0,
        "confidence": confidence,
        "reasoning": "test",
        "fac_path": "lib/g8/generic_md.fac",
        "osm_tags": {"building": "yes"},
        "thumbnail_b64": "aGVsbG8=",  # base64("hello")
        "human_decision": building_type,
    }


def _write_queue(path: Path, items: list[dict]) -> None:
    path.write_text(json.dumps(items), encoding="utf-8")


# ── run_review ────────────────────────────────────────────────────────────────


def test_run_review_empty_queue(tmp_path: Path) -> None:
    q = tmp_path / "queue.json"
    out = tmp_path / "resolved.json"
    _write_queue(q, [])
    run_review(str(q), str(out))
    assert out.exists()
    assert json.loads(out.read_text()) == []


def test_run_review_missing_queue(tmp_path: Path) -> None:
    out = tmp_path / "resolved.json"
    run_review(str(tmp_path / "missing.json"), str(out))
    assert not out.exists()


def test_run_review_confirm_default(tmp_path: Path) -> None:
    q = tmp_path / "queue.json"
    out = tmp_path / "resolved.json"
    _write_queue(q, [_make_item("residential")])

    # Simulate user pressing Enter (empty input = accept suggestion)
    with patch("xplane_gen.review._prompt", return_value=""):
        run_review(str(q), str(out))

    resolved = json.loads(out.read_text())
    assert len(resolved) == 1
    assert resolved[0]["human_decision"] == "residential"


def test_run_review_override_type(tmp_path: Path) -> None:
    q = tmp_path / "queue.json"
    out = tmp_path / "resolved.json"
    _write_queue(q, [_make_item("generic")])

    with patch("xplane_gen.review._prompt", return_value="commercial"):
        run_review(str(q), str(out))

    resolved = json.loads(out.read_text())
    assert resolved[0]["human_decision"] == "commercial"


def test_run_review_all_items_in_resolved(tmp_path: Path) -> None:
    q = tmp_path / "queue.json"
    out = tmp_path / "resolved.json"
    items = [_make_item("generic"), _make_item("residential"), _make_item("industrial")]
    _write_queue(q, items)

    with patch("xplane_gen.review._prompt", return_value=""):
        run_review(str(q), str(out))

    resolved = json.loads(out.read_text())
    assert len(resolved) == 3


def test_batch_approval_applies_to_similar(tmp_path: Path) -> None:
    q = tmp_path / "queue.json"
    out = tmp_path / "resolved.json"
    # Three items with same type — batch should apply to all
    items = [_make_item("generic"), _make_item("generic"), _make_item("generic")]
    _write_queue(q, items)

    # First prompt: batch confirm (y), second: type decision (commercial)
    responses = iter(["y", "commercial"])
    with patch("xplane_gen.review._prompt", side_effect=lambda _: next(responses)):
        run_review(str(q), str(out))

    resolved = json.loads(out.read_text())
    assert all(r["human_decision"] == "commercial" for r in resolved)


def test_resolved_queue_has_required_fields(tmp_path: Path) -> None:
    q = tmp_path / "queue.json"
    out = tmp_path / "resolved.json"
    _write_queue(q, [_make_item()])

    with patch("xplane_gen.review._prompt", return_value=""):
        run_review(str(q), str(out))

    item = json.loads(out.read_text())[0]
    for field in ("building_type", "height_m", "confidence", "human_decision", "osm_tags"):
        assert field in item


# ── validate_type ─────────────────────────────────────────────────────────────


def test_validate_type_valid() -> None:
    assert _validate_type("commercial", "generic") == "commercial"


def test_validate_type_invalid_falls_back() -> None:
    assert _validate_type("skyscraper", "generic") == "generic"


# ── load_resolved_decisions ───────────────────────────────────────────────────


def test_load_resolved_decisions_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "resolved.json"
    p.write_text("[]", encoding="utf-8")
    assert load_resolved_decisions(p) == {}


def test_load_resolved_decisions_missing_file(tmp_path: Path) -> None:
    assert load_resolved_decisions(tmp_path / "missing.json") == {}


def test_load_resolved_decisions_returns_mapping(tmp_path: Path) -> None:
    p = tmp_path / "resolved.json"
    p.write_text(json.dumps([_make_item("commercial")]), encoding="utf-8")
    mapping = load_resolved_decisions(p)
    assert isinstance(mapping, dict)
    assert "commercial" in mapping.values()
