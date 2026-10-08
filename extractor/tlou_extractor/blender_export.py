"""Blender export script: imports TLOU geometry, armature, and animations into Blender,
sets up all actions with fake users and NLA tracks, and exports .blend and animated .fbx.

Can be run:
  1. Inside Blender:
     blender --background --factory-startup --python blender_export.py -- <job.json | model.glb> [output_dir]
  2. Outside Blender via standard Python:
     python -m tlou_extractor.blender_export <job.json | model.glb> [-o output_dir]
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

try:
    import bpy
except ImportError:
    bpy = None


def find_blender():
    candidates = [
        os.environ.get('BLENDER_PATH'),
        shutil.which('blender'),
        r'D:\SteamLibrary\steamapps\common\Blender\blender.exe'
    ]
    candidates += [str(p) for p in Path('C:/Program Files/Blender Foundation').glob('Blender*/blender.exe')]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return candidate
    raise ValueError('Blender not found; set BLENDER_PATH environment variable')


def write_blender_readme(folder: Path, model_name: str, action_count: int):
    readme_path = folder / 'README_BLENDER.md'
    content = f"""# Инструкция по использованию в Blender ({model_name})

В данном архиве содержатся файлы для Blender и игровых движков:
- **`scene.blend`** (или **`{model_name}.blend`**) — проект Blender с полным скелетом (Armature), всеми полигональными мешами, весами вершин (Vertex Groups) и всеми анимациями ({action_count} шт.).
- **`scene.fbx`** (или **`{model_name}.fbx`**) — запеченный FBX со скелетом, мешами и запеченными ключевыми кадрами анимаций для импорта в Unreal Engine, Unity, Maya или 3ds Max.
- **`{model_name}.glb`** — исходная бинарная модель glTF 2.0 со встроенными анимациями.

---

## Как переключать анимации в Blender:

1. Откройте файл **`scene.blend`** в Blender (поддерживаются версии 4.x, 5.x, включая Blender 5.2 LTS).
2. Выделите объект **`Armature`** (скелет персонажа).
3. Переключитесь в окно **Dope Sheet** (Лист экспозиций) и в верхнем выпадающем меню выберите **Action Editor** (Редактор действий).
4. В селекторе действий (Action Selector) вы увидите полный список всех анимаций ({action_count} анимаций).
   - Выберите любую анимацию из списка (например, ходьба `*-walk-*`, ожидание `*-idle-*`, бег `*-run-*`).
5. Нажмите клавишу **Пробел** (**Spacebar**), чтобы запустить воспроизведение анимации!
6. Все анимации сохранены с флагом **Fake User**, поэтому они не пропадут при сохранении и закрытии файла.

---

## How to Switch Animations in Blender (English):

