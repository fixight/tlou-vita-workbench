"""Recreate the currently integrated cinematics from explicitly supplied inputs."""
import argparse
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXTRACTOR = ROOT / 'extractor'
ENGINE = ROOT / 'engine'


def run(script, *arguments):
    command = [sys.executable, str(script), *(str(value) for value in arguments)]
    print('Running:', script.name, flush=True)
    subprocess.run(command, cwd=EXTRACTOR, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-main', type=Path, required=True)
    parser.add_argument('--extracted', type=Path, required=True)
    parser.add_argument('--house', type=Path, required=True)
    parser.add_argument('--sarah-glb', type=Path, required=True)
    parser.add_argument('--language', choices=['russian', 'english'], default='russian')
    args = parser.parse_args()
    for name in ['game_main', 'extracted', 'house', 'sarah_glb']:
        value = getattr(args, name).resolve()
        if not value.exists():
            parser.error(f'Missing input: {value}')
        setattr(args, name, value)
    study = EXTRACTOR / 'output_study_cinematic'
    bedroom = EXTRACTOR / 'output_bedroom_cinematic'
    runtime = ENGINE / 'assets/assets/cinematics/bedroom'
    run(EXTRACTOR / 'tools/export_study_cinematic.py',
        '--workspace', EXTRACTOR, '--extracted', args.extracted,
        '--game-main', args.game_main, '--house', args.house, '--output', study)
    run(EXTRACTOR / 'tools/export_bedroom_cinematic.py',
        '--workspace', EXTRACTOR, '--extracted', args.extracted,
        '--game-main', args.game_main, '--house', args.house, '--output', bedroom)
    shutil.copyfile(ROOT / 'recipes/bedroom.runtime.json', bedroom / 'scene.runtime.json')
    run(EXTRACTOR / 'tools/extract_cinematic_audio.py', bedroom / 'scene.json',
        '--game-main', args.game_main, '--vox-source', 'dc1/vox-igc-hometown.bin',
        '--voice', 'vox-igc-sar-igc-hom-bedroom-phone-001', 0,
        '--voice', 'vox-igc-tmy-igc-hom-bedroom-phone-001', 0,
        '--engine-tools', ENGINE / 'tools', '--output', runtime / 'audio',
        '--runtime-root', 'app0:/assets/cinematics/bedroom/audio', '--language', args.language)
    run(ENGINE / 'tools/build_cinematic.py', bedroom / 'scene.json', runtime,
        '--gameplay-glb', args.sarah_glb, '--feet-offset', '0.0013379697')
    print('Cinematics recreated. Export the matching level, gameplay character and world mask separately.')


if __name__ == '__main__':
    main()

