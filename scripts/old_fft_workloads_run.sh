# cd ../fft_workload
# g++ -O0 \-nostdlib -static -ffreestanding -fno-exceptions -fno-rtti -fno-stack-protector -no-pie fft.cpp \-I~/ezh/gem5/include \-L~/ezh/gem5/util/m5/build/x86/out -lm5 -o fft
# cd ../gem5
# build/X86/gem5.opt \--outdir=../fft_workload/m5out_fft/ \configs/example/se.py   \--cpu-type=AtomicSimpleCPU   \--cpu-clock=4GHz   \--cacheline_size=64   \--num-cpus=1   \--cmd=../fft_workload/fft > ../fft_workload/fft_log.txt
# cd util
# python3 decode_packet_trace.py ~/ezh/fft_workload/m5out_fft/trace.ptrc.gz ~/ezh/fft_workload/fft_log_ascii_trace
# cd ../../ # repo root
# python3 ./scripts/convert_trace.py ./fft_workload/fft_log_417 ./fft_workload/fft_dramsim3.trace --tck-ps 630
# python3 ./scripts/divideDRAMSimtrace.py  --gem5-log ./fft_workload/fft_log.txt --trace ./fft_workload/fft_dramsim3.trace --outdir ./fft_workload/chunk_traces/fft_trace_chunks_bitshift_0 --tickDivParam 630
mkdir -p ~/ezh/fft_workload/dramsim_results
mkdir -p ~/ezh/fft_workload/chunk_traces
# run in dramsim build directory
cd ~/ezh/DRAMsim3/build
# assumes binary exists
for i in {0..6..2}
do
    if [ "$i" -ne 0 ]; then
        python3 ~/ezh/scripts/rewrite_dramsim3_bankshift.py --indir ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_0/ --outdir ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i --bank-count 16 --bank-lsb 0 --bank-bit-shift $i --iter-set 5
    fi
    python3 ~/ezh/scripts/set_trace_cycle_zero.py ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_0
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_1
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_2
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_3
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_4
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_5
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_6
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_7
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_8
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_9
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_10
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_11
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_12
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_13
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_14
    mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_15
    # mkdir -p ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_6
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 6384724 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000000*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_0
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 6131159 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000001*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_1
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 6074378 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000002*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_2
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5940989 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000003*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_3
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5909293 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000004*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_4
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5893445 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000005*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_5
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5885521 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000006*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_6
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5881560 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000007*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_7
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5879579 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000008*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_8
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5878588 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000009*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_9
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5878093 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000010*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_10
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5877845 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000011*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_11
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5877722 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000012*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_12
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5877659 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000013*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_13
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5877628 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000014*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_14
    ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 5877613 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_bitshift_$i/iter_000015*.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_15
    # ./dramsim3main ../configs/DDR4_8Gb_x8_3200.ini -c 807816 -t ~/ezh/fft_workload/chunk_traces/fft_trace_chunks_$i/iter_000006_cycles_792649_807816.trace -o ~/ezh/fft_workload/dramsim_results/dramsim_results_bitshift_$i/dramsim_results_6
done