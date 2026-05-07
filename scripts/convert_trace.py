#!/usr/bin/env python3
import argparse
import math
import sys


def parse_args():
    p = argparse.ArgumentParser(
        description=(
            "Convert decoded gem5 packet trace CSV into DRAMSim3 cycle-based trace, "
            "and report long consecutive runs to the same address."
        )
    )
    p.add_argument("input", help="Input decoded trace file")
    p.add_argument("output", help="Output DRAMSim3 trace file")
    p.add_argument(
        "--tick-ps",
        type=float,
        default=1.0,
        help="Length of one gem5 tick in picoseconds (default: 1.0)",
    )
    p.add_argument(
        "--tck-ps",
        type=float,
        required=True,
        help="DRAM clock period in picoseconds; cycles = floor((tick * tick_ps) / tck_ps)",
    )
    p.add_argument(
        "--run-threshold",
        type=int,
        default=100,
        help="Report consecutive runs to the same address with length > this value (default: 100)",
    )
    p.add_argument(
        "--addr-base",
        choices=["byte", "cacheline"],
        default="byte",
        help=(
            "Whether to preserve full byte addresses or collapse to cacheline addresses. "
            "Default: byte"
        ),
    )
    p.add_argument(
        "--line-size",
        type=int,
        default=64,
        help="Cacheline size in bytes if --addr-base cacheline is used (default: 64)",
    )
    return p.parse_args()


def map_cmd(cmd_char: str) -> str:
    c = cmd_char.strip().lower()
    if c in ("u", "r", "read"):
        return "READ"
    if c in ("w", "write"):
        return "WRITE"
    raise ValueError(f"Unknown command field: {cmd_char!r}")


def normalize_addr(addr: int, addr_base: str, line_size: int) -> int:
    if addr_base == "byte":
        return addr
    if addr_base == "cacheline":
        return (addr // line_size) * line_size
    raise ValueError(f"Unknown addr base: {addr_base}")


def tick_to_cycle(tick: int, tick_ps: float, tck_ps: float) -> int:
    # floor() is usually the least surprising choice for cycle stamping.
    return int(math.floor((tick * tick_ps) / tck_ps))


def parse_line(line: str, lineno: int):
    parts = [x.strip() for x in line.split(",")]
    if len(parts) < 6:
        raise ValueError(f"Line {lineno}: expected at least 6 comma-separated fields, got {len(parts)}")

    # Expected format:
    # requestor_id, cmd, addr, size, misc, tick
    cmd = map_cmd(parts[1])
    addr = int(parts[2], 0)
    size = int(parts[3], 0)
    tick = int(parts[5], 0)
    opt_flag = int(parts[6], 0)

    return cmd, addr, size, tick, opt_flag


def find_long_runs(addrs, threshold):
    """
    Find consecutive runs of the exact same address with length > threshold.
    Returns list of tuples: (start_index, run_length, address)
    """
    runs = []
    if not addrs:
        return runs

    start = 0
    cur = addrs[0]

    for i in range(1, len(addrs)):
        if addrs[i] != cur:
            run_len = i - start
            if run_len > threshold:
                runs.append((start, run_len, cur))
            start = i
            cur = addrs[i]

    # tail
    run_len = len(addrs) - start
    if run_len > threshold:
        runs.append((start, run_len, cur))

    return runs


def main():
    args = parse_args()

    converted = []
    out_lines = []

    with open(args.input, "r", encoding="utf-8") as f:
        for lineno, raw in enumerate(f, start=1):
            line = raw.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue

            try:
                cmd, addr, size, tick, opt_flag = parse_line(line, lineno)
            except Exception as e:
                print(f"Skipping line {lineno}: {e}", file=sys.stderr)
                continue

            norm_addr = normalize_addr(addr, args.addr_base, args.line_size)
            cycle = tick_to_cycle(tick, args.tick_ps, args.tck_ps)

            converted.append((norm_addr, cmd, cycle, size, lineno, opt_flag))
            out_lines.append(f"0x{norm_addr:08X} {cmd} {cycle} {opt_flag}")

    with open(args.output, "w", encoding="utf-8") as f:
        for line in out_lines:
            f.write(line + "\n")

    addrs = [x[0] for x in converted]
    runs = find_long_runs(addrs, args.run_threshold)

    print(f"Wrote {len(out_lines)} DRAMSim3 trace lines to {args.output}")
    print(
        f"Found {len(runs)} consecutive same-address runs with length > {args.run_threshold}"
    )

    if runs:
        print("\nStart indices of long runs:")
        for start_idx, run_len, addr in runs:
            print(f"start_index={start_idx} run_length={run_len} addr=0x{addr:08X}")


if __name__ == "__main__":
    main()