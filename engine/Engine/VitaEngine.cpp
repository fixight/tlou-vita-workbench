//
// Created by egors on 29.07.2026.
//

#include "VitaEngine.h"
#include "System/DataLoader.h"

#include <cstdio>
#include <vitaGL.h>
#include <psp2/ctrl.h>
#include <psp2/kernel/sysmem.h>

#include "MemoryManager.h"
#include "../Managers/CollisionManager.h"
#include "../Objects/CameraActor.h"
#include "Engine/Render.h"
#include "Engine/SkyDome.h"
#include "Engine/MoviePlayer.h"
#include "Engine/DebugHud.h"
#include "Engine/TriggerManager.h"
#include "Engine/DoorManager.h"
#include "Engine/TriggerDebugView.h"
#include "glm/vec3.hpp"
#include "Objects/Character.h"

// =============================================================================
// ШЕЙДЕРЫ ПЕРСОНАЖА (Char) — С динамическим светом и октаэдрической нормалью
// =============================================================================

// language=GLSL
const char* g_VertexCharShaderSource = R"(
attribute vec3 aPosition;
attribute vec2 aTexCoord;
attribute vec2 aOctNormal; // Октаэдрическая нормаль (2 байта)

attribute vec2 aBoneIds;
attribute float aWeight;
uniform mat4 uBones[24];
uniform vec3 uPositionOrigin;
uniform float uPositionStep;
uniform mat4 uMVP;
uniform mat4 uModel;
uniform mat3 uNormalMatrix;

uniform vec3 uLightPos0;
uniform vec3 uLightColor0;
uniform float uLightRadius0;

uniform vec3 uLightPos1;
uniform vec3 uLightColor1;
uniform float uLightRadius1;

uniform vec3 uAmbientLight;

varying vec2 vTexCoord;
varying vec3 vDynamicLight;

// Быстрая распаковка нормали без ветвлений (ALU-only)
vec3 unpack_octahedral(vec2 e) {
    vec3 n = vec3(e.x, e.y, 1.0 - abs(e.x) - abs(e.y));
    float t = max(-n.z, 0.0);
    vec2 s = step(0.0, n.xy) * 2.0 - 1.0;
    n.xy -= s * t;
    return normalize(n);
}

void main() {
    // Сначала распаковываем XYZ из int16 в метры в bind pose.
    vec3 bindPosition = uPositionOrigin + aPosition * uPositionStep;

    // Вершина хранит два индекса в палитре батча и только первый вес.
    // CPU уже интерполировал матрицы костей текущего кадра.
    mat4 skinMatrix = uBones[int(aBoneIds.x)] * aWeight
                    + uBones[int(aBoneIds.y)] * (1.0 - aWeight);
    vec4 posedPosition = skinMatrix * vec4(bindPosition, 1.0);
    vec3 worldPos = vec3(uModel * posedPosition);

    // Распаковываем 2D нормаль в 3D и переводим в мировые координаты
    vec3 localNormal = unpack_octahedral(aOctNormal);
    vec3 N = normalize(uNormalMatrix * (mat3(skinMatrix) * localNormal));

    vec3 totalLight = uAmbientLight;

    // Источник света 0
    if (uLightRadius0 > 0.05) {
        vec3 toLight = uLightPos0 - worldPos;
        float dist = length(toLight);
        if (dist < uLightRadius0) {
            vec3 L = toLight / dist;
            float NdotL = abs(dot(N, L));
            float atten = clamp(1.0 - (dist * dist) / (uLightRadius0 * uLightRadius0), 0.0, 1.0);
            totalLight += uLightColor0 * (NdotL * atten);
        }
    }

    // Источник света 1
    if (uLightRadius1 > 0.05) {
        vec3 toLight = uLightPos1 - worldPos;
        float dist = length(toLight);
        if (dist < uLightRadius1) {
            vec3 L = toLight / dist;
            float NdotL = abs(dot(N, L));
            float atten = clamp(1.0 - (dist * dist) / (uLightRadius1 * uLightRadius1), 0.0, 1.0);
            totalLight += uLightColor1 * (NdotL * atten);
        }
    }

    vDynamicLight = totalLight;
    vTexCoord = aTexCoord;
    gl_Position = uMVP * posedPosition;
}
)";

// language=GLSL
const char* g_FragmentCharShaderSource = R"(
precision mediump float;

varying vec2 vTexCoord;
varying vec3 vDynamicLight;

uniform sampler2D uTexture;

void main() {
    vec4 tex = texture2D(uTexture, vTexCoord);

    // Alpha-test для альфа-канала текстуры
    if (tex.a < 0.5) {
        discard;
    }

    vec3 finalColor = min(tex.rgb * vDynamicLight, vec3(1.0));
    gl_FragColor = vec4(finalColor, 1.0);
}
)";

