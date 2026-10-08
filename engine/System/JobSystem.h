#ifndef TLOU_VITA_JOBSYSTEM_H
#define TLOU_VITA_JOBSYSTEM_H

#include <condition_variable>
#include <cstddef>
#include <mutex>
#include <queue>
#include <thread>
#include <vector>
#include <exception>
#include <system_error>

#ifdef __vita__
#include <psp2/kernel/threadmgr.h>
#include <psp2/kernel/clib.h>
#endif

struct Job {
    void (*function)(void*);
    void* data;
};

class JobSystem {
public:
    JobSystem() = default;
    JobSystem(const JobSystem&) = delete;
    JobSystem& operator=(const JobSystem&) = delete;

    ~JobSystem() {
        // The owner must outlive its callbacks: destroying it inside a job
        // would free the queue while that job is still using it.
        if (!Shutdown()) std::terminate();
    }

    // Init/Shutdown are serialized. Repeated Init does not add more workers.
    bool Init() {
        if (IsExecutingJob()) return false;
        std::lock_guard<std::mutex> lifecycleLock(m_lifecycleMutex);
        {
            std::lock_guard<std::mutex> lock(m_queueMutex);
            if (m_initialized) return false;
            m_initialized = true;
            m_acceptingJobs = true;
            m_failedJobs = 0;
        }

#if defined(__cpp_exceptions)
        try {
#endif
            m_workers.reserve(2);
            for (unsigned workerIndex = 0; workerIndex < 2; ++workerIndex) {
                m_workers.emplace_back([this, workerIndex]() {
#ifdef __vita__
                    const int cpuMask = workerIndex == 0
                        ? SCE_KERNEL_CPU_MASK_USER_1 : SCE_KERNEL_CPU_MASK_USER_2;
                    sceKernelChangeThreadCpuAffinityMask(sceKernelGetThreadId(), cpuMask);
#else
                    (void)workerIndex;
#endif
                    WorkerLoop();
                });
            }
#if defined(__cpp_exceptions)
        } catch (const std::system_error& error) {
#ifdef __vita__
            sceClibPrintf("[Jobs] Worker creation failed: %s (code %d)\n",
                error.what(), error.code().value());
#endif
            StopAndJoin();
            return false;
        } catch (...) {
#ifdef __vita__
            sceClibPrintf("[Jobs] Worker creation failed: allocation or unknown exception\n");
#endif
            // Even partially started pools must finish accepted jobs.
            StopAndJoin();
            return false;
        }
#endif
        return true;
    }

    // data is borrowed: it must remain valid until this job finishes.
    // false means the job was NOT accepted; the caller still owns the work.
    bool Execute(void (*func)(void*), void* data) {
        if (!func) return false;
        {
            std::lock_guard<std::mutex> lock(m_queueMutex);
            if (!m_acceptingJobs) return false;
            // Publish and count under one lock. If push throws, count is unchanged.
            m_jobs.push({func, data});
            ++m_unfinishedJobs;
        }
        m_workAvailable.notify_one();
        m_progress.notify_all(); // A helping Wait may also be asleep.
        return true;
    }

    // Global barrier, NOT a group fence. Concurrent producers may add more work.
    // Helps execute jobs; sleeps when only other threads' jobs remain.
    // false: called from our callback, or a callback has failed since Init.
    bool Wait() {
        if (IsExecutingJob()) return false;
        for (;;) {
            Job job;
            {
                std::unique_lock<std::mutex> lock(m_queueMutex);
                m_progress.wait(lock, [this]() {
                    return m_unfinishedJobs == 0 || !m_jobs.empty();
                });
                if (m_unfinishedJobs == 0) return m_failedJobs == 0;
                job = m_jobs.front();
                m_jobs.pop();
            }
            RunJob(job);
        }
    }

    // Drain policy: reject new jobs, finish accepted jobs, then join workers.
    // Calling this from our callback is rejected to avoid joining ourselves.
    bool Shutdown() {
        if (IsExecutingJob()) return false;
        std::lock_guard<std::mutex> lifecycleLock(m_lifecycleMutex);
        StopAndJoin();
        return true;
    }

    // A nonblocking completion check for loading behind a movie/game frame.
    std::size_t GetPendingCount() {
        std::lock_guard<std::mutex> lock(m_queueMutex);
        return m_unfinishedJobs;
    }

    std::size_t GetFailureCount() {
        std::lock_guard<std::mutex> lock(m_queueMutex);
        return m_failedJobs;
    }

private:
    // A per-thread stack also detects waiting on an outer system from a
    // nested callback of another JobSystem. No shared-thread-ID bookkeeping.
    struct ExecutionScope {
        JobSystem* system;
        ExecutionScope* previous;
    };
    inline static thread_local ExecutionScope* s_executionScope = nullptr;

    bool IsExecutingJob() const {
        for (auto* scope = s_executionScope; scope; scope = scope->previous) {
            if (scope->system == this) return true;
        }
        return false;
    }

    void RunJob(const Job& job) {
        ExecutionScope scope{this, s_executionScope};
        s_executionScope = &scope;
        bool failed = false;
#if defined(__cpp_exceptions)
        try {
            job.function(job.data);
        } catch (...) {
            // Keep workers alive and completion counts consistent.
            // Wait reports failure; it does not roll back partial job output.
            failed = true;
        }
#else
        // In builds without exceptions callbacks must not throw.
        job.function(job.data);
#endif
        s_executionScope = scope.previous;
        {
            std::lock_guard<std::mutex> lock(m_queueMutex);
            if (failed) ++m_failedJobs;
            --m_unfinishedJobs;
        }
        m_progress.notify_all();
    }

    void WorkerLoop() {
        for (;;) {
            Job job;
            {
                std::unique_lock<std::mutex> lock(m_queueMutex);
                m_workAvailable.wait(lock, [this]() {
                    return !m_jobs.empty() || !m_acceptingJobs;
                });
                // Stopping alone is not enough: drain the queue first.
                if (!m_acceptingJobs && m_jobs.empty()) return;
                job = m_jobs.front();
                m_jobs.pop();
            }
            RunJob(job);
        }
    }

    // Called with lifecycleMutex held. Never hold queueMutex while joining.
    void StopAndJoin() {
        {
            std::lock_guard<std::mutex> lock(m_queueMutex);
            if (!m_initialized) return;
            // Same mutex as the wait predicate: no lost shutdown wake-up.
            m_acceptingJobs = false;
        }
        m_workAvailable.notify_all();
        for (auto& worker : m_workers) {
            if (worker.joinable()) worker.join();
        }
        m_workers.clear();
        // Handles partial Init failure (zero workers) and concurrent Wait helpers.
        Wait();
        {
            std::lock_guard<std::mutex> lock(m_queueMutex);
            m_initialized = false;
        }
    }

    std::vector<std::thread> m_workers;
    std::queue<Job> m_jobs;
    std::mutex m_lifecycleMutex;
    std::mutex m_queueMutex;
    std::condition_variable m_workAvailable;
    std::condition_variable m_progress;

    // All these fields are protected by queueMutex. No atomics are needed
    // because queue publication, counters and wait predicates share one lock.
    bool m_initialized = false;
    bool m_acceptingJobs = false;
    std::size_t m_unfinishedJobs = 0;
    std::size_t m_failedJobs = 0;
};

#endif // TLOU_VITA_JOBSYSTEM_H
