#!/usr/bin/env python3

import os
import re
import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

BITSHIFT_RE = re.compile(r"dramsim_results_bitshift_(\d+)")
ITERDIR_RE = re.compile(r"dramsim_results_(\d+)")
BANK0_RE = re.compile(r"all_bank_idle_cycles\.0\s*=\s*(\d+)")
BANK1_RE = re.compile(r"all_bank_idle_cycles\.1\s*=\s*(\d+)")


def filter_outliers_iqr(xs, ys):
    """
    Returns filtered (xs, ys) with outliers removed based on IQR.
    """
    if len(ys) < 4:
        return xs, ys  # not enough points to filter

    sorted_ys = sorted(ys)
    q1 = sorted_ys[len(sorted_ys) // 4]
    q3 = sorted_ys[(3 * len(sorted_ys)) // 4]
    iqr = q3 - q1

    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    filtered_xs = []
    filtered_ys = []

    for x, y in zip(xs, ys):
        if lower <= y <= upper:
            filtered_xs.append(x)
            filtered_ys.append(y)

    return filtered_xs, filtered_ys

def extract_iter_x(iter_dir_name: str):
    """
    For names like:
      dramsim_results_iter_0000
      dramsim_results_iter_0000-0016

    use the first iter number as the x-axis point.
    """
    m = ITERDIR_RE.search(iter_dir_name)
    if not m:
        return None
    return int(m.group(1))


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
        data[bitshift] = []

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

            bank0, bank1 = extract_bank_idle_vals(txt_path)
            if bank0 is None or bank1 is None:
                print(f"warning: could not find both bank idle values in {txt_path}")
                continue

            data[bitshift].append((iter_idx, bank0, bank1))

        data[bitshift].sort(key=lambda x: x[0])

    return data


def save_plots(data, outdir: Path):
    outdir.mkdir(parents=True, exist_ok=True)

    def filter_outliers_iqr(xs, ys):
        """
        More stable IQR filter using numpy percentiles.
        Returns filtered (xs, ys).
        """
        if len(ys) < 4:
            return xs[:], ys[:]  # not enough points to filter sensibly

        arr = np.array(ys, dtype=float)
        q1 = np.percentile(arr, 25)
        q3 = np.percentile(arr, 75)
        iqr = q3 - q1

        # If everything is nearly identical, keep all points
        if iqr == 0:
            return xs[:], ys[:]

        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        filtered = [(x, y) for x, y in zip(xs, ys) if lower <= y <= upper]
        if not filtered:
            return [], []

        filtered_xs = [p[0] for p in filtered]
        filtered_ys = [p[1] for p in filtered]
        return filtered_xs, filtered_ys

    def write_series_dump(filepath, title, rank_idx=None, filtered=False, combined=False):
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(title + "\n")
            f.write("=" * len(title) + "\n\n")

            for bitshift in sorted(data.keys()):
                points = data[bitshift]
                if not points:
                    f.write(f"bitshift {bitshift}: no data\n\n")
                    continue

                xs = [p[0] for p in points]
                ys0 = [p[1] for p in points]
                ys1 = [p[2] for p in points]

                if combined:
                    if filtered:
                        xs0, fys0 = filter_outliers_iqr(xs, ys0)
                        xs1, fys1 = filter_outliers_iqr(xs, ys1)
                    else:
                        xs0, fys0 = xs[:], ys0[:]
                        xs1, fys1 = xs[:], ys1[:]

                    f.write(f"bitshift {bitshift} rank0: kept {len(fys0)} / {len(ys0)} points\n")
                    for x, y in zip(xs0, fys0):
                        f.write(f"  iter={x} value={y}\n")
                    f.write("\n")

                    f.write(f"bitshift {bitshift} rank1: kept {len(fys1)} / {len(ys1)} points\n")
                    for x, y in zip(xs1, fys1):
                        f.write(f"  iter={x} value={y}\n")
                    f.write("\n")
                else:
                    ys = ys0 if rank_idx == 0 else ys1
                    if filtered:
                        fxs, fys = filter_outliers_iqr(xs, ys)
                    else:
                        fxs, fys = xs[:], ys[:]

                    f.write(f"bitshift {bitshift}: kept {len(fys)} / {len(ys)} points\n")
                    for x, y in zip(fxs, fys):
                        f.write(f"  iter={x} value={y}\n")
                    f.write("\n")

    def make_plot(rank_idx, title, ylabel, filename, filtered=False, dump_filename=None):
        plt.figure(figsize=(10, 6))

        summary_lines = []

        for bitshift in sorted(data.keys()):
            points = data[bitshift]
            if not points:
                summary_lines.append(f"bitshift {bitshift}: no data")
                continue

            xs = [p[0] for p in points]
            ys = [p[1] if rank_idx == 0 else p[2] for p in points]

            original_n = len(ys)
            if filtered:
                xs, ys = filter_outliers_iqr(xs, ys)

            kept_n = len(ys)
            summary_lines.append(f"bitshift {bitshift}: kept {kept_n}/{original_n}")

            if not xs:
                continue

            plt.plot(xs, ys, marker="o", label=f"bitshift {bitshift}")

        plt.xlabel("Iteration")
        plt.ylabel(ylabel)
        plt.title(title + (" (Outliers Removed)" if filtered else ""))
        plt.legend()
        plt.grid(True)
        plt.tight_layout()
        plt.savefig(outdir / filename, dpi=200)
        plt.close()

        if dump_filename is not None:
            write_series_dump(
                outdir / dump_filename,
                title + (" (Outliers Removed)" if filtered else ""),
                rank_idx=rank_idx,
                filtered=filtered,
                combined=False,
            )

        print(f"{filename}:")
        for line in summary_lines:
            print("  " + line)

    # Rank 0 raw + filtered
    make_plot(
        rank_idx=0,
        title="DRAMSim3 all_bank_idle_cycles.0 vs Iteration",
        ylabel="all_bank_idle_cycles.0",
        filename="rank0.png",
        filtered=False,
        dump_filename="rank0_values.txt",
    )

    make_plot(
        rank_idx=0,
        title="DRAMSim3 all_bank_idle_cycles.0 vs Iteration",
        ylabel="all_bank_idle_cycles.0",
        filename="rank0_filtered.png",
        filtered=True,
        dump_filename="rank0_filtered_values.txt",
    )

    # Rank 1 raw + filtered
    make_plot(
        rank_idx=1,
        title="DRAMSim3 all_bank_idle_cycles.1 vs Iteration",
        ylabel="all_bank_idle_cycles.1",
        filename="rank1.png",
        filtered=False,
        dump_filename="rank1_values.txt",
    )

    make_plot(
        rank_idx=1,
        title="DRAMSim3 all_bank_idle_cycles.1 vs Iteration",
        ylabel="all_bank_idle_cycles.1",
        filename="rank1_filtered.png",
        filtered=True,
        dump_filename="rank1_filtered_values.txt",
    )

    def make_combined(filtered=False):
        plt.figure(figsize=(12, 7))
        summary_lines = []

        for bitshift in sorted(data.keys()):
            points = data[bitshift]
            if not points:
                summary_lines.append(f"bitshift {bitshift}: no data")
                continue

            xs = [p[0] for p in points]
            ys0 = [p[1] for p in points]
            ys1 = [p[2] for p in points]

            original_n0 = len(ys0)
            original_n1 = len(ys1)

            if filtered:
                xs0, ys0 = filter_outliers_iqr(xs, ys0)
                xs1, ys1 = filter_outliers_iqr(xs, ys1)
            else:
                xs0, xs1 = xs[:], xs[:]

            summary_lines.append(
                f"bitshift {bitshift}: rank0 kept {len(ys0)}/{original_n0}, "
                f"rank1 kept {len(ys1)}/{original_n1}"
            )

            if xs0:
                plt.plot(xs0, ys0, marker="o", label=f"bitshift {bitshift} rank0")
            if xs1:
                plt.plot(xs1, ys1, marker="x", label=f"bitshift {bitshift} rank1")

        plt.xlabel("Iteration")
        plt.ylabel("all_bank_idle_cycles")
        plt.title("DRAMSim3 all_bank_idle_cycles vs Iteration" +
                  (" (Outliers Removed)" if filtered else ""))
        plt.legend()
        plt.grid(True)
        plt.tight_layout()

        fname = "combined_filtered.png" if filtered else "combined.png"
        dump_name = "combined_filtered_values.txt" if filtered else "combined_values.txt"

        plt.savefig(outdir / fname, dpi=200)
        plt.close()

        write_series_dump(
            outdir / dump_name,
            "DRAMSim3 all_bank_idle_cycles vs Iteration" +
            (" (Outliers Removed)" if filtered else ""),
            filtered=filtered,
            combined=True,
        )

        print(f"{fname}:")
        for line in summary_lines:
            print("  " + line)

    make_combined(filtered=False)
    make_combined(filtered=True)

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

    if not main_dir.exists() or not main_dir.is_dir():
        raise SystemExit(f"error: main_dir does not exist or is not a directory: {main_dir}")

    data = collect_data(main_dir)

    if not data:
        raise SystemExit("error: no matching dramsim3_bitshift* directories found")

    save_plots(data, outdir)
    print(f"saved plots to: {outdir}")


if __name__ == "__main__":
    main()