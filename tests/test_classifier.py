"""Bedrock LLM classification layer tests."""

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


def _fake_building_response(building_type: str, height: float, confidence: float) -> dict:
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
                            },
                        }
                    }
                ]
            }
        },
        "usage": {"inputTokens": 100, "outputTokens": 50},
    }


def _fake_forest_response(species: str, density: float, confidence: float) -> dict:
    return {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "name": "classify_forest",
                            "input": {
                                "species_mix": species,
                                "canopy_density": density,
                                "confidence": confidence,
                            },
                        }
                    }
                ]
            }
        },
        "usage": {"inputTokens": 100, "outputTokens": 50},
    }


def _fake_road_response(surface: str, lanes: int, confidence: float) -> dict:
    return {
        "output": {
            "message": {
                "content": [
                    {
                        "toolUse": {
                            "name": "classify_road",
                            "input": {
                                "surface_type": surface,
                                "lane_count": lanes,
                                "confidence": confidence,
                            },
                        }
                    }
                ]
            }
        },
        "usage": {"inputTokens": 100, "outputTokens": 50},
    }


def _make_classifier(tmp_path: Path, **kwargs: object) -> BedrockClassifier:
    with patch("boto3.client"):
        clf = BedrockClassifier(tmp_path, **kwargs)
    return clf


DUMMY_IMAGE = np.zeros((64, 64, 3), dtype=np.uint8)
DUMMY_TAGS = {"building": "yes"}


# ── routing logic ─────────────────────────────────────────────────────────────


def test_high_confidence_uses_haiku_only(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(return_value=_fake_building_response("residential", 7.0, 0.90))
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS)
    assert clf._client.converse.call_count == 1
    assert clf._client.converse.call_args[1]["modelId"] == _HAIKU


def test_medium_confidence_escalates_to_sonnet(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(
        side_effect=[
            _fake_building_response("residential", 7.0, 0.70),
            _fake_building_response("residential", 7.0, 0.80),
        ]
    )
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS)
    assert clf._client.converse.call_count == 2
    assert clf._client.converse.call_args_list[1][1]["modelId"] == _SONNET


def test_low_confidence_escalates_to_opus(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(
        side_effect=[
            _fake_building_response("generic", 8.0, 0.70),
            _fake_building_response("generic", 8.0, 0.50),
            _fake_building_response("commercial", 12.0, 0.55),
        ]
    )
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS)
    assert clf._client.converse.call_count == 3
    assert clf._client.converse.call_args_list[2][1]["modelId"] == _OPUS


# ── multi-feature classification ──────────────────────────────────────────────


def test_classify_forest(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(return_value=_fake_forest_response("deciduous", 0.85, 0.92))
    result = clf.classify_forest(DUMMY_IMAGE, "tree_cover", 0.7)
    assert result["species_mix"] == "deciduous"
    assert result["canopy_density"] == 0.85


def test_classify_road(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(return_value=_fake_road_response("gravel", 1, 0.88))
    result = clf.classify_road(DUMMY_IMAGE, {"highway": "track"})
    assert result["surface_type"] == "gravel"
    assert result["lane_count"] == 1


# ── review queue ──────────────────────────────────────────────────────────────


def test_low_confidence_queued_for_review(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(
        side_effect=[
            _fake_building_response("generic", 8.0, 0.50),
            _fake_building_response("generic", 8.0, 0.50),
            _fake_building_response("generic", 8.0, 0.50),
        ]
    )
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS)
    assert clf.review_count == 1


def test_high_confidence_not_queued(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(return_value=_fake_building_response("residential", 7.0, 0.90))
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS)
    assert clf.review_count == 0


def test_review_all_queues_everything(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path, review_all=True)
    clf._client.converse = MagicMock(return_value=_fake_building_response("residential", 7.0, 0.95))
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS)
    assert clf.review_count == 1


def test_flush_review_queue_writes_json(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(
        side_effect=[
            _fake_building_response("generic", 8.0, 0.50),
            _fake_building_response("generic", 8.0, 0.50),
            _fake_building_response("generic", 8.0, 0.50),
        ]
    )
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS)
    path = clf.flush_review_queue()
    assert path.exists()
    items = json.loads(path.read_text())
    assert len(items) == 1
    assert items[0]["tool"] == "classify_building"


# ── caching ───────────────────────────────────────────────────────────────────


def test_cache_hit_skips_api_call(tmp_path: Path) -> None:
    clf = _make_classifier(tmp_path)
    clf._client.converse = MagicMock(return_value=_fake_building_response("residential", 7.0, 0.90))
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS)
    clf.classify_building(DUMMY_IMAGE, DUMMY_TAGS)
    assert clf._client.converse.call_count == 1


def test_cache_key_deterministic() -> None:
    k1 = _cache_key("abc", "prompt")
    k2 = _cache_key("abc", "prompt")
    assert k1 == k2


def test_cache_key_differs_on_different_input() -> None:
    assert _cache_key("abc", "prompt1") != _cache_key("abc", "prompt2")


# ── parse_tool_response ───────────────────────────────────────────────────────


def test_parse_tool_response_extracts_result() -> None:
    resp = _fake_building_response("commercial", 15.0, 0.88)
    result = _parse_tool_response(resp, "classify_building", {"building_type": "generic"})
    assert result["building_type"] == "commercial"
    assert result["height_m"] == 15.0


def test_parse_tool_response_fallback_on_missing() -> None:
    resp = {"output": {"message": {"content": []}}}
    fallback = {"building_type": "generic", "height_m": 8.0, "confidence": 0.0}
    result = _parse_tool_response(resp, "classify_building", fallback)
    assert result == fallback
