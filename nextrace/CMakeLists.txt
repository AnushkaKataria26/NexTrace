cmake_minimum_required(VERSION 3.10)
project(NexTrace VERSION 1.0)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED True)

# Enable Address Sanitizer for Debug builds
if(CMAKE_BUILD_TYPE STREQUAL "Debug")
    set(CMAKE_CXX_FLAGS "${CMAKE_CXX_FLAGS} -fsanitize=address -g")
    set(CMAKE_EXE_LINKER_FLAGS "${CMAKE_EXE_LINKER_FLAGS} -fsanitize=address")
endif()

find_package(SQLite3 REQUIRED)

add_executable(nextrace_search 
    src/main.cpp
    src/query_parser.cpp
    src/posting_list.cpp
    src/filters.cpp
)

target_link_libraries(nextrace_search PRIVATE SQLite::SQLite3)
