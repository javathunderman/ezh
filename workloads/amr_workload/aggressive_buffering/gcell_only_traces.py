#!/usr/bin/env python3
"""Build g_cells-only baseline and optimistic DRAMSim3 traces."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import List, Optional, Tuple

import optimistic_buffer_trace_stream as common


Entry = Tuple[int, str, int, Optional[str], int]


def write_entry(f, addr: int, op: str, cycle: int, opt_flag: Optional[str]) -> None:
    line = f"0x{addr:08X} {op} {cycle}"
    if opt_flag is not None:
        line += f" {opt_flag}"
    f.write(line + "\n")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace", required=True, type=Path)
    ap.add_argument("--gcell-log", required=True, type=Path, action="append")
    ap.add_argument("--out-original", required=True, type=Path)
    ap.add_argument("--out-optimistic", required=True, type=Path)
    ap.add_argument("--summary-json", required=True, type=Path)
    ap.add_argument("--trace-address-delta", type=common.parse_int_auto, default=-0x400000)
    args = ap.parse_args()

    virtual_start, virtual_end, range_meta = common.parse_gcell_range(args.gcell_log)
    trace_start = virtual_start + args.trace_address_delta
    trace_end = virtual_end + args.trace_address_delta

    entries: List[Entry] = []
    first_cycle = None
    with args.trace.open("r", encoding="utf-8", errors="replace") as f:
        for original_index, line in enumerate(f):
            parsed = common.parse_trace_line(line)
            if parsed is None:
                continue
            addr, op, cycle, opt_flag = parsed
            if trace_start <= addr < trace_end:
                if first_cycle is None:
                    first_cycle = cycle
                entries.append((addr, op, cycle, opt_flag, original_index))

    if first_cycle is None:
        raise SystemExit("No g_cells trace entries found")

    args.out_original.parent.mkdir(parents=True, exist_ok=True)
    with args.out_original.open("w", encoding="utf-8") as f:
        for addr, op, cycle, opt_flag, _idx in entries:
            write_entry(f, addr, op, cycle - first_cycle, opt_flag)

    reads = sorted((e for e in entries if e[1] == "READ"), key=lambda e: (e[0], e[4]))
    writes = sorted((e for e in entries if e[1] == "WRITE"), key=lambda e: (e[0], e[4]))
    others = [e for e in entries if e[1] not in ("READ", "WRITE")]
    with args.out_optimistic.open("w", encoding="utf-8") as f:
        for addr, op, _cycle, opt_flag, _idx in reads:
            write_entry(f, addr, op, 0, opt_flag)
        for addr, op, _cycle, opt_flag, _idx in writes:
            write_entry(f, addr, op, 0, opt_flag)
        for addr, op, _cycle, opt_flag, _idx in others:
            write_entry(f, addr, op, 0, opt_flag)

    summary = {
        "trace": str(args.trace),
        "out_original": str(args.out_original),
        "out_optimistic": str(args.out_optimistic),
        "gcell_range": {
            **range_meta,
            "chosen_delta": args.trace_address_delta,
            "trace_start": trace_start,
            "trace_end": trace_end,
        },
        "entries": len(entries),
        "reads": len(reads),
        "writes": len(writes),
        "others": len(others),
        "original_first_cycle": first_cycle,
        "original_last_relative_cycle": entries[-1][2] - first_cycle,
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"Wrote g_cells-only traces: {args.out_original}, {args.out_optimistic}", flush=True)
    print(f"g_cells entries={len(entries)} reads={len(reads)} writes={len(writes)}", flush=True)


if __name__ == "__main__":
    main()
