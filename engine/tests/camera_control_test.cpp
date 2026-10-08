// Exercise the actual camera controller using SDK input types and a fake pad.
#include "../Objects/CameraActor.cpp"
#include <cassert>
#include <iostream>

static SceCtrlData input{};
int sceCtrlPeekBufferPositive(int, SceCtrlData* data, int) {
    *data = input;
    return 1;
}

int main() {
    input.lx = input.ly = input.rx = input.ry = 128;
    TLOU::Actor target;
    CameraActor camera;
    camera.SetTarget(&target);
    camera.SetPosition({5, 6, 7});
    camera.SetRotation({10, 20, 0});
    camera.SetMode(CameraMode::Spectate);
    camera.SetPlayerControl(PlayerControl::FullCinematic());
    input.lx = input.rx = 255;
    input.buttons = SCE_CTRL_SELECT | SCE_CTRL_RTRIGGER;
    camera.Update(.1f);
    assert(camera.GetPosition().x == 5 && camera.GetPosition().y == 6);
    assert(camera.GetRotation().y == 20); // no input and no orbit-follow
    assert(camera.GetMode() == CameraMode::ThirdPerson);
    camera.SetPlayerControl(PlayerControl::CameraOnly());
    camera.Update(.1f);
    assert(camera.GetYaw() < 20); // right stick works, SELECT does not
    assert(camera.GetMode() == CameraMode::ThirdPerson);
    camera.SetPlayerControl(PlayerControl{});
    camera.Update(.1f); // SELECT is still held: no accidental mode toggle
    assert(camera.GetMode() == CameraMode::Spectate);
    input.buttons = 0;
    camera.Update(.1f);
    input.buttons = SCE_CTRL_SELECT;
    camera.Update(.1f);
    assert(camera.GetMode() == CameraMode::ThirdPerson);
    PlayerControl frozen;
    frozen.movement = false;
    frozen.cameraLook = false;
    camera.SetMode(CameraMode::Spectate);
    camera.SetPlayerControl(frozen);
    auto before = camera.GetPosition();
    input.buttons = SCE_CTRL_RTRIGGER;
    camera.Update(.1f);
    assert(camera.GetPosition().x == before.x && camera.GetPosition().y == before.y);
    std::cout << "Camera input, pose ownership and held-button handoff OK\n";
}
