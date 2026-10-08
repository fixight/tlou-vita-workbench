from pathlib import Path
import hashlib,json,shutil,sys
build=Path(sys.argv[1]).resolve()
app=Path('C:/Users/egors/AppData/Roaming/Vita3K/Vita3K/ux0/app/TLOU00001')
assert app.is_dir()
files=[(source,source.relative_to(build)) for source in (build/'assets').rglob('*') if source.is_file()]
files.append((build/'level.bin',Path('level.bin')))
files.append((Path('//wsl.localhost/Ubuntu/home/TLOU_Vita/cmake-build-debug-wsl/eboot.bin'),Path('eboot.bin')))
changed=unchanged=0
for source,relative in files:
    target=app/relative;target.parent.mkdir(parents=True,exist_ok=True)
    digest=hashlib.sha256(source.read_bytes()).digest()
    if target.is_file() and hashlib.sha256(target.read_bytes()).digest()==digest:
        unchanged+=1;continue
    temporary=target.with_name(target.name+'.vita-deploy-temp')
    shutil.copy2(source,temporary);temporary.replace(target)
    assert hashlib.sha256(target.read_bytes()).digest()==digest
    changed+=1
report=json.loads((app/'assets/metadata/vita_export_report.json').read_text(encoding='utf-8'))
assert report['position_quantization']['grid']=='shared_world'
print('VITA3K_DEPLOY_VERIFIED',str(app),'changed',changed,'unchanged',unchanged,'levels',len(report['levels']),flush=True)
