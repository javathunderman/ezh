g++ -O0 \-nostdlib -static -ffreestanding -fno-exceptions -fno-rtti -fno-stack-protector -no-pie /ezh/workloads/graph_workloads/graph_coarsening.cpp \-I/ezh/gem5/include \-L/ezh/gem5/util/m5/build/x86/out -lm5 -o /ezh/workloads/graph_workloads/graph_coarsening
echo "===================== Compile complete ====================="
cd ../gem5 && build/X86/gem5.opt \--debug-flags=DRAMOpt \--outdir=/ezh/workloads/graph_workloads/m5out_graph_coarsening/ \configs/example/se.py   \--cpu-type=AtomicSimpleCPU   \--cpu-clock=4GHz   \--cacheline_size=64   \--num-cpus=1   \--cmd=/ezh/workloads/graph_workloads/graph_coarsening > /ezh/workloads/graph_workloads/graph_coarsening_log.txt
echo "===================== Gem5 Sim complete ====================="
cd ../scripts
python3 /ezh/gem5/util/decode_packet_trace.py /ezh/workloads/graph_workloads/m5out_graph_coarsening/trace.ptrc.gz /ezh/workloads/graph_workloads/graph_coarsening_log_raw_trace
echo "===================== Decode packet trace complete ====================="
python3 /ezh/scripts/convert_trace.py /ezh/workloads/graph_workloads/graph_coarsening_log_raw_trace /ezh/workloads/graph_workloads/graph_coarsening_dramsim3.trace --tck-ps 630
echo "===================== Trace conversion complete ====================="
python3 /ezh/scripts/divideDRAMSimtrace.py  --gem5-log /ezh/workloads/graph_workloads/graph_coarsening_log.txt --trace /ezh/workloads/graph_workloads/graph_coarsening_dramsim3.trace --outdir /ezh/workloads/graph_workloads/chunk_traces/graph_coarsening_trace_chunks_bitshift_0 --tickDivParam 630
mkdir -p /ezh/workloads/graph_workloads/dramsim_results
mkdir -p /ezh/workloads/graph_workloads/chunk_traces
# run in dramsim build directory
# assumes binary exists
for i in {0..6..2}
do
    if [ "$i" -ne 0 ]; then
        python3 /ezh/scripts/rewrite_dramsim3_bankshift.py --indir /ezh/workloads/graph_workloads/chunk_traces/graph_coarsening_trace_chunks_bitshift_0/ --outdir /ezh/workloads/graph_workloads/chunk_traces/graph_coarsening_trace_chunks_bitshift_$i --bank-count 16 --bank-lsb 0 --bank-bit-shift $i --iter-set 5 --clobber
        echo "===================== Shifted trace addresses by $i bits ====================="
    fi
    python3 /ezh/scripts/set_trace_cycle_zero.py /ezh/workloads/graph_workloads/chunk_traces/graph_coarsening_trace_chunks_bitshift_$i
    echo "===================== Zeroed cycle in trace for shift of $i bits ====================="
    for j in {0..5}
    do
        mkdir -p /ezh/workloads/graph_workloads/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_$j
        f=$(ls /ezh/workloads/graph_workloads/chunk_traces/graph_coarsening_trace_chunks_bitshift_$i/iter_00000$j_*)

        base=${f%.trace}

        last=${base##*_}
        second_last=${base%_*}
        second_last=${second_last##*_}

        diff=$((last - second_last))

        /ezh/DRAMsim3/build/dramsim3main /ezh/DRAMsim3/configs/DDR4_8Gb_x8_3200.ini -c $diff -t /ezh/workloads/graph_workloads/chunk_traces/graph_coarsening_trace_chunks_bitshift_$i/iter_00000$j*.trace -o /ezh/workloads/graph_workloads/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_$j
        echo "===================== DRAMSim simulation complete for $i bits shifted and trace segment $j ====================="
        
    done
    # ./ezh/DRAMsim3/build/dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 807816 -t /ezh/workloads/graph_workloads/chunk_traces/graph_coarsening_trace_chunks_$i/iter_000006_cycles_792649_807816.trace -o /ezh/workloads/graph_workloads/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_6
done
mv /ezh/dram_opt_markers* /ezh/workloads/graph_workloads