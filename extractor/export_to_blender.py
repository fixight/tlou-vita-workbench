#!/usr/bin/env python3
"""
export_to_blender.py
Универсальный инструмент для экспорта персонажей и моделей The Last of Us в Blender (.blend) и FBX.

Использование:
  python export_to_blender.py sarah
  python export_to_blender.py young-joel
  python export_to_blender.py --all
  python export_to_blender.py extracted_models/sarah/sarah.glb -o my_exports/sarah
"""
import argparse
import os
from pathlib import Path
import sys

from tlou_extractor.blender_export import find_blender, cli_outside_blender

MODELS_DIR = Path(__file__).resolve().parent / 'extracted_models'
EXPORTS_DIR = Path(__file__).resolve().parent / 'exports'

AVAILABLE_CHARACTERS = [
    'sarah',
    'young-joel',
    'young-tommy',
    'inf-fem-home-run-a'
]


def export_single(target: str, output: str = None) -> bool:
    try:
        cli_outside_blender([target, '-o', output] if output else [target])
        return True
    except SystemExit as e:
        return e.code == 0
    except Exception as e:
        print(f"[ERROR] Failed to export {target}: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Экспорт моделей TLOU в Blender (.blend со скелетом и анимациями) и FBX."
    )
    parser.add_argument("model", nargs="?", help="Имя персонажа (sarah, young-joel, young-tommy) или путь к .glb файлу")
    parser.add_argument("--all", action="store_true", help="Экспортировать всех доступных персонажей")
    parser.add_argument("-o", "--output", help="Папка для сохранения (по умолчанию: ./exports/<имя_модели>)")
    args = parser.parse_args()

    if args.all:
        print("=== Экспорт всех персонажей в Blender (.blend + .fbx) ===")
        success_count = 0
        total = 0
        for char in AVAILABLE_CHARACTERS:
            glb = MODELS_DIR / char / f"{char}.glb"
            if glb.is_file():
                total += 1
                out = EXPORTS_DIR / char
                print(f"\n--- Экспорт {char} -> {out} ---")
                if export_single(str(glb), str(out)):
                    success_count += 1
        print(f"\n=== Успешно экспортировано: {success_count} / {total} ===")
        return

    if not args.model:
        parser.print_help()
        print("\nДоступные персонажи в extracted_models:")
        for char in AVAILABLE_CHARACTERS:
            glb = MODELS_DIR / char / f"{char}.glb"
            status = "готов к экспорту" if glb.is_file() else "не найден"
            print(f"  - {char:20} [{status}]")
        return

    export_single(args.model, args.output)


if __name__ == '__main__':
    main()
