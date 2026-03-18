cmake_minimum_required(VERSION 3.20)
project(Memoir VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

find_package(pybind11 CONFIG REQUIRED)
find_package(cppwinrt CONFIG REQUIRED)
find_package(FFMPEG REQUIRED)

pybind11_add_module(_native
    src/bindings/module.cpp
    src/core/capture_engine.cpp
    src/core/keyboard.cpp
    src/core/window_finder.cpp
    src/recording/recording_session.cpp
)

target_include_directories(_native PRIVATE
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/src
    ${FFMPEG_INCLUDE_DIRS}
)

target_link_libraries(_native PRIVATE
    Microsoft::CppWinRT
    d3d11
    dxgi
    windowsapp
    ${FFMPEG_LIBRARIES}
)

target_compile_definitions(_native PRIVATE NOMINMAX)

if(MSVC)
    target_compile_options(_native PRIVATE /bigobj)
endif()

# Install: _native.pyd + FFmpeg DLLs into the memoir/ package
# (used by scikit-build-core for wheel packaging)
install(TARGETS _native LIBRARY DESTINATION memoir)

file(GLOB _FFMPEG_DLLS "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/av*.dll"
                       "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/sw*.dll")
install(FILES ${_FFMPEG_DLLS} DESTINATION memoir)

# Post-build: also copy to source tree for local dev (import memoir works)
add_custom_command(TARGET _native POST_BUILD
    COMMAND ${CMAKE_COMMAND} -E copy_if_different
        $<TARGET_FILE:_native>
        ${CMAKE_SOURCE_DIR}/memoir/_native.pyd
    COMMENT "Copying _native.pyd into memoir/"
)

foreach(_dll ${_FFMPEG_DLLS})
    add_custom_command(TARGET _native POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            "${_dll}" ${CMAKE_SOURCE_DIR}
    )
endforeach()
