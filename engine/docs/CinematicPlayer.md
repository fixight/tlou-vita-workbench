# Реалтайм-катсцены

При запуске порядок теперь такой: загрузка уровня → вступительное видео →
закрытие видеодекодера и загрузка ресурсов сцены →
`bedroom/scene.vcn` (Сара просыпается и отвечает на звонок) → геймплей.
Катсцена длится 30.3667 секунды. Пока она активна, перемещение, взаимодействие,
физика персонажа и свободная debug-камера отключены. По окончании возвращается
предыдущая политика управления. Сара продолжает игру из конечной позиции сцены;
`PlayerStart` повторно не применяется.

## Управление и завершение

После загрузки сцены запуск можно вызвать из сценария:

```cpp
engine.PlayCinematic(); // Политика и её смены читаются из scene.vcn.
// Явное переопределение при необходимости:
engine.PlayCinematic(PlayerControl::FullCinematic());
// Или тело анимируется сценой, но игрок может вращать игровую камеру:
engine.PlayCinematic(PlayerControl::CameraOnly());

if (engine.ConsumeCinematicFinished()) {
    // Пришло один раз: естественное завершение сцены и передача управления.
    StartNextStoryTask();
}
```

`GetCinematicPlayer()->GetPlaybackTime()` возвращает текущее время сцены.
Звуковые события VCN v3 запускаются проигрывателем автоматически.
`IsCinematicPlaying()` сообщает текущий статус, `GetStoryPhase()` отличает Loading,
Movie, RealtimeCinematic и Gameplay. `CancelCinematic()` возвращает управление,
но не выдаёт событие успешного завершения. Повторный запуск активной сцены отклоняется.
Событие можно проверять в `VitaEngine::Update()`; внутренний цикл обновляет сцену,
выполняет handoff и публикует событие. Оно сохраняется до чтения.

Политика первого запуска берётся из VCN v3. Ограничения задаются портом,
а не выдаются за восстановленные команды сценария Naughty Dog.

## Данные и время

`CinematicPlayer` читает подготовленный VCN1. Все актёры и камера используют одно
время сцены; её длина определяется таймлайном, не звуком или количеством отрисованных
кадров. Камера сохраняет quaternion, включая roll. Жёсткие скачки между отсчётами
не размазываются. VCN1 версии 2 хранит исходные фокусное расстояние, смешивание
с базовым FOV, маркер смены плана и параметры глубины резкости. Угол обзора
вычисляется через горизонтальную ширину кадра 36 мм и переводится в вертикальный
для glm. Старые VCN1 версии 1 читаются с прежним постоянным вертикальным FOV.

В этой сцене четыре отдельных SK16 v2 модели: Сара, телефон, кровать и подушка.
Совпадающие с игровой моделью текстуры переиспользуются из её банка.
Сохранён исходный root motion и все 912 кадров; gameplay-нормализация стоп и удаление
XZ-движения к ним не применяются. Для игровой камеры и handoff на ПК вычисляется
траектория опорной точки персонажа относительно корня игрового idle-скелета.

VCM1 временно убирает треугольники статических копий кровати/подушки/телефона,
сопоставленные по исходной геометрии. Соседние треугольники объединённых KD-батчей
сохраняются. После сцены восстанавливаются исходные меши. Коллизия не меняется.
Маска привязана к хэшу `level.bin`: после повторного экспорта уровня её нужно
пересобрать. При отсутствии/несовместимости данных начало сцены отклоняется,
движок продолжает обычный запуск и пишет причину в лог.

Текущий экспорт принадлежит bedroom-сцене. Сборщик понимает несколько последовательных
стадий и актёров, но игровой handoff сейчас строится для игрока с ID `sarah`.
Оригинальные тайминги аудио ещё не подтверждены. VCN v3 автоматически запускает
явно заданные события. Телефонный эффект запускается по исходной метке кадра 154 (5.133333 с).
Голоса Сары F189 и Томми F188 извлечены из russian-sp.psarc. Их начальная
тишина сохранена; оба потока запущены с начала сцены. Эта точка отсчёта речи
выбрана явно и ещё требует визуальной проверки синхронизации.

