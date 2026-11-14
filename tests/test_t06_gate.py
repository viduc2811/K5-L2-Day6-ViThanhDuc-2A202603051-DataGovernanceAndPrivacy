"""Test cho PoC T06 (release gate). Khong doc gt/, khong dung mang."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.common.context import RunContext
from src.common.review import AuditLog
from src.pipeline import _validate_release, review


def _write_release(d: Path, anns, cats, parent_sha, label_map_version="lm-3"):
    d.mkdir(parents=True, exist_ok=True)
    images = [{"id": 1, "file_name": "images/a.jpg", "width": 320, "height": 180}]
    (d / "annotations.json").write_text(json.dumps(
        {"images": images, "annotations": anns, "categories": cats}), encoding="utf-8")
    (d / "release_meta.json").write_text(json.dumps(
        {"label_map_version": label_map_version, "parent_sha256": parent_sha}), encoding="utf-8")


def _setup(tmp_path):
    cats = [{"id": 1, "name": "car"}, {"id": 2, "name": "sign"}]
    ann = [{"id": 1, "image_id": 1, "category_id": 1, "bbox": [10.0, 10.0, 20.0, 20.0]},
           {"id": 2, "image_id": 1, "category_id": 2, "bbox": [50.0, 50.0, 20.0, 20.0]}]
    parent_dir = tmp_path / "parent"
    _write_release(parent_dir, ann, cats, parent_sha=None)
    parent_path = parent_dir / "annotations.json"
    parent = json.loads(parent_path.read_text(encoding="utf-8"))
    sha = hashlib.sha256(parent_path.read_bytes()).hexdigest()
    label_maps = {"lm-2": {"1": "car"}, "lm-3": {"1": "car", "2": "sign"}}
    return ann, cats, parent, parent_path, sha, label_maps


def test_clean_release_has_no_issue(tmp_path):
    ann, cats, parent, parent_path, sha, lm = _setup(tmp_path)
    _write_release(tmp_path / "cand", ann, cats, sha)
    assert _validate_release(tmp_path, tmp_path / "cand", parent, parent_path, lm) == []


def test_duplicate_id_is_blocked(tmp_path):
    ann, cats, parent, parent_path, sha, lm = _setup(tmp_path)
    dup = [dict(ann[0]), dict(ann[1], id=1)]          # id trung
    _write_release(tmp_path / "cand", dup, cats, sha)
    assert "id_collision" in _validate_release(tmp_path, tmp_path / "cand", parent, parent_path, lm)


def test_swapped_class_names_are_blocked(tmp_path):
    ann, cats, parent, parent_path, sha, lm = _setup(tmp_path)
    swapped = [{"id": 1, "name": "sign"}, {"id": 2, "name": "car"}]   # JSON hop le nhung dao class map
    _write_release(tmp_path / "cand", ann, swapped, sha)
    assert "class_swap" in _validate_release(tmp_path, tmp_path / "cand", parent, parent_path, lm)


def test_bbox_shift_is_blocked(tmp_path):
    ann, cats, parent, parent_path, sha, lm = _setup(tmp_path)
    moved = [dict(a, bbox=[a["bbox"][0] + 8, a["bbox"][1], a["bbox"][2], a["bbox"][3]]) for a in ann]
    _write_release(tmp_path / "cand", moved, cats, sha)
    assert "bbox_shift" in _validate_release(tmp_path, tmp_path / "cand", parent, parent_path, lm)


def test_review_override_is_applied_and_audited(tmp_path):
    scored = pd.DataFrame({"release_id": ["r01", "r02"], "score": [1.0, 0.0],
                           "decision": ["HOLD", "PASS"], "root_cause": ["stale_map", "clean"],
                           "reason": ["x", "y"]})
    cols = ["rank", "item_id", "score", "reason", "suggested_action", "slice", "evidence_path",
            "reviewer", "reviewer_decision", "override_value", "review_note", "reviewed_at"]
    row = {c: "" for c in cols}
    row.update(rank="1", item_id="r01", score="1.0", reason="stale_map", reviewer="Tester",
               reviewer_decision="edit", override_value="PASS", review_note="false alarm (test)")
    pd.DataFrame([row], columns=cols).to_csv(tmp_path / "review_queue_reviewed.csv", index=False)
    ctx = RunContext(track="t06", input_dir=tmp_path, output_dir=tmp_path, config={}, seed=42,
                     rng=np.random.default_rng(42), audit=AuditLog(tmp_path / "audit_log.jsonl"))
    final = review(ctx, scored, scored)
    assert final.loc[final.release_id == "r01", "decision"].iloc[0] == "PASS"
    lines = (tmp_path / "audit_log.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1 and '"override:edit"' in lines[0]
