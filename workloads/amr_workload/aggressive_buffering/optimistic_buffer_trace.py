#!/usr/bin/env python3
"""Rewrite an AMR DRAMSim3 trace with optimistic g_cells read/write phasing."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


GCELL_RE = re.compile(
    r"GCELL\s+idx=(\d+)\s+base=(0x[0-9a-fA-F]+)\s+addr=(0x[0-9a-fA-F]+)\s+"
    r"offset=(0x[0-9a-fA-F]+)\s+sizeof_cell=(\d+)"
)
ITER_BEGIN_RE = re.compile(r"ITER_BEGIN\s+t=(\d+)\s+tick=(\d+)")
ITER_END_RE = re.compile(r"ITER_END\s+t=(\d+)\s+tick=(\d+)")


@dataclass
class TraceEntry:
    addr: int
    op: str
    cycle: int
    opt_flag: Optional[str]
    original_index: int


@dataclass
class Window:
    name: str
    begin: int
    end: int


def parse_int_auto(value: str) -> int:
    return int(value, 0)


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

    meta = {
        "gcell_lines": lines,
        "max_idx": max_idx,
        "sizeof_cell": sizeof_cell,
        "virtual_start": base,
        "virtual_end": max_end,
        "virtual_size": max_end - base,
    }
    return base, max_end, meta


def parse_windows(path: Path, tick_div: int) -> List[Window]:
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

    windows: List[Window] = []
    for t in sorted(set(begins) & set(ends)):
        if ends[t] >= begins[t]:
            windows.append(Window(name=f"iter_{t}", begin=begins[t], end=ends[t]))
    if not windows:
        raise ValueError(f"No iteration windows found in {path}")
    return windows


def parse_trace(path: Path) -> List[TraceEntry]:
    entries: List[TraceEntry] = []
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for idx, raw in enumerate(f):
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split()
            if len(parts) not in (3, 4):
                raise ValueError(f"Unsupported trace line {idx + 1}: {line}")
            entries.append(
                TraceEntry(
                    addr=int(parts[0], 16),
                    op=parts[1].upper(),
                    cycle=int(parts[2]),
                    opt_flag=parts[3] if len(parts) == 4 else None,
                    original_index=idx,
                )
            )
    if not entries:
        raise ValueError(f"Trace is empty: {path}")
    return entries


def choose_delta(
    entries: List[TraceEntry], start: int, end: int, explicit_delta: Optional[int]
) -> Tuple[int, int]:
    candidates = [0, -0x400000, -0x401000, -0x100000, -start]
    if explicit_delta is not None:
        candidates = [explicit_delta]

    best_delta = candidates[0]
    best_count = -1
    for delta in candidates:
        lo = start + delta
        hi = end + delta
        if lo < 0 or hi <= lo:
            continue
        count = sum(1 for e in entries if lo <= e.addr < hi)
        if count > best_count:
            best_count = count
            best_delta = delta
    return best_delta, max(best_count, 0)


def window_for_cycle(windows: List[Window], cycle: int) -> Optional[int]:
    # There are only a few AMR windows, so a linear scan keeps the code clear.
    for i, w in enumerate(windows):
        if w.begin <= cycle <= w.end:
            return i
    return None


def emit_entry(e: TraceEntry) -> str:
    base = f"0x{e.addr:08X} {e.op} {e.cycle}"
    if e.opt_flag is not None:
        return f"{base} {e.opt_flag}"
    return base


def assign_dense_cycles(entries: List[TraceEntry], start_cycle: int, issue_gap: int) -> None:
    for i, entry in enumerate(entries):
        entry.cycle = start_cycle + i * issue_gap


def rewrite_trace(
    entries: List[TraceEntry],
    windows: List[Window],
    gcell_start: int,
    gcell_end: int,
    issue_gap: int,
    phase_gap: int,
) -> Tuple[List[TraceEntry], Dict[str, object]]:
    window_buckets = [
        {"reads": [], "writes": [], "other_gcell": []} for _ in windows
    ]
    output: List[TraceEntry] = []
    total_gcell = 0
    outside_gcell = 0

    for e in entries:
        is_gcell = gcell_start <= e.addr < gcell_end
        win_idx = window_for_cycle(windows, e.cycle)
        if is_gcell:
            total_gcell += 1
        if is_gcell and win_idx is not None and e.op in ("READ", "WRITE"):
            key = "reads" if e.op == "READ" else "writes"
            window_buckets[win_idx][key].append(e)
        else:
            if is_gcell:
                outside_gcell += 1
            output.append(e)

    per_window = []
    for i, w in enumerate(windows):
        reads = sorted(window_buckets[i]["reads"], key=lambda e: (e.addr, e.original_index))
        writes = sorted(window_buckets[i]["writes"], key=lambda e: (e.addr, e.original_index))

        read_start = w.begin
        assign_dense_cycles(reads, read_start, issue_gap)
        if reads:
            write_start = reads[-1].cycle + phase_gap + max(issue_gap, 1)
        else:
            write_start = w.begin
        assign_dense_cycles(writes, write_start, issue_gap)

        output.extend(reads)
        output.extend(writes)
        per_window.append(
            {
                "name": w.name,
                "begin_cycle": w.begin,
                "end_cycle": w.end,
                "gcell_reads": len(reads),
                "gcell_writes": len(writes),
                "original_span_cycles": w.end - w.begin,
                "buffered_span_cycles": (
                    max([x.cycle for x in reads + writes], default=w.begin) - w.begin
                ),
            }
        )

    output.sort(key=lambda e: (e.cycle, 0 if e.op == "READ" else 1, e.addr, e.original_index))
    summary = {
        "input_entries": len(entries),
        "output_entries": len(output),
        "gcell_entries_total": total_gcell,
        "gcell_entries_rewritten": total_gcell - outside_gcell,
        "gcell_entries_outside_windows": outside_gcell,
        "non_gcell_entries": len(entries) - total_gcell,
        "per_window": per_window,
    }
    return output, summary


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--trace", required=True, type=Path)
    ap.add_argument("--gcell-log", required=True, type=Path, action="append")
    ap.add_argument("--iter-log", required=True, type=Path)
    ap.add_argument("--out-trace", required=True, type=Path)
    ap.add_argument("--summary-json", required=True, type=Path)
    ap.add_argument("--tick-div", type=int, default=630)
    ap.add_argument("--trace-address-delta", type=parse_int_auto)
    ap.add_argument(
        "--issue-gap",
        type=int,
        default=0,
        help="Cycle gap between requests inside a phase. 0 means same-cycle burst.",
    )
    ap.add_argument("--phase-gap", type=int, default=0)
    args = ap.parse_args()

    entries = parse_trace(args.trace)
    virtual_start, virtual_end, range_meta = parse_gcell_range(args.gcell_log)
    windows = parse_windows(args.iter_log, args.tick_div)
    delta, matched = choose_delta(entries, virtual_start, virtual_end, args.trace_address_delta)
    trace_start = virtual_start + delta
    trace_end = virtual_end + delta

    rewritten, rewrite_summary = rewrite_trace(
        entries=entries,
        windows=windows,
        gcell_start=trace_start,
        gcell_end=trace_end,
        issue_gap=args.issue_gap,
        phase_gap=args.phase_gap,
    )

    args.out_trace.parent.mkdir(parents=True, exist_ok=True)
    with args.out_trace.open("w", encoding="utf-8") as f:
        for e in rewritten:
            f.write(emit_entry(e) + "\n")

    summary = {
        "trace": str(args.trace),
        "out_trace": str(args.out_trace),
        "tick_div": args.tick_div,
        "issue_gap": args.issue_gap,
        "phase_gap": args.phase_gap,
        "gcell_range": {
            **range_meta,
            "chosen_delta": delta,
            "trace_start": trace_start,
            "trace_end": trace_end,
            "candidate_matched_entries": matched,
        },
        "windows": [w.__dict__ for w in windows],
        **rewrite_summary,
    }
    args.summary_json.parent.mkdir(parents=True, exist_ok=True)
    args.summary_json.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"Wrote rewritten trace: {args.out_trace}")
    print(f"Wrote summary: {args.summary_json}")
    print(
        "g_cells trace range "
        f"0x{trace_start:x}..0x{trace_end:x}; "
        f"rewrote {rewrite_summary['gcell_entries_rewritten']} requests"
    )


if __name__ == "__main__":
    main()
