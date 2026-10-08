#pragma once
#include <string>
#include <cmath>
#include "RenderStats.h"

// No printf-family variadic calls: Vita's formatter does not support every
// floating-point/length specifier and can shift all subsequent HUD arguments.
inline std::string HudUnsigned(uint64_t value){
    char buffer[21];char* end=buffer+sizeof(buffer);char* start=end;
    do{*--start=static_cast<char>('0'+value%10);value/=10;}while(value);
    return std::string(start,end);
}

inline std::string HudFixed(double value,unsigned decimals){
    if(!std::isfinite(value))return "N/A";
    const bool negative=value<0;value=std::abs(value);
    uint64_t scale=1;for(unsigned i=0;i<decimals;++i)scale*=10;
    if(value>1e15/static_cast<double>(scale))return "OVF";
    const uint64_t rounded=static_cast<uint64_t>(std::floor(value*scale+.5));
    std::string out=(negative?"-":"")+HudUnsigned(rounded/scale);
    if(decimals){
        std::string fraction=HudUnsigned(rounded%scale);
        out+='.';out+=std::string(decimals-fraction.size(),'0');out+=fraction;
    }
    return out;
}

inline std::string BuildHudText(double fps,double frameMs,double submitMs,double physicsMs,
                                const RenderStats& s,uint32_t collisionTriangles,bool noclip){
    const auto estimate=EstimateVitaFps(s);
    return "FPS "+HudFixed(fps,1)+"  FRAME "+HudFixed(frameMs,2)+" MS  SUBMIT "+HudFixed(submitMs,2)+" MS\n"
        +"SCENE DRAWS "+HudUnsigned(s.drawCalls)+"  TRIANGLES "+HudUnsigned(s.triangles)+"  VERTICES "+HudUnsigned(s.vertices)+"\n"
        +"OBJECTS "+HudUnsigned(s.objectsDrawn)+"/"+HudUnsigned(s.objectsTested)
        +"  CULL DIST "+HudUnsigned(s.culledDistance)+"  FRUSTUM "+HudUnsigned(s.culledFrustum)+"  INVALID "+HudUnsigned(s.invalidObjects)+"\n"
        +"TEX BINDS "+HudUnsigned(s.textureBinds)+"  VBO BINDS "+HudUnsigned(s.vboBinds)
        +"  VERTEX DATA "+HudFixed(s.vertices*16.0/1048576.0,2)+" MIB\n"
        +"VISIBLE TEX "+HudFixed(s.visibleTextureBytes/1048576.0,2)+" MIB  UPLOAD "+HudFixed(s.textureUploadBytes/1048576.0,2)+" MIB\n"
        +"NOCLIP "+(noclip?"ON":"OFF")+"  GRAVITY/COLLISION "+(noclip?"OFF":"ON")
        +"  PHYSICS "+HudFixed(physicsMs,2)+" MS ("+HudUnsigned(collisionTriangles)+" TRIS)\n"
        +"VITA MODEL "+HudFixed(estimate.low,0)+"-"+HudFixed(estimate.high,0)+" FPS (UNCALIBRATED)\n"
        +"MODEL EXCLUDES FILL/PHYSICS/STREAMING. TRIANGLE: HUD";
}
