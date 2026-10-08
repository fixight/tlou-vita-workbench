#include "TriggerDebugView.h"
#include "Render.h"
#include "glm/gtc/matrix_transform.hpp"
#include "glm/gtc/type_ptr.hpp"
#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <cctype>

namespace {
constexpr unsigned maxBoxes=8;
const char* vs=R"(
attribute vec3 aPosition;
attribute vec3 aColor;
uniform mat4 uMVP;
varying vec3 vColor;
void main(){gl_Position=uMVP*vec4(aPosition,1.0);vColor=aColor;}
)";
const char* fs=R"(
precision mediump float;
varying vec3 vColor;
void main(){gl_FragColor=vec4(vColor,1.0);}
)";
float DistanceSquared(const TriggerManager::Box& box,const TLOU::Vector3& eye){
    const float point[]={eye.x,eye.y,eye.z};float result=0;
    for(unsigned i=0;i<3;++i){float d=std::max(box.min[i]-point[i],std::max(0.f,point[i]-box.max[i]));result+=d*d;}
    return result;
}
bool Visible(const TriggerManager::Box& box,const Frustum& frustum){
    for(const auto& p:frustum.planes){
        float x=p.a>=0?box.max[0]:box.min[0],y=p.b>=0?box.max[1]:box.min[1],z=p.c>=0?box.max[2]:box.min[2];
        if(p.a*x+p.b*y+p.c*z+p.d<0)return false;
    }
    return true;
}
}

std::string TriggerDebugView::ShortName(std::string name){
    for(const auto& prefix:{"hom-house-","hom-","rgn-","region-"})
        if(name.compare(0,std::char_traits<char>::length(prefix),prefix)==0)name.erase(0,std::char_traits<char>::length(prefix));
    for(char& c:name){if(c=='-'||c=='_')c=' ';else c=static_cast<char>(std::toupper(static_cast<unsigned char>(c)));}
    if(name.size()>38)name=name.substr(0,35)+"...";
    return name;
}

bool TriggerDebugView::Init(){
    program=Render::CompileShader(vs,fs);if(!program)return false;
    position=glGetAttribLocation(program,"aPosition");color=glGetAttribLocation(program,"aColor");
    mvp=glGetUniformLocation(program,"uMVP");
    glGenBuffers(1,&vbo);glBindBuffer(GL_ARRAY_BUFFER,vbo);
    glBufferData(GL_ARRAY_BUFFER,maxBoxes*24*sizeof(Vertex),nullptr,GL_DYNAMIC_DRAW);
    glBindBuffer(GL_ARRAY_BUFFER,0);vertices.reserve(maxBoxes*24);labels.reserve(3);return true;
}

