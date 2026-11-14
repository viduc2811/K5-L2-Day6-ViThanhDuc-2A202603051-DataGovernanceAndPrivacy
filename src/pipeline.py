"""YOUR PoC PIPELINE — this is the file your group owns.

Lab contract = 5 automated steps, run by `python -m src.main ...`:
    01 load      input + provenance check (manifest.csv)
    02 process   your algorithm / model (the research part)
    03 rank      prioritise for a fixed review budget B
    04 review    human-in-the-loop: queue -> reviewer decisions -> overrides + audit log
    05 decide    GO / HOLD / REWORK (or track equivalent) with reason_code + owner, write outputs

Required output: out/<pred_file> with the columns listed for your track in
docs/tracks/TXX.md (also in src/metrics/tracks.py::TRACKS). Then evaluate with
    python -m src.evaluate --track tXX --pred out/<pred_file>

Rules: never read fixtures/*/gt/ here (the GT guard will stop you); seed everything via ctx.rng;
no network calls; fail loudly on missing models instead of downloading.
See src/examples/random_baseline.py for a minimal end-to-end wiring example.
"""
from __future__ import annotations

import hashlib
import json
from collections import defaultdict

import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .common.manifest import verify_manifest
from .common.review import apply_overrides, load_review_decisions, make_review_queue, write_review_queue
from .metrics.tracks import get_track


# ---------------------------------------------------------------- 01 load
def load(ctx: RunContext) -> dict:
    manifest = ctx.input_dir / "manifest.csv"
    problems = verify_manifest(manifest) if manifest.exists() else [{"problem": "no_manifest"}]
    if problems:
        ctx.audit.log(actor="pipeline", action="provenance_problems", item_id=str(manifest), after=problems[:20])
        if ctx.config.get("strict_provenance", True):
            raise ValueError(f"provenance check failed ({len(problems)} problems), first: {problems[:3]}")
    data = {"manifest": pd.read_csv(manifest) if manifest.exists() else None}
    data["releases"] = pd.read_csv(ctx.input_dir / "releases.csv")
    data["label_maps"] = json.loads((ctx.input_dir / "releases/label_maps.json").read_text(encoding="utf-8"))
    data["parent_path"] = ctx.input_dir / ctx.param("parent_release", "releases/v1.0") / "annotations.json"
    data["parent"] = json.loads(data["parent_path"].read_text(encoding="utf-8"))
    return data


# ---------------------------------------------------------------- 02 process
BBOX_SHIFT_PX = 1.0  # chốt trên split dev, TRƯỚC khi xem eval


def _validate_release(root, rel_dir, parent, parent_path, label_maps) -> list[str]:
    ann = json.loads((rel_dir / "annotations.json").read_text(encoding="utf-8"))
    meta = json.loads((rel_dir / "release_meta.json").read_text(encoding="utf-8"))
    anns, imgs = ann["annotations"], ann["images"]
    cats = {c["id"]: c["name"] for c in ann["categories"]}
    issues = []
    # 1) id trùng
    ids = [a["id"] for a in anns]
    if len(ids) != len(set(ids)):
        issues.append("id_collision")
    # 2) rơi frame (nhiều hơn parent 1 ảnh là thay đổi lành tính)
    if len(imgs) < len(parent["images"]):
        issues.append("dropped_frames")
    # 3) bbox lệch so với parent
    by_img = defaultdict(list)
    for p in parent["annotations"]:
        by_img[p["image_id"]].append(p)
    dist = []
    for a in anns:
        cand = by_img.get(a["image_id"])
        if cand:
            b = min(cand, key=lambda p: abs(p["bbox"][0] - a["bbox"][0]) + abs(p["bbox"][1] - a["bbox"][1]))
            dist.append(abs(a["bbox"][0] - b["bbox"][0]) + abs(a["bbox"][1] - b["bbox"][1]))
    if dist and sum(dist) / len(dist) > BBOX_SHIFT_PX:
        issues.append("bbox_shift")
    # 4) label map + provenance (sha256 của parent)
    declared = {int(k): v for k, v in label_maps.get(meta["label_map_version"], {}).items()}
    if meta.get("parent_sha256") != hashlib.sha256(parent_path.read_bytes()).hexdigest():
        issues.append("stale_map")
    elif cats != declared:
        old = {int(k): v for k, v in label_maps["lm-2"].items()}
        issues.append("stale_map" if cats == old else "class_swap")
    return issues


