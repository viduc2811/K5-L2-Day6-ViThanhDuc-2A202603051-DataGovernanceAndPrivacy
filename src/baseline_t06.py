"""Baseline T06: chỉ parse JSON + kiểm file ảnh tồn tại. KHÔNG so semantic invariants."""
from __future__ import annotations

import json

import pandas as pd

from .common.context import RunContext
from .common.decision import Decision, write_decision
from .metrics.tracks import get_track


def run(ctx: RunContext) -> None:
    spec = get_track(ctx.track)
    root = ctx.input_dir
    rows = []
    for r in pd.read_csv(root / "releases.csv").itertuples(index=False):
        d = root / r.path
        try:
            ann = json.loads((d / "annotations.json").read_text(encoding="utf-8"))
            json.loads((d / "release_meta.json").read_text(encoding="utf-8"))
            ok = {"images", "annotations", "categories"} <= ann.keys() and all(
                (root / im["file_name"]).exists() for im in ann["images"]
            )
        except Exception:
            ok = False
        rows.append({"release_id": r.release_id,
                     "decision": "PASS" if ok else "HOLD",
                     "root_cause": "clean" if ok else "schema_error"})
    out = pd.DataFrame(rows)
    ctx.stats["n_items"] = len(out)
    out.to_csv(ctx.out(spec.pred_file), index=False)
    blocked = int((out.decision != "PASS").sum())
    write_decision(
        Decision(status="HOLD" if blocked else "GO", reason_code="BASELINE_SCHEMA_ONLY",
                 reason=f"Baseline chỉ kiểm schema/file: chặn {blocked}/{len(out)} release",
                 owner=ctx.config.get("owner", "baseline"), scope=ctx.track,
                 evidence=[str(ctx.out(spec.pred_file))]),
        ctx.out("decision.json"), ctx.out("decision_log.csv"))