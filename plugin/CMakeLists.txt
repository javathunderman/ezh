cmake_minimum_required(VERSION 3.28)
project(EzhClangHints)

# Path to Clang and LLVM (you may need to adjust this)
find_package(Clang REQUIRED CONFIG)
find_package(LLVM REQUIRED CONFIG)

# Include Clang's header files
include_directories(${CLANG_INCLUDE_DIRS})

add_definitions(${CLANG_DEFINITIONS})

# add_library(assertion_plugin MODULE plugin.cpp)
add_executable(assertion_plugin src/plugin.cpp)

# Link against Clang's libraries
target_link_libraries(assertion_plugin PRIVATE
  clangAST
  clangFrontend
  clangBasic
  clangRewrite
  clangLex
  clangParse
  clangSema
  clangAnalysis
  clangEdit
  clangASTMatchers
  clangRewrite
  clangTooling
  clangFrontend
  clangDriver
  clangSerialization
)

# # Make sure that Clang can be found during the build
# set_target_properties(assertion_plugin PROPERTIES
#   PREFIX ""
#   SUFFIX ".so"
# )

