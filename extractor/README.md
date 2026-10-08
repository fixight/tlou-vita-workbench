# The Last of Us Remastered (PS4) Asset Extractor

Автономный инструмент и Python-библиотека для извлечения и конвертации ассетов из распакованных архивов игры **The Last of Us Remastered (PS4)**.

Поддерживает извлечение:
- **Статической геометрии чанков локаций** (`hom-house-interior`, `hom-road-chunk-*` и т.д.) с восстановлением мировой иерархии сцены.
- **Одиночных моделей объектов и персонажей** (сетка, нормали, тангенты, UV0/UV1, коллизии, LOD уровни).
- **Скелетов и скиннинга** (иерархия костей, локальные трансформации, привязка весов).
- **Анимаций** (кривые каналов поворотов/смещений, тайминги, FPS).

- **Текстур** (DDS оригиналы без потерь + автоматическая конвертация в PNG для моментального использования в Blender/Maya/Unreal/Unity).

Анимации Сары обновлены: восстановлены предиктивные XYZ-каналы и логарифмические
кватернионы без искусственного сглаживания. Точность походки проверяется по
исходным трекам обеих стоп. Это пока декодер основного скелетного потока:
вторичные потоки и некоторые операции других персонажей ещё не поддержаны.
Подробности и ограничения — в разделе 4 `ARCHITECTURE_AND_SPECS.md`.

> 📘 **Для разработчиков и ИИ-агентов**:  
> Полная техническая спецификация реверс-инжиниринга бинарных структур Naughty Dog (PAK, ANIM, JOINT_HIERARCHY, Tag 1054/1547, кватернионы, скиннинг, инстансинг локаций) вынесена в отдельный документ:  
> ➡️ **[`ARCHITECTURE_AND_SPECS.md`](ARCHITECTURE_AND_SPECS.md)**

---

## Установка и требования

- **Python 3.10+** (протестировано на Python 3.14)
- **Pillow** (`pip install pillow`)

---

## Использование CLI

Модуль запускается командой `python -m tlou_extractor`:

### 1. Сборка чанка локации (статическая геометрия + расстановка инстансов)

```bash
python -m tlou_extractor -i "D:\TLOUPS4\Extracted" -c "hom-house-interior" -o "./output"
```
*Скрипт читает манифест `pak32/hom-house-interior.txt`, распаковывает геометрию комнат и интерьера из `pak32/hom-house-interior-tstrm.pak`, достает координаты 121 расставленного в доме объекта из `pak32/hom-house-interior-ingame14.pak` (`SPAWNER_GROUP`), подтягивает текстуры и экспортирует готовую сцену в `hom-house-interior.glb` и `hom-house-interior.gltf`.*

Дополнительно в папке чанка создается `manifest.json` с полным описанием всех найденных сущностей.

### 2. Извлечение одиночной модели (пропс или персонаж)

```bash
python -m tlou_extractor -i "D:\TLOUPS4\Extracted" -f "actor50/cell-phone-tstrm.pak" -o "./output"
```
*Извлекает модель, текстуры (в папку `textures/`), скелет (`skel`) и ассоциированные анимации (`on`, `off`, `idle`).*

Для персонажей (например, Сары или Джоэла) инструмент автоматически найдет базовый скелет (`sarah-skel-tstrm.pak`) и анимации:
```bash
python -m tlou_extractor -i "D:\TLOUPS4\Extracted" -f "actor50/sarah-player-tstrm.pak" -o "./output"
```

### 3. Пакетное извлечение всех актеров

```bash
python -m tlou_extractor -i "D:\TLOUPS4\Extracted" --batch-actors -o "./output/all_actors"
```

---

## Дополнительные параметры CLI

| Параметр | Значения | Описание |
|---|---|---|
| `-i`, `--input` | Путь к папке | Корневая папка с извлеченными файлами PS4 (`actor50`, `pak32`) |
| `-o`, `--output` | Путь | Выходная директория (по умолчанию `./output`) |
| `-c`, `--chunk` | Имя чанка | Собрать уровень/чанк по имени (например, `hom-house-interior`) |
| `-f`, `--file` | Путь к файлу | Извлечь конкретный `.pak` файл |
| `--format` | `glb`, `gltf`, `both` | Выходной формат 3D-файлов (по умолчанию `both`) |
| `--textures` | `dds`, `png`, `both`, `none` | Формат сохранения текстур (по умолчанию `both`) |
| `--lods` | `all`, `lod0` | Экспорт всех LOD уровней или только LOD0 (по умолчанию `all`) |
| `--no-actors` | Флаг | Не спавнить расставленные актеры при сборке чанка (только статическая геометрия уровня) |

---

## Структура библиотеки

- [`tlou_extractor/pak_reader.py`](tlou_extractor/pak_reader.py) — парсер структуры архивов Naughty Dog PAK (magic 2681, страницы, pointer fixups, ResItems).
- [`tlou_extractor/mesh_builder.py`](tlou_extractor/mesh_builder.py) — чтение `GEOMETRY_1`, потоков вершин (Position, Normal, Tangent, UV), индексных буферов и LOD.
- [`tlou_extractor/skeleton_reader.py`](tlou_extractor/skeleton_reader.py) — парсинг `JOINT_HIERARCHY`, иерархии костей и локальных матриц трансформации.
- [`tlou_extractor/anim_reader.py`](tlou_extractor/anim_reader.py) — парсинг `ANIM` и `ANIM_RAWCHANNELS`, извлечение треков и кривых анимаций.
- [`tlou_extractor/texture_handler.py`](tlou_extractor/texture_handler.py) — обработка `VRAM_DESC`, сборка DDS заголовков (BC1-BC7, RGBA8) и авто-конвертация в PNG через Pillow.
- [`tlou_extractor/gltf_writer.py`](tlou_extractor/gltf_writer.py) — чистый генератор спецификации **glTF 2.0** и **GLB** с поддержкой нод, материалов, скиннинга и анимаций.
- [`tlou_extractor/level_assembler.py`](tlou_extractor/level_assembler.py) — парсер `.txt` манифестов, объединение статических чанков и спавн актеров по координатам `SPAWNER_GROUP`.
- [`tlou_extractor/cli.py`](tlou_extractor/cli.py) — точка входа CLI.

---

## Тестирование

Запуск набора тестов:
```bash
python -m unittest tests/test_extractor.py
```
