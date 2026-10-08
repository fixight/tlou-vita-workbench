#pragma once
#include "NativeStreaming.h"
namespace TlouStreaming {
inline StoryState InitialHomeState(){
    StoryState state;
    state.SetTask("home","hom-town-crash-rescue-outro",TaskStatus::Pending);
    state.SetTask("home","hom-town-cinema",TaskStatus::Pending);
    state.SetTask("home","hom-house-escape",TaskStatus::Pending);
    state.SetTask("home","hom-road-highway",TaskStatus::Pending);
    state.SetTask("home","hom-road-woods-start",TaskStatus::Pending);
    state.SetTask("home","hom-house-downstairs",TaskStatus::Pending);
    state.SetTask("home","hom-house-daughter-room-phone",TaskStatus::Pending);
    state.SetTask("home","hom-road-suburbs-intersection",TaskStatus::Pending);
    state.SetTask("home","hom-town-shops-start",TaskStatus::Pending);
    state.SetTask("home","movie-hom-mil-transition",TaskStatus::Pending);
    state.SetTask("home","hom-house-study",TaskStatus::Pending);
    state.SetTask("home","hom-town-shops-end",TaskStatus::Pending);
    state.SetTask("home","hom-road-freeway-traffic",TaskStatus::Pending);
    state.SetTask("home","hom-alley-bar-split-up",TaskStatus::Pending);
    state.SetTask("home","hom-woods-chase",TaskStatus::Pending);
    state.SetTask("home","hom-alley-clear",TaskStatus::Pending);
    state.SetTask("home","hom-road-suburbs-start",TaskStatus::Pending);
    state.SetTask("home","hom-town-crash-rescue-kick",TaskStatus::Pending);
    state.SetTask("home","hom-alley-bar-enter",TaskStatus::Pending);
    state.SetTask("home","hom-alley-start",TaskStatus::Pending);
    state.SetTask("home","hom-town-gas-station",TaskStatus::Pending);
    state.SetTask("home","hom-house-daughter-room",TaskStatus::Pending);
    state.SetTask("home","hom-town-crash",TaskStatus::Pending);
    state.SetTask("home","hom-house-joel-room",TaskStatus::Pending);
    state.SetTask("home","hom-town-crash-rescue-intro",TaskStatus::Pending);
    state.SetTask("home","hom-alley-parking-lot",TaskStatus::Pending);
    state.SetTask("home","hom-town-run-start",TaskStatus::Pending);
    state.SetTask("home","hom-house-daughter-room-phone",TaskStatus::Active);
    state.spawned[0x69c85a6du]=true;
    state.SetSarahCarStarted(false);
    return state;
}
}