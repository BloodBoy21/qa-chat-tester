"""
batch_runner.py

Reads a JSON file, splits it into batches of `batch_size`,
and spawns a separate Python subprocess for each batch to
achieve true parallelism.

Usage:
    python batch_runner.py json_file=data.json batch_size=10 max_workers=4 model=gemini-2.5-flash max_iterations=30

Arguments:
    json_file       - Path to the JSON file (required)
    batch_size      - Number of items per batch (default: 10)
    max_workers     - Max parallel subprocesses (default: number of batches, capped at os.cpu_count())
    model           - Model name override (default: from env or gemini-2.5-flash)
    max_iterations  - Max conversation iterations per agent (default: 30)
"""

import datetime
import json
import math
import os
import subprocess
import sys
import tempfile
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from loguru import logger

# ── Parse CLI args ──────────────────────────────────────────────
args = dict(arg.split("=", 1) for arg in sys.argv[1:] if "=" in arg)

JSON_FILE = args.get("json_file")
BATCH_SIZE = int(args.get("batch_size", 10))
MAX_WORKERS = int(args.get("max_workers", 0))  # 0 = auto
MAX_ITEMS = int(args.get("max_items", 0))       # 0 = all
MODEL = args.get("model", os.getenv("MODEL_NAME", "gemini-2.5-flash"))

# Forward any extra args to the child process
FORWARD_ARGS = {
    k: v for k, v in args.items() if k not in ("json_file", "batch_size", "max_workers", "max_items")
}


def load_and_split(file_path: str, batch_size: int, max_items: int = 0) -> list[list[dict]]:
    """Load JSON array, optionally cap at max_items, and split into chunks."""
    with open(file_path, "r") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("JSON file must contain a top-level array.")

    total = len(data)
    if max_items and max_items < total:
        data = data[:max_items]
        logger.info(f"Max items cap: using {max_items} of {total} total")

    num_batches = math.ceil(len(data) / batch_size)
    batches = [data[i * batch_size : (i + 1) * batch_size] for i in range(num_batches)]
    logger.info(f"Loaded {len(data)} items → {num_batches} batches of up to {batch_size}")
    return batches


def run_batch_subprocess(batch_index: int, batch_file: str) -> dict:
    """
    Spawn `python main.py json_file=<tmp_batch_file> ...forwarded_args`
    and capture output. Returns a result dict.
    """
    cmd = [
        sys.executable,
        "main.py",
        f"json_file={batch_file}",
        f"batch_size={BATCH_SIZE}",
    ]
    for k, v in FORWARD_ARGS.items():
        cmd.append(f"{k}={v}")

    logger.info(f"[Batch {batch_index}] Launching: {' '.join(cmd)}")
    start = datetime.datetime.now()

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        env={**os.environ, "MODEL_NAME": MODEL},
    )

    elapsed = (datetime.datetime.now() - start).total_seconds()

    return {
        "batch_index": batch_index,
        "batch_file": batch_file,
        "returncode": result.returncode,
        "elapsed_seconds": elapsed,
        "stdout_tail": result.stdout[-2000:] if result.stdout else "",
        "stderr_tail": result.stderr[-2000:] if result.stderr else "",
    }


def main():
    if not JSON_FILE:
        logger.error("Missing required argument: json_file=<path>")
        sys.exit(1)

    if not Path(JSON_FILE).exists():
        logger.error(f"File not found: {JSON_FILE}")
        sys.exit(1)

    batches = load_and_split(JSON_FILE, BATCH_SIZE, MAX_ITEMS)
    num_batches = len(batches)

    # Use a context manager so temp files are always cleaned up, even on error
    with tempfile.TemporaryDirectory(prefix="batch_runner_") as tmp_dir:
        batch_files: list[str] = []
        for i, batch in enumerate(batches):
            tmp_path = os.path.join(tmp_dir, f"batch_{i:04d}.json")
            with open(tmp_path, "w") as f:
                json.dump(batch, f)
            batch_files.append(tmp_path)

        logger.info(f"Temp batch files written to {tmp_dir}")

        max_workers = (
            MAX_WORKERS if MAX_WORKERS > 0 else min(num_batches, os.cpu_count() or 4)
        )
        logger.info(f"Launching {num_batches} batches with max_workers={max_workers}")

        start = datetime.datetime.now()
        results: list[dict] = []

        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {
                executor.submit(run_batch_subprocess, i, bf): i
                for i, bf in enumerate(batch_files)
            }

            for future in as_completed(futures):
                batch_idx = futures[future]
                try:
                    res = future.result()
                    results.append(res)
                    status = (
                        "OK" if res["returncode"] == 0 else f"FAIL (rc={res['returncode']})"
                    )
                    logger.info(
                        f"[Batch {res['batch_index']}] {status} in {res['elapsed_seconds']:.1f}s"
                    )
                    if res["returncode"] != 0 and res["stderr_tail"]:
                        logger.error(
                            f"[Batch {res['batch_index']}] stderr:\n{res['stderr_tail']}"
                        )
                except Exception as e:
                    logger.error(f"[Batch {batch_idx}] Exception: {e}")
                    results.append(
                        {"batch_index": batch_idx, "returncode": -1, "error": str(e)}
                    )

    total_elapsed = (datetime.datetime.now() - start).total_seconds()
    succeeded = sum(1 for r in results if r.get("returncode") == 0)
    failed = num_batches - succeeded

    logger.info("=" * 60)
    logger.info(f"All batches finished in {datetime.timedelta(seconds=total_elapsed)}")
    logger.info(f"  Succeeded: {succeeded}/{num_batches}")
    logger.info(f"  Failed:    {failed}/{num_batches}")
    logger.info("=" * 60)

    if failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
