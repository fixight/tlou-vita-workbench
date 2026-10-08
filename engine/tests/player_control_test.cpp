#include "../Engine/PlayerControl.h"
#include <cassert>
#include <iostream>

int main() {
    CinematicControl control;
    PlayerControl gameplay;
    gameplay.interaction = false;
    control.SetGameplay(gameplay);
    assert(control.Get().CanMove());
    assert(!control.Get().CanInteract());
    assert(control.Begin(PlayerControl::FullCinematic()));
    assert(!control.Get().HasCharacterPhysics());
    assert(control.Get().cameraPose == PoseOwner::Cinematic);
    assert(!control.Begin(PlayerControl{})); // must not lose saved restrictions
    control.SetSegment(PlayerControl::CameraOnly());
    assert(!control.Get().CanMove());
    assert(control.Get().cameraLook);
    assert(control.Get().cameraPose == PoseOwner::Gameplay);
    control.SetGameplay(PlayerControl{}); // gameplay cannot unlock an active scene
    assert(!control.Get().CanMove());
    control.End();
    assert(!control.Active());
    assert(control.Get().CanMove());
    assert(!control.Get().CanInteract());
    control.End(); // cancellation/completion is idempotent
    assert(!control.Get().CanInteract());
    PlayerControl stationary;
    stationary.movement = false;
    assert(stationary.HasCharacterPhysics());
    assert(stationary.CanInteract());
    std::cout << "Player control ownership and restoration OK\n";
}
