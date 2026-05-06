#!/usr/bin/env python3

import os
import re
import argparse
from pathlib import Path
from typing import Optional, Dict, List, Tuple

import matplotlib.pyplot as plt
import numpy as np

# Format:
#   "Display Label": {
#       "key":    "stat_key_in_file",   # required
#       "ylabel": "Y-axis label",       # optional, defaults to key
#       "ranked": True/False,           # optional, default True
#                                       #   True  → collect .0 and .1 variants
#                                       #   False → collect the bare key only
#   }
#
# Examples from the DRAMSim3 output:
#   ranked=True  → all_bank_idle_cycles.0 / all_bank_idle_cycles.1
#   ranked=False → average_read_latency, average_bandwidth, num_reads_done

STATS_CONFIG = {
    "All Bank Idle Cycles": {
        "key":    "all_bank_idle_cycles",
        "ylabel": "Idle Cycles",
        "ranked": True,
    },
    "Rank Active Cycles": {
        "key":    "rank_active_cycles",
        "ylabel": "Active Cycles",
        "ranked": True,
    },
    "Average Read Latency": {
        "key":    "average_read_latency",
        "ylabel": "Latency (cycles)",
        "ranked": False,
    },
    "Average Bandwidth": {
        "key":    "average_bandwidth",
        "ylabel": "Bandwidth",
        "ranked": False,
    },
    "Reads Done": {
        "key":    "num_reads_done",
        "ylabel": "Read Requests",
        "ranked": False,
    },
    "Read Row Hits": {
        "key":    "num_read_row_hits",
        "ylabel": "Row Buffer Hits",
        "ranked": False,
    },
    # ---- add more stats below as needed ----
    # "Total Energy": {
    #     "key":    "total_energy",
    #     "ylabel": "Energy (pJ)",
    #     "ranked": False,
    # },
    # "Average Power": {
    #     "key":    "average_power",
    #     "ylabel": "Power (mW)",
    #     "ranked": False,
    # },
}

BITSHIFT_RE = re.compile(r"dramsim_results_bitshift_(\d+)")
ITERDIR_RE = re.compile(r"dramsim_results_(\d+)")

def _make_stat_pattern(key: str, rank: Optional[int]) -> re.Pattern:
    """
    Build a compiled regex for a stat line.
 
    For ranked stats (rank=0 or rank=1):
        all_bank_idle_cycles.0   =   275159
    For unranked stats (rank=None):
        average_read_latency     =   312.823
    """
    if rank is not None:
        escaped = re.escape(f"{key}.{rank}")
    else:
        escaped = re.escape(key)
    return re.compile(rf"^\s*{escaped}\s*=\s*([0-9eE+\-.]+)")


def _build_patterns(config: dict) -> dict:
    """
    Pre-compile all regex patterns from STATS_CONFIG.
 
    Returns:
        {
          label: {
              "ranked": bool,
              "patterns": {
                  0: re.Pattern,   # for ranked=True
                  1: re.Pattern,
                  # -or-
                  None: re.Pattern # for ranked=False
              }
          }
        }
    """
    built = {}
    for label, cfg in config.items():
        key     = cfg["key"]
        ranked  = cfg.get("ranked", True)
    
        if ranked:
            patterns = {
                0: _make_stat_pattern(key, 0),
                1: _make_stat_pattern(key, 1),
            }
        else:
            patterns = {None: _make_stat_pattern(key, None)}
        
        built[label] = {"ranked": ranked, "patterns": patterns}
        
    return built

COMPILED = _build_patterns(STATS_CONFIG)



def extract_iter_x(iter_dir_name: str) -> Optional[int]:
    """Return the first iteration number from a directory name, or None"""
    m = ITERDIR_RE.search(iter_dir_name)
    return int(m.group(1)) if m else None


def parse_stat_file(txt_path: Path) -> dict:
    """
    Parse a single dramsim3.txt file.
 
    Returns a flat dict keyed by (label, rank_or_None) → float value.
    Missing stats are omitted rather than set to None.
    """

    # Build the lookup table
    search_table: list[tuple[re.Pattern, str, int | None]] = []
    
    for label, info in COMPILED.items():
        for rank_key, pat in info["patterns"].items():
            search_table.append((pat, label, rank_key))

    found: dict[tuple[str, int | None], float] = {}
    remaining = set(range(len(search_table)))
 
    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not remaining:
                break
            for idx in list(remaining):
                pat, label, rank_key = search_table[idx]
                m = pat.match(line)
                if m:
                    found[(label, rank_key)] = float(m.group(1))
                    remaining.discard(idx)
 
    return found


