//
// Created by egors on 30.07.2026.
//

#include "Render.h"
#include "SkinnedModel.h"
#include "SkyDome.h"
#include <glm/glm.hpp>
#include <glm/gtc/matrix_transform.hpp>
#include <psp2/kernel/clib.h>

#include "../Objects/CameraActor.h"
#include "../System/DataLoader.h"
#include "glm/gtc/type_ptr.hpp"




GLuint Render::CompileShader(const char* vertexShader , const char* fragmentShader) {
    GLint success;
    char infoLog[512];

    //Вершинный шейдер
    GLuint vertShader = glCreateShader(GL_VERTEX_SHADER);
    glShaderSource(vertShader, 1, &vertexShader, NULL);
    glCompileShader(vertShader);
    glGetShaderiv(vertShader, GL_COMPILE_STATUS, &success);
    if (!success) {
        glGetShaderInfoLog(vertShader, 512, NULL, infoLog);
        sceClibPrintf("Vertex Shader Error: %s\n", infoLog); // Печать в лог Vita
        glDeleteShader(vertShader);
        return 0;
    }

    // Фрагментный шейдер
    GLuint fragShader = glCreateShader(GL_FRAGMENT_SHADER);
    glShaderSource(fragShader, 1, &fragmentShader, NULL);
    glCompileShader(fragShader);
    glGetShaderiv(fragShader, GL_COMPILE_STATUS, &success);
    if (!success) {
        glGetShaderInfoLog(fragShader, 512, NULL, infoLog);
        sceClibPrintf("Fragment Shader Error: %s\n", infoLog);
        glDeleteShader(vertShader);
        glDeleteShader(fragShader);
        return 0;
    }

    // Линковка программы
    GLuint program = glCreateProgram();
    glAttachShader(program, vertShader);
    glAttachShader(program, fragShader);
    glLinkProgram(program);

    glGetProgramiv(program, GL_LINK_STATUS, &success);
    if (!success) {
        glGetProgramInfoLog(program, 512, NULL, infoLog);
        sceClibPrintf("Shader Link Error: %s\n", infoLog);
        glDeleteShader(vertShader);
        glDeleteShader(fragShader);
        glDeleteProgram(program);
        return 0;
    }

    glDeleteShader(vertShader);
    glDeleteShader(fragShader);

    TempShader = program;

    return program;
}






#include <chrono>
#include <algorithm>


inline static bool g_isolateSlowestMode = false; // <-- Поставьте true, когда начнется просад FP

