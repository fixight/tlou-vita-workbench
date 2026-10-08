cmake_minimum_required(VERSION 3.12)

if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
    if(DEFINED ENV{VITASDK})
        set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "toolchain file")
    else()
        set(CMAKE_TOOLCHAIN_FILE "/usr/local/vitasdk/share/vita.toolchain.cmake" CACHE PATH "toolchain file")
    endif()
endif()

project(TLOU_Vita C CXX)

include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

set(VITA_APP_NAME "TLOU Vita 3D")
set(VITA_TITLEID "TLOU00001")
set(VITA_VERSION "01.00")

# =========================================================================
# 1. ПОИСК ФАЙЛОВ ИСКЛЮЧИТЕЛЬНО В НАШИХ ПАПКАХ (Игнорируем папки сборки)
# =========================================================================
# =========================================================================
# 1. ПОИСК ФАЙЛОВ ИСКЛЮЧИТЕЛЬНО В НАШИХ ПАПКАХ
# =========================================================================
file(GLOB_RECURSE SOURCES CONFIGURE_DEPENDS
        "${CMAKE_CURRENT_SOURCE_DIR}/Engine/*.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/Engine/*.h"
        "${CMAKE_CURRENT_SOURCE_DIR}/Engine/*.hpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/Memory/*.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/Memory/*.h"
        "${CMAKE_CURRENT_SOURCE_DIR}/System/*.h"
        "${CMAKE_CURRENT_SOURCE_DIR}/System/*.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/Memory/*.hpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/*.cpp"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/*.h"
        "${CMAKE_CURRENT_SOURCE_DIR}/src/*.hpp"
)

# -------------------------------------------------------------------------
# ИССПРАВЛЕНИЕ: Выкидываем служебные тесты GLM из сборки!
# -------------------------------------------------------------------------
list(FILTER SOURCES EXCLUDE REGEX "Engine/glm/.*")

# Добавляем главный main.cpp из корня проекта
list(FILTER SOURCES EXCLUDE REGEX "Engine/glm/.*")

# Добавляем главный main.cpp из корня проекта
list(APPEND SOURCES "${CMAKE_CURRENT_SOURCE_DIR}/main.cpp")

# Создаем исполняемый файл
add_executable(TLOU_Vita ${SOURCES}
        Objects/Object.cpp
        Objects/Object.h
        Engine/World.cpp
        Engine/World.h
        Engine/Math3D.h
        Memory/MemoryManager.cpp
        Memory/MemoryManager.h
        Objects/Actor.cpp
        Objects/Actor.h
        System/DataLoader.cpp
        System/DataLoader.h
        System/Types.h
        Objects/CameraActor.cpp
        Objects/CameraActor.h
        Components/BaseComponent.cpp
        Components/BaseComponent.h
        Managers/AudioManager.cpp
        Managers/AudioManager.h
        Managers/InputManager.cpp
        Managers/InputManager.h
        Managers/CollisionManager.cpp
        Managers/CollisionManager.h
        Managers/StreamManager.cpp
        Managers/StreamManager.h
        Memory/StackAllocator.cpp
        Memory/StackAllocator.h
        Objects/Character.cpp
        Objects/Character.h
        System/ThreadManager.cpp
        System/ThreadManager.h)

# =========================================================================
# 2. УНИВЕРСАЛЬНЫЕ ПУТИ ДЛЯ #include
# =========================================================================
target_include_directories(TLOU_Vita PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}
        ${CMAKE_CURRENT_SOURCE_DIR}/Engine
        ${CMAKE_CURRENT_SOURCE_DIR}/Memory
        ${CMAKE_CURRENT_SOURCE_DIR}/src
)

target_include_directories(TLOU_Vita PRIVATE
        ${CMAKE_CURRENT_SOURCE_DIR}/Engine/glm
)

# =========================================================================
# 3. ЛИНКОВКА БИБЛИОТЕК VITA3D
# =========================================================================
# libstdc++ and GCC TLS use weak pthread symbols (cancel, once, etc.).
# Keep the complete VitaSDK pthread runtime so those references are resolved.
target_link_libraries(TLOU_Vita
        "-Wl,--whole-archive"
        pthread
        "-Wl,--no-whole-archive"
        vitaGL
        vitashark
        SceShaccCgExt
        SceShaccCg_stub
        mathneon
        taihen_stub
        SceKernelDmacMgr_stub
        SceDisplay_stub
        SceGxm_stub
        SceCtrl_stub
        SceAppMgr_stub
        SceAvPlayer_stub
        SceAudio_stub
        SceAudiodec_stub
        SceSysmodule_stub
        SceCommonDialog_stub
        SceTouch_stub
        m
)

# =========================================================================
# 4. УПАКОВКА В VPK
# =========================================================================
# =========================================================================
# 4. АВТОМАТИЧЕСКАЯ СБОРКА И УПАКОВКА ВСЕХ АССЕТОВ В VPK
# =========================================================================
vita_create_self(eboot.bin TLOU_Vita UNSAFE)

# 1. Указываем папку на ПК, где будут лежать все ваши ассеты
set(ASSETS_DIR "${CMAKE_CURRENT_SOURCE_DIR}/assets")

# 2. Находим ВСЕ файлы внутри папки assets (рекурсивно во всех подпапках)
file(GLOB_RECURSE ALL_ASSETS CONFIGURE_DEPENDS "${ASSETS_DIR}/*")

# 3. Автоматически формируем список аргументов "FILE путь_на_пк путь_в_vpk"
set(VPK_ASSETS_LIST)
foreach(ASSET_FILE ${ALL_ASSETS})
    # Вычисляем относительный путь (например, "models/joel.bin")
    file(RELATIVE_PATH REL_PATH "${ASSETS_DIR}" "${ASSET_FILE}")

    # Добавляем пару аргументов для vita_create_vpk
    list(APPEND VPK_ASSETS_LIST FILE "${ASSET_FILE}" "${REL_PATH}")
endforeach()

# 4. Передаем сформированный список в vita_create_vpk
vita_create_vpk(TLOU_Vita.vpk ${VITA_TITLEID} eboot.bin
        NAME ${VITA_APP_NAME}
        VERSION ${VITA_VERSION}
        ${VPK_ASSETS_LIST} # <-- Сюда подставятся все ваши файлы автоматически!
)

add_custom_command(TARGET TLOU_Vita POST_BUILD
        COMMAND ${CMAKE_COMMAND} --build ${CMAKE_BINARY_DIR} --target TLOU_Vita.vpk-vpk
        COMMENT "--> Packaging TLOU_Vita.vpk with all assets..."
)

set(VITA3K_APP_DIR "" CACHE PATH "Optional installed Vita3K app directory for auto-deployment")
if(NOT VITA3K_APP_DIR AND EXISTS "/mnt/c/Users/egors/AppData/Roaming/Vita3K/Vita3K/ux0/app/TLOU00001")
    set(VITA3K_APP_DIR "/mnt/c/Users/egors/AppData/Roaming/Vita3K/Vita3K/ux0/app/TLOU00001")
endif()

if(VITA3K_APP_DIR)

add_custom_command(TARGET TLOU_Vita POST_BUILD
        # 1. Копируем свежий eboot.bin прямо в папку эмулятора
        COMMAND ${CMAKE_COMMAND} -E copy ${CMAKE_CURRENT_BINARY_DIR}/eboot.bin ${VITA3K_APP_DIR}/eboot.bin

        # 2. Копируем всю папку assets со всеми .bin моделями и текстурами
        COMMAND ${CMAKE_COMMAND} -E copy_directory ${CMAKE_CURRENT_SOURCE_DIR}/assets ${VITA3K_APP_DIR}/

        COMMENT "--> [AUTO-DEPLOY] Сборка и ассеты автоматически скопированы в Vita3K!"
)
endif()
