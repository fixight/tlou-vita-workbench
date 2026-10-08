# Bedroom audio evidence

The previous VCN phone-only test started SFX at zero and omitted localized speech.
It was not a reconstructed soundtrack.

## SFX event

actor50/hom1-tstrm.pak, ANIM hom1-house-sarah-bedroom-phone--sarah:
notes pointer at ANIM+0x48 → owner 0x487dace9, count 1.
Note at 0x21aab8, type 0x5645883a, frame 154.0.
Properties: name 0x89e96364 → 0xe2092bbe.
MSB-first CRC32 of sfx-sarah-bedroom-phone-call = 0xe2092bbe.
Original stream: sound1/streams/sfx/sarah-bedroom-phone-call.xvag.
Scene time: 154 / 30 = 5.133333 seconds. Preserve the native note time.

## Localized speech

main/ss-audio-precache.txt lists the voice identifiers under
ss-hom-house-daughter-room. The daughter-room script contains say calls for
both identifiers, and say-pre-roll for Tommy. The bedroom-phone interaction
script is a separate script and must not replace the initial-room scene source.

DC globals in dc1/vox-igc-hometown.bin:

| Identifier | Global offset | Speech archive entry |
|---|---|---|
| vox-igc-sar-igc-hom-bedroom-phone-001 | 0xad0 | F189 |
| vox-igc-tmy-igc-hom-bedroom-phone-001 | 0x5d0 | F188 |

XVAG files from sound1/streams/speech/russian-sp.psarc contain matching SUBT
speech IDs. Sarah has stream-local subtitle frames 326, 424, 575; Tommy 348, 471.
Language ID 17 resolves text1/17.subtitles (CP1251 Russian). The English variants
have the same subtitle frame marks. Decoding the originals with the existing
Vita3K LibAtrac9 offline confirms leading silence (Sarah audible around 10.97 s,
Tommy Russian around 11.7 s). Do not remove this silence during bank conversion.

Both voices currently use explicitly selected scene offset zero. This is an
alignment configuration for complete performances, not a claim that a native
script-start offset has been fully proven. Player-facing verification remains
necessary. A different offset can be changed in scene.runtime.json without
changing C++ or re-encoding the audio.

Extraction is generic: ANIM events are decoded with relocation and bounds checks;
voice names resolve DC globals, then archive entry identities are checked against
SUBT metadata. The selected scene's voice identifiers and stream origins are
explicit inputs. See tools/extract_cinematic_audio.py.
