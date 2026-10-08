#include <algorithm>
#include "DebugHud.h"
#include "Render.h"
#include <array>
#include "DebugHudText.h"
#include <cstddef>
#include <cctype>

namespace {
struct Glyph { char code; unsigned char rows[7]; };
const Glyph glyphs[]={
 {'A',{14,17,17,31,17,17,17}}, {'B',{30,17,17,30,17,17,30}},
 {'C',{14,17,16,16,16,17,14}}, {'D',{30,17,17,17,17,17,30}},
 {'E',{31,16,16,30,16,16,31}}, {'F',{31,16,16,30,16,16,16}},
 {'G',{14,17,16,23,17,17,15}}, {'H',{17,17,17,31,17,17,17}},
 {'I',{14,4,4,4,4,4,14}}, {'J',{7,2,2,2,18,18,12}},
 {'K',{17,18,20,24,20,18,17}}, {'L',{16,16,16,16,16,16,31}},
 {'M',{17,27,21,21,17,17,17}}, {'N',{17,25,21,19,17,17,17}},
 {'O',{14,17,17,17,17,17,14}}, {'P',{30,17,17,30,16,16,16}},
 {'Q',{14,17,17,17,21,18,13}}, {'R',{30,17,17,30,20,18,17}},
 {'S',{15,16,16,14,1,1,30}}, {'T',{31,4,4,4,4,4,4}},
 {'U',{17,17,17,17,17,17,14}}, {'V',{17,17,17,17,17,10,4}},
 {'W',{17,17,17,21,21,21,10}}, {'X',{17,17,10,4,10,17,17}},
 {'Y',{17,17,10,4,4,4,4}}, {'Z',{31,1,2,4,8,16,31}},
 {'0',{14,17,19,21,25,17,14}}, {'1',{4,12,4,4,4,4,14}},
 {'2',{14,17,1,2,4,8,31}}, {'3',{30,1,1,14,1,1,30}},
 {'4',{2,6,10,18,31,2,2}}, {'5',{31,16,16,30,1,1,30}},
 {'6',{14,16,16,30,17,17,14}}, {'7',{31,1,2,4,8,8,8}},
 {'8',{14,17,17,14,17,17,14}}, {'9',{14,17,17,15,1,1,14}},
 {'.',{0,0,0,0,0,12,12}}, {':',{0,12,12,0,12,12,0}},
 {'-',{0,0,0,31,0,0,0}}, {'/',{1,2,2,4,8,8,16}},
 {'(',{2,4,8,8,8,4,2}}, {')',{8,4,2,2,2,4,8}},
 {'%',{17,2,4,8,16,17,0}}, {'+',{0,4,4,31,4,4,0}},
 {'[',{14,8,8,8,8,8,14}}, {']',{14,2,2,2,2,2,14}}, {'?',{14,17,1,2,4,0,4}}, {'_',{0,0,0,0,0,0,31}}
};
const char* hudVs=R"(
attribute vec2 aPosition;
attribute vec2 aTexCoord;
attribute vec4 aColor;
varying vec2 vUV;
varying vec4 vColor;
void main(){gl_Position=vec4(aPosition,0.0,1.0);vUV=aTexCoord;vColor=aColor;}
)";
const char* hudFs=R"(
precision mediump float;
uniform sampler2D uTexture;
varying vec2 vUV;
varying vec4 vColor;
void main(){gl_FragColor=vec4(vColor.rgb,vColor.a*texture2D(uTexture,vUV).a);}
)";
constexpr size_t maxVertices=8192;
}

bool DebugHud::Init() {
    program=Render::CompileShader(hudVs,hudFs);
    if(!program)return false;
    position=glGetAttribLocation(program,"aPosition");
    uv=glGetAttribLocation(program,"aTexCoord");
    color=glGetAttribLocation(program,"aColor");
    std::array<unsigned char,128*64*4> atlas{};
    for(size_t i=0;i<atlas.size();i+=4)atlas[i]=atlas[i+1]=atlas[i+2]=255;
    atlas[3]=255; // Reserved white pixel for the background rectangle.
    for(const auto& glyph:glyphs){
        int x=(glyph.code%16)*8,y=(glyph.code/16)*8;
        for(int row=0;row<7;++row)for(int col=0;col<5;++col)
            if(glyph.rows[row]&(1<<(4-col)))atlas[((y+row)*128+x+col)*4+3]=255;
    }
    glGenTextures(1,&texture);glBindTexture(GL_TEXTURE_2D,texture);
    glTexImage2D(GL_TEXTURE_2D,0,GL_RGBA,128,64,0,GL_RGBA,GL_UNSIGNED_BYTE,atlas.data());
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
    glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
    glGenBuffers(1,&vbo);glBindBuffer(GL_ARRAY_BUFFER,vbo);
    glBufferData(GL_ARRAY_BUFFER,maxVertices*sizeof(HudVertex),nullptr,GL_DYNAMIC_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER,0);glBindTexture(GL_TEXTURE_2D,0);
    vertices.reserve(maxVertices);
    return true;
}

