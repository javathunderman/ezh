#!/usr/bin/env python3
"""
rewrite_dramsim3_bankshift.py

Initial oracle-style trace rewriter for per-iteration DRAMSim3 traces.

What it does
------------
- Reads a directory of per-iteration DRAMSim3 traces.
- For each adjacent pair of iterations (0,1), (1,2), ...
- If iteration i is in iterSet, then:
    * writes in iteration i-1 are rewritten
    * reads  in iteration i   are rewritten
- The rewrite applies a "bank bit shift" that moves a chosen bank-bit field
  up or down in the address, which effectively changes the stride at which
  those bank bits vary.

Interpretation of bankBitShift
------------------------------
This script assumes:
- There is a bank-bit field of width log2(bank_count)
- That field starts at bit position bank_lsb
- bankBitShift = +d means move that whole bank-bit field upward by d bits
- bankBitShift = -d means move that whole bank-bit field downward by d bits

The bank-bit value itself is preserved; only its location in the address changes.
All other non-overlapping bits are preserved.

Example:
    old field at bits [10:8], bankBitShift = +2
    -> new field goes to bits [12:10]

This is a simple first-pass approximation. It does NOT yet enforce:
- one-to-one write/read matching
- isolated-region allocation
- collision avoidance between rewritten addresses
- row-hit-aware packing

Input trace format
------------------
Each line must look like:
    0x000021F0 READ 3185572
or
    0x00035DF4 WRITE 3185572

Output
------
Writes a new directory containing rewritten per-iteration traces in the same format.

Usage example
-------------
python3 rewrite_dramsim3_bankshift.py \
    --indir dramsim3_tracechunks \
    --outdir dramsim3_tracechunks_shifted \
    --bank-count 16 \
    --bank-lsb 8 \
    --bank-bit-shift 2 \
    --iter-set 1,3,4

Meaning:
- bank_count = 16 -> bank width = 4 bits
- bank field originally starts at bit 8
- shift it up by 2 bits
- apply to pairs ending at iterations 1, 3, 4:
    * iter 1 -> rewrite writes in 0 and reads in 1
    * iter 3 -> rewrite writes in 2 and reads in 3
    * iter 4 -> rewrite writes in 3 and reads in 4

Notes
-----
- If an iteration belongs to multiple affected pairs, the rewrite is applied once.
- If shifting would make the destination bank-bit range overlap the source range
  in an invalid way, that's okay: this implementation extracts the bank field
  first and then reconstructs the address cleanly.
- If the shifted bank field would go below bit 0, the script errors out.
"""

from __future__ import annotations

import argparse
import math
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


TRACE_RE = re.compile(r"^\s*(0x[0-9a-fA-F]+)\s+(READ|WRITE)\s+(\d+)\s*$")


@dataclass
class TraceEntry:
    addr: int
    op: str
    cycle: int
    raw_line: str


def parse_trace_line(line: str) -> Optional[TraceEntry]:
    m = TRACE_RE.match(line)
    if not m:
        return None
    addr_s, op, cycle_s = m.groups()
    return TraceEntry(
        addr=int(addr_s, 16),
        op=op,
        cycle=int(cycle_s),
        raw_line=line.rstrip("\n"),
    )


def format_trace_entry(e: TraceEntry) -> str:
    return f"0x{e.addr:08X} {e.op} {e.cycle}"


def natural_sort_key(p: Path):
    parts = re.split(r"(\d+)", p.name)
    out = []
    for x in parts:
        if x.isdigit():
            out.append(int(x))
        else:
            out.append(x.lower())
    return out


