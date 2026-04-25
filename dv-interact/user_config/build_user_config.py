"""
Aggregate DV-Interact per-task configs into two outputs:
1) user_config/user.json  (full simulator config list; JSON array)
2) user_config/tasks.jsonl (lightweight task list: instance_id + instruction)

Usage:
    python build_user_config.py
"""

from __future__ import annotations

import json
from pathlib import Path


def _normalize_table_schema(val):
    """
    If table_schema is a list/dict, convert to a compact JSON string on one line.
    If already a string, return as is.
    """
    if isinstance(val, (list, dict)):
        return json.dumps(val, ensure_ascii=False, separators=(",", ":"))
    return val


def main() -> None:
    here = Path(__file__).resolve().parent  # .../DV-Interact/user_config
    root = here.parent                      # .../DV-Interact
    tasks_dir = root / "tasks"
    out_user = here / "user.json"
    out_tasks = root / "tasks" / "dv-interact.jsonl"

    user_entries = []
    task_entries = []

    if not tasks_dir.exists():
        raise FileNotFoundError(f"Tasks directory not found: {tasks_dir}")

    for task_dir in sorted(p for p in tasks_dir.iterdir() if p.is_dir()):
        cfg_path = task_dir / "config.json"
        if not cfg_path.exists():
            continue
        try:
            data = json.loads(cfg_path.read_text(encoding="utf-8"))
            if isinstance(data, list):
                items = data
            else:
                items = [data]
            # normalize table_schema before aggregating
            norm_items = []
            for item in items:
                if isinstance(item, dict) and "table_schema" in item:
                    item = dict(item)
                    item["table_schema"] = _normalize_table_schema(item.get("table_schema"))
                norm_items.append(item)
            user_entries.extend(norm_items)
            # Extract lightweight task fields
            for item in norm_items:
                if not isinstance(item, dict):
                    continue
                inst_id = item.get("instance_id")
                instr = item.get("instruction")
                if inst_id and instr:
                    task_entries.append({"instance_id": inst_id, "instruction": instr})
        except Exception as exc:
            print(f"[warn] skip {cfg_path}: {exc}")
            continue

    out_user.parent.mkdir(parents=True, exist_ok=True)
    out_user.write_text(json.dumps(user_entries, ensure_ascii=False, indent=4), encoding="utf-8")
    out_tasks.write_text("\n".join(json.dumps(t, ensure_ascii=False) for t in task_entries), encoding="utf-8")

    print(f"Aggregated {len(user_entries)} user entries into {out_user}")
    print(f"Wrote {len(task_entries)} tasks into {out_tasks} (jsonl)")


if __name__ == "__main__":
    main()
