"""Prepare original PS4 movie BSF + localized XVAG audio for Vita SceAvPlayer.
Example (WSL; ffmpeg and ffprobe must be on PATH):
  python3 tools/prepare_vita_movies.py IMAGE_MAIN /home/TLOU_Vita/assets/movies \
      --movie hom-intro --language russian
No runtime transcoding or copyrighted assets are embedded in the engine code.
"""
import argparse
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from research.streaming.psarc import Psarc
from research.streaming.visibility_base import string_id


def movie_catalog(data):
    """DC00 movie definitions: symbol, name pointer, localized speech resource ID."""
    if data[:8] != b"00CD\x01\0\0\0":
        raise ValueError("Unsupported movies.bin")
    count = struct.unpack_from("<I", data, 20)[0]
    result = {}
    for index in range(count):
        symbol, kind, offset = struct.unpack_from("<IIQ", data, 32 + index * 16)
        if kind != 0x2ABB8A55:
            continue
        if offset + 80 > len(data):
            raise ValueError("Invalid movie definition offset")
        name_pointer = struct.unpack_from("<Q", data, offset + 8)[0]
        name = data[name_pointer:data.index(0, name_pointer)].decode("ascii")
        if string_id(name) != symbol or struct.unpack_from("<I", data, offset)[0] != symbol:
            raise ValueError("Movie name/symbol mismatch")
        result[name] = {"speech_id": struct.unpack_from("<I", data, offset + 16)[0]}
    return result


def xvag_atrac9_wave(data):
    """Rewrap a single continuous XVAG ATRAC9 stream; FFmpeg handles decoding.
    XVAG field meanings verified against vgmstream/src/meta/xvag.c.
    Layered/interleaved streams are rejected, rather than silently producing bad audio.
    """
    if data[:4] != b"XVAG" or data[8] & 1:
        raise ValueError("Expected little endian XVAG")
    start = struct.unpack_from("<I", data, 4)[0]
    chunks = {}
    position = 32
    while position + 8 <= start:
        tag = data[position:position + 4]
        size = struct.unpack_from("<I", data, position + 4)[0]
        if position + 8 + size > start:
            raise ValueError("Invalid XVAG chunk")
        chunks[tag] = data[position + 8:position + 8 + size]
        position += 8 + size
        if tag == b"0000":
            break
    fmt, info = chunks[b"fmat"], chunks[b"a9in"]
    channels, codec, samples, _, factor, rate, _, subsongs, layers = struct.unpack_from("<9I", fmt)
    if codec != 9 or factor != 1 or subsongs != 1 or layers != 1:
        raise ValueError("Only single, non-interleaved ATRAC9 movie tracks are supported")
    block_size, samples_per_block = struct.unpack_from("<II", info)
    if not block_size or not samples_per_block or start >= len(data):
        raise ValueError("Invalid ATRAC9 stream")
    config = info[8:12]
    delay = struct.unpack_from("<I", info, 20)[0]
    guid = bytes.fromhex("d242e147ba368d4d88fc61654f8c836c")
    wave_fmt = struct.pack("<HHIIHHHHI", 0xFFFE, channels, rate,
        rate * block_size // samples_per_block, block_size, 0, 34, 0, 0)
    wave_fmt += guid + struct.pack("<I", 1) + config + struct.pack("<I", 0)
    def chunk(tag, payload):
        return tag + struct.pack("<I", len(payload)) + payload + (b"\0" if len(payload) % 2 else b"")
    # WAVE's Sony ATRAC9 fact stores sample count and encoder delay.
    body = b"WAVE" + chunk(b"fmt ", wave_fmt)
    body += chunk(b"fact", struct.pack("<III", samples, 0, delay))
    body += chunk(b"data", data[start:])
    return b"RIFF" + struct.pack("<I", len(body)) + body


def prepare(image, output, movies, language, source_fps=60):
    output.mkdir(parents=True, exist_ok=True)
    catalog = movie_catalog(Psarc(image / "bin.psarc").read("dc1/movies.bin"))
    speech = Psarc(image / f"sound1/streams/speech/{language}-sp.psarc")
    reports = []
    for movie in movies:
        definition = catalog[movie]
        resource = f"{definition['speech_id']:04X}"
        source = image / f"movie1/{movie}.bsf"
        if not source.is_file():
            raise FileNotFoundError(source)
        target = output / f"{movie}.mp4"
        with tempfile.TemporaryDirectory(prefix="vita-movie-") as temporary:
            audio = Path(temporary) / "audio.at9"
            audio.write_bytes(xvag_atrac9_wave(speech.read(resource)))
            staged = Path(temporary) / "movie.mp4"
            command = ["ffmpeg", "-hide_banner", "-loglevel", "warning", "-y",
                "-framerate", str(source_fps), "-f", "h264", "-i", str(source),
                "-i", str(audio), "-map", "0:v:0", "-map", "1:a:0",
                "-vf", "scale=960:540,setsar=1", "-r", "30",
                "-c:v", "libx264", "-preset", "fast", "-crf", "20",
                "-profile:v", "baseline", "-level:v", "3.1", "-pix_fmt", "yuv420p",
                "-maxrate", "4M", "-bufsize", "8M", "-g", "60",
                "-c:a", "aac", "-ac", "2", "-ar", "48000", "-b:a", "160k",
                "-movflags", "+faststart", "-shortest", str(staged)]
            print(f"Preparing {movie}: localized audio {resource}, {source_fps} -> 30 fps", flush=True)
            subprocess.run(command, check=True)
            probe = subprocess.check_output(["ffprobe", "-v", "error", "-show_streams",
                "-show_format", "-of", "json", str(staged)], text=True)
            metadata = json.loads(probe)
            # Move only completed files; failed conversion leaves the installed movie intact.
            import shutil
            shutil.copyfile(staged, target.with_suffix(".mp4.tmp"))
            target.with_suffix(".mp4.tmp").replace(target)
            report = {"movie": movie, "speech_id": resource, "language": language,
                "source_fps": source_fps, "output": str(target), "probe": metadata}
            reports.append(report)
            (output / f"{movie}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    return reports


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image_main", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--movie", action="append", required=True)
    parser.add_argument("--language", default="russian")
    parser.add_argument("--source-fps", type=float, default=60,
        help="Source playback rate, not FFprobe's raw H264 guessed rate (hom-intro = 60)")
    args = parser.parse_args()
    prepare(args.image_main, args.output, args.movie, args.language, args.source_fps)
