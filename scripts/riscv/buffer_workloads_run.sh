#!/bin/bash

# Run this in the scripts repo

set -e 

# Set vars
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/../.."; pwd)

WORKLOAD_DIR=$REPO_ROOT/workloads/graph_workloads
GEM5_DIR=$REPO_ROOT/gem5
DRAMSIM_DIR=$REPO_ROOT/DRAMsim3
SCRIPTS_DIR=$REPO_ROOT/scripts

WORKLOAD_NAME=graph_coarsening
WORKLOAD_BIN=$WORKLOAD_DIR/$WORKLOAD_NAME
WORKLOAD_SRC=$WORKLOAD_DIR/$WORKLOAD_NAME.cpp

M5OUT_DIR=$WORKLOAD_DIR/m5out_${WORKLOAD_NAME}_riscv
RAW_TRACE=$WORKLOAD_DIR/${WORKLOAD_NAME}_log_raw_trace_riscv
DRAMSIM_TRACE=$WORKLOAD_DIR/${WORKLOAD_NAME}_dramsim3_riscv.trace

DRAMSIM_RESULTS_DIR=$WORKLOAD_DIR/dramsim_results_riscv

DRAMSIM_RESULTS=$DRAMSIM_RESULTS_DIR/unspecified
UNIFIED_DRAMSIM_RESULTS=$DRAMSIM_RESULTS_DIR/unified_queue
NONUNIFIED_DRAMSIM_RESULTS=$DRAMSIM_RESULTS_DIR/non_unified_queue

DRAM_CONFIG=DDR4_8Gb_x8_3200          # unspecified unified queue

# These are the most architecturally similar pairs that exist in DRAM sim naturally
# DRAM_CONFIG=HBM1_4Gb_x128            # unspecified unified queue
# UNIFIED_DRAM_CONFIG=HMC_2GB_4Lx16    # unified queue config
# NONUNIFIED_DRAM_CONFIG=HBM2_4Gb_x128 # non-unified queue config

# echo "Source:   $WORKLOAD_SRC"
# echo "Include:  $GEM5_DIR/include"
# echo "Output:   $WORKLOAD_BIN"

# ls $WORKLOAD_SRC

riscv64-linux-gnu-g++ -O0 \-nostdlib -static -ffreestanding -fno-exceptions -fno-rtti \
    -fno-stack-protector -no-pie \
    $WORKLOAD_SRC \
    -I$GEM5_DIR/include \
    -L$GEM5_DIR/util/m5/build/riscv/out -lm5 \
    -DRISCV \
    -o$WORKLOAD_BIN

echo "===================== Compile complete ====================="

$GEM5_DIR/build/RISCV/gem5.opt \
    --debug-flags=DRAMOpt \
    --outdir=$M5OUT_DIR \
    $GEM5_DIR/configs/example/riscv-se.py \
    --cpu-type=AtomicSimpleCPU \
    --cpu-clock=1GHz \
    --cacheline_size=64 \
    --num-cpus=1 \
    --mem-size=2147483648 \
    --cmd=$WORKLOAD_BIN > $WORKLOAD_DIR/${WORKLOAD_NAME}_log.txt

echo "===================== Gem5 Sim complete ====================="

python3 $GEM5_DIR/util/decode_packet_trace.py \
    $M5OUT_DIR/trace.ptrc.gz \
    $RAW_TRACE
echo "===================== Decode packet trace complete ====================="

# python3 $SCRIPTS_DIR/convert_trace.py \
#     $RAW_TRACE \
#     $DRAMSIM_TRACE \
#     --tck-ps 630
python3 $SCRIPTS_DIR/parse_gem5.py --gem5_trace_file $RAW_TRACE --dramsim3_trace_file $DRAMSIM_TRACE --dramsim3_tCK 0.63

echo "===================== Trace conversion complete ====================="


final_cycle=$(tail -n 1 $DRAMSIM_TRACE | awk '{print $3}')

mkdir -p $DRAMSIM_RESULTS
mkdir -p $UNIFIED_DRAMSIM_RESULTS
mkdir -p $NONUNIFIED_DRAMSIM_RESULTS

# RUN EXPERIMENTS FORALL THREE QUEUE TYPES

$DRAMSIM_DIR/build/dramsim3main \
    $DRAMSIM_DIR/configs/$DRAM_CONFIG.ini \
    -c $final_cycle \
    -t $DRAMSIM_TRACE \
    -o $DRAMSIM_RESULTS \
    --enable_buffering

$DRAMSIM_DIR/build/dramsim3main \
    $DRAMSIM_DIR/configs/${DRAM_CONFIG}_unified.ini \
    -c $final_cycle \
    -t $DRAMSIM_TRACE \
    -o $UNIFIED_DRAMSIM_RESULTS \
    --enable_buffering

$DRAMSIM_DIR/build/dramsim3main \
    $DRAMSIM_DIR/configs/${DRAM_CONFIG}_non_unified.ini \
    -c $final_cycle \
    -t $DRAMSIM_TRACE \
    -o $NONUNIFIED_DRAMSIM_RESULTS \
    --enable_buffering

echo "===================== DRAMSim simulations complete ====================="


# todo: Run scape and plot.py 