void Render::render(std::vector<Instance> &objects, CameraActor* Camera, const std::vector<EngineLight>& lights, GLuint shader, bool isPlayerPass, AlphaMode materialPass) {
    if (objects.empty() || !Camera) return;
    // Скелетные меши рисуются своим форматом вершин и палитрой костей.
    if (isPlayerPass) {
        for (const auto& instance : objects) {
            if (instance.skinned) {
                instance.skinned->Draw(instance.modelMatrix, Camera, lights, shader, stats);
            }
        }
        return;
    }

    // 1. Настройки глубины и куллинга
    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LEQUAL);
    const bool transparentPass = materialPass == AlphaMode::Blend;
    glDepthMask(transparentPass ? GL_FALSE : GL_TRUE);
    if (transparentPass) {
        glEnable(GL_BLEND);
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    } else {
        glDisable(GL_BLEND);
    }

    if (isPlayerPass) {
        // Для персонажа отключаем отсечение граней, чтобы волосы было видно с двух сторо
        glDisable(GL_CULL_FACE);
    } else {
        // Для уровня включаем отсечение (экономит FPS)
        glEnable(GL_CULL_FACE);
        glCullFace(GL_BACK);
        glFrontFace(GL_CCW);
    }

    // 2. Камера и матрицы
    TLOU::Vector3 eye = Camera->GetPosition();
    TLOU::Vector3 LookAt = eye + Camera->GetForwardVector();
    glm::vec3 cameraPos(eye.x, eye.y, eye.z);

    glm::mat4 cameraView = Camera->GetViewMatrix();
    glm::mat4 projection = Camera->GetProjectionMatrix();
    glm::mat4 viewProj = projection * cameraView;

    Frustum cameraFrustum;
    cameraFrustum.extractFromMatrix(glm::value_ptr(viewProj));

    constexpr float MAX_VISIBLE_DIST = 150.0f;
    constexpr float MAX_DIST_SQ = MAX_VISIBLE_DIST * MAX_VISIBLE_DIST;

    // 3. Подготовка шейдера
    glUseProgram(shader);

    GLint mvpLoc       = glGetUniformLocation(shader, "uMVP");
    GLint modelLoc     = glGetUniformLocation(shader, "uModel");
    GLint normalMatLoc = glGetUniformLocation(shader, "uNormalMatrix"); // <--- Новая матрица нормалей
    GLint texLoc       = glGetUniformLocation(shader, "uTexture");
    GLint cutoffLoc    = glGetUniformLocation(shader, "uAlphaCutoff");

    GLint posLoc       = glGetAttribLocation(shader, "aPosition");
    GLint uvLoc        = glGetAttribLocation(shader, "aTexCoord");
    GLint colLoc       = glGetAttribLocation(shader, "aColor");
    GLint normalLoc    = glGetAttribLocation(shader, "aOctNormal");

    if (texLoc != -1) glUniform1i(texLoc, 0);

    // Включаем массивы атрибутов 1 раз перед циклом
    if (posLoc != -1)    glEnableVertexAttribArray(posLoc);
    if (uvLoc != -1)     glEnableVertexAttribArray(uvLoc);
    if (colLoc != -1)    glEnableVertexAttribArray(colLoc);
    if (normalLoc != -1) glEnableVertexAttribArray(normalLoc);

    glActiveTexture(GL_TEXTURE0);

    glm::vec3 playerPos = glm::vec3(objects[0].modelMatrix[3]);

    // Поиск 2 ближайших ламп
    // --- ИСПРАВЛЕНИЕ: Поиск 2 самых ВЛИЯТЕЛЬНЫХ ламп (а не просто ближайших) ---
    const EngineLight* closestLights[2] = { nullptr, nullptr };
    float maxInfluence[2] = { 0.0f, 0.0f }; // Теперь мы ищем максимальное влияние, а не минимальную дистанцию

    for (const auto& light : lights) {
        glm::vec3 diff = light.position - playerPos;
        float distSq = glm::dot(diff, diff);
        float radiusSq = light.radius * light.radius;

        // Защита от деления на ноль, если радиус лампы кривой
        if (radiusSq <= 0.001f) continue;

        // Вычисляем "силу" света в текущей точке:
        // 1.0 = мы прямо в центре лампы, 0.0 = мы на самом краю её радиуса
        float influence = 1.0f - (distSq / radiusSq);

        // Если влияние <= 0, значит свет сюда ВООБЩЕ НЕ ДОСТАЕТ.
        // Пропускаем эту лампу, чтобы она не крала место у других!
        if (influence <= 0.0f) continue;

        // Сортировка по силе влияния
        if (influence > maxInfluence[0]) {
            // Сдвигаем текущего лидера на 2-е место
            maxInfluence[1] = maxInfluence[0];
            closestLights[1] = closestLights[0];

            // Ставим новую лампу на 1-е место
            maxInfluence[0] = influence;
            closestLights[0] = &light;
        }
        else if (influence > maxInfluence[1]) {
            // Ставим лампу на 2-е место
            maxInfluence[1] = influence;
            closestLights[1] = &light;
        }
    }
    // -------------------------------------------------------------------------
    // Подготавливаем данные ламп
    glm::vec3 lightPositions[2] = { glm::vec3(0.0f), glm::vec3(0.0f) };
    glm::vec3 lightColors[2]    = { glm::vec3(0.0f), glm::vec3(0.0f) };
    float lightRadii[2]         = { 0.0f, 0.0f };

    for (int i = 0; i < 2; i++) {
        if (closestLights[i] != nullptr) {
            lightPositions[i] = closestLights[i]->position;

            // Нормализуем цвет (уберегаем от пересвета, если цвет 0-255)
            glm::vec3 lColor = closestLights[i]->color;
            if (lColor.r > 1.0f || lColor.g > 1.0f || lColor.b > 1.0f) {
                lColor /= 255.0f;
            }
            lightColors[i] = lColor;
            lightRadii[i]  = closestLights[i]->radius;

            if (isPlayerPass) {
                sceClibPrintf("  -> Light [%u]: Pos(%.1f, %.1f, %.1f), Color(%.2f, %.2f, %.2f), Radius: %.1fm\n",
                    i, lightPositions[i].x, lightPositions[i].y, lightPositions[i].z,
                    lightColors[i].r, lightColors[i].g, lightColors[i].b, lightRadii[i]);
            }
        }
    }

    // --- ПЕРЕДАЧА СВЕТА В ШЕЙДЕР БЕЗ МАССИВОВ ---
    GLint ambLoc = glGetUniformLocation(shader, "uAmbientLight");
    if (ambLoc != -1) glUniform3f(ambLoc, 0.35f, 0.35f, 0.38f);

    GLint pos0Loc = glGetUniformLocation(shader, "uLightPos0");
    GLint col0Loc = glGetUniformLocation(shader, "uLightColor0");
    GLint rad0Loc = glGetUniformLocation(shader, "uLightRadius0");

    GLint pos1Loc = glGetUniformLocation(shader, "uLightPos1");
    GLint col1Loc = glGetUniformLocation(shader, "uLightColor1");
    GLint rad1Loc = glGetUniformLocation(shader, "uLightRadius1");

    if (pos0Loc != -1) glUniform3fv(pos0Loc, 1, glm::value_ptr(lightPositions[0]));
    if (col0Loc != -1) glUniform3fv(col0Loc, 1, glm::value_ptr(lightColors[0]));
    if (rad0Loc != -1) glUniform1f(rad0Loc, lightRadii[0]);

    if (pos1Loc != -1) glUniform3fv(pos1Loc, 1, glm::value_ptr(lightPositions[1]));
    if (col1Loc != -1) glUniform3fv(col1Loc, 1, glm::value_ptr(lightColors[1]));
    if (rad1Loc != -1) glUniform1f(rad1Loc, lightRadii[1]);

    // Переменные кэша состояний
    GLuint lastBoundTexture = 0;
    GLuint lastBoundVBO = 0;

    // 4. Отбираем объекты только текущего прохода. Culling остаётся прежним.
    visibleWorld.clear();
    const glm::vec3 cameraForward = glm::normalize(glm::vec3(LookAt.x, LookAt.y, LookAt.z) - cameraPos);
    for (const auto& inst : objects) {
        if (inst.skyGeometry) continue;
        if (!inst.mesh || !inst.texture) {
            if (materialPass == AlphaMode::Opaque) { ++stats.objectsTested; ++stats.invalidObjects; }
            continue;
        }
        if (inst.texture->material.alphaMode != materialPass) continue;
        ++stats.objectsTested;

        glm::vec3 objPos = glm::vec3(inst.modelMatrix[3]);
        glm::vec3 diff = objPos - cameraPos;
        if (glm::dot(diff, diff) > MAX_DIST_SQ) { ++stats.culledDistance; continue; }

        if (!isBoxInFrustum(cameraFrustum, inst.boundingBox.minBounds, inst.boundingBox.maxBounds) && !isPlayerPass) {
            ++stats.culledFrustum;
            continue;
        }

        const glm::vec3 center = (inst.boundingBox.minBounds + inst.boundingBox.maxBounds) * 0.5f;
        visibleWorld.push_back({&inst, glm::dot(center - cameraPos, cameraForward)});
    }

    // Стекло: дальние объекты раньше ближних. Сортировка по центру AABB —
    // приближение для пересекающихся мешей, не сортировка каждого треугольника.
    if (transparentPass) {
        std::sort(visibleWorld.begin(), visibleWorld.end(), [](const auto& a, const auto& b) {
            return a.viewDepth > b.viewDepth;
        });
    }

    bool lastDoubleSided = false;
    for (const auto& visible : visibleWorld) {
        const Instance& inst = *visible.instance;
        Texture* texture = inst.texture;
        if (texture->material.doubleSided != lastDoubleSided) {
            if (texture->material.doubleSided) glDisable(GL_CULL_FACE);
            else glEnable(GL_CULL_FACE);
            lastDoubleSided = texture->material.doubleSided;
        }
        if (cutoffLoc != -1) glUniform1f(cutoffLoc, texture->material.alphaCutoff);
        if (std::find(visibleTextures.begin(),visibleTextures.end(),texture)==visibleTextures.end()) {
            visibleTextures.push_back(texture);
            stats.visibleTextureBytes += static_cast<uint64_t>(texture->size_x) * texture->size_y * 4;
        }
        if (texture->textureID == 0) {
            GLuint texID = 0;
            glGenTextures(1, &texID);
            glBindTexture(GL_TEXTURE_2D, texID);
            ++stats.textureBinds;
            stats.textureUploadBytes += static_cast<uint64_t>(texture->size_x) * texture->size_y * 4;
            glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, texture->size_x, texture->size_y, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture->dataPointer);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
            texture->textureID = texID;
            lastBoundTexture = texID;
        } else if (texture->textureID != lastBoundTexture) {
            glBindTexture(GL_TEXTURE_2D, texture->textureID);
            ++stats.textureBinds;
            lastBoundTexture = texture->textureID;
        }

        if (inst.mesh->vboID != lastBoundVBO) {
            glBindBuffer(GL_ARRAY_BUFFER, inst.mesh->vboID);
            ++stats.vboBinds;
            lastBoundVBO = inst.mesh->vboID;

            if (posLoc != -1)    glVertexAttribPointer(posLoc, 3, GL_SHORT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, x));
            if (colLoc != -1)    glVertexAttribPointer(colLoc, 4, GL_UNSIGNED_BYTE, GL_TRUE, sizeof(Vertex), (void*)offsetof(Vertex, color));
            if (uvLoc != -1)     glVertexAttribPointer(uvLoc, 2, GL_HALF_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex, u));
            if (normalLoc != -1) glVertexAttribPointer(normalLoc, 2, GL_BYTE, GL_TRUE, sizeof(Vertex), (void*)offsetof(Vertex, oct_nx));
        }

        glm::mat4 modelMatrix = inst.modelMatrix;
        glm::mat4 scaledModel = glm::scale(modelMatrix, glm::vec3(0.01f, 0.01f, 0.01f));
        glm::mat4 mvp = viewProj * scaledModel;

        // ВЫЧИСЛЕНИЕ ИДЕАЛЬНОЙ МАТРИЦЫ НОРМАЛЕЙ:
        // Транспонирование обратной матрицы защищает нормали от любых искажений масштаба,
        // а расчет на стороне процессора (C++) гарантирует, что 16-битный чип Виты не порежет числа нулям
        glm::mat3 normalMatrix = glm::transpose(glm::inverse(glm::mat3(modelMatrix)));

        if (mvpLoc != -1)       glUniformMatrix4fv(mvpLoc, 1, GL_FALSE, glm::value_ptr(mvp));
        if (modelLoc != -1)     glUniformMatrix4fv(modelLoc, 1, GL_FALSE, glm::value_ptr(scaledModel));

        // ПЕРЕДАЕМ МАТРИЦУ НОРМАЛЕЙ В ШЕЙДЕР
        if (normalMatLoc != -1) glUniformMatrix3fv(normalMatLoc, 1, GL_FALSE, glm::value_ptr(normalMatrix));

        glDrawArrays(GL_TRIANGLES, 0, inst.mesh->vertexCount);
        ++stats.drawCalls;
        ++stats.objectsDrawn;
        stats.vertices += inst.mesh->vertexCount;
        stats.triangles += inst.mesh->vertexCount / 3;
    }

    glBindBuffer(GL_ARRAY_BUFFER, 0);
    glBindTexture(GL_TEXTURE_2D, 0);
    lastBoundVBO = lastBoundTexture = 0;

    if (posLoc != -1)    glDisableVertexAttribArray(posLoc);
    if (uvLoc != -1)     glDisableVertexAttribArray(uvLoc);
    if (colLoc != -1)    glDisableVertexAttribArray(colLoc);
    if (normalLoc != -1) glDisableVertexAttribArray(normalLoc);

    // Следующий проход (персонаж, отладка, HUD) не наследует blending стекла.
    glDepthMask(GL_TRUE);
    glDisable(GL_BLEND);
    glEnable(GL_CULL_FACE);
    glUseProgram(0);
}

