#ifndef TLOU_VITA_THREADMANAGER_H
#define TLOU_VITA_THREADMANAGER_H

#include <cstdint>
#include <string>
#include <vector>
#include <thread>
#include <queue>
#include <functional>
#include <mutex>
#include <condition_variable>
#include <atomic>

#include <psp2/kernel/threadmgr.h>

class VitaThread {
public:
    VitaThread(const std::string& threadName,
               SceKernelThreadEntry entry,
               int priority = 0x10000100,                        // SCE_KERNEL_DEFAULT_PRIORITY_USER
               SceSize stackSize = 64 * 1024,                    // 64 КБ стека по умолчанию
               int cpuAffinityMask = SCE_KERNEL_CPU_MASK_USER_1) // Ядро 1 по умолчанию
        : m_threadName(threadName),
          m_priority(priority),
          m_stackSize(stackSize),
          m_cpuMask(cpuAffinityMask),
          m_entry(entry),
          m_threadID(-1),
          m_isRunning(false)
    {
        // 1. Создаем нативный поток Vita
        m_threadID = sceKernelCreateThread(
            m_threadName.c_str(),
            m_entry,
            m_priority,
            m_stackSize,
            0,
            m_cpuMask,
            nullptr
        );
    }

    // Запрещаем копирование (чтобы два объекта не владели одним ID потока)
    VitaThread(const VitaThread&) = delete;
    VitaThread& operator=(const VitaThread&) = delete;

    // Разрешаем перемещение для безопасной работы с std::vector
    VitaThread(VitaThread&& other) noexcept
        : m_threadName(std::move(other.m_threadName)),
          m_priority(other.m_priority),
          m_stackSize(other.m_stackSize),
          m_cpuMask(other.m_cpuMask),
          m_entry(other.m_entry),
          m_threadID(other.m_threadID),
          m_isRunning(other.m_isRunning)
    {
        other.m_threadID = -1;
        other.m_isRunning = false;
    }

    VitaThread& operator=(VitaThread&& other) noexcept {
        if (this != &other) {
            if (m_threadID >= 0) {
                sceKernelDeleteThread(m_threadID);
            }
            m_threadName = std::move(other.m_threadName);
            m_priority = other.m_priority;
            m_stackSize = other.m_stackSize;
            m_cpuMask = other.m_cpuMask;
            m_entry = other.m_entry;
            m_threadID = other.m_threadID;
            m_isRunning = other.m_isRunning;

            other.m_threadID = -1;
            other.m_isRunning = false;
        }
        return *this;
    }

    // Деструктор: подчищаем поток
    ~VitaThread() {
        if (m_threadID >= 0) {
            sceKernelDeleteThread(m_threadID);
            m_threadID = -1;
        }
    }

    // Запуск потока
    bool Start(SceSize arglen = 0, void *argp = nullptr) {
        if (m_threadID < 0) {
            return false;
        }

        int ret = sceKernelStartThread(m_threadID, arglen, argp);
        if (ret >= 0) {
            m_isRunning = true;
            return true;
        }
        return false;
    }

    // Дождаться завершения потока
    void Join() {
        if (m_threadID >= 0 && m_isRunning) {
            sceKernelWaitThreadEnd(m_threadID, nullptr, nullptr);
            m_isRunning = false;
        }
    }

    bool IsValid() const { return m_threadID >= 0; }
    SceUID GetID() const { return m_threadID; }

public:
    std::string m_threadName;
    int m_priority;
    SceSize m_stackSize;
    int m_cpuMask;
    SceKernelThreadEntry m_entry;
    SceUID m_threadID;
    bool m_isRunning;
};

// ==========================================
// ThreadManager
// ==========================================
class ThreadManager {
public:
    ThreadManager() = default;

    ~ThreadManager() {
        for (auto& th : m_threads) {
            th.Join();
        }
    }

    bool CreateAndStartThread(const std::string& name,
                              SceKernelThreadEntry entry,
                              int cpuMask = SCE_KERNEL_CPU_MASK_USER_1,
                              SceSize arglen = 0,
                              void* argp = nullptr,
                              int priority = 0x10000100,
                              SceSize stackSize = 64 * 1024)
    {
        m_threads.emplace_back(name, entry, priority, stackSize, cpuMask);
        VitaThread& newThread = m_threads.back();

        if (!newThread.IsValid()) {
            m_threads.pop_back();
            return false;
        }

        return newThread.Start(arglen, argp);
    }

private:
    std::vector<VitaThread> m_threads;
};

// JobSystem is portable and can be tested without the Vita runtime.
#include "JobSystem.h"

#endif // TLOU_VITA_THREADMANAGER_H
