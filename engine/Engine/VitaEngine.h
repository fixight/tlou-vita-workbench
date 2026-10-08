//
// Created by egors on 29.07.2026.
//

#ifndef TLOU_VITA_VITAENGINE_H
#define TLOU_VITA_VITAENGINE_H
#include <cstdint>
#include "PlayerControl.h"
#include "CinematicPlayer.h"
#include "Managers/AudioManager.h"
#include <vitaGL.h>
#include <psp2/kernel/processmgr.h>


class VitaEngine {
public:
    VitaEngine();

public:
    bool InitEngine();

    void Update();
    AudioManager* GetAudioManager() { return &m_audio; }

    enum class StoryPhase { Loading, Movie, RealtimeCinematic, Gameplay };
    StoryPhase GetStoryPhase() const { return m_storyPhase; }
    CinematicPlayer* GetCinematicPlayer() { return &m_cinematic; }
    bool PlayCinematic() {
        m_useSceneControl = true;
        return StartCinematic(m_cinematic.GetControl());
    }
    bool PlayCinematic(const PlayerControl& policy) {
        m_useSceneControl = false;
        return StartCinematic(policy);
    }
    bool StartCinematic(const PlayerControl& policy) {
        if (!m_control.Begin(policy)) return false;
        if (!m_cinematic.Play()) { m_control.End(); return false; }
        m_cinematicFinished = false; m_storyPhase = StoryPhase::RealtimeCinematic; return true;
    }
    bool IsCinematicPlaying() const { return m_cinematic.IsPlaying(); }
    bool ConsumeCinematicFinished() {
        bool result = m_cinematicFinished; m_cinematicFinished = false; return result;
    }
    void CancelCinematic() {
        m_cinematic.Cancel(); m_control.End(); m_cinematicFinished = false;
        m_storyPhase = StoryPhase::Gameplay;
    }
    bool BeginCinematicControl(const PlayerControl& policy) { return m_control.Begin(policy); }
    void SetCinematicSegmentControl(const PlayerControl& policy) { m_control.SetSegment(policy); }
    void EndCinematicControl() { m_control.End(); }
    void SetGameplayControl(const PlayerControl& policy) { m_control.SetGameplay(policy); }
    const PlayerControl& GetPlayerControl() const { return m_control.Get(); }

    void CalculateDeltaTime() {
        uint64_t currentTime = sceKernelGetProcessTimeWide();

        m_deltaTime = static_cast<float>(currentTime - m_lastTime) / 1000000.0f;
        m_lastTime = currentTime;

        // Защита от резких скачков кадров при лагах
        if (m_deltaTime > 0.1f) m_deltaTime = 0.1f;
    }

private:
    CinematicPlayer m_cinematic;
    StoryPhase m_storyPhase = StoryPhase::Loading;
    bool m_cinematicFinished = false;
    bool m_useSceneControl = true;
    AudioManager m_audio;
    CinematicControl m_control;
    uint64_t m_lastTime = 0;
    float m_deltaTime = 0.0f;


    void InitVitaGLCulling() {
        // 1. Отсечение задних граней мешей
        glEnable(GL_CULL_FACE);
        glCullFace(GL_BACK);
        glFrontFace(GL_CCW);

        // 2. Включаем тест глубины для HSR
        glEnable(GL_DEPTH_TEST);
        glDepthFunc(GL_LEQUAL);
        glDepthMask(GL_TRUE);

        // 3. Отключаем альфа-блендинг по умолчанию для непрозрачных объектов
        glDisable(GL_BLEND);

        // 4. Настройка очистки
        glClearDepth(1.0f);
        glClearColor(0.1f, 0.1f, 0.1f, 1.0f);
    }

};



#endif //TLOU_VITA_VITAENGINE_H
