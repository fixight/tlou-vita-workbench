> Историческая заметка от 2026-10-04. Актуальный порядок восстановления и состояние на 2026-10-08: [RESTORE.md](../RESTORE.md).

# Продолжение проекта на другом ПК — 2026-10-04

## Что сохранено в Git

Парсер PAK/анимаций/текстур, просмотрщик, Blender-инструменты, экспорт LVL5 и SK16 v2,
исследования стриминга и триггеров, native-данные взаимодействия с дверями, тесты.
Репозиторий движка сохраняется отдельно (`TLOU_Vita`).

Образ игры, распакованные PAK, текстуры, GLB, Blender-сцены, готовые бинарники и SDK
не входят в коммит исходников. Они нужны для полного восстановления; см. отдельные
архивы и manifest в резервной копии. Один clone исходников не восстановит сцену.

## Исходные расположения

- актуальный парсер: `D:/TLOUPS4/fervent-pascal`;
- старый каталог `C:/Users/egors/Documents/antigravity/fervent-pascal` устарел;
- движок: WSL Ubuntu `/home/TLOU_Vita`;
- данные игры: `D:/TLOUPS4/Extracted` (actor50, pak32, texturedict1), главы также Extracted2/3;
- образ: `D:/Новая папка (3)/The Last of Us™ Remastered/build/Image0/build/ps4/main`;
- Blender: `D:/TLOUPS4/AustinStaticLighting/scene_door_process.blend` (двери, точки подхода);
- другая важная сцена: `scene_props_lighting.blend` (исправления освещения пропсов);
- последний экспорт уровня определяется `D:/TLOUPS4/vita_latest_props_lighting_build.txt`;
- актуальные runtime-ассеты: `/home/TLOU_Vita/assets`, именно их нужно восстановить;
- Vita3K: `C:/dev/Vita3K/cmake-build-debug/bin`;
- установленная игра: `C:/Users/egors/AppData/Roaming/Vita3K/Vita3K/ux0/app/TLOU00001`.

Сначала удобно восстановить расположение `D:/TLOUPS4`: многие старые исследовательские
скрипты используют абсолютные пути. Для другой структуры нужно поправить эти пути;
просмотрщик поддерживает переменную `TLOU_ASSET_ROOT`.

## Парсер и просмотрщик

Python 3.10+ (рабочая машина: 3.14), зависимости `python -m pip install -r requirements.txt`.
Capstone нужен для дизассемблирования; pyswizzle необязателен для части текстур.
Blender использовался 5.2.2 LTS; bpy предоставляется самим Blender.
Запустить `python serve.py` из репозитория; открыть `http://127.0.0.1:8080/viewer.html?animation-codec=4`.
При восстановлении моделей просмотрщика нужны соответствующие viewer_models/extracted_models.

## Текущее состояние

- animation codec 4, исправлены основные потоки, учтены сигнатуры rig;
  вторичные/corrective-потоки пока не восстановлены полностью;
- статические и скелетные вершины по 16 байт;
- SK16 v2 добавляет bind-space центры костей перед батчами, старый v1 читается;
- переходы используют центры костей и продолжающееся движение уходящего клипа;
  локомоция 0.28 s, взаимодействия 0.18 s;
- общий InteractionProcess: подход, разворот, парная анимация двери/персонажа,
  root motion XZ и коллизия, возврат управления;
- профили Сары: её спальня, ванная, спальня Джоэла. Входная дверь пока legacy;
- VDOR и VDIP привязаны к FNV1a содержимого конкретного level.bin. При переэкспорте
  уровня экспортировать sidecar заново; не смешивать бинарники разных сборок.

## Восстановление анимаций/дверей

Исходный расширенный GLB: `extracted_models/sarah/sarah_door_process.glb`.
Если его нет, после извлечения Сары см. `tools/append_sarah_door_push.py`:
скрипт сохраняет существующие клипы и добавляет push из hom1; пути пока локальные.
Экспорт:

```text
python tools/export_vita_character.py extracted_models/sarah/sarah_door_process.glb SARAH_OUT --interaction-clip sar-p-open-pull-l--sarah --interaction-clip hom1-house-door-push--sarah
python tools/build_vita_door_profiles.py --level ENGINE/assets/level.bin --output ENGINE/assets/assets/metadata/door_interactions.bin
```

SK16 и текстуры из SARAH_OUT разместить в ENGINE/assets/characters/sarah16.
Для исследования: research/door_interactions/*.json и tlou_extractor/door_interaction_data.py.
Для Blender см. BLENDER_VITA_EXPORT.md, BLENDER_LEVEL_EDITOR.md, STATIC_LIGHTING.md.

## Проверки

В WSL движка: `python3 tools/tests/run_skinned_smoke.py`, `run_door_smoke.py`,
`run_debug_smoke.py` (нужны g++, runtime-ассеты, GLM submodule должен быть инициализирован).
В парсере `python tests/verify_vita_character.py PATH/sarah.sk16` требует текстуры
рядом с пакетом. Значительная часть других тестов требует исходные PAK и старые
локальные пути: их отсутствие не является ошибкой восстановленного кода.

## Ещё не сделано

Асинхронный стриминг ассетов пользователь планирует написать сам. Сейчас основная
логика однопоточная. Вершинный свет ограничен плотностью сетки; lightmap обсуждались,
но переход обратно к lightmap не реализован. Новейшую правку плеч ещё нужно оценить
визуально на Vita3K/реальном железе; host-тесты прошли.