// =============================================================================
// ШЕЙДЕРЫ ДЕБАГА (Коллизии, линии, кости)
// =============================================================================

// language=GLSL
const char* g_VertexDebugShaderSource = R"(
attribute vec3 aPosition;
uniform mat4 uMVP;

void main() {
    gl_Position = uMVP * vec4(aPosition, 1.0);
}
)";

// language=GLSL
const char* g_FragmentDebugShaderSource = R"(
precision mediump float;

void main() {
    gl_FragColor = vec4(1.0, 0.0, 0.0, 1.0); // Красный дебаг-цвет
}
)";

// =============================================================================
// ОСНОВНЫЕ ШЕЙДЕРЫ МИРА / УРОВНЯ (Static World — 16 байт вершина)
// =============================================================================

// language=GLSL
const char* g_VertexShaderSource = R"(
attribute vec3 aPosition;
attribute vec2 aTexCoord;
attribute vec4 aColor;      // Запеченное освещение в вершинах
attribute vec2 aOctNormal;  // [НОВОЕ] Октаэдрическая нормаль (16-бит)

uniform mat4 uMVP;

varying vec2 vTexCoord;
varying vec4 vColor;

void main() {
    gl_Position = uMVP * vec4(aPosition, 1.0);
    vTexCoord = aTexCoord;
    vColor = aColor;
}
)";

// language=GLSL
const char* g_FragmentShaderSource = R"(
precision mediump float;

varying vec2 vTexCoord;
varying vec4 vColor;

uniform sampler2D uTexture;

void main() {
    vec3 color = texture2D(uTexture, vTexCoord).rgb * vColor.rgb * 1.45;
    gl_FragColor = vec4(color, 1.0);
}
)";

// Растительность/решётки: вырезаем пустые пиксели, остальные пишут глубину.
const char* g_FragmentMaskedShaderSource = R"(
precision mediump float;
varying vec2 vTexCoord;
varying vec4 vColor;
uniform sampler2D uTexture;
uniform float uAlphaCutoff;
void main() {
    vec4 texel = texture2D(uTexture, vTexCoord);
    if (texel.a < uAlphaCutoff) discard;
    gl_FragColor = vec4(texel.rgb * vColor.rgb * 1.45, 1.0);
}
)";

// Стекло: освещение меняет RGB, исходная альфа сохраняется.
const char* g_FragmentTransparentShaderSource = R"(
precision mediump float;
varying vec2 vTexCoord;
varying vec4 vColor;
uniform sampler2D uTexture;
void main() {
    vec4 texel = texture2D(uTexture, vTexCoord);
    if (texel.a < 0.0039) discard;
    gl_FragColor = vec4(texel.rgb * vColor.rgb * 1.45, texel.a);
}
)";

VitaEngine::VitaEngine() {
}

const char* g_SkyVertexShader = R"(
precision highp float;
attribute vec3 aPosition;
attribute vec2 aTexCoord;
uniform mat4 uMVP;
uniform float uPositionStep;
varying vec2 vTexCoord;
void main() {
    vec4 clip = uMVP * vec4(aPosition * uPositionStep, 1.0);
    gl_Position = vec4(clip.xy, clip.w, clip.w);
    vTexCoord = aTexCoord;
}
)";
const char* g_SkyFragmentShader = R"(
precision mediump float;
uniform sampler2D uTexture;
varying vec2 vTexCoord;
void main() {
    vec4 texel = texture2D(uTexture, vTexCoord);
    gl_FragColor = texel;
}
)";

