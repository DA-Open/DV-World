"""
Collect task folders into a jsonl file.

Usage:
  python collect_tasks.py --root /path/to/tasks --prefix dv-interact --output dv-interact.jsonl

Rules:
- Under root, each subfolder whose name starts with prefix is a task.
- Expect an instruction markdown (default: instruction.md or query.md) inside each task folder.
- Emit jsonl with fields: {"instance_id": folder_name, "instruction": <md text>}
"""

import argparse
import json
from pathlib import Path
from typing import List


def find_instruction(task_dir: Path, candidates: List[str]) -> str:
    for name in candidates:
        p = task_dir / name
        if p.exists() and p.is_file():
            return p.read_text(encoding="utf-8").strip()
    return ""


def main():
    parser = argparse.ArgumentParser(description="Collect task instructions into jsonl")
    parser.add_argument("--root",  type=Path, default="/Users/bytedance/Documents/DVSheet-1/DV-Sheet/tasks", help="Root directory containing task folders")
    parser.add_argument("--prefix", default="dvsheet", help="Task folder prefix to match (e.g., dv-interact)")
    parser.add_argument("--output", type=Path, default="/Users/bytedance/Documents/DVSheet-1/DV-Sheet/tasks/dvsheet-all.jsonl", help="Output jsonl path")
    parser.add_argument("--instruction-files", nargs="*", default=["instruction.md", "query.md", "task.md"], help="Candidate instruction filenames")
    parser.add_argument("--delete-md", action="store_true", help="Delete instruction md file after collection")
    args = parser.parse_args()

    if not args.root.exists():
        raise FileNotFoundError(f"root not found: {args.root}")

    rows = []
    for task_dir in sorted(p for p in args.root.iterdir() if p.is_dir() and p.name.startswith(args.prefix)):
        instr_path = None
        instr = ""
        for name in args.instruction_files:
            p = task_dir / name
            if p.exists() and p.is_file():
                instr_path = p
                instr = p.read_text(encoding="utf-8").strip()
                break
        if not instr:
            print(f"[warn] missing instruction in {task_dir}")
            continue
        row = {"instance_id": task_dir.name, "instruction": instr}
        rows.append(row)
        if args.delete_md and instr_path:
            try:
                instr_path.unlink()
            except Exception as exc:
                print(f"[warn] failed to delete {instr_path}: {exc}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"Wrote {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
