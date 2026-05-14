#!/usr/bin/env python3
"""Streaming AMR DRAMSim3 trace rewriter for optimistic g_cells buffering."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


GCELL_RE = re.compile(
    r"GCELL\s+idx=(\d+)\s+base=(0x[0-9a-fA-F]+)\s+addr=(0x[0-9a-fA-F]+)\s+"
    r"offset=(0x[0-9a-fA-F]+)\s+sizeof_cell=(\d+)"
)
ITER_BEGIN_RE = re.compile(r"ITER_BEGIN\s+t=(\d+)\s+tick=(\d+)")
ITER_END_RE = re.compile(r"ITER_END\s+t=(\d+)\s+tick=(\d+)")


def parse_int_auto(value: str) -> int:
    return int(value, 0)


def parse_trace_line(line: str) -> Optional[Tuple[int, str, int, Optional[str]]]:
    parts = line.strip().split()
    if not parts:
        return None
    if len(parts) not in (3, 4):
        raise ValueError(f"Unsupported trace line: {line.rstrip()}")
    return int(parts[0], 16), parts[1].upper(), int(parts[2]), parts[3] if len(parts) == 4 else None


def parse_gcell_range(paths: Iterable[Path]) -> Tuple[int, int, Dict[str, int]]:
    base: Optional[int] = None
    max_end = 0
    max_idx = -1
    sizeof_cell = 0
    lines = 0

    for path in paths:
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = GCELL_RE.search(line)
                if not m:
                    continue
                idx_s, base_s, addr_s, _offset_s, size_s = m.groups()
                idx = int(idx_s)
                cur_base = int(base_s, 16)
                addr = int(addr_s, 16)
                size = int(size_s)
                if base is None:
                    base = cur_base
                elif base != cur_base:
                    raise ValueError(f"Conflicting GCELL bases: 0x{base:x} vs 0x{cur_base:x}")
                max_idx = max(max_idx, idx)
                sizeof_cell = size
                max_end = max(max_end, addr + size)
                lines += 1

    if base is None or max_end <= base:
        raise ValueError("No GCELL lines found; cannot recover g_cells range")

    return base, max_end, {
        "gcell_lines": lines,
        "max_idx": max_idx,
        "sizeof_cell": sizeof_cell,
        "virtual_start": base,
        "virtual_end": max_end,
        "virtual_size": max_end - base,
    }


def parse_windows(path: Path, tick_div: int) -> List[Dict[str, int]]:
    begins: Dict[int, int] = {}
    ends: Dict[int, int] = {}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            m = ITER_BEGIN_RE.search(line)
            if m:
                begins[int(m.group(1))] = int(m.group(2)) // tick_div
                continue
            m = ITER_END_RE.search(line)
            if m:
                ends[int(m.group(1))] = int(m.group(2)) // tick_div

    windows: List[Dict[str, int]] = []
    for t in sorted(set(begins) & set(ends)):
        if ends[t] >= begins[t]:
            windows.append({"id": t, "begin": begins[t], "end": ends[t]})
    if not windows:
        raise ValueError(f"No iteration windows found in {path}")
    return windows


def choose_delta(trace: Path, start: int, end: int, explicit_delta: Optional[int]) -> Tuple[int, int]:
    candidates = [0, -0x400000, -0x401000, -0x100000, -start]
    if explicit_delta is not None:
        candidates = [explicit_delta]
    counts = {delta: 0 for delta in candidates if start + delta >= 0 and end + delta > start + delta}

    with trace.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            parsed = parse_trace_line(line)
            if parsed is None:
                continue
            addr = parsed[0]
            for delta in counts:
                if start + delta <= addr < end + delta:
                    counts[delta] += 1

    if not counts:
        raise ValueError("No valid address-translation candidates")
    best_delta = max(counts, key=lambda d: counts[d])
    return best_delta, counts[best_delta]


def advance_window(windows: List[Dict[str, int]], cycle: int, cur: int) -> int:
    while cur < len(windows) and cycle > windows[cur]["end"]:
        cur += 1
    return cur


def format_entry(addr: int, op: str, cycle: int, opt_flag: Optional[str]) -> str:
    out = f"0x{addr:08X} {op} {cycle}"
    if opt_flag is not None:
        out += f" {opt_flag}"
    return out + "\n"


def flush_window(
    out_f,
    temp_path: Path,
    window: Dict[str, int],
    reads: List[Tuple[int, str, Optional[str], int]],
    writes: List[Tuple[int, str, Optional[str], int]],
) -> Dict[str, int]:
    begin = window["begin"]
    reads.sort(key=lambda x: (x[0], x[3]))
    writes.sort(key=lambda x: (x[0], x[3]))

    # Max-optimistic burst: all buffered g_cells requests arrive at the window
    # begin cycle. File order still puts the read phase before the write phase.
    for addr, op, opt_flag, _idx in reads:
        out_f.write(format_entry(addr, op, begin, opt_flag))
    for addr, op, opt_flag, _idx in writes:
        out_f.write(format_entry(addr, op, begin, opt_flag))

    if temp_path.exists():
        with temp_path.open("r", encoding="utf-8", errors="replace") as temp_f:
            shutil.copyfileobj(temp_f, out_f, length=1024 * 1024)
        temp_path.unlink()

    return {
        "id": window["id"],
        "begin_cycle": window["begin"],
        "end_cycle": window["end"],
        "gcell_reads": len(reads),
        "gcell_writes": len(writes),
        "original_span_cycles": window["end"] - window["begin"],
        "buffered_span_cycles": 0,
    }


def rewrite_streaming(
    trace: Path,
    out_trace: Path,
    windows: List[Dict[str, int]],
    gcell_start: int,
    gcell_end: int,
) -> Dict[str, object]:
    out_trace.parent.mkdir(parents=True, exist_ok=True)
    temp_dir = out_trace.parent / ".tmp_windows"
    temp_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    gcell_total = 0
    rewritten = 0
    outside = 0
    cur_win = 0
    active_temp = None
    reads: List[Tuple[int, str, Optional[str], int]] = []
    writes: List[Tuple[int, str, Optional[str], int]] = []
    per_window: List[Dict[str, int]] = []

    with trace.open("r", encoding="utf-8", errors="replace") as in_f, out_trace.open(
        "w", encoding="utf-8"
    ) as out_f:
        for original_index, line in enumerate(in_f):
            parsed = parse_trace_line(line)
            if parsed is None:
                continue
            addr, op, cycle, opt_flag = parsed
            total += 1

            next_win = advance_window(windows, cycle, cur_win)
            while cur_win < next_win and cur_win < len(windows):
                if active_temp is not None:
                    active_temp.close()
                    active_temp = None
                temp_path = temp_dir / f"window_{windows[cur_win]['id']}.trace"
                per_window.append(flush_window(out_f, temp_path, windows[cur_win], reads, writes))
                reads = []
                writes = []
                cur_win += 1

            in_window = cur_win < len(windows) and windows[cur_win]["begin"] <= cycle <= windows[cur_win]["end"]
            is_gcell = gcell_start <= addr < gcell_end
            if is_gcell:
                gcell_total += 1

            if in_window:
                if active_temp is None:
                    active_temp = (temp_dir / f"window_{windows[cur_win]['id']}.trace").open(
                        "w", encoding="utf-8"
                    )
                if is_gcell and op in ("READ", "WRITE"):
                    rewritten += 1
                    (reads if op == "READ" else writes).append((addr, op, opt_flag, original_index))
                else:
                    active_temp.write(line)
                    if is_gcell:
                        outside += 1
            else:
                out_f.write(line)
                if is_gcell:
                    outside += 1

        while cur_win < len(windows):
            if active_temp is not None:
                active_temp.close()
                active_temp = None
            temp_path = temp_dir / f"window_{windows[cur_win]['id']}.trace"
            per_window.append(flush_window(out_f, temp_path, windows[cur_win], reads, writes))
            reads = []
            writes = []
            cur_win += 1

    shutil.rmtree(temp_dir, ignore_errors=True)
    return {
        "input_entries": total,
        "output_entries": total,
        "gcell_entries_total": gcell_total,
        "gcell_entries_rewritten": rewritten,
        "gcell_entries_outside_windows": outside,
        "non_gcell_entries": total - gcell_total,
        "per_window": per_window,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace", required=True, type=Path)
    ap.add_argument("--gcell-log", required=True, type=Path, action="append")
    ap.add_argument("--iter-log", required=True, type=Path)
    ap.add_argument("--out-trace", required=True, type=Path)
    ap.add_argument("--summary-json", required=True, type=Path)
    ap.add_argument("--tick-div", type=int, default=630)
    ap.add_argument("--trace-address-delta", type=parse_int_auto)
    ap.add_argument("--issue-gap", type=int, default=0, help="Accepted for compatibility; streaming mode uses same-cycle bursts.")
    ap.add_argument("--phase-gap", type=int, default=0, help="Accepted for compatibility; streaming mode uses same-cycle bursts.")
    args = ap.parse_args()

    virtual_start, virtual_end, range_meta = parse_gcell_range(args.gcell_log)
    windows = parse_windows(args.iter_log, args.tick_div)
    delta, matched = choose_delta(args.trace, virtual_start, virtual_end, args.trace_address_delta)
    trace_start = virtual_start + delta
    trace_end = virtual_end + delta
    rewrite_summary = rewrite_streaming(args.trace, args.out_trace, windows, trace_start, trace_end)

    summary = {
        "trace": str(args.trace),
        "out_trace": str(args.out_trace),
        "tick_div": args.tick_div,
        "rewrite_model": "same-cycle read phase followed by same-cycle write phase at each iteration begin",
        "gcell_range": {
            **range_meta,
            "chosen_delta": delta,
            "trace_start": trace_start,
            "trace_end": trace_end,
            "candidate_matched_entries": matched,
        },
        "windows": windows,
        **rewrite_summary,
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote rewritten trace: {args.out_trace}", flush=True)
    print(f"Wrote summary: {args.summary_json}", flush=True)
    print(
        "g_cells trace range "
        f"0x{trace_start:x}..0x{trace_end:x}; "
        f"rewrote {rewrite_summary['gcell_entries_rewritten']} requests",
        flush=True,
    )


if __name__ == "__main__":
    main()