void Render::renderCollision(std::vector<AABB>& collisions, CameraActor *Camera, uint32_t shader) {
    if (collisions.empty() || !Camera || shader == 0) return;

    sceClibPrintf("render collision\n");

    // 1. Настройки рендеринга для отладочных линий
    glEnable(GL_DEPTH_TEST);
    glDepthFunc(GL_LEQUAL);
    glDepthMask(GL_FALSE); // Запрещаем запись в глубину, чтобы линии не перекрывали друг друга
    glDisable(GL_CULL_FACE); // Для линий Culling не нужен

    // 2. Камера и матрицы
    TLOU::Vector3 eye = Camera->GetPosition();
    TLOU::Vector3 LookAt = eye + Camera->GetForwardVector();
    glm::vec3 cameraPos(eye.x, eye.y, eye.z);

    glm::mat4 cameraView = Camera->GetViewMatrix();
    glm::mat4 projection = Camera->GetProjectionMatrix();
    glm::mat4 viewProj = projection * cameraView;

    constexpr float MAX_VISIBLE_DIST = 35.0f;
    constexpr float MAX_DIST_SQ = MAX_VISIBLE_DIST * MAX_VISIBLE_DIST;

    // 3. Активация шейдера
    glUseProgram(shader);

    GLint mvpLoc   = glGetUniformLocation(shader, "uMVP");
    GLint modelLoc = glGetUniformLocation(shader, "uModel");
    GLint posLoc   = glGetAttribLocation(shader, "aPosition");

    if (posLoc == -1) {
        glUseProgram(0);
        glDepthMask(GL_TRUE);
        return;
    }

    // Так как AABB уже находятся в мировых координатах, модель = единичная матрица
    glm::mat4 identityModel = glm::mat4(1.0f);
    glm::mat4 mvp = viewProj * identityModel;

    if (mvpLoc != -1)   glUniformMatrix4fv(mvpLoc, 1, GL_FALSE, glm::value_ptr(mvp));
    if (modelLoc != -1) glUniformMatrix4fv(modelLoc, 1, GL_FALSE, glm::value_ptr(identityModel));

    // 4. Сборка геометрии всех коробок в один буфер (Пакетная обработка)
    std::vector<glm::vec3> lineVertices;
    lineVertices.reserve(collisions.size() * 24); // 12 ребер * 2 вершины на ребро

    for (const auto& box : collisions) {
        // Проверка дистанции (Culling по дистанции до центра AABB)
        glm::vec3 center = (box.minBounds + box.maxBounds) * 0.5f;
        glm::vec3 diff = center - cameraPos;
        if (glm::dot(diff, diff) > MAX_DIST_SQ) continue;

        const glm::vec3& min = box.minBounds;
        const glm::vec3& max = box.maxBounds;

        // Извлекаем 8 угловых вершин куба/параллелепипеда
        glm::vec3 c[8] = {
            glm::vec3(min.x, min.y, min.z), // 0: min
            glm::vec3(max.x, min.y, min.z), // 1
            glm::vec3(max.x, max.y, min.z), // 2
            glm::vec3(min.x, max.y, min.z), // 3
            glm::vec3(min.x, min.y, max.z), // 4
            glm::vec3(max.x, min.y, max.z), // 5
            glm::vec3(max.x, max.y, max.z), // 6: max
            glm::vec3(min.x, max.y, max.z)  // 7
        };

        // Формируем 12 ребер (каждое ребро — это пара вершин для GL_LINES)

        // Нижнее основание (Z min)
        lineVertices.push_back(c[0]); lineVertices.push_back(c[1]);
        lineVertices.push_back(c[1]); lineVertices.push_back(c[2]);
        lineVertices.push_back(c[2]); lineVertices.push_back(c[3]);
        lineVertices.push_back(c[3]); lineVertices.push_back(c[0]);

        // Верхнее основание (Z max)
        lineVertices.push_back(c[4]); lineVertices.push_back(c[5]);
        lineVertices.push_back(c[5]); lineVertices.push_back(c[6]);
        lineVertices.push_back(c[6]); lineVertices.push_back(c[7]);
        lineVertices.push_back(c[7]); lineVertices.push_back(c[4]);

        // Вертикальные стойки (соединяем низ и верх)
        lineVertices.push_back(c[0]); lineVertices.push_back(c[4]);
        lineVertices.push_back(c[1]); lineVertices.push_back(c[5]);
        lineVertices.push_back(c[2]); lineVertices.push_back(c[6]);
        lineVertices.push_back(c[3]); lineVertices.push_back(c[7]);
    }

    // 5. Отрисовка за ОДИН Draw Call
    if (!lineVertices.empty()) {
        glBindBuffer(GL_ARRAY_BUFFER, 0); // Отвязываем VBO, рисуем напрямую из RAM
        glEnableVertexAttribArray(posLoc);
        glVertexAttribPointer(posLoc, 3, GL_FLOAT, GL_FALSE, sizeof(glm::vec3), lineVertices.data());

        glDrawArrays(GL_LINES, 0, static_cast<GLsizei>(lineVertices.size()));

        glDisableVertexAttribArray(posLoc);
    }

    // Восстанавливаем состояния
    glDepthMask(GL_TRUE);
    glUseProgram(0);
}

