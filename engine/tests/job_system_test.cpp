// Host regression tests: g++ -std=c++17 -pthread tests/job_system_test.cpp -o /tmp/tlou-jobs-test
#include "../System/JobSystem.h"
#include <atomic>
#include <cassert>
#include <chrono>
#include <iostream>
#include <stdexcept>

static void Increment(void* data) {
    static_cast<std::atomic<int>*>(data)->fetch_add(1);
}

struct NestedCheck {
    JobSystem* jobs;
    std::atomic<int> rejected{0};
};
static void CheckNestedCalls(void* data) {
    auto& check = *static_cast<NestedCheck*>(data);
    if (!check.jobs->Wait()) ++check.rejected;
    if (!check.jobs->Shutdown()) ++check.rejected;
    if (!check.jobs->Init()) ++check.rejected;
}

struct Gate {
    std::mutex mutex;
    std::condition_variable condition;
    int entered = 0;
    bool released = false;
};
static void Block(void* data) {
    auto& gate = *static_cast<Gate*>(data);
    std::unique_lock<std::mutex> lock(gate.mutex);
    ++gate.entered;
    gate.condition.notify_all();
    gate.condition.wait(lock, [&]() { return gate.released; });
}
static void WaitForWorkers(Gate& gate) {
    std::unique_lock<std::mutex> lock(gate.mutex);
    assert(gate.condition.wait_for(lock, std::chrono::seconds(3), [&]() {
        return gate.entered == 2;
    }));
}
static void Release(Gate& gate) {
    {
        std::lock_guard<std::mutex> lock(gate.mutex);
        gate.released = true;
    }
    gate.condition.notify_all();
}

int main() {
    JobSystem jobs;
    std::atomic<int> completed{0};
    assert(!jobs.Execute(Increment, &completed));
    assert(jobs.Wait());
    assert(jobs.Init());
    assert(!jobs.Init());
    assert(!jobs.Execute(nullptr, nullptr));

    // Concurrent publication: every accepted job must execute exactly once.
    std::vector<std::thread> producers;
    for (int p = 0; p < 4; ++p) {
        producers.emplace_back([&]() {
            for (int j = 0; j < 2000; ++j) assert(jobs.Execute(Increment, &completed));
        });
    }
    for (auto& producer : producers) producer.join();
    assert(jobs.Wait());
    assert(completed == 8000);

    NestedCheck nested{&jobs};
    assert(jobs.Execute(CheckNestedCalls, &nested));
    assert(jobs.Wait());
    assert(nested.rejected == 3);

    assert(jobs.Execute([](void*) { throw std::runtime_error("expected"); }, nullptr));
    assert(!jobs.Wait());
    assert(jobs.GetFailureCount() == 1);
    assert(jobs.Execute(Increment, &completed));
    assert(!jobs.Wait()); // Failure status persists until the next Init.
    assert(completed == 8001);
    assert(jobs.Shutdown());

    // Both workers are busy: Wait must help, not just wait for them.
    assert(jobs.Init());
    assert(jobs.GetFailureCount() == 0);
    Gate helpGate;
    assert(jobs.Execute(Block, &helpGate));
    assert(jobs.Execute(Block, &helpGate));
    WaitForWorkers(helpGate);
    const auto mainThread = std::this_thread::get_id();
    struct HelperData { Gate* gate; std::thread::id mainThread; bool ranOnMain = false; };
    HelperData helper{&helpGate, mainThread};
    assert(jobs.Execute([](void* data) {
        auto& h = *static_cast<HelperData*>(data);
        h.ranOnMain = std::this_thread::get_id() == h.mainThread;
        Release(*h.gate);
    }, &helper));
    assert(jobs.Wait());
    assert(helper.ranOnMain);
    assert(jobs.Shutdown());

    // Shutdown racing a producer: reject new work, drain all accepted work.
    assert(jobs.Init());
    Gate shutdownGate;
    assert(jobs.Execute(Block, &shutdownGate));
    assert(jobs.Execute(Block, &shutdownGate));
    WaitForWorkers(shutdownGate);
    std::atomic<int> drained{0};
    int accepted = 100;
    for (int i = 0; i < accepted; ++i) assert(jobs.Execute(Increment, &drained));
    std::thread stopper([&]() { assert(jobs.Shutdown()); });
    const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (jobs.Execute(Increment, &drained)) {
        ++accepted;
        assert(std::chrono::steady_clock::now() < deadline);
        std::this_thread::yield();
    }
    Release(shutdownGate);
    stopper.join();
    assert(drained == accepted);
    assert(jobs.Wait());
    assert(!jobs.Execute(Increment, &drained));

    // A loading frame must poll completion without executing blocked worker jobs.
    assert(jobs.Init());
    Gate movieGate;
    assert(jobs.Execute(Block, &movieGate));
    assert(jobs.Execute(Block, &movieGate));
    WaitForWorkers(movieGate);
    assert(jobs.GetPendingCount() == 2);
    Release(movieGate);
    const auto movieDeadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
    while (jobs.GetPendingCount() != 0) {
        assert(std::chrono::steady_clock::now() < movieDeadline);
        std::this_thread::yield();
    }
    assert(jobs.Wait());
    assert(jobs.GetPendingCount() == 0);
    assert(jobs.Shutdown());

    // Repeated idle shutdown stresses the condition-variable wake-up race.
    for (int i = 0; i < 300; ++i) {
        assert(jobs.Init());
        assert(jobs.Shutdown());
    }
    std::cout << "JobSystem: all regression checks passed\n";
}
