#!/bin/bash

set -e 

# Set vars
REPO_ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.."; pwd)

WORKLOAD_DIR=$REPO_ROOT/workloads/graph_workloads
GEM5_DIR=$REPO_ROOT/gem5
DRAMSIM_DIR=$REPO_ROOT/DRAMsim3
SCRIPTS_DIR=$REPO_ROOT/scripts

WORKLOAD_NAME=graph_coarsening
WORKLOAD_BIN=$WORKLOAD_DIR/$WORKLOAD_NAME
WORKLOAD_SRC=$WORKLOAD_DIR/$WORKLOAD_NAME.cpp

M5OUT_DIR=$WORKLOAD_DIR/m5out_$WORKLOAD_NAME
RAW_TRACE=$WORKLOAD_DIR/${WORKLOAD_NAME}_log_raw_trace
DRAMSIM_TRACE=$WORKLOAD_DIR/${WORKLOAD_NAME}_dramsim3.trace
DRAMSIM_RESULTS=$WORKLOAD_DIR/dramsim_results

# echo "Source:   $WORKLOAD_SRC"
# echo "Include:  $GEM5_DIR/include"
# echo "Lib:      $GEM5_DIR/util/m5/build/x86/out"
# echo "Output:   $WORKLOAD_BIN"

# ls $WORKLOAD_SRC

g++ -O0 \-nostdlib -static -ffreestanding -fno-exceptions -fno-rtti \
    -fno-stack-protector -no-pie \
    $WORKLOAD_SRC \
    -I$GEM5_DIR/include \
    -L$GEM5_DIR/util/m5/build/x86/out -lm5 \
    -o$WORKLOAD_BIN

echo "===================== Compile complete ====================="

$GEM5_DIR/build/X86/gem5.opt \
    --debug-flags=DRAMOpt \
    --outdir=$M5OUT_DIR \
    $GEM5_DIR/configs/example/se.py \
    --cpu-type=AtomicSimpleCPU \
    --cpu-clock=4GHz \
    --cacheline_size=64 \
    --num-cpus=1 \
    --cmd=$WORKLOAD_BIN > $WORKLOAD_DIR/${WORKLOAD_NAME}_log.txt


echo "===================== Gem5 Sim complete ====================="

python3 $GEM5_DIR/util/decode_packet_trace.py \
    $M5OUT_DIR/trace.ptrc.gz \
    $RAW_TRACE
echo "===================== Decode packet trace complete ====================="

python3 $SCRIPTS_DIR/convert_trace.py \
    $RAW_TRACE \
    $DRAMSIM_TRACE \
    --tck-ps 630
echo "===================== Trace conversion complete ====================="


final_cycle=$(tail -n 1 $DRAMSIM_TRACE | awk '{print $1}')

mkdir -p $DRAMSIM_RESULTS
$DRAMSIM_DIR/build/dramsim3main \
    $DRAMSIM_DIR/configs/DDR4_8Gb_x8_3200.ini \
    -c $final_cycle \
    -t $DRAMSIM_TRACE \
    -o $DRAMSIM_RESULTS

echo "===================== DRAMSim simulation complete ====================="






