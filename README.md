## How to go from workload to dramsim results
### Write workload:
- No syscalls, no libraries, no nothing
- Unless specifically using C++ features, use C (This is so we can use gcc over g++)
- See already written workloads for start and end setups + other stuff

### Compiling workload:
- We basically want the compiler to think it's compiling for the Intel 4004 
- Compilation command: `gcc -O0 -nostdlib -static -ffreestanding -fno-stack-protector -no-pie -e _start <workload>.c -Ipath/to/ezh/gem5/include -Lpath/to/ezh/gem5/util/m5/build/x86/out -lm5 -o <workload>`

### Simulating with gem5:
- Build gem5 with Scons
- Simulate with gem5: `build/X86/gem5.opt --outdir=m5out/ ../se.py --cpu-type=AtomicSimpleCPU --cpu-clock=4GHz --cacheline_size=64 --mem-size=2GB --num-cpus=1 --cmd=../<workload>_workload>/<workload>`
- Note: You may need to increase mem_size, depending on the amount of memory used by your workload

### Extracting trace file from output:
- Move m5out/ to your desired location
- Use gunzip to extract the trace file: `gunzip -k trace.ptrc.gz` (-k preserves the .gz incase you need it again)
- This will produce `trace.ptrc`, which we then feed to `/gem5/util/decode_packet_trace.py`
- Example: `./util/decode_packet_trace.py ../<workload>_workload/<workload>_gem5_output/trace.ptrc ../<workload>_workload/<workload>_gem5_output/trace.txt

### Converting and splitting the gem5 trace
- We need to convert the gem5 trace into a DRAMSim3 trace so that we can use it with DRAMSim3
- We then need to break that trace across our iterative loops so that we can simulate them to get better performance
- To convert the trace, use `parse_gem5_trace.py` in the root
- Example:  `./parse_gem5_trace.py --gem5_trace_file <workload>_workload/<workload>_gem5_output/trace.txt --dramsim3_trace_file /<workload>_workload/<workload>_dramsim.trace --dramsim3_tCK 0.94`
- Then, we need to break the trace into the multiple iterations -- todo: Finish this


### Simulating with DRAMSim3:
- This one is easy, as you can get the command from the MP3 doc.
- Example: ./build/dramsim3main configs/DDR4_8Gb_x8_3200.ini -c <num_cycles> -t ../ezh/<workload>_workload/<workload>_dramsim.trace.trace -o ./

Congratulations, you've completed the entire flow!



1: 

after building gem5, yhou'll need to build the m5ops library so you can put the m5_ops m5_work_begin/m5_work_end in your workload

to do this, you need to use scons to build the m5 library

/mnt/c/Users/alexl5/Documents/ece511_mp_dir/gem5_tracecopy/util/m5$ scons build/x86/out/m5

2:

2a: write your workload with manual hook instead of main (or don't) (see amr_counts.cpp)


2b:  bulid your workload with:

g++ -O0 \
-nostdlib -static -ffreestanding -fno-exceptions -fno-rtti -fno-stack-protector -no-pie \
amr_counts.cpp \
-I/mnt/c/Users/alexl5/Documents/ece511_mp_dir/gem5_tracecopy/include \
-L/mnt/c/Users/alexl5/Documents/ece511_mp_dir/gem5_tracecopy/util/m5/build/x86/out \
-lm5 -o amr_counts

(1 - absolutley no linux OS calls and 2 - include m5 ops)


3: run gem5 with your workload

build/X86/gem5.opt \
--outdir=m5out/ \
configs/example/se.py   \
--cpu-type=AtomicSimpleCPU   \
--cpu-clock=4GHz   \
--cacheline_size=64   \
--num-cpus=1   \
--cmd=./myworkloads/amr_counts

3b: copy-paste the output of gem5 into ezh\myworkloads\amr_gem5_output

4: convert trace obj into text trace (this is in the mp3 manual)

alexl5@AlexLeeComputer:/mnt/c/Users/alexl5/Documents/ece511_mp_dir/gem5_tracecopy/util$
python3 decode_packet_trace.py ../m5out/trace.ptrc.gz ./415log1_1iter

5: convert text trace to dramsim3 compt trace

alexl5@AlexLeeComputer:/mnt/c/Users/alexl5/Documents/ece511_mp_dir/gem5_tracecopy/myworkloads$

python3 convert_trace.py \
../util/415log1_1iter dramsim3.trace \
--tck-ps 250

6: split dramsim3.trace into chunks based on iter begin/end ticks

/mnt/c/Users/alexl5/Documents/ece511_mp_dir/alexl5_mp3/tmp/DRAMsim3/build/dramsim3main \
/mnt/c/Users/alexl5/Documents/ece511_mp_dir/alexl5_mp3/tmp/DRAMsim3/configs/DDR4_8Gb_x8_3200.ini \
-c 10909541 \
-t ./dramsim3_tracechunks/iter_000000_cycles_3185554_10909541.trace \
-o ./dramsim_results