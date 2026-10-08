//
// Created by egors on 05.08.2026.
//

#ifndef TLOU_VITA_BASECOMPONENT_H
#define TLOU_VITA_BASECOMPONENT_H
#include "Objects/Actor.h"


class BaseComponent {
    public:
    BaseComponent() {

    }
    virtual ~BaseComponent() {

    }

protected:
    TLOU::Actor Owner;

public:
    void SetOwner(TLOU::Actor Owner) {
        this->Owner = Owner;
    }

    void OnStart();

    void Update(float dt);
};


#endif //TLOU_VITA_BASECOMPONENT_H