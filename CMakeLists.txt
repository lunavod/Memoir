cmake_minimum_required(VERSION 3.20)
project(memoir-capture VERSION 0.1.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(MEMOIR_BUILD_PYTHON "Build Python bindings (pybind11)" ON)
option(MEMOIR_BUILD_NODE   "Build Node.js bindings (N-API)"   OFF)

find_package(cppwinrt CONFIG REQUIRED)
find_package(FFMPEG REQUIRED)

# ── Shared core (static lib, compiled once) ──────────────────────

add_library(memoir_core STATIC
    src/core/capture_engine.cpp
    src/core/keyboard.cpp
    src/core/window_finder.cpp
    src/recording/recording_session.cpp
)

target_include_directories(memoir_core PUBLIC
    ${CMAKE_SOURCE_DIR}/include
    ${CMAKE_SOURCE_DIR}/src
    ${FFMPEG_INCLUDE_DIRS}
)

target_link_libraries(memoir_core PUBLIC
    Microsoft::CppWinRT
    d3d11
    dxgi
    windowsapp
    ${FFMPEG_LIBRARIES}
)

target_compile_definitions(memoir_core PUBLIC NOMINMAX)

if(MSVC)
    target_compile_options(memoir_core PRIVATE /bigobj)
endif()

# ── Python target (conditional) ──────────────────────────────────

if(MEMOIR_BUILD_PYTHON)
    find_package(pybind11 CONFIG REQUIRED)

    pybind11_add_module(_native src/bindings/module.cpp)
    target_link_libraries(_native PRIVATE memoir_core)

    install(TARGETS _native LIBRARY DESTINATION memoir_capture)

    file(GLOB _FFMPEG_DLLS "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/av*.dll"
                           "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/sw*.dll"
                           "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/libx265.dll")
    install(FILES ${_FFMPEG_DLLS} DESTINATION memoir_capture)

    # Post-build: copy to source tree for local dev
    add_custom_command(TARGET _native POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy_if_different
            $<TARGET_FILE:_native>
            ${CMAKE_SOURCE_DIR}/memoir_capture/_native.pyd
        COMMENT "Copying _native.pyd into memoir/"
    )

    foreach(_dll ${_FFMPEG_DLLS})
        add_custom_command(TARGET _native POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${_dll}" ${CMAKE_SOURCE_DIR}
        )
    endforeach()
endif()

# ── Node target (conditional) ────────────────────────────────────

if(MEMOIR_BUILD_NODE)
    # cmake-js provides CMAKE_JS_INC and CMAKE_JS_LIB
    include_directories(${CMAKE_JS_INC})

    # node-addon-api headers
    execute_process(
        COMMAND node -p "require('node-addon-api').include_dir"
        WORKING_DIRECTORY ${CMAKE_SOURCE_DIR}
        OUTPUT_VARIABLE NODE_ADDON_API_DIR
        OUTPUT_STRIP_TRAILING_WHITESPACE
    )

    add_library(memoir_node SHARED src/bindings/node_module.cpp)

    set_target_properties(memoir_node PROPERTIES PREFIX "" SUFFIX ".node")

    target_include_directories(memoir_node PRIVATE ${NODE_ADDON_API_DIR})

    target_link_libraries(memoir_node PRIVATE
        memoir_core
        ${CMAKE_JS_LIB}
    )

    target_compile_definitions(memoir_node PRIVATE
        NAPI_VERSION=8
        NODE_ADDON_API_DISABLE_DEPRECATED
    )

    # Copy FFmpeg DLLs next to .node
    file(GLOB _NODE_FFMPEG_DLLS
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/av*.dll"
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/sw*.dll"
        "${VCPKG_INSTALLED_DIR}/${VCPKG_TARGET_TRIPLET}/bin/libx265.dll"
    )
    foreach(_dll ${_NODE_FFMPEG_DLLS})
        add_custom_command(TARGET memoir_node POST_BUILD
            COMMAND ${CMAKE_COMMAND} -E copy_if_different
                "${_dll}" $<TARGET_FILE_DIR:memoir_node>
        )
    endforeach()
endif()