def load_trace_file(path: Path) -> List[TraceEntry]:
    entries: List[TraceEntry] = []
    with path.open("r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            entry = parse_trace_line(line)
            if entry is None:
                raise ValueError(
                    f"Failed to parse line {lineno} in {path}: {line.rstrip()}"
                )
            entries.append(entry)
    return entries


def write_trace_file(path: Path, entries: List[TraceEntry]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(format_trace_entry(e) + "\n")


def move_bitfield(addr: int, src_lsb: int, width: int, shift: int) -> int:
    """
    Move a contiguous bitfield [src_lsb + width - 1 : src_lsb]
    to [dst_lsb + width - 1 : dst_lsb], preserving its value.

    All bits outside the source and destination fields are preserved.
    If src and dst overlap, reconstruction still works because we:
      1. extract field value from original address
      2. clear both source and destination ranges
      3. insert field into destination
    """
    if width <= 0:
        return addr

    dst_lsb = src_lsb + shift
    if dst_lsb < 0:
        raise ValueError(
            f"Invalid bankBitShift={shift}: destination field would start below bit 0 "
            f"(src_lsb={src_lsb}, width={width}, dst_lsb={dst_lsb})"
        )

    field_mask = (1 << width) - 1
    src_mask = field_mask << src_lsb
    dst_mask = field_mask << dst_lsb

    field_val = (addr >> src_lsb) & field_mask

    # Clear both source and destination regions.
    cleared = addr & ~src_mask & ~dst_mask

    # Insert field at destination.
    rewritten = cleared | (field_val << dst_lsb)
    return rewritten


def rewrite_entries(
    entries: List[TraceEntry],
    apply_to_op: str,
    bank_lsb: int,
    bank_width: int,
    bank_bit_shift: int,
) -> List[TraceEntry]:
    out: List[TraceEntry] = []
    for e in entries:
        if e.op == apply_to_op:
            new_addr = move_bitfield(
                addr=e.addr,
                src_lsb=bank_lsb,
                width=bank_width,
                shift=bank_bit_shift,
            )
            out.append(TraceEntry(addr=new_addr, op=e.op, cycle=e.cycle, raw_line=e.raw_line))
        else:
            out.append(e)
    return out


def parse_iter_set(iter_set_str: str) -> Set[int]:
    if not iter_set_str.strip():
        return set()
    vals = set()
    for part in iter_set_str.split(","):
        p = part.strip()
        if not p:
            continue
        vals.add(int(p))
    return vals


def collect_trace_files(indir: Path) -> List[Path]:
    files = [p for p in indir.iterdir() if p.is_file()]
    files.sort(key=natural_sort_key)
    return files


def build_pair_application_maps(
    n_iters: int, iter_set: Set[int]
) -> Tuple[Dict[int, Set[str]], List[Tuple[int, int]]]:
    """
    Returns:
      apply_map[it] = set of ops to rewrite in iteration file it
                      {'READ'} and/or {'WRITE'}
      affected_pairs = list of adjacent pairs (i-1, i) for i in iter_set
    """
    apply_map: Dict[int, Set[str]] = {i: set() for i in range(n_iters)}
    affected_pairs: List[Tuple[int, int]] = []

    for i in sorted(iter_set):
        if i <= 0 or i >= n_iters:
            continue
        prev_it = i - 1
        cur_it = i
        affected_pairs.append((prev_it, cur_it))
        apply_map[prev_it].add("WRITE")
        apply_map[cur_it].add("READ")

    return apply_map, affected_pairs


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--indir", required=True, help="Directory containing per-iteration DRAMSim3 traces")
    ap.add_argument("--outdir", required=True, help="Directory to write rewritten traces")
    ap.add_argument("--bank-count", type=int, required=True, help="Number of banks (must be power of 2)")
    ap.add_argument("--bank-lsb", type=int, required=True, help="LSB of the current bank-bit field")
    ap.add_argument("--bank-bit-shift", type=int, required=True, help="Signed shift amount for bank bit field")
    ap.add_argument(
        "--iter-set",
        required=True,
        help="Comma-separated list of iterations i to affect, meaning rewrite WRITEs in i-1 and READs in i",
    )
    ap.add_argument(
        "--clobber",
        action="store_true",
        help="Delete outdir first if it already exists",
    )
    args = ap.parse_args()

    indir = Path(args.indir)
    outdir = Path(args.outdir)

    if not indir.exists() or not indir.is_dir():
        raise SystemExit(f"--indir is not a directory: {indir}")

    bank_count = args.bank_count
    if bank_count <= 0 or (bank_count & (bank_count - 1)) != 0:
        raise SystemExit(f"--bank-count must be a positive power of 2, got {bank_count}")

    bank_width = int(math.log2(bank_count))
    bank_lsb = args.bank_lsb
    bank_bit_shift = args.bank_bit_shift
    iter_set = parse_iter_set(args.iter_set)

    trace_files = collect_trace_files(indir)
    if not trace_files:
        raise SystemExit(f"No files found in {indir}")

    if outdir.exists():
        if args.clobber:
            shutil.rmtree(outdir)
        else:
            raise SystemExit(
                f"--outdir already exists: {outdir}\n"
                f"Use --clobber to remove it first."
            )
    outdir.mkdir(parents=True, exist_ok=True)

    apply_map, affected_pairs = build_pair_application_maps(len(trace_files), iter_set)

    print("Discovered iteration files:")
    for idx, f in enumerate(trace_files):
        print(f"  iter {idx}: {f.name}")

    print("\nAffected pairs:")
    if not affected_pairs:
        print("  (none)")
    else:
        for a, b in affected_pairs:
            print(f"  ({a}, {b})")

    print("\nPer-iteration rewrite plan:")
    for i in range(len(trace_files)):
        ops = apply_map[i]
        if ops:
            print(f"  iter {i}: rewrite {sorted(ops)}")
        else:
            print(f"  iter {i}: unchanged")

    for i, infile in enumerate(trace_files):
        entries = load_trace_file(infile)
        ops = apply_map[i]

        rewritten = entries
        if "WRITE" in ops:
            rewritten = rewrite_entries(
                rewritten,
                apply_to_op="WRITE",
                bank_lsb=bank_lsb,
                bank_width=bank_width,
                bank_bit_shift=bank_bit_shift,
            )
        if "READ" in ops:
            rewritten = rewrite_entries(
                rewritten,
                apply_to_op="READ",
                bank_lsb=bank_lsb,
                bank_width=bank_width,
                bank_bit_shift=bank_bit_shift,
            )

        outfile = outdir / infile.name
        write_trace_file(outfile, rewritten)

    print(f"\nWrote rewritten traces to: {outdir}")


if __name__ == "__main__":
    main()