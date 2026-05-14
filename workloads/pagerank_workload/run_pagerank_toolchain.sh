#!/bin/bash
set -e

REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.."; pwd)
WORKLOAD_DIR=$REPO_ROOT/workloads/pagerank_workload
GEM5_DIR=$REPO_ROOT/gem5
SCRIPTS_DIR=$REPO_ROOT/scripts

WORKLOAD_NAME=pagerank_pull
WORKLOAD_SRC=$WORKLOAD_DIR/${WORKLOAD_NAME}.cpp
WORKLOAD_BIN=$WORKLOAD_DIR/${WORKLOAD_NAME}
M5OUT_DIR=$WORKLOAD_DIR/m5out_${WORKLOAD_NAME}
RAW_TRACE=$WORKLOAD_DIR/${WORKLOAD_NAME}_raw_trace
DRAMSIM_TRACE=$WORKLOAD_DIR/${WORKLOAD_NAME}_dramsim3.trace

g++ -O0 -nostdlib -static -ffreestanding -fno-exceptions -fno-rtti \
    -fno-stack-protector -no-pie \
    "$WORKLOAD_SRC" \
    -I"$GEM5_DIR/include" \
    -L"$GEM5_DIR/util/m5/build/x86/out" -lm5 \
    -o "$WORKLOAD_BIN"

echo "===================== Compile complete ====================="

"$GEM5_DIR/build/X86/gem5.opt" \
    --debug-flags=DRAMOpt \
    --outdir="$M5OUT_DIR" \
    "$GEM5_DIR/configs/example/se.py" \
    --cpu-type=AtomicSimpleCPU \
    --cpu-clock=4GHz \
    --cacheline_size=64 \
    --num-cpus=1 \
    --mem-size=2147483648 \
    --cmd="$WORKLOAD_BIN" > "$WORKLOAD_DIR/${WORKLOAD_NAME}_log.txt"

echo "===================== gem5 complete ====================="

python3 "$GEM5_DIR/util/decode_packet_trace.py" \
    "$M5OUT_DIR/trace.ptrc.gz" \
    "$RAW_TRACE"

echo "===================== Decode complete ====================="

python3 "$SCRIPTS_DIR/convert_trace.py" \
    "$RAW_TRACE" \
    "$DRAMSIM_TRACE" \
    --tck-ps 630

echo "===================== Trace conversion complete ====================="
