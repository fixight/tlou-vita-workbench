"""Verify the initial snapshot's files without requiring any game resources."""
from pathlib import Path
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]


def main():
    manifest = json.loads((ROOT / 'source-checksums.json').read_text(encoding='utf-8'))
    errors = []
    for name, expected in manifest.items():
        file = ROOT / name
        if not file.is_file():
            errors.append(f'Missing: {name}')
            continue
        # Git text normalization may change CRLF to LF between operating systems.
        raw = file.read_bytes().replace(b'\r\n', b'\n')
        if hashlib.sha256(raw).hexdigest() != expected:
            errors.append(f'Changed: {name}')
    if errors:
        print('\n'.join(errors))
        raise SystemExit(1)
    print(f'Verified {len(manifest)} source/configuration files against the initial snapshot.')


if __name__ == '__main__':
    main()
