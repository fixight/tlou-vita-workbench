# Prerecorded cutscenes

`Engine/MoviePlayer.cpp` uses SceAvPlayer (H.264/AAC MP4), five GPU-visible YUV output buffers,
a single fullscreen draw, and a separate PCM output thread. Public calls belong to the render
thread. `Close()` joins audio and waits for GPU use before releasing decoder resources.

GPU programs, the sky and Sarah are prepared before playback to avoid shader compilation
freezing the video or delaying control after it ends.

Startup optionally plays `app0:/movies/hom-intro.mp4`; START skips. Without that file, the old
three-thread loading path remains available. During video playback the loader pumps frames,
leaves resource reading/collision preparation to two workers, and publishes GL resources
between movie frames on the render thread. It still reads the level description/reserves
arenas on that thread: this is a startup integration, not a gameplay streaming manager.

Prepare videos on the PC using the parser tool `tools/prepare_vita_movies.py`:

```sh
python3 /mnt/d/TLOUPS4/fervent-pascal/tools/prepare_vita_movies.py \
  "IMAGE_MAIN" /home/TLOU_Vita/assets/movies --movie hom-intro --language russian
```

FFmpeg/FFprobe are required. `movies.bin` supplies localized speech resource IDs; the tool
extracts a single XVAG/ATRAC9 stream and converts it with video into 960x540/30 baseline
H.264 + 48 kHz stereo AAC. Source playback rate is explicit (`--source-fps`, default 60),
because FFprobe's raw H.264 rate can be misleading. The tool rejects unsupported layered
or interleaved audio. `.json` alongside MP4 records source ID, language and output metadata.

Other clips use the same `Open/Update/Draw/Close` API; story triggers are not automatically
bound to movie playback. Real hardware decoder throughput and memory usage need a physical
Vita test. Emulator playback alone cannot measure those.