def collect_data(main_dir: Path) -> dict:
    """
    Walk the directory tree and collect all configured stats.
 
    Returns:
        {
          bitshift_int: {
              (label, rank_or_None): [(iter_idx, value), ...],
              ...
          }
        }
    """
    
    data: dict[int, dict] = {}
    
    for child in sorted(main_dir.iterdir()):
        if not child.is_dir():
            continue
        m = BITSHIFT_RE.fullmatch(child.name)
        if not m:
            continue
 
        bitshift = int(m.group(1))
        series: dict[tuple, list] = {}
 
        for sub in sorted(child.iterdir()):
            if not sub.is_dir():
                continue
            iter_idx = extract_iter_x(sub.name)
            if iter_idx is None:
                continue
 
            txt_path = sub / "dramsim3.txt"
            if not txt_path.exists():
                print(f"warning: missing {txt_path}")
                continue
 
            parsed = parse_stat_file(txt_path)
            if not parsed:
                print(f"warning: no configured stats found in {txt_path}")
                continue
 
            for (label, rank_key), value in parsed.items():
                series.setdefault((label, rank_key), []).append((iter_idx, value))
 
        # Sort each series by iteration
        for key in series:
            series[key].sort(key=lambda p: p[0])
 
        data[bitshift] = series
 
    return data



def filter_outliers_iqr(xs: list, ys: list) -> Tuple[list, list]:
    """Remove outliers using the 1.5×IQR rule. Returns (xs, ys)."""
    if len(ys) < 4:
        return xs[:], ys[:]
 
    arr = np.array(ys, dtype=float)
    q1  = np.percentile(arr, 25)
    q3  = np.percentile(arr, 75)
    iqr = q3 - q1
 
    if iqr == 0:
        return xs[:], ys[:]
 
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    pairs  = [(x, y) for x, y in zip(xs, ys) if lo <= y <= hi]
    if not pairs:
        return [], []
    
    return [p[0] for p in pairs], [p[1] for p in pairs]


def extract_bank_idle_vals(txt_path: Path):
    bank0 = None
    bank1 = None

    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if bank0 is None:
                m0 = BANK0_RE.search(line)
                if m0:
                    bank0 = int(m0.group(1))

            if bank1 is None:
                m1 = BANK1_RE.search(line)
                if m1:
                    bank1 = int(m1.group(1))

            if bank0 is not None and bank1 is not None:
                break

    return bank0, bank1


def collect_data(main_dir: Path):
    """
    Returns:
      {
        bitshift_value: [
          (iter_idx, bank0_val, bank1_val),
          ...
        ],
        ...
      }
    """
    data = {}

    for child in sorted(main_dir.iterdir()):
        if not child.is_dir():
            continue

        m = BITSHIFT_RE.fullmatch(child.name)
        if not m:
            continue

        bitshift = int(m.group(1))
        series: dict[tuple, list] = {}
 
        for sub in sorted(child.iterdir()):
            if not sub.is_dir():
                continue
            iter_idx = extract_iter_x(sub.name)
            if iter_idx is None:
                continue
 
            txt_path = sub / "dramsim3.txt"
            if not txt_path.exists():
                print(f"warning: missing {txt_path}")
                continue
 
            parsed = parse_stat_file(txt_path)
            if not parsed:
                print(f"warning: no configured stats found in {txt_path}")
                continue
 
            for (label, rank_key), value in parsed.items():
                series.setdefault((label, rank_key), []).append((iter_idx, value))
 
        # Sort each series by iteration
        for key in series:
            series[key].sort(key=lambda p: p[0])
 
        data[bitshift] = series
 
    return data