void TriggerDebugView::Draw(const TriggerManager& manager,CameraActor* camera,bool showHud){
    vertices.clear();labels.clear();
    legend=mode==0?"TRIGGER VIEW OFF - CIRCLE: NEARBY":mode==1?
        "TRIGGER VIEW NEARBY - CIRCLE: FOCUS":"TRIGGER VIEW FOCUS - CIRCLE: OFF";
    legend+="\nCYAN: AREA  GREEN: INSIDE  RANGE: 12M\n";
    if(!mode||!program||!camera)return;
    const auto eye=camera->GetPosition(),forward=camera->GetForwardVector();
    glm::mat4 vp=glm::perspective(glm::radians(45.f),960.f/544.f,.5f,150.f)*
        glm::lookAt(glm::vec3(eye.x,eye.y,eye.z),glm::vec3(eye.x+forward.x,eye.y+forward.y,eye.z+forward.z),glm::vec3(0,1,0));
    Frustum frustum;frustum.extractFromMatrix(glm::value_ptr(vp));
    struct Candidate{const TriggerManager::Trigger* trigger=nullptr;float distance=0;};
    std::array<Candidate,3> nearest{};unsigned count=0;const unsigned limit=mode==2?1:3;
    auto better=[](const Candidate& a,const Candidate& b){
        if(a.trigger->inside!=b.trigger->inside)return a.trigger->inside;
        return a.distance<b.distance;
    };
    for(const auto& trigger:manager.GetTriggers()){
        float distance=1e30f;
        for(const auto& box:trigger.volumes){
            // Giant scene-wide areas would hide local door/room triggers.
            const float size=std::max({box.max[0]-box.min[0],box.max[1]-box.min[1],box.max[2]-box.min[2]});
            if(size<=40.f&&Visible(box,frustum))distance=std::min(distance,DistanceSquared(box,eye));
        }
        if(distance>144.f)continue;
        Candidate candidate{&trigger,distance};unsigned insertion=0;
        while(insertion<count&&!better(candidate,nearest[insertion]))++insertion;
        if(insertion>=limit)continue;
        for(unsigned i=std::min(count,limit-1);i>insertion;--i)nearest[i]=nearest[i-1];
        nearest[insertion]=candidate;if(count<limit)++count;
    }
    constexpr unsigned edges[24]={0,1,1,3,3,2,2,0,4,5,5,7,7,6,6,4,0,4,1,5,2,6,3,7};
    unsigned boxes=0;
    for(unsigned index=0;index<count;++index){
        const auto& trigger=*nearest[index].trigger;
        const float r=trigger.inside?.35f:.25f,g=trigger.inside?1.f:.8f,b=trigger.inside?.4f:1.f;
        const TriggerManager::Box* anchor=nullptr;float anchorDistance=1e30f;
        for(const auto& box:trigger.volumes){
            const float size=std::max({box.max[0]-box.min[0],box.max[1]-box.min[1],box.max[2]-box.min[2]});
            const float d=DistanceSquared(box,eye);
            if(size>40.f||d>144.f||!Visible(box,frustum)||boxes==maxBoxes)continue;
            ++boxes;
            if(d<anchorDistance){anchor=&box;anchorDistance=d;}
            for(unsigned corner:edges)vertices.push_back({
                corner&1?box.max[0]:box.min[0],corner&2?box.max[1]:box.min[1],corner&4?box.max[2]:box.min[2],r,g,b});
        }
        if(!anchor)continue;
        glm::vec4 clip=vp*glm::vec4((anchor->min[0]+anchor->max[0])*.5f,
            (anchor->min[1]+anchor->max[1])*.5f,(anchor->min[2]+anchor->max[2])*.5f,1);
        if(clip.w<=.5f||clip.z < -clip.w||clip.z>clip.w)continue;
        const float x=(clip.x/clip.w+1.f)*480.f,y=(1.f-clip.y/clip.w)*272.f;
        if(x<0||x>960||y<0||y>544)continue;
        std::string text=std::to_string(index+1)+": "+ShortName(trigger.name)+(trigger.inside?" [INSIDE]":"");
        // Keep labels away from the statistics panel and from one another.
        float labelX=std::max(12.f,std::min(x,948.f-6.f*text.size()));
        float labelY=std::max(showHud?310.f:16.f,std::min(y,510.f));
        for(const auto& previous:labels)
            if(std::abs(labelY-previous.y)<24&&labelX<previous.x+6*previous.text.size()+10&&labelX+6*text.size()+10>previous.x)
                labelY=previous.y+24;
        if(labelY>520)labelY=showHud?310.f:16.f;
        labels.push_back({labelX,labelY,text,r,g,b,x,y});
    }
    if(vertices.empty())return;
    glEnable(GL_DEPTH_TEST);glDepthMask(GL_FALSE);glDisable(GL_CULL_FACE);glDisable(GL_BLEND);
    glUseProgram(program);glUniformMatrix4fv(mvp,1,GL_FALSE,glm::value_ptr(vp));
    glBindBuffer(GL_ARRAY_BUFFER,vbo);glBufferSubData(GL_ARRAY_BUFFER,0,vertices.size()*sizeof(Vertex),vertices.data());
    if(position>=0){glEnableVertexAttribArray(position);glVertexAttribPointer(position,3,GL_FLOAT,GL_FALSE,sizeof(Vertex),(void*)offsetof(Vertex,x));}
    if(color>=0){glEnableVertexAttribArray(color);glVertexAttribPointer(color,3,GL_FLOAT,GL_FALSE,sizeof(Vertex),(void*)offsetof(Vertex,r));}
    glDrawArrays(GL_LINES,0,static_cast<GLsizei>(vertices.size()));
    if(position>=0)glDisableVertexAttribArray(position);
    if(color>=0)glDisableVertexAttribArray(color);
    glBindBuffer(GL_ARRAY_BUFFER,0);glUseProgram(0);glDepthMask(GL_TRUE);
}
