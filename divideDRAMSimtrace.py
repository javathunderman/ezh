#!/usr/bin/env python3
import argparse
import os
import re
from pathlib import Path


ITER_BEGIN_RE = re.compile(r"ITER_BEGIN\s+t=(\d+)\s+tick=(\d+)")
ITER_END_RE   = re.compile(r"ITER_END\s+t=(\d+)\s+tick=(\d+)")


def parse_gem5_iters(gem5_log_path: Path, tick_div: int):
    """
    Parse ITER_BEGIN / ITER_END pairs from gem5 log.

    Returns a list of dicts like:
      {
        "t": 1,
        "begin_tick": 2727392500,
        "end_tick": 4658143250,
        "begin_cycle": 10909570,
        "end_cycle": 18632573,
      }
    """
    begins = {}
    ends = {}

    with gem5_log_path.open("r", encoding="utf-8", errors="replace") as f:
        for lineno, line in enumerate(f, start=1):
            m = ITER_BEGIN_RE.search(line)
            if m:
                t = int(m.group(1))
                tick = int(m.group(2))
                if t in begins:
                    raise ValueError(
                        f"Duplicate ITER_BEGIN for t={t} at line {lineno}"
                    )
                begins[t] = tick
                continue

            m = ITER_END_RE.search(line)
            if m:
                t = int(m.group(1))
                tick = int(m.group(2))
                if t in ends:
                    raise ValueError(
                        f"Duplicate ITER_END for t={t} at line {lineno}"
                    )
                ends[t] = tick

    all_ts = sorted(set(begins.keys()) | set(ends.keys()))
    iters = []

    for t in all_ts:
        if t not in begins:
            raise ValueError(f"Missing ITER_BEGIN for t={t}")
        if t not in ends:
            raise ValueError(f"Missing ITER_END for t={t}")

        begin_tick = begins[t]
        end_tick = ends[t]

        if end_tick < begin_tick:
            raise ValueError(
                f"ITER_END tick < ITER_BEGIN tick for t={t}: "
                f"{end_tick} < {begin_tick}"
            )

        iters.append({
            "t": t,
            "begin_tick": begin_tick,
            "end_tick": end_tick,
            "begin_cycle": begin_tick // tick_div,
            "end_cycle": end_tick // tick_div,
        })

    return sorted(iters, key=lambda x: x["t"])


def open_output_files(iters, outdir: Path):
    """
    Open one output file per iteration.
    """
    outdir.mkdir(parents=True, exist_ok=True)
    handles = {}
    for it in iters:
        t = it["t"]
        path = outdir / f"iter_{t:06d}_cycles_{it['begin_cycle']}_{it['end_cycle']}.trace"
        handles[t] = path.open("w", encoding="utf-8")
    return handles


def split_trace_by_iters(trace_path: Path, iters, outdir: Path):
    """
    Stream the DRAMSim3-style trace and write each line into the matching
    iteration file if cycle is within [begin_cycle, end_cycle].
    """
    sorted_iters = sorted(iters, key=lambda x: x["begin_cycle"])
    out_handles = open_output_files(sorted_iters, outdir)

    try:
        idx = 0
        n = len(sorted_iters)

        with trace_path.open("r", encoding="utf-8", errors="replace") as f:
            for lineno, raw_line in enumerate(f, start=1):
                line = raw_line.strip()
                if not line:
                    continue

                parts = line.split()
                if len(parts) < 3:
                    continue

                # Expected format:
                #   0x00002698 READ 10909570
                try:
                    cycle = int(parts[-1])
                except ValueError:
                    continue

                # Advance idx while current iteration ended before this cycle.
                while idx < n and cycle > sorted_iters[idx]["end_cycle"]:
                    idx += 1

                if idx >= n:
                    break

                cur = sorted_iters[idx]

                if cur["begin_cycle"] <= cycle <= cur["end_cycle"]:
                    out_handles[cur["t"]].write(raw_line)
                else:
                    # cycle < current iteration start; ignore
                    pass

    finally:
        for fh in out_handles.values():
            fh.close()


def write_summary(iters, outdir: Path):
    summary_path = outdir / "iteration_ranges.txt"
    with summary_path.open("w", encoding="utf-8") as f:
        for it in iters:
            f.write(
                f"t={it['t']} "
                f"begin_tick={it['begin_tick']} end_tick={it['end_tick']} "
                f"begin_cycle={it['begin_cycle']} end_cycle={it['end_cycle']}\n"
            )


def main():
    parser = argparse.ArgumentParser(
        description="Split a DRAMSim3-style trace into one file per gem5 iteration block."
    )
    parser.add_argument(
        "--gem5-log",
        required=True,
        help="Path to gem5 log containing ITER_BEGIN / ITER_END lines",
    )
    parser.add_argument(
        "--trace",
        required=True,
        help="Path to DRAMSim3-style trace file",
    )
    parser.add_argument(
        "--outdir",
        required=True,
        help="Directory to write per-iteration trace files",
    )
    parser.add_argument(
        "--tickDivParam",
        type=int,
        default=630,
        help="Tick divisor to convert gem5 ticks to trace cycles (default: 250)",
    )

    args = parser.parse_args()

    gem5_log_path = Path(args.gem5_log)
    trace_path = Path(args.trace)
    outdir = Path(args.outdir)

    iters = parse_gem5_iters(gem5_log_path, args.tickDivParam)
    if not iters:
        raise ValueError("No ITER_BEGIN / ITER_END pairs found in gem5 log")

    #write_summary(iters, outdir)
    split_trace_by_iters(trace_path, iters, outdir)

    print(f"Parsed {len(iters)} iteration blocks")
    print(f"Wrote outputs to: {outdir}")


if __name__ == "__main__":
    main()