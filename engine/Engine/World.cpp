//
// Created by egors on 30.07.2026.
//

#include "World.h"

bool World::initMemoryPools(size_t Size) {
    return true;
}

template<typename T>
    T * World::Spawn(const TLOU::Vector3 &pos) {
    return new T(pos);
}
