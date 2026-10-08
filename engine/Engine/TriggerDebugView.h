#pragma once
#include <vitaGL.h>
#include <string>
#include <vector>
#include "TriggerManager.h"
#include "Objects/CameraActor.h"

struct HudLabel {
    float x=0,y=0;
    std::string text;
    float r=.3f,g=.85f,b=1.f;
    float anchorX=-1,anchorY=-1;
};

class TriggerDebugView {
public:
    bool Init();
    // 0 = off, 1 = three nearby areas, 2 = only the nearest visible area.
    void CycleMode() { mode=(mode+1)%3; }
    unsigned GetMode() const { return mode; }
    void Draw(const TriggerManager& manager, CameraActor* camera, bool showHud);
    const std::vector<HudLabel>& GetLabels() const { return labels; }
    const std::string& GetLegend() const { return legend; }
    static std::string ShortName(std::string name);
private:
    struct Vertex { float x,y,z,r,g,b; };
    GLuint program=0,vbo=0;
    GLint position=-1,color=-1,mvp=-1;
    unsigned mode=1;
    std::vector<Vertex> vertices;
    std::vector<HudLabel> labels;
    std::string legend;
};
