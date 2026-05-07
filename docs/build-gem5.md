scons -j 4 build/X86/gem5.opt

(substitute your preferred # of threads if 4 is too many/few)

cd util/m5 && scons -j 4 build/x86/out/libm5.a

builds the library that we need to instrument the DRAM optimizations