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