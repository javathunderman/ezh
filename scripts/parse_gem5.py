#!/usr/bin/env python3

import math
import argparse

# Parse the gem5 trace file and output a DRAMsim3 trace file

# parse args
parser = argparse.ArgumentParser(description='Parse gem5 trace file and output a DRAMsim3 trace file')

parser.add_argument('--gem5_trace_file', type=str, required=True, help='gem5 trace file (input)')
parser.add_argument('--dramsim3_trace_file', type=str, required=True, help='DRAMsim3 trace file (output)')

parser.add_argument('--dramsim3_tCK', type=float, default=1.25, help='DRAMsim3 tCK (ns) (default: 1.25)')
parser.add_argument('--gem5_tick_per_second', type=int, default=1000000000000, help='gem5 tick per second (default: 1e12)')

args = parser.parse_args()

dramsim3_freq = 1e9 / args.dramsim3_tCK

with open(args.gem5_trace_file, "r") as fin:
    with open(args.dramsim3_trace_file, "w") as fout:
        for line in fin:
            tokens = line.strip().split(",")
            cmd = tokens[1]
            # ascii_out.write(f"0x{int(addr):0>8X} {cmd} {tick}\n")
            addr = int(tokens[2], 0)
            tick = math.ceil(int(tokens[5]) * dramsim3_freq / args.gem5_tick_per_second)
            opt_stream_id = int(tokens[6], 0)
            opt_flag = int(tokens[7], 0)
            
            if (len(tokens) == 9):
                opt_stream_size = int(tokens[8])
                out_str = (f"0x{int(addr):08X} {cmd} {tick} {opt_stream_id} {opt_stream_size} {opt_flag}\n")
            else:
                out_str = (f"0x{int(addr):08X} {cmd} {tick} 0 0 0\n")
            
            fout.write(out_str)
        print(f"final tick: {tick}")