def process(ctx: RunContext, data: dict) -> pd.DataFrame:
    rows = []
    for r in data["releases"].itertuples(index=False):
        issues = _validate_release(ctx.input_dir, ctx.input_dir / r.path, data["parent"], data["parent_path"], data["label_maps"])
        rows.append({"release_id": r.release_id, "score": float(len(issues)),
                     "decision": "HOLD" if issues else "PASS",
                     "root_cause": issues[0] if issues else "clean",
                     "reason": ";".join(issues) if issues else "no_violation", "split": r.split})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- 03 rank
def rank(ctx: RunContext, scored: pd.DataFrame) -> pd.DataFrame:
    """Default: top-B by `score`. Adapt id/score/reason columns to your track."""
    budget = int(ctx.param("budget", 20))
    if "score" not in scored.columns:
        raise ValueError("rank(): process() output needs a numeric `score` column (higher = review first), "
                         "or adapt rank() to your track")
    q = make_review_queue(scored, id_col=scored.columns[0], score_col="score", budget=budget,
                          reason_col="reason" if "reason" in scored.columns else None)
    write_review_queue(q, ctx.out("review_queue.csv"))
    return q


# ---------------------------------------------------------------- 04 review
def review(ctx: RunContext, scored: pd.DataFrame, queue: pd.DataFrame) -> pd.DataFrame:
    """If a reviewed queue exists (out/review_queue_reviewed.csv), apply it. Otherwise pass through.

    TODO: decide what an `edit` / `reject` means for your track and apply it
    (e.g. via common.review.apply_overrides), logging every change to ctx.audit.
    """
    reviewed_path = ctx.output_dir / "review_queue_reviewed.csv"
    if reviewed_path.exists():
        reviewed = load_review_decisions(reviewed_path)
        ctx.stats["n_reviewed"] = len(reviewed)
        for r in reviewed.itertuples(index=False):
            if r.reviewer_decision == "approve" and ctx.audit:
                cur = scored.loc[scored["release_id"].astype(str) == str(r.item_id), "decision"]
                ctx.audit.log(actor=r.reviewer, action="review:approve", item_id=r.item_id,
                              before=cur.iloc[0] if len(cur) else None,
                              after=cur.iloc[0] if len(cur) else None, reason=r.review_note)
        return apply_overrides(scored, reviewed, id_col="release_id", value_col="decision", audit=ctx.audit)
    return scored


# ---------------------------------------------------------------- 05 decide
def decide(ctx: RunContext, final: pd.DataFrame) -> Decision:
    blocked = final[final["decision"] != "PASS"]
    owner = ctx.config.get("owner", "TODO-owner")
    ev = [str(ctx.out("release_decisions.csv"))]
    if len(blocked):
        causes = blocked["root_cause"].value_counts().to_dict()
        return Decision(status="HOLD", reason_code="SILENT_DEFECTS_FOUND",
                        reason=f"{len(blocked)}/{len(final)} release bị chặn: {causes}",
                        owner=owner, scope=ctx.track, evidence=ev,
                        metrics={"blocked": int(len(blocked)), "total": int(len(final))})
    return Decision(status="GO", reason_code="ALL_RELEASES_CLEAN", reason="Không phát hiện lỗi nào",
                    owner=owner, scope=ctx.track, evidence=ev)


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    data = load(ctx)
    scored = process(ctx, data)
    ctx.stats["n_items"] = len(scored)
    queue = rank(ctx, scored)
    final = review(ctx, scored, queue)
    final[spec.pred_columns + [c for c in final.columns if c not in spec.pred_columns]].to_csv(ctx.out(spec.pred_file), index=False)
    write_decision(decide(ctx, final), ctx.out("decision.json"), ctx.out("decision_log.csv"))
