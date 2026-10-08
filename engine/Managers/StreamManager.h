//
// Created by egors on 13.08.2026.
//

#ifndef TLOU_VITA_STREAMMANAGER_H
#define TLOU_VITA_STREAMMANAGER_H
#include "../Memory/StackAllocator.h"

struct Level {
    int id;

    StackAllocator::Marker marker; // Закладка для выгрузки

    ///MemorySlice<CollisionInstance> colliders;
};

class StreamManager {
};


#endif //TLOU_VITA_STREAMMANAGER_H