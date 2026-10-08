#include "Engine/CinematicClock.h"
#include "Engine/PlayerControl.h"
#include <cassert>
#include <limits>
int main() {
    CinematicClock scene;
    CinematicControl controls;
    PlayerControl gameplay; gameplay.interaction = false;
    controls.SetGameplay(gameplay);
    assert(scene.Play(30.3666667)); assert(controls.Begin(PlayerControl::FullCinematic()));
    assert(!scene.Play(1)); assert(!controls.Get().CanMove());
    scene.Update(30); assert(scene.IsPlaying()); assert(!scene.ConsumeFinished());
    scene.Update(-1); scene.Update(std::numeric_limits<double>::quiet_NaN());
    assert(scene.Time()==30);
    scene.Update(5); assert(!scene.IsPlaying()); assert(scene.Time()==30.3666667);
    assert(scene.ConsumeFinished()); assert(!scene.ConsumeFinished());
    controls.End(); assert(controls.Get().CanMove()); assert(!controls.Get().interaction);
    assert(scene.Play(1)); scene.Cancel(); assert(!scene.ConsumeFinished());
    scene.Update(10); assert(scene.GetState()==CinematicClock::State::Cancelled);
    assert(!scene.Play(0));
}