def filter_outliers_iqr(xs: list, ys: list) -> Tuple[list, list]:
    """Remove outliers using the 1.5×IQR rule. Returns (xs, ys)."""
    if len(ys) < 4:
        return xs[:], ys[:]
 
    arr = np.array(ys, dtype=float)
    q1  = np.percentile(arr, 25)
    q3  = np.percentile(arr, 75)
    iqr = q3 - q1
 
    if iqr == 0:
        return xs[:], ys[:]
 
    lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    pairs  = [(x, y) for x, y in zip(xs, ys) if lo <= y <= hi]
    if not pairs:
        return [], []
    return [p[0] for p in pairs], [p[1] for p in pairs]


def _series_label(label: str, rank_key: Optional[int]) -> str:
    """Human-readable series label for plot legend / dump header."""
    if rank_key is None:
        return label
    return f"{label} rank{rank_key}"

def make_plot(data: dict, label: str, rank_key: Optional[int],
              outdir: Path, filtered: bool,) -> None:
    
    """Produce one PNG for a single (label, rank_key) stat."""
    cfg    = STATS_CONFIG[label]
    ylabel = cfg.get("ylabel", cfg["key"])
    suffix = " (Outliers Removed)" if filtered else ""
    ranked_tag = "" if rank_key is None else f" Rank {rank_key}"
    title  = f"{label}{ranked_tag} vs Iteration{suffix}"
 
    slug       = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")
    rank_str   = "" if rank_key is None else f"_rank{rank_key}"
    filt_str   = "_filtered" if filtered else ""
    filename   = f"{slug}{rank_str}{filt_str}.png"
    dump_name  = f"{slug}{rank_str}{filt_str}_values.txt"
 
    plt.figure(figsize=(10, 6))
    dump_lines: list[str] = [title, "=" * len(title), ""]
 
    for bitshift in sorted(data.keys()):
        series = data[bitshift]
        points = series.get((label, rank_key), [])
 
        if not points:
            dump_lines.append(f"bitshift {bitshift}: no data\n")
            continue
 
        xs = [p[0] for p in points]
        ys = [p[1] for p in points]
        original_n = len(ys)
 
        if filtered:
            xs, ys = filter_outliers_iqr(xs, ys)
 
        dump_lines.append(
            f"bitshift {bitshift}: kept {len(ys)}/{original_n}"
        )
        for x, y in zip(xs, ys):
            dump_lines.append(f"  iter={x}  value={y}")
        dump_lines.append("")
 
        if xs:
            plt.plot(xs, ys, marker="o", label=f"bitshift {bitshift}")
 
    plt.xlabel("Iteration")
    plt.ylabel(ylabel)
    plt.title(title)
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(outdir / filename, dpi=200)
    plt.close()
 
    (outdir / dump_name).write_text("\n".join(dump_lines), encoding="utf-8")
    print(f"  saved: {filename}")


def save_plots(data: dict, outdir: Path) -> None:
    outdir.mkdir(parents=True, exist_ok=True)
 
    for label, info in COMPILED.items():
        print(f"\n[{label}]")
        for rank_key in info["patterns"]:
            for filtered in (False, True):
                make_plot(data, label, rank_key, outdir, filtered)

def main():
    parser = argparse.ArgumentParser(
        description="Plot DRAMSim3 all_bank_idle_cycles.0/.1 vs iteration for each bitshift."
    )
    parser.add_argument(
        "main_dir",
        help="Top-level directory containing dramsim3_bitshift* subdirectories",
    )
    parser.add_argument(
        "--outdir",
        default="bank_idle_plots",
        help="Directory where output figures will be saved",
    )
    args = parser.parse_args()

    main_dir = Path(args.main_dir)
    outdir = Path(args.outdir)

    print(f"Collecting stats from: {main_dir}")
    print(f"Configured stats ({len(STATS_CONFIG)}):")
    for lbl, cfg in STATS_CONFIG.items():
        ranked_str = "ranked (rank0 + rank1)" if cfg.get("ranked", True) else "unranked"
        print(f"  {lbl!r} → key={cfg['key']!r}, {ranked_str}")
 
    data = collect_data(main_dir)
 
    if not data:
        raise SystemExit("error: no matching dramsim_results_bitshift_* directories found")
 
    print(f"\nSaving plots to: {outdir}/")
    save_plots(data, outdir)
    print(f"\nDone. All output in: {outdir}/")
 

if __name__ == "__main__":
    main()