## Сборка и проверки

Из корня движка (Python с NumPy/Pillow):

```sh
python tools/build_cinematic.py /path/to/output_bedroom_cinematic/scene.json \
    assets/assets/cinematics/bedroom --gameplay-glb /path/to/extracted_models/sarah/sarah.glb \
    --feet-offset 0.0013379697 --shared-assets assets
python tools/build_cinematic_world_mask.py /path/to/output_bedroom_cinematic/scene.json \
    assets/level.bin assets/assets/cinematics/bedroom/mask
python3 tools/tests/run_cinematic_smoke.py
```

Host-тест проверяет реальные SK16-файлы, камеру, draw totals, опорную точку,
завершение один раз, отмену и привязку/восстановление маски уровня. Отдельный
`tests/cinematic_clock_test.cpp` проверяет восстановление ограниченной политики,
паузы времени/некорректный dt и перепрыгивание конца при длинном кадре.

Регрессионный `run_skinned_smoke.py` проходит загрузку/рендер и останавливается
на существующем несовпадении sidecar дверей с текущим `level.bin`
(`doors.Load`), до теста переходов. Дверные sidecar этой задачей не менялись.

Для этой сборки `_newlib_heap_size_user` поднят с 256 до 320 МиБ.
Формат матриц поз, точность и количество кадров не сокращались.
Размеры mesh/texture-арен не менялись; текстуры Сары переиспользуются.

Проверено в Vita3K/OpenGL: видео → полная реалтайм-катсцена спальни →
геймплей, с восстановлением камеры, персонажа, физики и HUD. После изменения
CameraActor выполнена полная перекомпиляция всех 29 единиц трансляции: старые
объектные файлы с прежним расположением полей вызывали вылет при передаче управления.
На физической PS Vita эта сборка пока не проверялась.


## Камера: объектив и глубина резкости

`camera.GetCinematicLens()` возвращает текущие параметры; `HasCinematicLens()`
отличает их от старого формата. `focalLengthMm` — фокусное расстояние объектива,
`horizontalFov` — рассчитанный угол обзора. В первой сцене 50 мм дают 39.60°
по горизонтали. Позиция камеры не подгонялась вручную.

`nearStart`, `nearEnd`, `farStart`, `farEnd` — исходные дистанционные границы
legacy DOF. Резкая область находится между nearEnd и farStart. `blurRadius`
хранит радиус, `overrideDisable >= .5` отключает именно авторский override,
а `hasDepthOfField` сообщает наличие канала в исходнике. Это не f-stop и не
одна «точка фокуса». Автоматический постпроцесс размытия пока не включён.

VCN1 v2 после cameraTrack и playerTrack каждой стадии добавляет:
float fps, uint32 sampleCount, uint32 flags (бит 0: DOF есть), затем по
10 float на кадр: horizontalFov, focalLengthMm, defaultFovBlend, cutMarker,
blurRadius, nearStart, nearEnd, farStart, farEnd, overrideDisable.
Количество/частота совпадают с камерой; поля проверяются на конечность.
На дробных кадрах сначала интерполируется объектив, потом рассчитывается FOV.
Маркер cut использует пороги оригинального PS4 sampler и общий вес для камеры
и её дополнительных параметров. Для спальни дополнение занимает 36 492 байта.

`--timeline-only` обновляет только scene.vcn и отчёт, не пересобирая SK16.
При таком экспорте нужно сохранить исходный `--feet-offset 0.0013379697`.


## Unified resource: VCN version 3

`assets/assets/cinematics/bedroom/scene.vcn` is the runtime entry point. It contains
actor animation references, placement curves, player anchor/handoff, camera pose
and animated lens/DOF metadata, control changes, audio bank references and timed
sound starts. SK16 models/textures and VAS sound payloads stay external so that
shared resources do not need duplication. The catalogues are prepared before
playback; playback does not parse JSON or synchronously open assets.

