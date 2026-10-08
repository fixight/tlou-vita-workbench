# AudioManager

Менеджер уже принадлежит `VitaEngine`. `GetAudioManager()` возвращает его адрес.
Он запускается после закрытия вступительного SceAvPlayer и автоматически читает
`app0:/assets/audio/level.vabk`, если банк существует. Загрузка банка не запускает
его звуки: моменты воспроизведения задаёт сценарий или игровой код.

```cpp
auto* audioManager = engine.GetAudioManager();
SoundHandle voice = audioManager->playSound("door.open");
audioManager->setVolume(voice, 0.7f);
audioManager->setPan(voice, -0.3f);
audioManager->stopSound(voice, 0.15f); // плавно остановить

SoundOptions options;
options.loop = SoundLoop::Loop;
auto music = audioManager->playSound("music.house", options);
audioManager->setBusVolume(AudioBus::Music, 0.4f);
audioManager->setPaused(true);
audioManager->setPaused(false);
```

Каждое проигрывание получает отдельный handle. Один звук можно проиграть несколько
раз одновременно. Нулевой handle означает неизвестный звук, превышение числа
голосов или переполнение очереди. `getState()` отличает Pending, Playing, Paused,
Finished, Failed и Stopped. Старый handle не управляет новым звуком в том же слоте.
`playSound()` и управление голосами не читают файлы, не декодируют звук и не ждут
завершения аудиобуфера; они помещают команду в ограниченную очередь под коротким mutex.
Команда применяется на следующем аудиобуфере (512 кадров, примерно 10.7 мс).

## Банки уровня и чанков

```cpp
audioManager->loadBank("app0:/assets/audio/house.vabk");
audioManager->loadBank("app0:/assets/audio/street.vabk");
audioManager->unloadBank("app0:/assets/audio/house.vabk");
```

Одинаковые определения звуков в двух банках используют один ресурс. Пока хотя бы
один банк владеет звуком, выгрузка другого не останавливает его. При исчезновении
последнего владельца проигрывания останавливаются в аудиопотоке, затем память
освобождается. До этого она остаётся учтена в бюджете. Конфликт имени/ID, файла или
параметров хранения отклоняет новый банк, сохраняя старые ресурсы.

`loadBank` делает блокирующую подготовку: заголовки проверяются, resident-пayload
читается целиком. Вызывайте его на экране загрузки или из загрузочной задачи,
а не в обновлении/рендере кадра. Повторная загрузка того же пути идемпотентна.
`unloadBank` только публикует остановку; оно не ждёт её выполнения.
Init/shutdown вызываются владельцем менеджера. Перед уничтожением нужно закончить
внешние задачи загрузки и вызовы API. Init и shutdown не вызываются из аудиопотока.

## Сборка на ПК

Отредактируйте `tools/audio_bank.example.json`, указав существующие исходные файлы:

```sh
python3 tools/build_audio_bank.py tools/audio_bank.example.json assets/assets/audio
# Отдельный банк для следующего чанка, с тем же каталогом ресурсов:
python3 tools/build_audio_bank.py street_audio.json assets/assets/audio --bank street.vabk
```

Команды выше запускаются из корня движка. Его staging-каталог `assets/`
копируется в app0, поэтому ресурсы попадают в `assets/assets/audio` на ПК
и в `app0:/assets/audio` при запуске.

Пути `source` задаются относительно JSON. По умолчанию runtime-путь —
`app0:/assets/audio`; для экспорта в staging-папку можно передать `--runtime-root`.
WAV должен содержать PCM16, 48 кГц, один или два канала. `--ffmpeg /usr/bin/ffmpeg`
включает конвертацию WAV при сборке; стерео сохраняется, явное `channels: 1`
разрешает downmix. XVAG принимается только с одним непрерывным ATRAC9-потоком
48 кГц, mono/stereo, без слоёв и чередования подресурсов. Неподдерживаемые варианты
отклоняются и требуют отдельной подготовки. Сам XVAG не передаётся декодеру.

Сборщик пишет короткие имена `.vas` (64-байтовый заголовок и payload), каталог
`.vabk` и JSON-отчёт. Контентные имена позволяют разным банкам ссылаться на тот же
файл. Файл каталога публикуется после проверки всех определений и бюджета.
`resident` держит payload в RAM: для ATRAC9 это сжатые данные, не весь PCM.
`stream` читает payload из файла по мере проигрывания; у активного голоса есть
16 КиБ буфер чтения и небольшие буферы декодера. Их память не входит в residentBytes.
По умолчанию resident-бюджет 8 МиБ, максимум 24 голоса, верхняя граница 32.

## Аудиопоток и Vita

Один аудиопоток выполняет чтение, native ATRAC9 decode, микширование в stereo PCM
и блокирующий `sceAudioOutOutput`. PCM не требует декодера. ATRAC9 использует
`SceAudiodec`: сохраняются параметры исходного потока, encoder delay пропускается,
контекст сбрасывается при зацикливании. Служебный padding/RIFF из XVAG
убирается сборщиком; входной и выходной буферы декодера выделяются в uncached RAM.
Количество сжатых голосов дополнительно
ограничено системным пулом ATRAC9 (16 каналов); отказ возвращается как Failed.
Произвольного runtime ресэмплинга, изменения pitch и пространственных эффектов
пока нет. Позиционный звук можно пока свести к вычислению volume/pan в игровом коде.

Микшер и жизненный цикл проверяются host-тестом с управляемым аудиоустройством,
а формат и упаковка — Python-тестами.
Отдельный native-тест `tests/audio_vita_smoke.cpp` проверяет PCM и два
исходных ATRAC9-звука телефона в Vita3K: потоковый и resident. Host-тест
использует тестовый декодер и не измеряет аппаратную нагрузку.
Производительность и звук на физической Vita ещё не проверены.
Звук предзаписанного видео остаётся у SceAvPlayer.

```sh
python3 tools/tests/test_audio_bank.py
g++ -std=c++17 -pthread -I. Managers/AudioManager.cpp System/AudioBank.cpp \
    System/VitaAudioBackend.cpp tests/audio_manager_test.cpp -o /tmp/audio_test
/tmp/audio_test
```

## Готовые звуки для первого уровня

В `level.vabk` подготовлены `sarah.phone.call` (stream) и `sarah.phone.dead`
(resident, 126976 байт сжатых данных). Можно сразу вызвать:

```cpp
auto voice = engine.GetAudioManager()->playSound("sarah.phone.call");
```

Это имена ресурсов, а не восстановленные события игрового сценария.
Автоматическая привязка к триггерам и таймлайну катсцены пока не сделана.
