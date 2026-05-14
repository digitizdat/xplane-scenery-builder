"""Task 9: Bedrock LLM classification layer tests."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np

from xplane_gen.classifier import (
    _HAIKU,
    _OPUS,
    _SONNET,
    BedrockClassifier,
    _cache_key,
    _parse_tool_response,
)


def _fake_response(building_type: str, height: float, confidence: float) -> dict:
    return {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "name": "classify_building",
                            "input": {
                                "building_type": building_type,
                                "height_m": height,
                                "confidence": confidence,
                                "reasoning": "test",
                            },
                        }
                    }
                ]
            }
        }
    }


def _make_classifier(tmp_path: Path) -> BedrockClassifier:
    with patch("boto3.client"):
        clf = BedrockClassifier(tmp_path)
    return clf


DUMMY_IMAGE = np.zeros((64, 64, 3), dtype=np.uint8)
DUMMY_TAGS = {"building": "residential"}


# ── routing logic ─────────────────────────────────────────────────────────────


def test_high_confidence_uses_haiku_only(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(return_value=_fake_response("residential", 7.0, 0.90))
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS, 47.6, -122.3)
    assert clf._client.converse.call_count == 1
    assert clf._client.converse.call_args[1]["modelId"] == _HAIKU


def test_medium_confidence_escalates_to_sonnet(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(
        side_effect=[
            _fake_response("residential", 7.0, 0.70),  # Haiku → below HIGH
            _fake_response("residential", 7.0, 0.80),  # Sonnet → above LOW
        ]
    )
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS, 47.6, -122.3)
    assert clf._client.converse.call_count == 2
    assert clf._client.converse.call_args_list[1][1]["modelId"] == _SONNET


def test_low_confidence_escalates_to_opus(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(
        side_effect=[
            _fake_response("generic", 8.0, 0.70),  # Haiku
            _fake_response("generic", 8.0, 0.50),  # Sonnet → below LOW
            _fake_response("commercial", 12.0, 0.55),  # Opus
        ]
    )
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS, 47.6, -122.3)
    assert clf._client.converse.call_count == 3
    assert clf._client.converse.call_args_list[2][1]["modelId"] == _OPUS


# ── review queue ──────────────────────────────────────────────────────────────


def test_low_confidence_queued_for_review(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(
        side_effect=[
            _fake_response("generic", 8.0, 0.50),
            _fake_response("generic", 8.0, 0.50),
            _fake_response("generic", 8.0, 0.50),
        ]
    )
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS, 47.6, -122.3)
    assert len(clf._review_queue) == 1
    item = clf._review_queue[0]
    assert "building_type" in item
    assert "confidence" in item
    assert "osm_tags" in item
    assert "human_decision" in item
    assert "thumbnail_b64" in item


def test_high_confidence_not_queued(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(return_value=_fake_response("residential", 7.0, 0.90))
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS, 47.6, -122.3)
    assert len(clf._review_queue) == 0


def test_flush_review_queue_writes_json(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(
        side_effect=[
            _fake_response("generic", 8.0, 0.50),
            _fake_response("generic", 8.0, 0.50),
            _fake_response("generic", 8.0, 0.50),
        ]
    )
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS, 47.6, -122.3)
    path = clf.flush_review_queue()
    assert path.exists()
    items = json.loads(path.read_text())
    assert isinstance(items, list)
    assert len(items) == 1


# ── caching ───────────────────────────────────────────────────────────────────


def test_cache_hit_skips_api_call(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(return_value=_fake_response("residential", 7.0, 0.90))
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS, 47.6, -122.3)
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS, 47.6, -122.3)
    assert clf._client.converse.call_count == 1  # second call hits cache


def test_cache_key_deterministic() -> None:
    k1 = _cache_key("abc", "prompt")
    k2 = _cache_key("abc", "prompt")
    assert k1 == k2


def test_cache_key_differs_on_different_input() -> None:
    assert _cache_key("abc", "prompt1") != _cache_key("abc", "prompt2")


# ── output schema ─────────────────────────────────────────────────────────────


def test_result_has_valid_fac_path(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(return_value=_fake_response("commercial", 15.0, 0.90))
    result = clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS, 47.6, -122.3)
    assert result["fac_path"].startswith("lib/")
    assert result["fac_path"].endswith(".fac")


def test_parse_tool_response_fallback() -> None:
    result = _parse_tool_response({"output": {"message": {"content": []}}})
    assert result["building_type"] == "generic"
    assert result["confidence"] == 0.0
