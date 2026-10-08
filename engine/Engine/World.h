//
// Created by egors on 30.07.2026.
//

#ifndef TLOU_VITA_WORLD_H
#define TLOU_VITA_WORLD_H
#include "Math3D.h"


class World {
public:
    World() {
        //создаем пулы
    }

public:
    bool initMemoryPools(size_t Size); //пока создаем пул аллокатор только для постоянных объектов.


    template<typename T>
    T* Spawn(const TLOU::Vector3& pos);


};


#endif //TLOU_VITA_WORLD_H