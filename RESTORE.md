# Восстановление на другом ПК

## 1. Исходники и зависимости

Клонировать с `--recurse-submodules`. При обычном clone выполнить
`git submodule update --init --recursive`. GLM, vitaGL и vdpm закреплены на конкретных
коммитах. Их версии и базовые коммиты исходных проектов есть в `dependencies.lock.json`.

Рабочий стек: Windows + WSL Ubuntu, Python 3.14 с numpy/Pillow; C++17;
VitaSDK arm-vita-eabi-g++ 15.2.0; Blender (bpy внутри Blender), FFmpeg/FFprobe.
Версию Blender и установленные расширения потребуется настроить отдельно.

В Ubuntu установить host-инструменты:

```sh
sudo apt-get update
sudo apt-get install git build-essential cmake ninja-build python3-venv ffmpeg wget patch unzip
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r extractor/requirements.txt
python -m pip install capstone
```

После проверки своего каталога VitaSDK можно воспользоваться официальным vdpm:

```sh
cd dependencies/vdpm
./bootstrap-vitasdk.sh
export VITASDK=/usr/local/vitasdk
export PATH="$VITASDK/bin:$PATH"
./install-all.sh
```

vdpm скачивает доступную версию SDK/пакетов; их двоичные версии не закреплены
историческим снимком. Для точного повторения сравнивать fingerprints или использовать
собственный архив установленного SDK. Нужны vitaGL, vitashark, SceShaccCgExt,
mathneon, taihen и VitaSDK pthread/stub-библиотеки; полный список — CMakeLists.txt.
Исходники используемой vitaGL закреплены в подмодуле. При пересборке её опции
Makefile выбирать осознанно: прежние опции конкретной установленной библиотеки
не удалось надёжно восстановить только по её файлу. Список установленных пакетов
сохранён в `sdk-packages.list`.

## 2. Образ и извлечение

Нужен собственный образ PS4 The Last of Us Remastered, содержащий
`build/Image0/build/ps4/main`. Это не PS5/PC Part I. Распакованные входные данные
должны содержать `actor50`, `pak32`, `texturedict1` и другие словари текстур.
Образ и распакованные ресурсы не включены.

У просмотрщика есть `TLOU_ASSET_ROOT` (основная папка распакованных ресурсов).
Более старые исследовательские скрипты ещё используют пути `D:/TLOUPS4/...`:
они сохранены, но могут потребовать явных аргументов или замены путей.
Не менять исходники массовой строковой заменой: сначала проверить конкретный скрипт.

Из папки `extractor`:

```sh
python -m tlou_extractor -i EXTRACTED -c hom-house-interior -o output_house
python -m tlou_extractor -i EXTRACTED -f actor50/sarah-player-tstrm.pak -o extracted_models/sarah
python -m tlou_extractor.export_austin_editor --help
python serve.py
```

Программы `--help` показывают актуальные параметры. Экспорт Остина, коллизий,
стриминга и Blender подробно описан в `extractor/BLENDER_LEVEL_EDITOR.md`,
`BLENDER_VITA_EXPORT.md`, `STATIC_LIGHTING.md`, `research/streaming`.

Сохранённый `extractor/viewer.html` очищен от встроенных ассетов. Для пересоздания
пустого viewer работает `python build_viewer.py --empty`; при этом используется
шаблон старого генератора. Сохранённый viewer является основной копией текущего UI.

## 3. Уровень и персонаж

1. Собрать/импортировать нужный уровень в Blender с исходными коллизиями.
2. Установить PlayerStart инструментом Vita и проверить теги дверей/триггеров.
3. Экспортировать актуальным `extractor/tlou_extractor/blender_vita_export.py`.
4. Разместить `level.bin` в `engine/assets/level.bin`, папки models/textures/metadata
   — в `engine/assets/assets/`. Персонажи — `engine/assets/characters/sarah16`.
5. При изменении level.bin заново создавать VDOR/VDIP и маску катсцены:
   они связаны с FNV1a содержимого уровня. Старые sidecar нельзя смешивать с новым уровнем.

Исходные световые данные парсятся; текущий движок использует цвет вершин.
Ручные изменения света, удаление/возврат объектов и положение PlayerStart, если они
сохранены только в старом `.blend`, потребуется повторить. Коллизия является отдельным
набором данных: удаление видимого меша не удаляет её автоматически.

Профили дверей: `extractor/tools/build_vita_door_profiles.py --help`.
Декодированные большие JSON-анимации дверей исключены, но код их получения
`tools/extract_door_interactions.py`, план профилей и результаты исследования сохранены.

## 4. Вступление и телефонная сцена

Требуются уже извлечённые house.glb и sarah.glb. Из корня репозитория:

```sh
python scripts/restore_cinematics.py --game-main IMAGE_MAIN --extracted EXTRACTED \
  --house HOUSE_GLB --sarah-glb SARAH_GLB --language russian
```

Скрипт экспортирует сцену кабинета как исходную основу, спальню, применяет сохранённую
политику управления, собирает ATRAC9 банк с голосами Сары/Томми и VCN v3.
Телефон берёт время из ANIM (154/30 = 5.133333 s); голосам оставляет оригинальную
внутреннюю тишину. Нулевой старт голосовых потоков — явная настройка порта, а не
заявление о полностью восстановленной VM игры.

Дополнительно подготовить предзаписанное вступление (FFmpeg должен быть в PATH):

```sh
python extractor/tools/prepare_vita_movies.py IMAGE_MAIN engine/assets/movies \
  --movie hom-intro --language russian
```

Маска мира требует конечного level.bin. Она собирается отдельно инструментом
`engine/tools/build_cinematic_world_mask.py` после получения уровня; смотреть `--help`
и `engine/docs/CinematicPlayer.md`. Не переносить маску от предыдущего level.bin.

## 5. Сборка и проверка

```sh
export VITASDK=/usr/local/vitasdk
export PATH="$VITASDK/bin:$PATH"
cmake -S engine -B engine/build -DCMAKE_BUILD_TYPE=Debug
cmake --build engine/build -j3
```

VPK будет в `engine/build/TLOU_Vita.vpk`. Упаковка всех ресурсов может занимать минуты.
Vita3K и реальная Vita настраиваются отдельно. Автодеплой: `-DVITA3K_APP_DIR=...`.
Без подготовленных ресурсов компиляция исходников не означает играбельный уровень.

Проверка содержимого снимка: `python scripts/verify_source_snapshot.py`.
Host-тесты: `python -m unittest discover -s engine/tools/tests -p test_audio_bank.py`.
Тесты `engine/tools/tests/run_*_smoke.py` и многие parser-тесты требуют
восстановленных ресурсов; не запускать весь набор, ожидая успеха без образа.

После изменения C++ заголовков использовать обычную чистую CMake-сборку. Старые
объектные файлы не сохранены: это исключает смешивание несовместимых ABI.

## Ограничения текущей работы

Вторичные/корректирующие и полные лицевые анимации восстановлены не полностью.
Камера сохраняет native lens/cut/DOF-параметры, но DOF blur не реализован.
Есть JobSystem и параллельная стартовая подготовка ресурсов, полноценный фоновый
стриминг во время геймплея ещё предстоит довести. Сценарная VM оригинала целиком
не восстановлена. FPS и память необходимо измерять на физической Vita.

