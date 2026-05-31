from __future__ import annotations

import argparse
import json
from pathlib import Path

from .pipeline import WebGALPipeline
from .storage import JobStore


def main() -> int:
    parser = argparse.ArgumentParser(description="Drive the WebGAL function-call pipeline.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create = subparsers.add_parser("create", help="Create a job and print its JSON.")
    create.add_argument("--source", required=True, help="Path to a source story text file.")
    create.add_argument("--options", help="Path to an options JSON file.")

    run = subparsers.add_parser("run", help="Create and run a job.")
    run.add_argument("--source", required=True, help="Path to a source story text file.")
    run.add_argument("--options", help="Path to an options JSON file.")
    run.add_argument("--generate-assets", action="store_true", help="Run image generation scripts.")

    phase = subparsers.add_parser("phase", help="Run one phase for an existing job.")
    phase.add_argument("job_id")
    phase.add_argument(
        "phase",
        choices=[
            "narrative",
            "game_design",
            "asset_manifest",
            "asset_generation",
            "script_rewrite",
            "assets",
            "scenes",
            "validation",
        ],
    )

    status = subparsers.add_parser("status", help="Print job status JSON.")
    status.add_argument("job_id")

    args = parser.parse_args()
    store = JobStore()
    pipeline = WebGALPipeline(store)

    if args.command in {"create", "run"}:
        source = Path(args.source).read_text(encoding="utf-8")
        options = load_options(args.options)
        if args.command == "run" and args.generate_assets:
            options["generate_assets"] = True
        job = store.create(source, options)
        if args.command == "run":
            job = pipeline.run_all(job["id"])
        print(json.dumps(job, ensure_ascii=False, indent=2))
        return 0

    if args.command == "phase":
        job = pipeline.run_phase(args.job_id, args.phase)
        print(json.dumps(job, ensure_ascii=False, indent=2))
        return 0

    if args.command == "status":
        print(json.dumps(store.get(args.job_id), ensure_ascii=False, indent=2))
        return 0

    return 2


def load_options(path: str | None) -> dict:
    if not path:
        return {}
    return json.loads(Path(path).read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())