Edit `scene.runtime.json` beside the extracted `scene.json`, then rebuild with
`tools/build_cinematic.py --timeline-only` (same gameplay model and feet offset as
the original export). Times are absolute seconds from scene start, across stages.
The runtime sidecar accepts:

```json
{
  "timing_source": "port_authored_not_recovered_script",
  "control": [{"time": 0, "profile": "full_cinematic"}],
  "audio_banks": ["app0:/assets/audio/level.vabk"],
  "audio": [{"time": 0, "sound": "sarah.phone.call", "volume": 1,
             "pan": 0, "loop": false}]
}
```

`full_cinematic` locks walking/camera/interaction; `camera_only` keeps scripted
character motion but permits gameplay camera look. `gameplay` restores gameplay
pose permissions; normally use scene completion for the actual handoff.
Existing extracted control profiles are used if the sidecar omits `control`.
Controls must start at zero and have strictly increasing times. Sounds may share
one time. Each crossed sound start is submitted once, including across long
frames. Cancellation/end stops only voices created by this player, preserving
unrelated ambient/music voices. Completion remains a consume-once event.

The bedroom phone SFX now starts at native ANIM note frame **154 / 30 = 5.133333 seconds**.
Sarah F189 and Tommy F188 are separate localized composite performances. Both
keep their original pre-roll silence and use an explicitly selected scene origin
of zero; this voice origin still requires visual synchronization verification.
Their internal SUBT marks are preserved in the extractor evidence.
The original phone-dead sound is an interaction asset, not automatically played
at the end of this scene. Native controller transition times are also not proven.
DOF values are stored; a GPU depth-of-field blur pass is not enabled.

Engine usage after AudioManager initialization:

```cpp
cinematic.Load("app0:/assets/cinematics/bedroom/scene.vcn", memory);
cinematic.PrepareAudio(audioManager);
PlayCinematic(); // use the resource's controller track
```

The overload `PlayCinematic(policy)` deliberately overrides the resource's control
track. On finish/cancel the engine restores the previously active control policy.

Binary layout: V3 preserves the complete V2 stage layout, then appends:

* `u32 controlCount`, followed by `{f32 time, u32 flags}`.
  Flags: bit 0 cinematic character pose; bit 1 cinematic camera pose;
  bits 2..5 movement, camera look, interaction, debug camera.
* `u32 bankCount`, followed by length-prefixed UTF-8 bank paths.
* `u32 soundCount`, followed by `{f32 time, string soundName,
  f32 volume, f32 pan, u32 loop}`; loop is 0 once or 1 loop.

All numeric values are little-endian. Reader validates limits, times, flags,
finite values, strings and EOF. V1/V2 keep legacy full-cinematic control and have
no audio cue track. Banks stay cached in AudioManager and can be unloaded by the
level's resource owner; the player does not unload shared banks.


## Extract localized dialogue and native animation sound events

`tlou_extractor/cinematic_audio.py` reads relocated ANIM notes, DC vox bindings
and XVAG SUBT records. `tools/extract_cinematic_audio.py` in the parser project
resolves SFX names against the archive, extracts explicitly selected voices,
creates a dedicated streaming VAB bank and updates scene.runtime.json. It does
not infer voice origin from the duration difference or trim silence.

Bedroom bindings:

* `vox-igc-sar-igc-hom-bedroom-phone-001` → F189 (Russian 22.904354 s).
* `vox-igc-tmy-igc-hom-bedroom-phone-001` → F188 (Russian 17.264708 s).
* `sfx-sarah-bedroom-phone-call` → ANIM note frame 154.

The voice bindings are present in ss-hom-house-daughter-room and resolved through
dc1/vox-igc-hometown.bin; ss-hom-house-bedroom-phone alone does not supply this
initial scene's dialogue. Composite voice files contain leading silence. SUBT
records identify Sarah's segments at frames 326/424/575 and Tommy's at 348/471;
these are stream-local marks, not scene-start instructions.

All three sounds are streamed as original ATRAC9; no uncompressed WAV copies are
installed in the game. Current combined compressed payload is 794880 bytes.
The voices use the dialogue bus; the telephone uses the effects bus.
