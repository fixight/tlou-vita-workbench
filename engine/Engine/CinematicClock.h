#pragma once
#include <algorithm>
#include <cmath>

// A completed scene stays completed until explicitly restarted.
class CinematicClock {
public:
    enum class State { Ready, Playing, Finished, Cancelled };
    bool Play(double duration) {
        if (state == State::Playing || !std::isfinite(duration) || duration <= 0) return false;
        length = duration; time = 0; finishedEvent = false; state = State::Playing; return true;
    }
    void Update(double deltaSeconds) {
        if (state != State::Playing || !std::isfinite(deltaSeconds) || deltaSeconds < 0) return;
        time = std::min(length, time + deltaSeconds);
        if (time >= length) { state = State::Finished; finishedEvent = true; }
    }
    void Cancel() { if (state == State::Playing) state = State::Cancelled; finishedEvent = false; }
    bool ConsumeFinished() { bool result = finishedEvent; finishedEvent = false; return result; }
    State GetState() const { return state; }
    bool IsPlaying() const { return state == State::Playing; }
    double Time() const { return time; }
private:
    State state = State::Ready;
    double time = 0, length = 0;
    bool finishedEvent = false;
};