// Draw after opaque geometry, before glass. The far-depth sky fills only background pixels.
void Render::RenderSky(const SkyDome& sky, CameraActor* camera, GLuint shader) {
    if (!sky.mesh || !sky.texture || !camera || !shader) return;
    const auto eye = camera->GetPosition();
    const auto forward = camera->GetForwardVector();
    const glm::vec3 position(eye.x, eye.y, eye.z);
    const glm::mat4 view = camera->GetViewMatrix();
    const glm::mat4 rotationOnly = glm::mat4(glm::mat3(view));
    const glm::mat4 projection = camera->GetProjectionMatrix();
    const glm::mat4 mvp = projection * rotationOnly;
    // No distance/frustum culling; camera translation never leaves the dome.
    glEnable(GL_DEPTH_TEST); glDepthFunc(GL_LEQUAL); glDepthMask(GL_FALSE);
    glDisable(GL_CULL_FACE);
    glEnable(GL_BLEND); glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA);
    glUseProgram(shader);
    glUniformMatrix4fv(glGetUniformLocation(shader, "uMVP"), 1, GL_FALSE, glm::value_ptr(mvp));
    glUniform1f(glGetUniformLocation(shader, "uPositionStep"), sky.positionStep);
    glUniform1i(glGetUniformLocation(shader, "uTexture"), 0);
    glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, sky.texture->textureID);
    glBindBuffer(GL_ARRAY_BUFFER, sky.mesh->vboID);
    const GLint positionAttribute = glGetAttribLocation(shader, "aPosition");
    const GLint uvAttribute = glGetAttribLocation(shader, "aTexCoord");
    glEnableVertexAttribArray(positionAttribute); glEnableVertexAttribArray(uvAttribute);
    glVertexAttribPointer(positionAttribute, 3, GL_SHORT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex,x));
    glVertexAttribPointer(uvAttribute, 2, GL_HALF_FLOAT, GL_FALSE, sizeof(Vertex), (void*)offsetof(Vertex,u));
    glDrawArrays(GL_TRIANGLES, 0, sky.mesh->vertexCount);
    glDisableVertexAttribArray(positionAttribute); glDisableVertexAttribArray(uvAttribute);
    glBindBuffer(GL_ARRAY_BUFFER, 0); glBindTexture(GL_TEXTURE_2D, 0);
    glDepthMask(GL_TRUE); glDisable(GL_BLEND); glEnable(GL_CULL_FACE);
    ++stats.drawCalls; ++stats.objectsTested; ++stats.objectsDrawn;
    ++stats.textureBinds; ++stats.vboBinds;
    stats.vertices += sky.mesh->vertexCount; stats.triangles += sky.mesh->vertexCount / 3;
    if (std::find(visibleTextures.begin(),visibleTextures.end(),sky.texture)==visibleTextures.end()) {
        visibleTextures.push_back(sky.texture);
        stats.visibleTextureBytes += sky.texture->sizeInBytes;
    }
    lastBoundTexture = lastBoundVBO = 0;
}

#include "CinematicPlayer.h"
void Render::RenderCinematic(CinematicPlayer& scene, CameraActor* camera, const std::vector<EngineLight>& lights, GLuint shader) {
    scene.Draw(camera, lights, shader, stats);
}