1. Open **`scene.blend`** in Blender (4.x / 5.x / 5.2 LTS).
2. Select the **`Armature`** object.
3. Open the **Dope Sheet** editor and switch its mode to **Action Editor**.
4. In the Action Selector dropdown, choose any of the {action_count} actions.
5. Press **Spacebar** to play the animation.
"""
    readme_path.write_text(content, encoding='utf-8')


def setup_armature_and_actions(armature_obj=None):
    """Marks all actions with fake user, ensures NLA tracks or stashing, and activates an action."""
    if not bpy:
        return 0

    actions = list(bpy.data.actions)
    for act in actions:
        act.use_fake_user = True

    arm = armature_obj
    if not arm:
        arms = [o for o in bpy.data.objects if o.type == 'ARMATURE']
        if arms:
            arm = arms[0]

    if arm:
        if not arm.animation_data:
            arm.animation_data_create()

        # Choose a good default action (walk or idle if present, else first action)
        if actions:
            best_act = next((a for a in actions if any(k in a.name.lower() for k in ('walk-fw', 'walk', 'idle', 'run'))), actions[0])
            arm.animation_data.action = best_act

    return len(actions)


def add_streaming(document, folder):
    from mathutils import Vector
    collection = bpy.data.collections.new('Streaming & gameplay regions')
    bpy.context.scene.collection.children.link(collection)
    root = bpy.data.objects.new('TLOU_STREAMING_DATA', None)
    collection.objects.link(root)
    root['nd_type'] = 'streaming_metadata'
    root['nd_streaming_json'] = json.dumps(document, ensure_ascii=False)
    text = bpy.data.texts.new('streaming.json')
    text.write(json.dumps(document, ensure_ascii=False, indent=2))
    cards={card['id']:card for card in document.get('trigger_catalog',{}).get('triggers',[])}
    for record in document['regions']:
        points = [v for s in record['shapes'] for f in s['faces'] for v in f['world_vertices']]
        center = [(min(v[a] for v in points) + max(v[a] for v in points)) / 2 for a in range(3)]
        parent = bpy.data.objects.new(record['name'], None)
        collection.objects.link(parent)
        parent.location = (center[0], -center[2], center[1])
        parent.empty_display_size = 0.5
        parent['nd_type'] = record['type']
        parent['nd_region_id'] = record['id']
        parent['nd_source_level'] = record['source_level']
        parent['nd_preview_set'] = record.get('selector', {}).get('value', 1)
        parent['nd_condition_status'] = record.get('selector', {}).get('kind', 'gameplay_not_decoded')
        if record['id'] in cards:
            parent['nd_trigger_info_json']=json.dumps(cards[record['id']],ensure_ascii=False)
            parent['nd_trigger_category']=cards[record['id']]['category']
        for key,value in {'nd_cpp_enabled':False,'nd_cpp_action':'','nd_cpp_phase':'enter',
                          'nd_cpp_once':False,'nd_cpp_target':'','nd_cpp_parameters':'{}'}.items():
            parent[key]=value
        for index, shape in enumerate(record['shapes']):
            vertices = [v for face in shape['faces'] for v in face['world_vertices']]
            midpoint = [(min(v[a] for v in vertices) + max(v[a] for v in vertices)) / 2 for a in range(3)]
            native_center = Vector((midpoint[0], -midpoint[2], midpoint[1]))
            mesh = bpy.data.meshes.new('Region volume')
            faces=[];cursor=0
            for face in shape['faces']:
                count=len(face['world_vertices']);faces.append(list(range(cursor,cursor+count)));cursor+=count
            mesh.from_pydata([Vector((x,-z,y)) - native_center for x,y,z in vertices], [],faces)
            mesh.update()
            obj = bpy.data.objects.new(f'{record["name"]}__volume_{index}', mesh)
            collection.objects.link(obj)
            obj.parent = parent
            obj.location = native_center - parent.location
            obj['nd_type'] = 'region_volume'
            obj['nd_role'] = 'display' if record['type'] == 'streaming_region' else 'gameplay'
            obj['nd_region_id'] = record['id']
            obj.display_type = 'WIRE'
            obj.hide_render = True
            obj.color = (1.0, 0.55, 0.1, 0.2)
    runtime_path = Path(__file__).with_name('region_runtime.py')
    bpy.data.texts.load(str(runtime_path))
    shutil.copy2(runtime_path, folder/'region_runtime.py')
    alpha_path=Path(__file__).with_name('blender_material_alpha.py')
    bpy.data.texts.load(str(alpha_path))
    shutil.copy2(alpha_path,folder/alpha_path.name)
    vita_path=Path(__file__).with_name('blender_vita_export.py')
    bpy.data.texts.load(str(vita_path))
    shutil.copy2(vita_path,folder/vita_path.name)
    prop_path=Path(__file__).with_name('blender_prop_lighting.py')
    shutil.copy2(prop_path,folder/prop_path.name)
    tools_path = Path(__file__).with_name('blender_streaming_tools.py')
    if tools_path.exists():
        bpy.data.texts.load(str(tools_path))
        (folder/'blender_streaming_tools.py').write_text(tools_path.read_text(encoding='utf-8'), encoding='utf-8')


def apply_imported_alpha(folder):
    import importlib.util
    path=Path(__file__).with_name('blender_material_alpha.py')
    spec=importlib.util.spec_from_file_location('nd_material_alpha',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module.apply_imported(folder)


def refresh_imported_alpha():
    import importlib.util
    path=Path(__file__).with_name('blender_material_alpha.py')
    spec=importlib.util.spec_from_file_location('nd_material_alpha',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.toggle(bpy.context.scene)


def apply_scene_static_lighting(paths, folder, default_level=None):
    """Consume automatic lighting sidecars without changing streaming visibility."""
    import importlib.util
    spec = importlib.util.spec_from_file_location('nd_static_lighting',Path(__file__).with_name('blender_static_lighting.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    reports=[]
    for value in paths:
        manifest_path=Path(value)
        if not manifest_path.is_absolute(): manifest_path=folder/manifest_path
        manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        if not manifest.get('records'): continue
        if default_level:
            for obj in bpy.context.scene.objects:
                if obj.type=='MESH':
                    obj['nd_type']='visual'; obj['nd_level_id']=default_level
        reports.append(module.apply_lighting(manifest_path,configure_view=False))
    if any(r['matched'] for r in reports):
        module.configure_preview_view()
    (folder/'static_lighting_report.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
    guide=Path(__file__).resolve().parents[1]/'STATIC_LIGHTING.md'
    if reports and guide.exists(): shutil.copyfile(guide,folder/'STATIC_LIGHTING.md')
    return reports


def configure_material_previews():
    for mesh in bpy.data.meshes:
        if mesh.uv_layers:
            primary = mesh.uv_layers.get('UVMap') or mesh.uv_layers[0]
            mesh.uv_layers.active = primary
            primary.active_render = True
    for material in bpy.data.materials:
        if not material.use_nodes:
            continue
        nodes = material.node_tree.nodes
        shader = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if shader:
            links = shader.inputs['Base Color'].links
            if links and links[0].from_node.type == 'TEX_IMAGE':
                nodes.active = links[0].from_node


def export_direct_glb(glb_path: Path, output_dir: Path, base_name: str = None):
    """Imports a GLB model into Blender, sets up fake users & NLA, and exports .blend and .fbx."""
    if not base_name:
        base_name = glb_path.stem

    output_dir.mkdir(parents=True, exist_ok=True)

    # Clean default Blender scene completely
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)

    print(f"[Blender] Importing GLB: {glb_path}")
    bpy.ops.import_scene.gltf(filepath=str(glb_path))
    apply_imported_alpha(glb_path.parent)
    lighting_source=glb_path.parent/'static_lighting'
    if (lighting_source/'lighting.json').is_file():
        lighting_target=output_dir/'static_lighting'
        if lighting_source.resolve()!=lighting_target.resolve():
            shutil.copytree(lighting_source,lighting_target,dirs_exist_ok=True)
        apply_scene_static_lighting(['static_lighting/lighting.json'],output_dir,default_level=glb_path.stem)

    refresh_imported_alpha()
    # Configure Armature and all Actions
    num_actions = setup_armature_and_actions()
    has_armature = any(o.type == 'ARMATURE' for o in bpy.data.objects)

    print(f"[Blender] Loaded: {len(bpy.data.objects)} objects, {num_actions} actions, has_armature={has_armature}")

    # Set unit settings
    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.0

    # Export animated FBX
    fbx_path = output_dir / f'{base_name}.fbx'
    scene_fbx = output_dir / 'scene.fbx'
    print(f"[Blender] Exporting animated FBX: {fbx_path}")

    fbx_kwargs = dict(
        use_selection=False,
        object_types={'ARMATURE', 'MESH', 'EMPTY'} if has_armature else {'MESH', 'EMPTY'},
        add_leaf_bones=False,
        bake_anim=bool(num_actions > 0),
        bake_anim_use_all_actions=bool(num_actions > 0),
        bake_anim_use_nla_strips=bool(num_actions > 0),
        bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0,
        use_custom_props=True,
        path_mode='AUTO',
        embed_textures=True,
        axis_forward='-Z',
        axis_up='Y'
    )
    refresh_imported_alpha()
    configure_material_previews()
    bpy.ops.export_scene.fbx(filepath=str(fbx_path), **fbx_kwargs)
    if fbx_path != scene_fbx:
        shutil.copyfile(fbx_path, scene_fbx)

    # Pack textures
    packing_warnings = []
    for image in bpy.data.images:
        if image.source == 'FILE' and not image.packed_file:
            try:
                image.pack()
            except RuntimeError as exc:
                packing_warnings.append({'image': image.name, 'error': str(exc)})
    (output_dir / 'packing_warnings.json').write_text(json.dumps(packing_warnings, indent=2))

    # Save .blend files
    blend_path = output_dir / f'{base_name}.blend'
    scene_blend = output_dir / 'scene.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
    if blend_path != scene_blend:
        shutil.copyfile(blend_path, scene_blend)

    # Copy GLB to output folder as well
    target_glb = output_dir / f'{base_name}.glb'
    if glb_path.resolve() != target_glb.resolve():
        shutil.copyfile(glb_path, target_glb)

    # Write instructions
    write_blender_readme(output_dir, base_name, num_actions)
    print(f"[Blender] Successfully exported {base_name}.blend, {base_name}.fbx, and {base_name}.glb!")


def run_scene_json(path: Path):
    """Handles level/chunk export from scene.json, including characters or static geometry."""
    scene = json.loads(path.read_text(encoding='utf-8'))
    folder = path.parent

    # If this job specifies a character GLB:
    char_glb = scene.get('character_glb')
    if char_glb and Path(char_glb).is_file():
        char_name = scene.get('character_name', Path(char_glb).stem)
        export_direct_glb(Path(char_glb).resolve(), folder, base_name=char_name)
        return

    # Otherwise, clean scene and load geometry/collisions/streaming
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    visible = bpy.data.collections.new('Visual geometry')
    collision = bpy.data.collections.new('Original game collision')
    bpy.context.scene.collection.children.link(visible)
    bpy.context.scene.collection.children.link(collision)
    materials = {}
    level_collections = {}

    for item in scene.get('meshes', []) + scene.get('collisions', []):
        is_collision = item.get('collision', False)
        points = list(item['vertices'])
        faces = item['faces']
        if is_collision:
            seen = set()
            faces = []
            for face in item['faces']:
                key = tuple(sorted(face))
                if key in seen:
                    first = len(points)
                    points.extend(item['vertices'][v] for v in face)
                    faces.append(list(range(first, first+len(face))))
                else:
                    seen.add(key)
                    faces.append(face)
        mesh = bpy.data.meshes.new(item['name'])
        mesh.from_pydata([(x, -z, y) for x,y,z in points], [], faces)
        mesh.update()
        obj = bpy.data.objects.new(item['name'], mesh)
        owner = item.get('level_id', '')
        destination = collision if is_collision else visible
        if owner:
            key = (is_collision, owner)
            if key not in level_collections:
                level_collections[key] = bpy.data.collections.new(('COLLISION_' if is_collision else 'LEVEL_') + owner)
                destination.children.link(level_collections[key])
            destination = level_collections[key]
        destination.objects.link(obj)
        obj['nd_type'] = 'collision' if is_collision else 'visual'
        obj['nd_level_id'] = item.get('level_id', '')
        obj['nd_source_mesh'] = item.get('source_mesh',item['name'])
        if is_collision:
            obj.display_type = 'WIRE'
            obj.hide_render = True
            obj['collision'] = True
            obj['collision_kind'] = 'triangle_mesh'
            obj['source_resource'] = item.get('source_resource', '')
            continue
        uvs = item.get('uvs', [])
        if len(uvs) == len(points):
            layer = mesh.uv_layers.new(name='UVMap')
            for loop in mesh.loops:
                layer.data[loop.index].uv = uvs[loop.vertex_index]
        normals = item.get('normals', [])
        if len(normals) == len(points):
            mesh.normals_split_custom_set_from_vertices([(x,-z,y) for x,y,z in normals])
        texture = item.get('texture_path')
        key = texture or item.get('material', 'Default')
        if key not in materials:
            mat = bpy.data.materials.new(item.get('material', 'Material'))
            mat.use_nodes = True
            if texture:
                tex = mat.node_tree.nodes.new('ShaderNodeTexImage')
                tex.image = bpy.data.images.load(str(folder / texture), check_existing=True)
                bsdf = mat.node_tree.nodes.get('Principled BSDF')
                if bsdf:
                    mat.node_tree.links.new(tex.outputs['Color'], bsdf.inputs['Base Color'])
                    mat.node_tree.links.new(tex.outputs['Alpha'], bsdf.inputs['Alpha'])
            materials[key] = mat
        mesh.materials.append(materials[key])

    # Import any level GLBs
    for entry in scene.get('level_glbs', []):
        before = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(Path(entry['path']).resolve()))
        apply_imported_alpha(Path(entry['path']).resolve().parent)
        level_collection = bpy.data.collections.new('LEVEL_' + entry['level_id'])
        visible.children.link(level_collection)
        for obj in set(bpy.data.objects) - before:
            for old in list(obj.users_collection):
                old.objects.unlink(obj)
            level_collection.objects.link(obj)
            obj['nd_type'] = 'visual'
            obj['nd_level_id'] = entry['level_id']

    if scene.get('streaming'):
        add_streaming(scene['streaming'], folder)
        bpy.context.view_layer.update()
        import importlib.util
        spec = importlib.util.spec_from_file_location('nd_streaming_tools', Path(__file__).with_name('blender_streaming_tools.py'))
        if spec and spec.loader:
            tools = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(tools)
            tools.write_streaming(folder / 'streaming.bin')
        guide = Path(__file__).resolve().parents[1] / 'BLENDER_LEVEL_EDITOR.md'
        if guide.exists():
            (folder / 'START_HERE.md').write_text(guide.read_text(encoding='utf-8'), encoding='utf-8')

    num_actions = setup_armature_and_actions()
    has_armature = any(o.type == 'ARMATURE' for o in bpy.data.objects)

    bpy.context.scene.unit_settings.system = 'METRIC'
    bpy.context.scene.unit_settings.scale_length = 1.0

    fbx_kwargs = dict(
        use_selection=False,
        object_types={'ARMATURE', 'MESH', 'EMPTY'} if has_armature else {'MESH', 'EMPTY'},
        add_leaf_bones=False,
        bake_anim=bool(num_actions > 0),
        bake_anim_use_all_actions=bool(num_actions > 0),
        bake_anim_use_nla_strips=bool(num_actions > 0),
        bake_anim_step=1.0,
        bake_anim_simplify_factor=0.0,
        use_custom_props=True,
        path_mode='COPY',
        embed_textures=True,
        axis_forward='-Z',
        axis_up='Y'
    )
    lighting_paths=scene.get('static_lighting',[])
    if not lighting_paths:
        lighting_paths=[str(Path(e['path']).parent/'static_lighting'/'lighting.json')
                        for e in scene.get('level_glbs',[])
                        if (Path(e['path']).parent/'static_lighting'/'lighting.json').is_file()]
    if lighting_paths:
        apply_scene_static_lighting(lighting_paths,folder)
    refresh_imported_alpha()
    configure_material_previews()
    bpy.ops.export_scene.fbx(filepath=str(folder / 'scene.fbx'), **fbx_kwargs)

    packing_warnings = []
    for image in bpy.data.images:
        if image.source == 'FILE' and not image.packed_file:
            try:
                image.pack()
            except RuntimeError as exc:
                packing_warnings.append({'image': image.name, 'error': str(exc)})
    (folder / 'packing_warnings.json').write_text(json.dumps(packing_warnings, indent=2))

    if scene.get('level_glbs') and scene.get('streaming'):
        home = next((r for r in scene['streaming']['regions'] if r['name'] == 'regionshape-4747'), None)
        if home:
            displayed = home['sets']['1']['display']
            for obj in bpy.context.scene.objects:
                if obj.get('nd_type') == 'visual':
                    obj.hide_set(obj.get('nd_level_id') not in displayed)
                    obj.hide_render = obj.get('nd_level_id') not in displayed
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type == 'VIEW_3D':
                        area.spaces.active.region_3d.view_location = (15, 35, 30)
                        area.spaces.active.region_3d.view_distance = 45

    if scene.get('streaming') and spec and spec.loader:
        tools.register()
        bpy.ops.nd.focus_level()
        if lighting_paths:
            # Editor registration selects Solid; show reconstructed lighting instead.
            import importlib.util
            light_spec=importlib.util.spec_from_file_location('nd_static_view',Path(__file__).with_name('blender_static_lighting.py'))
            light_module=importlib.util.module_from_spec(light_spec); light_spec.loader.exec_module(light_module)
            light_module.configure_preview_view()
    bpy.ops.wm.save_as_mainfile(filepath=str(folder / 'scene.blend'))
    write_blender_readme(folder, 'TLOU_Scene', num_actions)


def run(path_arg: str, output_dir: str = None):
    """Main Blender entrypoint (called inside Blender)."""
    p = Path(path_arg).resolve()
    if p.suffix.lower() == '.json':
        run_scene_json(p)
    elif p.suffix.lower() in ('.glb', '.gltf'):
        out = Path(output_dir).resolve() if output_dir else p.parent
        export_direct_glb(p, out)
    else:
        raise ValueError(f"Unsupported file format for Blender export: {path_arg}")


def cli_outside_blender(args=None):
    """CLI runner when called outside Blender via standard Python."""
    import argparse
    parser = argparse.ArgumentParser(description="Export TLOU models with armature and animations into Blender (.blend) and FBX.")
    parser.add_argument("input", help="Path to .glb / .gltf file or scene.json or character name (e.g. sarah)")
    parser.add_argument("-o", "--output", help="Output directory (default: same as input or ./exports/<model>)")
    parsed = parser.parse_args(args)

    input_target = parsed.input
    # If a short character name was given, check extracted_models/
    if not os.path.exists(input_target):
        cand = Path(__file__).resolve().parents[1] / 'extracted_models' / input_target / f'{input_target}.glb'
        if cand.is_file():
            input_target = str(cand)

    target_path = Path(input_target).resolve()
    if not target_path.is_file():
        print(f"[ERROR] Target file not found: {input_target}")
        sys.exit(1)

    out_dir = parsed.output
    if not out_dir:
        if target_path.suffix.lower() in ('.glb', '.gltf'):
            out_dir = str(Path(__file__).resolve().parents[1] / 'exports' / target_path.stem)
        else:
            out_dir = str(target_path.parent)

    blender_exe = find_blender()
    print(f"[*] Found Blender at: {blender_exe}")
    print(f"[*] Exporting '{target_path.name}' to: {out_dir}")

    cmd = [
        blender_exe,
        '--background',
        '--factory-startup',
        '--python-exit-code', '1',
        '--python', str(Path(__file__).resolve()),
        '--',
        str(target_path),
        str(Path(out_dir).resolve())
    ]
    res = subprocess.run(cmd)
    sys.exit(res.returncode)


if __name__ == '__main__':
    if bpy is not None:
        # Running inside Blender
        args = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
        if not args:
            print("[ERROR] No arguments passed to blender_export.py")
            sys.exit(1)
        in_path = args[0]
        out_path = args[1] if len(args) > 1 else None
        run(in_path, out_path)
    else:
        # Running outside Blender in standard Python
        cli_outside_blender()
