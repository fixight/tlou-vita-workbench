#pragma once
#include <vitaGL.h>
#include <vector>
#include <string>
#include "RenderStats.h"
#include "TriggerDebugView.h"

class DebugHud {
public:
    bool Init();
    void Draw(double frameSeconds,double submitMs,double physicsMs,
              const RenderStats& stats,uint32_t collisionTriangles,bool noclip,
              const std::string& triggerText = {},
              const std::vector<HudLabel>& labels = {},bool showStats = true);
private:
    struct HudVertex { float x,y,u,v,r,g,b,a; };
    GLuint program=0,texture=0,vbo=0;
    GLint position=-1,uv=-1,color=-1;
    std::vector<HudVertex> vertices;
    double elapsed=0,averageFrameMs=0;
    uint32_t frames=0;
    void Quad(float x,float y,float w,float h,float u0,float v0,float u1,float v1,
              float r,float g,float b,float a);
};