void DebugHud::Quad(float x,float y,float w,float h,float u0,float v0,float u1,float v1,
                    float r,float g,float b,float a){
    if(vertices.size()+6>maxVertices)return;
    float left=x/480.f-1.f,right=(x+w)/480.f-1.f;
    float top=1.f-y/272.f,bottom=1.f-(y+h)/272.f;
    HudVertex tl{left,top,u0,v0,r,g,b,a},tr{right,top,u1,v0,r,g,b,a};
    HudVertex bl{left,bottom,u0,v1,r,g,b,a},br{right,bottom,u1,v1,r,g,b,a};
    vertices.insert(vertices.end(),{tl,bl,tr,tr,bl,br});
}

void DebugHud::Draw(double frameSeconds,double submitMs,double physicsMs,
                     const RenderStats& stats,uint32_t collisionTriangles,bool noclip,const std::string& triggerText,const std::vector<HudLabel>& labels,bool showStats){
    if(!program)return;
    elapsed+=frameSeconds;++frames;
    if(elapsed>=.5){averageFrameMs=elapsed*1000.0/frames;elapsed=0;frames=0;}
    const double fps=averageFrameMs>0?1000.0/averageFrameMs:0;
    std::string text=BuildHudText(fps,averageFrameMs,submitMs,physicsMs,stats,collisionTriangles,noclip);
    if(!triggerText.empty()) { if(!text.empty() && text.back()!='\n') text+='\n'; text+=triggerText; }
    if(!showStats)text.clear();
    vertices.clear();
    const float panelHeight=std::max(140.f,20.f+16.f*float(std::count(text.begin(),text.end(),'\n')));
    if(showStats)Quad(8,8,932,panelHeight,.5f/128.f,.5f/64.f,.5f/128.f,.5f/64.f,0,0,0,.72f);
    float x=14,y=14;
    for(const unsigned char* ptr=reinterpret_cast<const unsigned char*>(text.c_str());*ptr;++ptr){
        if(*ptr=='\n'){x=14;y+=16;continue;}
        const int ch=std::toupper(*ptr);
        if(ch!=' '){
            float u=(ch%16)*8.f/128.f,v=(ch/16)*8.f/64.f;
            Quad(x,y,10,14,u,v,u+5.f/128.f,v+7.f/64.f,.65f,1.f,.72f,1.f);
        }
        x+=12;
    }
    for(const auto& label:labels){
        if(label.anchorX>=0&&label.anchorY>=0&&(!showStats||label.anchorY>panelHeight+12)){
            const float u=.5f/128.f,v=.5f/64.f;
            Quad(label.anchorX-2,label.anchorY-2,4,4,u,v,u,v,label.r,label.g,label.b,1);
            Quad(std::min(label.anchorX,label.x),label.anchorY,std::abs(label.anchorX-label.x)+1,1,u,v,u,v,label.r,label.g,label.b,.65f);
            Quad(label.x,std::min(label.anchorY,label.y),1,std::abs(label.anchorY-label.y)+1,u,v,u,v,label.r,label.g,label.b,.65f);
        }
        const float width=6.f*label.text.size()+12.f;
        Quad(label.x-5,label.y-4,width,18,.5f/128.f,.5f/64.f,.5f/128.f,.5f/64.f,0,0,0,.85f);
        float lx=label.x;
        for(unsigned char raw:label.text){
            int ch=std::toupper(raw);if(ch>=128)ch='?';
            if(ch!=' '){float u=(ch%16)*8.f/128.f,v=(ch/16)*8.f/64.f;
                Quad(lx,label.y,5,9,u,v,u+5.f/128.f,v+7.f/64.f,label.r,label.g,label.b,1);}
            lx+=6;
        }
    }
    glDisable(GL_DEPTH_TEST);glDepthMask(GL_FALSE);glDisable(GL_CULL_FACE);
    glEnable(GL_BLEND);glBlendFunc(GL_SRC_ALPHA,GL_ONE_MINUS_SRC_ALPHA);
    glUseProgram(program);glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,texture);
    glUniform1i(glGetUniformLocation(program,"uTexture"),0);
    glBindBuffer(GL_ARRAY_BUFFER,vbo);
    glBufferSubData(GL_ARRAY_BUFFER,0,vertices.size()*sizeof(HudVertex),vertices.data());
    if(position>=0){glEnableVertexAttribArray(position);glVertexAttribPointer(position,2,GL_FLOAT,GL_FALSE,sizeof(HudVertex),(void*)offsetof(HudVertex,x));}
    if(uv>=0){glEnableVertexAttribArray(uv);glVertexAttribPointer(uv,2,GL_FLOAT,GL_FALSE,sizeof(HudVertex),(void*)offsetof(HudVertex,u));}
    if(color>=0){glEnableVertexAttribArray(color);glVertexAttribPointer(color,4,GL_FLOAT,GL_FALSE,sizeof(HudVertex),(void*)offsetof(HudVertex,r));}
    glDrawArrays(GL_TRIANGLES,0,static_cast<GLsizei>(vertices.size()));
    if(position>=0)glDisableVertexAttribArray(position);
    if(uv>=0)glDisableVertexAttribArray(uv);
    if(color>=0)glDisableVertexAttribArray(color);
    glBindBuffer(GL_ARRAY_BUFFER,0);glBindTexture(GL_TEXTURE_2D,0);glUseProgram(0);
    glDisable(GL_BLEND);glDepthMask(GL_TRUE);glEnable(GL_DEPTH_TEST);
}
