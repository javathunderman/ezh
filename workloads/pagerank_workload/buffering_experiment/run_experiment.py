#!/usr/bin/env python3
"""Run optimistic buffering experiments for the pull PageRank workload."""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple


STATS = {
    "num_cycles": "DRAM cycles",
    "average_bandwidth": "Average bandwidth",
    "average_read_latency": "Average read latency",
    "num_reads_done": "Reads done",
    "num_writes_done": "Writes done",
    "num_read_row_hits": "Read row hits",
    "num_write_row_hits": "Write row hits",
}

REG_RE = re.compile(r"PRREG\s+name=(\S+)\s+base=(0x[0-9a-fA-F]+)\s+end=(0x[0-9a-fA-F]+)\s+bytes=(\d+)")
ITER_BEGIN_RE = re.compile(r"ITER_BEGIN\s+t=(\d+)\s+tick=(\d+)")
ITER_END_RE = re.compile(r"ITER_END\s+t=(\d+)\s+tick=(\d+)")


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def run(cmd: List[str], cwd: Path) -> None:
    print("+ " + " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=str(cwd), check=True)


def parse_trace_line(line: str) -> Optional[Tuple[int, str, int, Optional[str]]]:
    parts = line.strip().split()
    if not parts:
        return None
    if len(parts) not in (3, 4):
        raise ValueError(f"Bad trace line: {line.rstrip()}")
    return int(parts[0], 16), parts[1].upper(), int(parts[2]), parts[3] if len(parts) == 4 else None


def emit(addr: int, op: str, cycle: int, opt_flag: Optional[str]) -> str:
    line = f"0x{addr:08X} {op} {cycle}"
    if opt_flag is not None:
        line += f" {opt_flag}"
    return line + "\n"


def parse_regions(paths: Iterable[Path], delta: int) -> Dict[str, Tuple[int, int]]:
    regions: Dict[str, Tuple[int, int]] = {}
    for path in paths:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8", errors="replace") as f:
            for line in f:
                m = REG_RE.search(line)
                if not m:
                    continue
                name, base_s, end_s, _bytes_s = m.groups()
                regions[name] = (int(base_s, 16) + delta, int(end_s, 16) + delta)
    if not regions:
        raise ValueError("No PRREG region metadata found")
    return regions


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
    windows = []
    for i in sorted(set(begins) & set(ends)):
        windows.append({"id": i, "begin": begins[i], "end": ends[i]})
    if not windows:
        raise ValueError("No PageRank iteration windows found")
    return windows


def in_range(addr: int, ranges: Iterable[Tuple[int, int]]) -> bool:
    return any(lo <= addr < hi for lo, hi in ranges)


def dest_range_for_iter(regions: Dict[str, Tuple[int, int]], iter_id: int) -> Tuple[int, int]:
    return regions["rank_b"] if iter_id % 2 == 0 else regions["rank_a"]


def advance_window(windows: List[Dict[str, int]], cycle: int, cur: int) -> int:
    while cur < len(windows) and cycle > windows[cur]["end"]:
        cur += 1
    return cur


def flush_targeted(
    out_f,
    temp_path: Path,
    window: Dict[str, int],
    reads: List[Tuple[int, str, Optional[str], int]],
    writes: List[Tuple[int, str, Optional[str], int]],
) -> Dict[str, int]:
    reads.sort(key=lambda x: (x[0], x[3]))
    writes.sort(key=lambda x: (x[0], x[3]))
    # Targeted method: only rank-array traffic gets the giant optimistic buffer.
    # CSR/control traffic is copied afterward with original timing.
    for addr, op, opt_flag, _idx in reads:
        out_f.write(emit(addr, op, window["begin"], opt_flag))
    for addr, op, opt_flag, _idx in writes:
        out_f.write(emit(addr, op, window["begin"], opt_flag))
    if temp_path.exists():
        with temp_path.open("r", encoding="utf-8", errors="replace") as temp_f:
            shutil.copyfileobj(temp_f, out_f, length=1024 * 1024)
        temp_path.unlink()
    return {
        "id": window["id"],
        "targeted_rank_reads": len(reads),
        "targeted_output_writes": len(writes),
        "begin": window["begin"],
        "end": window["end"],
    }


def rewrite_targeted(trace: Path, out_trace: Path, regions: Dict[str, Tuple[int, int]], windows: List[Dict[str, int]]) -> Dict[str, object]:
    out_trace.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_trace.parent / ".tmp_targeted"
    tmp.mkdir(parents=True, exist_ok=True)

    cur = 0
    temp_f = None
    reads: List[Tuple[int, str, Optional[str], int]] = []
    writes: List[Tuple[int, str, Optional[str], int]] = []
    per_window = []
    total = 0
    rewritten = 0
    rank_ranges = [regions["rank_a"], regions["rank_b"]]

    with trace.open("r", encoding="utf-8", errors="replace") as in_f, out_trace.open("w", encoding="utf-8") as out_f:
        for idx, line in enumerate(in_f):
            parsed = parse_trace_line(line)
            if parsed is None:
                continue
            addr, op, cycle, opt_flag = parsed
            total += 1
            nxt = advance_window(windows, cycle, cur)
            while cur < nxt and cur < len(windows):
                if temp_f is not None:
                    temp_f.close()
                    temp_f = None
                per_window.append(flush_targeted(out_f, tmp / f"w{cur}.trace", windows[cur], reads, writes))
                reads = []
                writes = []
                cur += 1

            in_win = cur < len(windows) and windows[cur]["begin"] <= cycle <= windows[cur]["end"]
            if in_win:
                if temp_f is None:
                    temp_f = (tmp / f"w{cur}.trace").open("w", encoding="utf-8")
                dest = dest_range_for_iter(regions, windows[cur]["id"])
                if op == "READ" and in_range(addr, rank_ranges):
                    reads.append((addr, op, opt_flag, idx))
                    rewritten += 1
                elif op == "WRITE" and dest[0] <= addr < dest[1]:
                    writes.append((addr, op, opt_flag, idx))
                    rewritten += 1
                else:
                    temp_f.write(line)
            else:
                out_f.write(line)

        while cur < len(windows):
            if temp_f is not None:
                temp_f.close()
                temp_f = None
            per_window.append(flush_targeted(out_f, tmp / f"w{cur}.trace", windows[cur], reads, writes))
            reads = []
            writes = []
            cur += 1

    shutil.rmtree(tmp, ignore_errors=True)
    return {"input_entries": total, "targeted_rank_entries": rewritten, "per_window": per_window}


def flush_blind(out_f, reads: List[Tuple[int, str, Optional[str], int]], writes: List[Tuple[int, str, Optional[str], int]], window: Dict[str, int], issue_gap: int = 0) -> Dict[str, int]:
    reads.sort(key=lambda x: (x[0], x[3]))
    writes.sort(key=lambda x: (x[0], x[3]))
    # Blind giant queues: every request, including control-flow memory, is
    # absorbed and reissued as a sorted read phase then sorted write phase.
    cycle = window["begin"]
    for addr, op, opt_flag, _idx in reads:
        out_f.write(emit(addr, op, cycle, opt_flag))
        cycle += issue_gap
    for addr, op, opt_flag, _idx in writes:
        out_f.write(emit(addr, op, cycle, opt_flag))
        cycle += issue_gap
    return {"id": window["id"], "reads": len(reads), "writes": len(writes), "issue_gap": issue_gap, "drain_end": cycle}


def rewrite_blind(trace: Path, out_trace: Path, windows: List[Dict[str, int]], issue_gap: int = 0) -> Dict[str, object]:
    out_trace.parent.mkdir(parents=True, exist_ok=True)
    cur = 0
    reads: List[Tuple[int, str, Optional[str], int]] = []
    writes: List[Tuple[int, str, Optional[str], int]] = []
    per_window = []
    total = 0
    buffered = 0

    with trace.open("r", encoding="utf-8", errors="replace") as in_f, out_trace.open("w", encoding="utf-8") as out_f:
        for idx, line in enumerate(in_f):
            parsed = parse_trace_line(line)
            if parsed is None:
                continue
            addr, op, cycle, opt_flag = parsed
            total += 1
            nxt = advance_window(windows, cycle, cur)
            while cur < nxt and cur < len(windows):
                per_window.append(flush_blind(out_f, reads, writes, windows[cur], issue_gap))
                reads = []
                writes = []
                cur += 1

            in_win = cur < len(windows) and windows[cur]["begin"] <= cycle <= windows[cur]["end"]
            if in_win and op in ("READ", "WRITE"):
                (reads if op == "READ" else writes).append((addr, op, opt_flag, idx))
                buffered += 1
            else:
                out_f.write(line)

        while cur < len(windows):
            per_window.append(flush_blind(out_f, reads, writes, windows[cur], issue_gap))
            reads = []
            writes = []
            cur += 1

    return {"input_entries": total, "blind_buffered_entries": buffered, "issue_gap": issue_gap, "per_window": per_window}


def make_region_only_traces(
    trace: Path,
    out_original: Path,
    out_targeted: Path,
    out_blind: Path,
    regions: Dict[str, Tuple[int, int]],
    windows: List[Dict[str, int]],
) -> Dict[str, object]:
    rank_ranges = [regions["rank_a"], regions["rank_b"]]
    entries: List[Tuple[int, str, int, Optional[str], int]] = []
    with trace.open("r", encoding="utf-8", errors="replace") as f:
        for idx, line in enumerate(f):
            parsed = parse_trace_line(line)
            if parsed is None:
                continue
            addr, op, cycle, opt_flag = parsed
            if in_range(addr, rank_ranges):
                entries.append((addr, op, cycle, opt_flag, idx))

    first = entries[0][2] if entries else 0
    out_original.parent.mkdir(parents=True, exist_ok=True)
    with out_original.open("w", encoding="utf-8") as f:
        for addr, op, cycle, opt_flag, _idx in entries:
            f.write(emit(addr, op, cycle - first, opt_flag))

    with out_targeted.open("w", encoding="utf-8") as f:
        reads = sorted([e for e in entries if e[1] == "READ"], key=lambda x: (x[0], x[4]))
        writes = sorted([e for e in entries if e[1] == "WRITE"], key=lambda x: (x[0], x[4]))
        for addr, op, _cycle, opt_flag, _idx in reads:
            f.write(emit(addr, op, 0, opt_flag))
        for addr, op, _cycle, opt_flag, _idx in writes:
            f.write(emit(addr, op, 0, opt_flag))

    reads = sorted([e for e in entries if e[1] == "READ"], key=lambda x: (x[0], x[4]))
    writes = sorted([e for e in entries if e[1] == "WRITE"], key=lambda x: (x[0], x[4]))
    with out_blind.open("w", encoding="utf-8") as f:
        for addr, op, _cycle, opt_flag, _idx in reads:
            f.write(emit(addr, op, 0, opt_flag))
        for addr, op, _cycle, opt_flag, _idx in writes:
            f.write(emit(addr, op, 0, opt_flag))

    return {
        "rank_entries": len(entries),
        "rank_reads": sum(1 for e in entries if e[1] == "READ"),
        "rank_writes": sum(1 for e in entries if e[1] == "WRITE"),
        "original_span": entries[-1][2] - first if entries else 0,
    }


def final_cycle(trace: Path) -> int:
    max_cycle = -1
    line_count = 0
    with trace.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                line_count += 1
                parsed = parse_trace_line(line)
                if parsed is not None:
                    max_cycle = max(max_cycle, parsed[2])
    if max_cycle < 0:
        raise ValueError(f"Empty trace: {trace}")
    return max(max_cycle, line_count * 4 if max_cycle == 0 else max_cycle)


def run_dramsim(dramsim: Path, config: Path, trace: Path, outdir: Path) -> None:
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    run([str(dramsim), str(config), "-c", str(final_cycle(trace)), "-t", str(trace), "-o", str(outdir)], dramsim.parent)


def parse_dramsim_txt(path: Path) -> Dict[str, float]:
    out: Dict[str, float] = {}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "=" not in line:
                continue
            key = line.split("=", 1)[0].strip()
            val = line.split("=", 1)[1].split("#", 1)[0].strip()
            if key in STATS:
                try:
                    out[key] = float(val)
                except ValueError:
                    pass
    return out


def plot_group(results: Dict[str, Dict[str, float]], outdir: Path, prefix: str, title: str) -> None:
    import matplotlib.pyplot as plt

    outdir.mkdir(parents=True, exist_ok=True)
    labels = list(results.keys())
    stats = [s for s in STATS if all(s in results[label] for label in labels)]
    width = 0.8 / max(len(labels), 1)

    for selected, suffix, ylabel in [
        (["num_cycles"], "cycles", "DRAMSim3 cycles"),
        ([s for s in stats if s != "num_cycles"], "other_stats", "Raw DRAMSim3 value"),
    ]:
        x = range(len(selected))
        fig, ax = plt.subplots(figsize=(12, 6) if len(selected) > 1 else (7, 5))
        for i, label in enumerate(labels):
            vals = [results[label].get(s, 0.0) for s in selected]
            offset = (i - (len(labels) - 1) / 2) * width
            ax.bar([p + offset for p in x], vals, width=width, label=label)
        ax.set_xticks(list(x))
        ax.set_xticklabels([STATS[s] for s in selected], rotation=25 if len(selected) > 1 else 0, ha="right" if len(selected) > 1 else "center")
        ax.set_ylabel(ylabel)
        ax.set_title(f"{title}: {suffix.replace('_', ' ')}")
        ax.legend()
        ax.grid(axis="y", alpha=0.25)
        fig.tight_layout()
        png = outdir / f"{prefix}_{suffix}.png"
        fig.savefig(png, dpi=180)
        plt.close(fig)
        print(f"Wrote plot: {png}", flush=True)

    (outdir / f"{prefix}_stats.json").write_text(json.dumps(results, indent=2), encoding="utf-8")


def plot_buffer_scope(summary: Dict[str, object], outdir: Path) -> None:
    import matplotlib.pyplot as plt

    targeted = int(summary["targeted"]["targeted_rank_entries"])
    blind = int(summary["blind_costly"]["blind_buffered_entries"])
    labels = ["targeted rank arrays", "blind all memory"]
    vals = [targeted, blind]

    fig, ax = plt.subplots(figsize=(8, 5))
    ax.bar(labels, vals)
    ax.set_ylabel("Trace requests captured by huge buffer")
    ax.set_title("PageRank Buffer Scope: Targeted vs Blind")
    ax.grid(axis="y", alpha=0.25)
    for i, v in enumerate(vals):
        ax.text(i, v, f"{v:,}", ha="center", va="bottom", fontsize=9)
    fig.tight_layout()
    png = outdir / "buffer_scope_targeted_vs_blind.png"
    fig.savefig(png, dpi=180)
    plt.close(fig)
    print(f"Wrote plot: {png}", flush=True)


def write_explanation(path: Path, summary: Dict[str, object], whole: Dict[str, Dict[str, float]], rank: Dict[str, Dict[str, float]]) -> None:
    def ratio(a: float, b: float) -> float:
        return a / b if b else 0.0

    base_rank = rank["rank_original"]
    targeted_rank = rank["rank_targeted"]
    blind_rank = rank["rank_blind"]
    text = f"""Pull PageRank buffering experiment explanation
==============================================

This workload is a pull-style, double-buffered PageRank. Each iteration scans
all vertices, reads graph-control arrays such as row_ptr/col_idx/out_deg, reads
the old rank buffer, and writes each element of the next rank buffer once. The
next rank buffer is not read until the following iteration, which is the exact
condition this buffering idea wants.

The targeted method is intentionally optimistic but selective: it buffers only
rank-array traffic, namely old-rank reads and the current iteration's
write-once next-rank stores. It does not put row_ptr, col_idx, or out_deg into
the huge buffer, so graph traversal/control-flow memory keeps its original
timing. The blind method is more like conceptually making the whole memory
system's read/write queues enormous: it captures every in-iteration READ and
WRITE, including row_ptr/col_idx/out_deg traffic, and reissues sorted reads
followed by sorted writes. That can look good in a trace, but it is much less
plausible because control-flow loads would be stuck behind the same giant
queueing/reordering mechanism.

For the isolated rank-buffer stream, the original trace used
{base_rank.get('num_cycles', 0):.0f} DRAMSim3 cycles. The targeted method used
{targeted_rank.get('num_cycles', 0):.0f} cycles, a
{ratio(base_rank.get('num_cycles', 0), targeted_rank.get('num_cycles', 0)):.2f}x
cycle reduction. The blind method used {blind_rank.get('num_cycles', 0):.0f}
cycles, a {ratio(base_rank.get('num_cycles', 0), blind_rank.get('num_cycles', 0)):.2f}x
cycle reduction. Bandwidth moved from {base_rank.get('average_bandwidth', 0):.4f}
to {targeted_rank.get('average_bandwidth', 0):.4f} for targeted and
{blind_rank.get('average_bandwidth', 0):.4f} for blind.

The whole-trace plots should be read more cautiously. Targeted buffering is the
more architecture-motivated comparison because it leaves graph traversal/control
traffic alone. Blind buffering is included as a contrast point: it approximates
what happens if huge queues indiscriminately absorb everything, which can
improve synthetic DRAM scheduling while being expensive or illegal for real
control-flow-dependent execution. The buffer-scope plot shows this difference
directly: targeted buffering captures {int(summary["targeted"]["targeted_rank_entries"]):,}
rank-array requests, while blind buffering captures
{int(summary["blind_costly"]["blind_buffered_entries"]):,} requests across rank,
adjacency, control, and other in-window traffic.

Summary metadata:
{json.dumps(summary, indent=2)}
"""
    path.write_text(text, encoding="utf-8")


def main() -> None:
    root = repo_root()
    workload = root / "workloads" / "pagerank_workload"
    outdir = workload / "buffering_experiment" / "results"
    trace = workload / "pagerank_pull_dramsim3.trace"
    log = workload / "pagerank_pull_log.txt"
    stdout = workload / "m5out_pagerank_pull" / "workload.stdout"
    dramsim = root / "DRAMsim3" / "build" / "dramsim3main"
    config = root / "DRAMsim3" / "configs" / "DDR4_8Gb_x8_1866.ini"

    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-toolchain", action="store_true")
    ap.add_argument("--skip-dramsim", action="store_true")
    ap.add_argument("--tick-div", type=int, default=630)
    args = ap.parse_args()

    if not args.skip_toolchain or not trace.exists():
        run(["bash", str(workload / "run_pagerank_toolchain.sh")], root)

    regions = parse_regions([log, stdout], -0x400000)
    windows = parse_windows(log, args.tick_div)
    traces = outdir / "traces"
    plots = outdir / "plots"
    targeted_trace = traces / "pagerank_targeted_rank_write_buffer.trace"
    blind_trace = traces / "pagerank_blind_all_buffer.trace"
    blind_costly_trace = traces / "pagerank_blind_all_buffer_costly.trace"
    rank_original = traces / "pagerank_rank_only_original.trace"
    rank_targeted = traces / "pagerank_rank_only_targeted.trace"
    rank_blind = traces / "pagerank_rank_only_blind.trace"

    targeted_summary = rewrite_targeted(trace, targeted_trace, regions, windows)
    blind_summary = rewrite_blind(trace, blind_trace, windows, issue_gap=0)
    blind_costly_summary = rewrite_blind(trace, blind_costly_trace, windows, issue_gap=1)
    rank_summary = make_region_only_traces(trace, rank_original, rank_targeted, rank_blind, regions, windows)
    summary = {
        "regions": regions,
        "windows": windows,
        "targeted": targeted_summary,
        "blind_unrealistic_free": blind_summary,
        "blind_costly": blind_costly_summary,
        "rank_only": rank_summary,
    }
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "experiment_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")

    dramsim_out = outdir / "dramsim"
    if not args.skip_dramsim:
        for name, tr in [
            ("baseline", trace),
            ("targeted", targeted_trace),
            ("blind_unrealistic_free", blind_trace),
            ("blind_costly", blind_costly_trace),
            ("rank_original", rank_original),
            ("rank_targeted", rank_targeted),
            ("rank_blind", rank_blind),
        ]:
            run_dramsim(dramsim, config, tr, dramsim_out / name)

    whole_results = {
        "baseline": parse_dramsim_txt(dramsim_out / "baseline" / "dramsim3.txt"),
        "targeted_rank_writes": parse_dramsim_txt(dramsim_out / "targeted" / "dramsim3.txt"),
        "blind_free_all_memory": parse_dramsim_txt(dramsim_out / "blind_unrealistic_free" / "dramsim3.txt"),
        "blind_costly_all_memory": parse_dramsim_txt(dramsim_out / "blind_costly" / "dramsim3.txt"),
    }
    rank_results = {
        "rank_original": parse_dramsim_txt(dramsim_out / "rank_original" / "dramsim3.txt"),
        "rank_targeted": parse_dramsim_txt(dramsim_out / "rank_targeted" / "dramsim3.txt"),
        "rank_blind": parse_dramsim_txt(dramsim_out / "rank_blind" / "dramsim3.txt"),
    }
    plot_group(whole_results, plots, "whole_trace_baseline_vs_targeted_vs_blind", "Whole PageRank Trace")
    plot_group(rank_results, plots, "rank_only_original_vs_targeted_vs_blind", "Rank Buffers Only")
    plot_buffer_scope(summary, plots)
    write_explanation(outdir / "algo_explain.txt", summary, whole_results, rank_results)
    print(f"Wrote explanation: {outdir / 'algo_explain.txt'}", flush=True)


if __name__ == "__main__":
    main()
