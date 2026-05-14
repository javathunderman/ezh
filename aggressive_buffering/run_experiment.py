#!/usr/bin/env python3
"""Run the optimistic AMR g_cells buffering experiment and plot results."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List


STATS = {
    "num_cycles": "DRAM cycles",
    "average_read_latency": "Average read latency",
    "average_bandwidth": "Average bandwidth",
    "num_reads_done": "Reads done",
    "num_writes_done": "Writes done",
    "num_read_row_hits": "Read row hits",
    "num_write_row_hits": "Write row hits",
}


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[3]


def run(cmd: List[str], cwd: Path) -> None:
    print("+ " + " ".join(cmd))
    subprocess.run(cmd, cwd=str(cwd), check=True)


def parse_dramsim_txt(path: Path) -> Dict[str, float]:
    stats: Dict[str, float] = {}
    with path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if "=" not in line:
                continue
            lhs, rhs = line.split("=", 1)
            key = lhs.strip()
            value_s = rhs.split("#", 1)[0].strip()
            if key in STATS:
                try:
                    stats[key] = float(value_s)
                except ValueError:
                    pass
    return stats


def final_cycle(trace: Path) -> int:
    last = ""
    line_count = 0
    with trace.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if line.strip():
                last = line
                line_count += 1
    if not last:
        raise ValueError(f"Trace is empty: {trace}")
    cycle = int(last.split()[2])
    if cycle <= 0:
        return max(line_count * 4, 1)
    return cycle


def run_dramsim(dramsim: Path, config: Path, trace: Path, outdir: Path) -> None:
    if outdir.exists():
        shutil.rmtree(outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    run(
        [
            str(dramsim),
            str(config),
            "-c",
            str(final_cycle(trace)),
            "-t",
            str(trace),
            "-o",
            str(outdir),
        ],
        cwd=dramsim.parent,
    )


def plot_results(results: Dict[str, Dict[str, float]], out_png: Path, out_json: Path) -> None:
    import matplotlib.pyplot as plt

    labels = list(results.keys())
    stats = [s for s in STATS if all(s in results[label] for label in labels)]
    x = range(len(stats))
    width = 0.8 / max(len(labels), 1)

    fig, axes = plt.subplots(2, 1, figsize=(12, 9))

    for i, label in enumerate(labels):
        vals = [results[label][s] for s in stats]
        offset = (i - (len(labels) - 1) / 2) * width
        axes[0].bar([p + offset for p in x], vals, width=width, label=label)

    axes[0].set_xticks(list(x))
    axes[0].set_xticklabels([STATS[s] for s in stats], rotation=25, ha="right")
    axes[0].set_ylabel("Raw DRAMSim3 value")
    axes[0].set_title("AMR DRAMSim3 Baseline vs Optimistic g_cells Buffering")
    axes[0].legend()
    axes[0].grid(axis="y", alpha=0.25)

    if "baseline" in results:
        baseline = results["baseline"]
        ratio_labels = [label for label in labels if label != "baseline"]
        for i, label in enumerate(ratio_labels):
            ratios = []
            for s in stats:
                base = baseline[s]
                ratios.append(results[label][s] / base if base else 0.0)
            offset = (i - (len(ratio_labels) - 1) / 2) * width
            axes[1].bar([p + offset for p in x], ratios, width=width, label=f"{label}/baseline")
        axes[1].axhline(1.0, color="black", linewidth=1)
        axes[1].set_xticks(list(x))
        axes[1].set_xticklabels([STATS[s] for s in stats], rotation=25, ha="right")
        axes[1].set_ylabel("Ratio")
        axes[1].set_title("Normalized Effect")
        axes[1].legend()
        axes[1].grid(axis="y", alpha=0.25)

    fig.tight_layout()
    out_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_png, dpi=180)
    plt.close(fig)
    out_json.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote plot: {out_png}")
    print(f"Wrote parsed stats: {out_json}")


def plot_gcell_split(results: Dict[str, Dict[str, float]], outdir: Path) -> None:
    import matplotlib.pyplot as plt

    labels = list(results.keys())
    width = 0.8 / max(len(labels), 1)

    cycle_stat = "num_cycles"
    fig, ax = plt.subplots(figsize=(7, 5))
    for i, label in enumerate(labels):
        offset = (i - (len(labels) - 1) / 2) * width
        ax.bar([offset], [results[label][cycle_stat]], width=width, label=label)
    ax.set_xticks([0])
    ax.set_xticklabels([STATS[cycle_stat]])
    ax.set_ylabel("DRAMSim3 cycles")
    ax.set_title("g_cells Only: DRAM Cycles")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    cycle_png = outdir / "gcells_only_dram_cycles.png"
    fig.savefig(cycle_png, dpi=180)
    plt.close(fig)

    other_stats = [s for s in STATS if s != cycle_stat and all(s in results[label] for label in labels)]
    x = range(len(other_stats))
    fig, ax = plt.subplots(figsize=(12, 6))
    for i, label in enumerate(labels):
        vals = [results[label][s] for s in other_stats]
        offset = (i - (len(labels) - 1) / 2) * width
        ax.bar([p + offset for p in x], vals, width=width, label=label)
    ax.set_xticks(list(x))
    ax.set_xticklabels([STATS[s] for s in other_stats], rotation=25, ha="right")
    ax.set_ylabel("Raw DRAMSim3 value")
    ax.set_title("g_cells Only: Non-cycle Stats")
    ax.legend()
    ax.grid(axis="y", alpha=0.25)
    fig.tight_layout()
    other_png = outdir / "gcells_only_other_stats.png"
    fig.savefig(other_png, dpi=180)
    plt.close(fig)

    print(f"Wrote split g_cells cycle plot: {cycle_png}")
    print(f"Wrote split g_cells other-stats plot: {other_png}")


def main() -> None:
    repo = repo_root_from_script()
    default_workload = repo / "workloads" / "amr_workload"
    default_out = default_workload / "aggressive_buffering" / "results"

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workload-dir", type=Path, default=default_workload)
    ap.add_argument("--outdir", type=Path, default=default_out)
    ap.add_argument("--config-name", default="DDR4_8Gb_x8_1866.ini")
    ap.add_argument("--tick-div", type=int, default=630)
    ap.add_argument("--skip-dramsim", action="store_true")
    args = ap.parse_args()

    workload = args.workload_dir
    outdir = args.outdir
    trace = workload / "amr_counts_dramsim3_baseline.trace"
    log = workload / "amr_counts_log_baseline.txt"
    stdout = workload / "m5out_amr_counts_baseline" / "workload.stdout"
    rewritten_trace = outdir / "traces" / "amr_counts_gcells_optimistic.trace"
    rewrite_summary = outdir / "gcells_optimistic_summary.json"
    gcell_original_trace = outdir / "traces" / "amr_counts_gcells_only_original.trace"
    gcell_optimistic_trace = outdir / "traces" / "amr_counts_gcells_only_optimistic.trace"
    gcell_only_summary = outdir / "gcells_only_summary.json"
    dramsim = repo / "DRAMsim3" / "build" / "dramsim3main"
    config = repo / "DRAMsim3" / "configs" / args.config_name

    run(
        [
            "python3",
            str(Path(__file__).resolve().with_name("optimistic_buffer_trace_stream.py")),
            "--trace",
            str(trace),
            "--gcell-log",
            str(log),
            "--gcell-log",
            str(stdout),
            "--iter-log",
            str(log),
            "--out-trace",
            str(rewritten_trace),
            "--summary-json",
            str(rewrite_summary),
            "--tick-div",
            str(args.tick_div),
            "--trace-address-delta=-0x400000",
            "--issue-gap",
            "0",
            "--phase-gap",
            "0",
        ],
        cwd=repo,
    )

    if not dramsim.exists():
        raise SystemExit(f"Missing DRAMSim3 executable: {dramsim}")
    if not config.exists():
        raise SystemExit(f"Missing DRAMSim3 config: {config}")

    run(
        [
            "python3",
            str(Path(__file__).resolve().with_name("gcell_only_traces.py")),
            "--trace",
            str(trace),
            "--gcell-log",
            str(log),
            "--gcell-log",
            str(stdout),
            "--out-original",
            str(gcell_original_trace),
            "--out-optimistic",
            str(gcell_optimistic_trace),
            "--summary-json",
            str(gcell_only_summary),
            "--trace-address-delta=-0x400000",
        ],
        cwd=Path(__file__).resolve().parent,
    )

    baseline_out = outdir / "dramsim" / "baseline"
    optimistic_out = outdir / "dramsim" / "gcells_optimistic"
    gcell_original_out = outdir / "dramsim" / "gcells_only_original"
    gcell_optimistic_out = outdir / "dramsim" / "gcells_only_optimistic"

    if not args.skip_dramsim:
        run_dramsim(dramsim, config, trace, baseline_out)
        run_dramsim(dramsim, config, rewritten_trace, optimistic_out)
        run_dramsim(dramsim, config, gcell_original_trace, gcell_original_out)
        run_dramsim(dramsim, config, gcell_optimistic_trace, gcell_optimistic_out)

    results = {
        "baseline": parse_dramsim_txt(baseline_out / "dramsim3.txt"),
        "gcells_optimistic": parse_dramsim_txt(optimistic_out / "dramsim3.txt"),
    }
    plot_results(
        results,
        outdir / "plots" / "baseline_vs_gcells_optimistic.png",
        outdir / "plots" / "baseline_vs_gcells_optimistic_stats.json",
    )
    gcell_results = {
        "gcell_original": parse_dramsim_txt(gcell_original_out / "dramsim3.txt"),
        "gcell_optimistic": parse_dramsim_txt(gcell_optimistic_out / "dramsim3.txt"),
    }
    plot_results(
        gcell_results,
        outdir / "plots" / "gcells_only_original_vs_optimistic.png",
        outdir / "plots" / "gcells_only_original_vs_optimistic_stats.json",
    )
    plot_gcell_split(gcell_results, outdir / "plots")


if __name__ == "__main__":
    main()