bool VitaEngine::InitEngine() {
    // Reserve contiguous memory for AvPlayer instead of giving all of it to GL.
    // A threshold above the dialog pool size leaves that pool unused, as vglInit did.
    constexpr int leaveDialogMemoryUnused = 0x7FFFFFFF;
    vglInitWithCustomThreshold(0x800000, 960, 544, 0x1000000, 0, 32 * 1024 * 1024,
        leaveDialogMemoryUnused, SCE_GXM_MULTISAMPLE_4X);
    glViewport(0, 0, 960, 544); // Область отрисовки на весь экран Vita
    glEnable(GL_DEPTH_TEST);    // Включаем 3D буфер глубины
    // Отключаем отсечение задних граней для отладки
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG);

    InitVitaGLCulling();

    std::vector<Instance> g_LevelInstances;

    MemoryManager memoryManager;
    Render render;
    uint32_t modelSize;

    std::vector<AABB> g_LevelCollision;

    CollisionManager collision_manager;
    PlayerStartInfo spawnPoint;

    std::vector<EngineLight> lights;

    // Показываем первый загрузочный кадр до блокирующей подготовки уровня.
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
    vglSwapBuffers(GL_FALSE);
    memoryManager.LoadMaterialSettings("app0:/assets/metadata/materials.bin");
    // Compile GPU programs before playback: shader compilation cannot run on a worker.
    // The long level read/preparation below then overlaps the movie.
    GLuint shader = render.CompileShader(g_VertexShaderSource, g_FragmentShaderSource);
    GLuint maskedShader = render.CompileShader(g_VertexShaderSource, g_FragmentMaskedShaderSource);
    GLuint transparentShader = render.CompileShader(g_VertexShaderSource, g_FragmentTransparentShaderSource);
    GLuint characterShader = render.CompileShader(g_VertexCharShaderSource, g_FragmentCharShaderSource);
    if (!shader || !maskedShader || !transparentShader || !characterShader) return false;

    SkyDome sky;
    sky.Load("app0:/assets/metadata/sky.bin", memoryManager);
    GLuint skyShader = sky.mesh ? Render::CompileShader(g_SkyVertexShader, g_SkyFragmentShader) : 0;
    if (sky.mesh && !skyShader) return false;
    SkinnedModel sarahModel;
    const bool hasSarah = sarahModel.Load("app0:/characters/sarah16/sarah.sk16", memoryManager);
    TriggerDebugView triggerView;
    triggerView.Init();
    DebugHud hud;
    hud.Init();

    MoviePlayer intro;
    m_storyPhase = StoryPhase::Movie;
    const bool hasIntro = intro.Open("app0:/movies/hom-intro.mp4");
    DataLoader::LoadingFramePump movieFrame = [](void* context) {
        auto& movie = *static_cast<MoviePlayer*>(context);
        movie.Update();
        movie.Draw();
        vglSwapBuffers(GL_FALSE);
    };
    if (!DataLoader::LoadStartupLevel("app0:/level.bin", memoryManager, collision_manager,
        g_LevelInstances, g_LevelCollision, spawnPoint, lights, hasIntro ? movieFrame : nullptr, &intro)) {
        sceClibPrintf("[Startup] Level loading failed; gameplay will not start\n");
        return false;
    }




    if (hasIntro) movieFrame(&intro);

    CameraActor* camera = new CameraActor();
    camera->SetPosition(TLOU::Vector3(0, 5, 3));
    if (sky.mesh) sky.ExcludeLegacyGeometry(g_LevelInstances);
    GLuint debugShader;

    float playerRadius = 0.3f;

    Character character;
    character.SetPosition(TLOU::Vector3(spawnPoint.position.x, spawnPoint.position.y - 1.5f , spawnPoint.position.z));
    if (hasSarah) {
        character.setSkinnedModel(&sarahModel);
    }
    character.initModel();
    character.SetScale(TLOU::Vector3(1.0f,1.0f,1.0f));




    sceClibPrintf("Sarah startup: shader=%u, spawn=(%.3f,%.3f,%.3f)\n",characterShader,spawnPoint.position.x,spawnPoint.position.y-1.5f,spawnPoint.position.z);
    character.SetCamera(camera);
    DoorManager doors;
    doors.Load("app0:/assets/metadata/doors.bin", "app0:/level.bin", g_LevelInstances, collision_manager);
    if (hasIntro) movieFrame(&intro);
    doors.LoadInteractions("app0:/assets/metadata/door_interactions.bin", "app0:/level.bin");
    if (hasIntro) movieFrame(&intro);
    TriggerManager triggers;
    triggers.Load("app0:/assets/metadata/triggers.bin");
    bool triggerViewHeld=false;
    bool showHud = true, hudToggleHeld = false;
    while (intro.IsPlaying()) movieFrame(&intro);
    intro.Close();
    // Release the movie decoder before allocating cinematic poses/textures.
    const bool hasBedroomScene = m_cinematic.Load("app0:/assets/cinematics/bedroom/scene.vcn", memoryManager) &&
        m_cinematic.LoadWorldMask("app0:/assets/cinematics/bedroom/mask/world.vcm", "app0:/level.bin", g_LevelInstances, memoryManager);
    if (!hasBedroomScene) sceClibPrintf("[Cinematic] Bedroom unavailable: %s\n",m_cinematic.GetLastError().c_str());
    if (!m_audio.init()) {
        sceClibPrintf("[Audio] Output initialization failed; gameplay continues without sound\n");
    } else {
        // The level exporter chooses resident/stream policy. Banks can be added
        // or removed later when chunks enter or leave the streaming set.
        const char* audioBank = "app0:/assets/audio/level.vabk";
        FILE* bankFile = fopen(audioBank, "rb");
        if (bankFile) {
            fclose(bankFile);
            if (!m_audio.loadBank(audioBank))
                sceClibPrintf("[Audio] Bank error: %s\n", m_audio.getLastError().c_str());
        }
    }
    m_storyPhase = StoryPhase::Gameplay;
    if (hasBedroomScene && !m_cinematic.PrepareAudio(m_audio))
        sceClibPrintf("[Cinematic] Audio unavailable: %s\n",m_cinematic.GetLastError().c_str());
    if (hasBedroomScene && PlayCinematic()) {
        m_cinematic.ApplyWorldMask(g_LevelInstances,true);
        sceClibPrintf("[Cinematic] Started %s\n",m_cinematic.GetName().c_str());
    }
    glEnable(GL_DEPTH_TEST);
    glEnable(GL_BLEND);
    glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    InitVitaGLCulling();
    uint64_t lastFrameStart = sceKernelGetProcessTimeWide();
    m_lastTime = lastFrameStart; // Loading/movie time is not a gameplay frame.
    unsigned startupFrames = 0;
    bool cinematicWorldMasked = m_cinematic.IsPlaying();

    while (true) {
        const uint64_t frameStart = sceKernelGetProcessTimeWide();
        const double rawFrameSeconds = (frameStart - lastFrameStart) / 1000000.0;
        lastFrameStart = frameStart;
        render.BeginFrame();
        CalculateDeltaTime();
        Update();



        if (cinematicWorldMasked != m_cinematic.IsPlaying()) {
            cinematicWorldMasked = m_cinematic.IsPlaying();
            m_cinematic.ApplyWorldMask(g_LevelInstances,cinematicWorldMasked);
        }
        if (m_cinematic.IsPlaying()) {
            m_cinematic.Update(rawFrameSeconds);
            if (m_cinematic.ConsumeFinished()) {
                m_cinematic.ApplyWorldMask(g_LevelInstances,false);
                cinematicWorldMasked = false;
                m_cinematic.ApplyGameplayHandoff(character);
                m_control.End(); m_cinematicFinished = true;
                m_storyPhase = StoryPhase::Gameplay;
                sceClibPrintf("[Cinematic] Finished %s; gameplay control restored\n",m_cinematic.GetName().c_str());
            }
        }
        if (m_cinematic.IsPlaying() && m_useSceneControl)
            m_control.SetSegment(m_cinematic.GetControl());
        const PlayerControl& control = m_control.Get();
        if (m_cinematic.IsPlaying() && control.characterPose == PoseOwner::Cinematic)
            m_cinematic.ApplyPlayerAnchor(character);
        camera->SetPlayerControl(control);
        character.SetPlayerControl(control);
        if (m_cinematic.IsPlaying() && control.cameraPose == PoseOwner::Cinematic) m_cinematic.ApplyCamera(*camera);
        camera->Update(m_deltaTime);
        SceCtrlData interactionPad{};
        sceCtrlPeekBufferPositive(0, &interactionPad, 1);
        const auto p = character.GetPosition();
        doors.Update(m_deltaTime, {{p.x-.35f,p.y,p.z-.35f},{p.x+.35f,p.y+1.6f,p.z+.35f}},
                     (interactionPad.buttons & SCE_CTRL_SQUARE) != 0,
                     control.CanInteract() && camera->GetMode() != CameraMode::Spectate && !character.IsInteracting(),
                     g_LevelInstances, collision_manager);
        glm::vec3 interactionTarget;
        if (doors.ConsumeInteraction(interactionTarget)) character.StartDoorInteraction(interactionTarget);
        InteractionProcess::Plan interactionPlan;
        if(doors.ConsumeProcess(interactionPlan) && !character.StartInteraction(interactionPlan)) {
            doors.CancelProcess(interactionPlan.object);
            sceClibPrintf("Interaction rejected: character lacks clip %s\n",interactionPlan.clip);
        }
        character.Update(m_deltaTime);
        if(character.SampledInteractionThisFrame())
            doors.SampleProcess(character.GetInteraction().GetPlan().object,
                character.GetInteraction().PlaybackTime(),g_LevelInstances,collision_manager);
        if(character.GetInteraction().GetState()==InteractionProcess::State::Cancelled)
            doors.CancelProcess(character.GetInteraction().GetPlan().object);

        //collision_manager.computeCollision(camera)
        const bool noclip = camera->GetMode() == CameraMode::Spectate;
        const uint64_t physicsStart = sceKernelGetProcessTimeWide();
        if (!noclip && control.HasCharacterPhysics()) collision_manager.computeCollision(&character);
        if(character.GetInteraction().GetState()==InteractionProcess::State::Ready && character.BeginInteractionPlayback())
            doors.BeginProcess(character.GetInteraction().GetPlan().object);
        character.initModel();
        const double physicsMs = (sceKernelGetProcessTimeWide() - physicsStart) / 1000.0;

        // Match the existing character collider; spectate uses a small camera probe.
        const auto triggerPos = noclip ? camera->GetPosition() : character.GetPosition();
        const float triggerRadius = noclip ? 0.1f : 0.35f;
        const float triggerHeight = noclip ? 0.1f : 1.6f;
        triggers.Update({{triggerPos.x-triggerRadius, triggerPos.y-(noclip ? 0.1f : 0.0f), triggerPos.z-triggerRadius},
                         {triggerPos.x+triggerRadius, triggerPos.y+triggerHeight, triggerPos.z+triggerRadius}}, noclip);


        SceCtrlData hudPad{};
        sceCtrlPeekBufferPositive(0, &hudPad, 1);
        const bool triangleHeld = (hudPad.buttons & SCE_CTRL_TRIANGLE) != 0;
        if (triangleHeld && !hudToggleHeld) showHud = !showHud;
        hudToggleHeld = triangleHeld;
        const bool circleHeld=(hudPad.buttons & SCE_CTRL_CIRCLE)!=0;
        if(circleHeld&&!triggerViewHeld)triggerView.CycleMode();
        triggerViewHeld=circleHeld;

        TLOU::Vector3 camPos = camera->GetPosition();

        glm::vec3 playerPoint(camPos.x, camPos.y, camPos.z);

        glClearColor(0.1f, 0.2f, 0.3f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        // 1. Получаем позицию камеры ОДИН РАЗ перед началом цик
        TLOU::Vector3 eye = camera->GetPosition();
        glm::vec3 cameraPos(eye.x, eye.y, eye.z);

        // 2. Квадрат максимальной дистанции: 20 * 20 = 400.0f
        // Сравнение квадратов избавляет CPU от вызова дорогой функции корня (sqrt
        constexpr float MAX_DIST_SQ = 20.0f * 60.0f; // 400.0f

        std::vector<Instance> characters;
        characters.push_back(character.GetRenderData());

        const uint64_t submitStart = sceKernelGetProcessTimeWide();
        // Сначала все поверхности, записывающие глубину, включая персонажей.
        render.render(g_LevelInstances, camera, lights, shader, false, AlphaMode::Opaque);
        render.render(g_LevelInstances, camera, lights, maskedShader, false, AlphaMode::Mask);
        if (m_cinematic.IsPlaying()) render.RenderCinematic(m_cinematic, camera, lights, characterShader);
        else render.render(characters, camera, lights, characterShader, true);
        render.RenderSky(sky, camera, skyShader);
        // Затем стекло поверх уже готового мира: depth test включён, запись выключена.
        render.render(g_LevelInstances, camera, lights, transparentShader, false, AlphaMode::Blend);

        //render.renderCollision(g_LevelCollision , camera , debugShader);


        //rotation.y += 8.f * m_deltaTime;



        const double submitMs = (sceKernelGetProcessTimeWide() - submitStart) / 1000.0;
        const bool cinematicFrame = m_cinematic.IsPlaying();
        if (!cinematicFrame) triggerView.Draw(triggers,camera,showHud);
        auto hudLabels = triggerView.GetLabels();
        if (!doors.GetHudText().empty()) {
            std::string prompt = doors.GetHudText();
            std::replace(prompt.begin(), prompt.end(), '\n', ' ');
            HudLabel label; label.x=24; label.y=510; label.text=prompt;
            label.r=1.f; label.g=.9f; label.b=.55f;
            hudLabels.push_back(label);
        }
        if (!cinematicFrame && (showHud || !hudLabels.empty())) hud.Draw(rawFrameSeconds, submitMs, physicsMs, render.GetStats(),
                             static_cast<uint32_t>(collision_manager.GetTriangleCount()), noclip, triggers.GetHudText()+triggerView.GetLegend(), hudLabels, showHud);
        vglSwapBuffers(GL_FALSE);
        if (startupFrames < 120) {
            ++startupFrames;
            if (startupFrames == 1 || startupFrames == 120)
                sceClibPrintf("[Startup] %s frame %u submitted\n", m_cinematic.IsPlaying() ? "Cinematic" : "Gameplay", startupFrames);
        }



    }

    return true;
}

void VitaEngine::Update() {
    //printf("Update");
}
