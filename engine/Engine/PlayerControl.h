#pragma once

// Input permissions and pose ownership are independent: disabling walking must
// not disable a scripted animation or a camera that still follows the actor.
enum class PoseOwner { Gameplay, Cinematic };

struct PlayerControl {
    PoseOwner characterPose = PoseOwner::Gameplay;
    PoseOwner cameraPose = PoseOwner::Gameplay;
    bool movement = true;
    bool cameraLook = true;
    bool interaction = true;
    bool debugCamera = true;

    bool CanMove() const { return characterPose == PoseOwner::Gameplay && movement; }
    bool CanInteract() const { return characterPose == PoseOwner::Gameplay && interaction; }
    bool HasCharacterPhysics() const { return characterPose == PoseOwner::Gameplay; }

    static PlayerControl FullCinematic() {
        return {PoseOwner::Cinematic, PoseOwner::Cinematic, false, false, false, false};
    }
    static PlayerControl CameraOnly() {
        return {PoseOwner::Cinematic, PoseOwner::Gameplay, false, true, false, false};
    }
};

// Saves the previous policy once, including any restrictions set by gameplay.
// End() is also the cancellation/error path. Nested starts are rejected.
class CinematicControl {
public:
    const PlayerControl& Get() const { return current; }
    bool Active() const { return active; }
    bool Begin(const PlayerControl& policy) {
        if (active) return false;
        saved = current;
        current = policy;
        active = true;
        return true;
    }
    void SetSegment(const PlayerControl& policy) {
        if (active) current = policy;
    }
    void SetGameplay(const PlayerControl& policy) {
        if (!active) current = policy;
    }
    void End() {
        if (!active) return;
        current = saved;
        active = false;
    }
private:
    PlayerControl current{}, saved{};
    bool active = false;
};
