Execute from root directory:

To build: `docker build -t ezh-dev .`
To run the container: `docker run -it -v .:/ezh ezh-dev`

If you get warnings that libpng and libhd5 headers are missing, this is likely due to a previous build that ran when libpng-dev or libhd5-dev were not installed (this should now be fixed in the Dockerfile). 
To resolve this, delete the following files/directories: `build/*/gem5.build/scons_config`, `.sconsign.dblite`. If, after this, you get an error that scons could not find the Python header files, delete the `build/` directory (NOT THE OTHER build_* DIRECTORIES!) and start a fresh build with `scons -j 4 build/X86/gem5.opt` (substitute your preferred # of threads if 4 is too few/many). 