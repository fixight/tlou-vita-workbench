#pragma once
#include <glm/glm.hpp>
#include <algorithm>
#include <cmath>

// One allocation-free cooperative process per character. It owns execution
// state; the level owns immutable animation/entry data.
class InteractionProcess {
public:
    enum class State { Idle, Approach, Ready, Playing, Finished, Cancelled };
    struct MotionKey { float time; glm::vec2 displacement; };
    struct Plan {
        unsigned object=0;
        glm::vec3 entry{};
        float visualYaw=0, duration=0;
        const char* clip=nullptr;
        const MotionKey* motion=nullptr;
        unsigned motionCount=0;
    };
    bool Start(const Plan& plan) {
        if (Active() || plan.duration<=0 || !std::isfinite(plan.duration)) return false;
        m_plan=plan;m_state=State::Approach;m_elapsed=0;m_approachTime=0;
        return true;
    }
    void Cancel() { if (Active()) m_state=State::Cancelled; }
    bool Active() const { return m_state==State::Approach || m_state==State::Ready || m_state==State::Playing; }
    State GetState() const { return m_state; }
    const Plan& GetPlan() const { return m_plan; }
    float PlaybackTime() const { return m_elapsed; }
    static float AngleDelta(float target,float current) {
        float delta=std::fmod(target-current,360.f);
        if(delta>180)delta-=360;if(delta<-180)delta+=360;
        return delta;
    }
    bool BeginPlayback(const glm::vec3& position,float visualYaw) {
        if(m_state!=State::Ready || glm::length(glm::vec2(position.x-m_plan.entry.x,position.z-m_plan.entry.z))>.08f ||
           std::abs(position.y-m_plan.entry.y)>.18f || std::abs(AngleDelta(m_plan.visualYaw,visualYaw))>3.f) return false;
        m_state=State::Playing;m_elapsed=0;return true;
    }
    void Update(float dt,glm::vec3& position,float& visualYaw) {
        dt=std::max(0.f,dt);
        if(m_state==State::Approach || m_state==State::Ready) {
            m_approachTime+=dt;
            if(m_approachTime>5.f) {Cancel();return;}
            const glm::vec2 delta(m_plan.entry.x-position.x,m_plan.entry.z-position.z);
            const float distance=glm::length(delta), step=std::min(distance,1.2f*std::min(dt,.05f));
            if(distance>1e-6f) {position.x+=delta.x*step/distance;position.z+=delta.y*step/distance;}
            const float turn=AngleDelta(m_plan.visualYaw,visualYaw), maxTurn=240.f*std::min(dt,.05f);
            visualYaw+=std::max(-maxTurn,std::min(maxTurn,turn));
            if(distance<=.04f && std::abs(turn)<=2.f) m_state=State::Ready;
        } else if(m_state==State::Playing) {
            m_elapsed=std::min(m_plan.duration,m_elapsed+dt);
            glm::vec2 displacement(0);
            if(m_plan.motion && m_plan.motionCount) {
                unsigned next=1;
                while(next<m_plan.motionCount && m_plan.motion[next].time<m_elapsed)++next;
                const unsigned a=next?std::min(next-1,m_plan.motionCount-1):0;
                const unsigned b=std::min(next,m_plan.motionCount-1);
                const float span=m_plan.motion[b].time-m_plan.motion[a].time;
                const float weight=span>0?std::max(0.f,std::min(1.f,(m_elapsed-m_plan.motion[a].time)/span)):0;
                displacement=m_plan.motion[a].displacement*(1-weight)+m_plan.motion[b].displacement*weight;
            }
            const float angle=glm::radians(m_plan.visualYaw), c=std::cos(angle), s=std::sin(angle);
            position.x=m_plan.entry.x+c*displacement.x+s*displacement.y;
            position.z=m_plan.entry.z-s*displacement.x+c*displacement.y;
            visualYaw=m_plan.visualYaw;
            if(m_elapsed>=m_plan.duration)m_state=State::Finished;
        }
    }
private:
    Plan m_plan{};
    State m_state=State::Idle;
    float m_elapsed=0, m_approachTime=0;
};
