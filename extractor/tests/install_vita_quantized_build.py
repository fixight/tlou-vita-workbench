"""Install a validated PC export into engine assets; preserve unrelated files."""
from pathlib import Path
import hashlib,json,shutil,struct,sys
build=Path(sys.argv[1]).resolve()
engine=Path('//wsl.localhost/Ubuntu/home/TLOU_Vita/assets')
new=json.loads((build/'assets/metadata/vita_export_report.json').read_text(encoding='utf-8'))
old=json.loads((engine/'assets/metadata/vita_export_report.json').read_text(encoding='utf-8'))
assert new['position_quantization']['grid']=='shared_world'
assert (build/'assets/metadata/verification.json').is_file()
assert set(new['levels'])==set(old['levels'])
assert new['main_level']['instances']==old['main_level']['instances']
comparison=json.loads((build/'assets/metadata/rebuild_comparison.json').read_text())
assert all(row['collision_bytes_unchanged'] and row['old_instances']==row['new_instances'] for row in comparison.values())
assert (build/'level.bin').read_bytes()[:32]==(engine/'level.bin').read_bytes()[:32]
# Old content-addressed resources remain available, allowing rollback with these records.
backup=build/'previous_installed_records';backup.mkdir(exist_ok=True)
for relative in ['level.bin']+[str(p.relative_to(engine)) for p in (engine/'assets/levels').glob('*.bin')]+[str(p.relative_to(engine)) for p in (engine/'assets/metadata').iterdir() if p.is_file()]:
    source=engine/relative;destination=backup/relative;destination.parent.mkdir(parents=True,exist_ok=True)
    shutil.copy2(source,destination)
changed=0;unchanged=0
files=sorted(p for p in (build/'assets').rglob('*') if p.is_file())+[build/'level.bin']
for source in files:
    relative=source.relative_to(build);target=engine/relative;target.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(source.read_bytes()).digest()
    if target.is_file() and hashlib.sha256(target.read_bytes()).digest()==digest:
        unchanged+=1;continue
    temporary=target.with_name(target.name+'.vita-install-temp')
    shutil.copy2(source,temporary);temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).digest()==digest
    changed+=1
print('ENGINE_ASSETS_INSTALLED',str(build),'changed',changed,'unchanged',unchanged,'rollback',str(backup),flush=True)
