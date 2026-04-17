cd graph_workloads
g++ -O0 \-nostdlib -static -ffreestanding -fno-exceptions -fno-rtti -fno-stack-protector -no-pie graph_coarsening.cpp \-I/../gem5/include \-L/../gem5/util/m5/build/x86/out -lm5 -o graph_coarsening
cd ../gem5
build/X86/gem5.opt \--outdir=../graph_workloads/m5out_graph_coarsening/ \configs/example/se.py   \--cpu-type=AtomicSimpleCPU   \--cpu-clock=4GHz   \--cacheline_size=64   \--num-cpus=1   \--cmd=../graph_workloads/graph_coarsening > ../graph_workloads/graph_coarsening_log.txt
cd util
python3 decode_packet_trace.py /home/arjun/ezh/graph_workloads/m5out_graph_coarsening/trace.ptrc.gz /home/arjun/ezh/graph_workloads/graph_coarsening_log_ascii_trace
cd ../../ # repo root
python3 ./amr_workload/convert_trace.py ./graph_workloads/graph_coarsening_log_417 ./graph_workloads/graph_coarsening_dramsim3.trace --tck-ps 630
python3 ./divideDRAMSimtrace.py  --gem5-log ./graph_workloads/graph_coarsening_log.txt --trace ./graph_workloads/graph_coarsening_dramsim3.trace --outdir ./graph_workloads/graph_coarsening_trace_chunks --tickDivParam 630

# run in dramsim build directory
cd DRAMSim3/build
# assumes binary exists
./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 467999 -t ~/ezh/graph_workloads/graph_coarsening_trace_chunks/iter_000000_cycles_42514_467999.trace -o ~/ezh/graph_workloads/dramsim_results_0

./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 631190 -t ~/ezh/graph_workloads/graph_coarsening_trace_chunks/iter_00000
1_cycles_468010_631190.trace -o ~/ezh/graph_workloads/dramsim_results_1
./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 705886 -t ~/ezh/graph_workloads/graph_coarsening_trace_chunks/iter_00000
2_cycles_631202_705886.trace -o ~/ezh/graph_workloads/dramsim_results_2
./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 747161 -t ~/ezh/graph_workloads/graph_coarsening_trace_chunks/iter_00000
3_cycles_705898_747161.trace -o ~/ezh/graph_workloads/dramsim_results_3
./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 773753 -t ~/ezh/graph_workloads/graph_coarsening_trace_chunks/iter_00000
4_cycles_747172_773753.trace -o ~/ezh/graph_workloads/dramsim_results_4
./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 792638 -t ~/ezh/graph_workloads/graph_coarsening_trace_chunks/iter_00000
5_cycles_773765_792638.trace -o ~/ezh/graph_workloads/dramsim_results_5
./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 807816 -t ~/ezh/graph_workloads/graph_coarsening_trace_chunks/iter_00000
6_cycles_792649_807816.trace -o ~/ezh/graph_workloads/dramsim_results_6
