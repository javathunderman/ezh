scons -j 4  --linker=mold build/X86/gem5.opt

(substitute your preferred # of threads if 4 is too many/few)

cd util/m5 && scons -j 4 --linker=mold build/x86/out/libm5.a

builds the library that we need to instrument the DRAM optimizations

If you get an error when trying to use scons this way, try wrapping it in a mold command: mold -run scons build/X86/gem5.opt -j 4