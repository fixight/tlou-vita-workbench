"""Run in Blender's Text Editor (Alt-P); sidebar: TLOU.

TLST v1 is streaming metadata, not a renderer-specific mesh binary.
"""
import copy
import json
import re
from pathlib import Path
import struct

import bpy
from bpy.props import StringProperty, BoolProperty, EnumProperty, IntProperty
from bpy_extras.io_utils import ExportHelper


def metadata():
    roots = [o for o in bpy.context.scene.objects if o.get('nd_type') == 'streaming_metadata']
    if len(roots) != 1:
        raise ValueError('Expected exactly one streaming metadata object')
    return json.loads(roots[0]['nd_streaming_json'])


NATIVE_TASK_ITEMS=[]


def native_runtime():
    import sys
    project=str(Path(r'D:\TLOUPS4\fervent-pascal'))
    if project not in sys.path:sys.path.insert(0,project)
    from tlou_extractor import streaming_native
    return streaming_native


def trigger_runtime():
    native_runtime()  # Ensure the local parser package is importable in Blender.
    from tlou_extractor import trigger_catalog
    return trigger_catalog


def native_story_state(scene,document):
    runtime=native_runtime();graph=document['task_graphs']['home']
    # Explicit preview preset: previous graph nodes complete, selected node active.
    chain=[];edges={e['from']:e['to'] for e in graph['edges']}
    incoming={e['to'] for e in graph['edges']}
    roots=[e['from'] for e in graph['edges'] if e['from'] not in incoming]
    if len(roots)!=1:raise ValueError('Preview requires an unbranched task graph')
    node=roots[0];visited=set()
    while node in edges:
        if node in visited:raise ValueError('Cyclic story graph')
        visited.add(node);node=edges[node]
        if node in graph['nodes']:chain.append(node)
    current=int(scene.nd_native_task)
    tasks={(graph['id'],key):'pending' for key in graph['nodes']}
    for i,key in enumerate(chain):tasks[graph['id'],key]='complete' if i<current else 'active' if i==current else 'pending'
    return runtime.GameState(tasks,{'0x69c85a6d':True},
        {('0x4f12da44','0x69c85a6d'):scene.nd_native_object_flag})


def parent_region(obj):
    while obj and obj.get('nd_type') not in ('streaming_region', 'gameplay_region'):
        obj = obj.parent
    return obj


LEVEL_ITEMS = []
PLAYER_FAMILY_ITEMS = []
STORY_ROUTE = []
STORY_ITEMS = []
# Authored tour of Austin, NOT a decoded original story/trigger order.
AUSTIN_TOUR = (
    ('regionshape-4747', 'Дом Сары'),
    ('regionshape-4746', 'Двор и пригород'),
    ('regionshape-5982', 'Выезд из пригорода'),
    ('regionshape-4750', 'Дорога: холмы'),
    ('regionshape-11241', 'Дорога: лес и ферма'),
    ('regionshape-4751', 'Подъезд к шоссе'),
    ('regionshape-4752', 'Шоссе'),
    ('regionshape-13203', 'Въезд в город'),
    ('regionshape-5771', 'Город: freeway'),
    ('regionshape-4753', 'Город: первые улицы'),
    ('regionshape-6939', 'Город: следующие улицы'),
    ('regionshape-7273', 'Улицы у переулка'),
    ('regionshape-6157', 'Переулок и бар'),
    ('regionshape-7267', 'Выход к лесу'),
)
SERVICE_MATERIALS = {'lib-shadowblocker', 'lib-shadowblocker-double', 'default-collision-color'}
INITIALIZING = False
PLAYER_CACHE = {'dirty':True}


def alpha_runtime():
    if 'alpha_runtime' not in PLAYER_CACHE:
        import types
        text=bpy.data.texts.get('blender_material_alpha.py')
        source=text.as_string() if text else Path(__file__).with_name('blender_material_alpha.py').read_text(encoding='utf-8')
        module=types.ModuleType('nd_material_alpha')
        exec(compile(source,'blender_material_alpha.py','exec'),module.__dict__)
        PLAYER_CACHE['alpha_runtime']=module
    return PLAYER_CACHE['alpha_runtime']


def alpha_toggle(scene,context):
    if not INITIALIZING: alpha_runtime().toggle(scene)


class ND_OT_material_view(bpy.types.Operator):
    bl_idname='nd.material_view'
    bl_label='Включить Material Preview'
    def execute(self,context):
        for area in context.screen.areas if context.screen else []:
            if area.type=='VIEW_3D': area.spaces.active.shading.type='MATERIAL'
        return {'FINISHED'}


class ND_OT_alpha_mode(bpy.types.Operator):
    bl_idname='nd.alpha_mode'
    bl_label='Настроить прозрачность материала'
    mode: EnumProperty(items=[('OPAQUE','Без прозрачности',''),('MASK','Отсечение',''),('BLEND','Плавная',''),('KEEP','Применить параметры','')])
    def execute(self,context):
        material=context.object.active_material if context.object else None
        if material is None or not material.get('nd_transparency_image'):
            self.report({'ERROR'},'У выбранного материала нет исходной маски прозрачности');return {'CANCELLED'}
        if self.mode!='KEEP': material['nd_alpha_mode']=self.mode
        alpha_runtime().configure(material,context.scene.nd_alpha_preview)
        return {'FINISHED'}


def player_runtime():
    if 'runtime' not in PLAYER_CACHE:
        import types
        text=bpy.data.texts.get('region_runtime.py')
        source=text.as_string() if text else Path(__file__).with_name('region_runtime.py').read_text(encoding='utf-8')
        module=types.ModuleType('nd_region_runtime')
        exec(compile(source,'region_runtime.py','exec'),module.__dict__)
        PLAYER_CACHE['runtime']=module
    return PLAYER_CACHE['runtime']


def prepare_player_regions(scene):
    runtime=player_runtime()
    document=metadata()
    records={r['id']:r for r in document['regions']}
    available={o.get('nd_level_id') for o in scene.objects if o.get('nd_type')=='visual' and o.get('nd_level_id')}
    family=scene.nd_player_family
    families={name.split('-',1)[0] for name in available} if family=='__ALL__' else {family}
    scoped_levels={name for name in available if name.split('-',1)[0] in families}
    # Metadata can contain several chapters sharing world coordinates. Only use
    # the families actually loaded, plus world regions referencing loaded chunks.
    scoped={rid:r for rid,r in records.items() if
            r.get('source_level','').split('-',1)[0] in families or
            (r.get('source_level','').startswith('world-') and
             any(set(state.get('display',[])+state.get('resident_only',[])) & scoped_levels
                 for state in r.get('sets',{}).values()))}
    skipped=sorted(set(records)-set(scoped));records=scoped
    volumes=[];errors=[];parents={};mesh_ids=set()
    for parent in scene.objects:
        if parent.get('nd_type') not in ('streaming_region','gameplay_region'): continue
        rid=parent.get('nd_region_id')
        if rid not in records: continue
        parents[rid]=parent
        for child in parent.children_recursive:
            if child.type!='MESH' or child.get('nd_type')!='region_volume': continue
            if child.get('nd_role')=='prefetch': continue
            mesh_ids.add(child.data.as_pointer())
            mesh=child.data
            try:
                points=[tuple(child.matrix_world @ v.co) for v in mesh.vertices]
                shape=runtime.convex_volume(points,[list(p.vertices) for p in mesh.polygons])
                volumes.append({'region':rid,'object':child.name,'shape':shape})
            except ValueError as exc:
                errors.append({'region':rid,'volume':child.name,'reason':str(exc)})
    PLAYER_CACHE.update(records=records,parents=parents,volumes=volumes,errors=errors,
                        mesh_ids=mesh_ids,scene=scene.as_pointer(),dirty=False,signature=None,
                        available=available,skipped_regions=skipped,native_document=document)


def ensure_player(scene):
    player=next((o for o in scene.objects if o.get('nd_type')=='player_preview'),None)
    if player: return player
    if PLAYER_CACHE.get('dirty') or PLAYER_CACHE.get('scene')!=scene.as_pointer(): prepare_player_regions(scene)
    player=bpy.data.objects.new('TLOU_PLAYER_PREVIEW',None)
    scene.collection.objects.link(player)
    player['nd_type']='player_preview';player['nd_export']=False
    player.empty_display_type='SPHERE';player.empty_display_size=.3;player.show_in_front=True
    player.color=(.1,1,.2,1);player.hide_render=True
    point=tuple(scene.cursor.location)
    if not any(player_runtime().contains(v['shape'],point) for v in PLAYER_CACHE['volumes']):
        preferred=next((v for v in PLAYER_CACHE['volumes'] if v['region']=='world-home:regionshape-4747'),
                       next(iter(PLAYER_CACHE['volumes']),None))
        if preferred: point=preferred['shape']['center']
    from mathutils import Matrix
    player.matrix_world=Matrix.Translation(point)
    return player


def player_update(scene,force=False):
    if PLAYER_CACHE.get('dirty') or PLAYER_CACHE.get('scene')!=scene.as_pointer(): prepare_player_regions(scene)
    player=ensure_player(scene)
    point=tuple(player.matrix_world.translation)
    if scene.nd_player_follow_view:
        area=next((a for s in bpy.data.screens for a in s.areas if a.type=='VIEW_3D'),None)
        if area:
            space=area.spaces.active
            if space.region_3d.view_perspective=='CAMERA' and scene.camera:
                point=tuple(scene.camera.matrix_world.translation)
            else: point=tuple(space.region_3d.view_matrix.inverted().translation)
            player.location=point
    variants={rid:int(parent.get('nd_preview_set',1)) for rid,parent in PLAYER_CACHE['parents'].items()}
    native_mode=scene.nd_native_enabled and bool(PLAYER_CACHE['native_document'].get('native_grids'))
    signature=(point,tuple(sorted(variants.items())),scene.nd_player_hold_outside,scene.nd_player_follow_view,
               native_mode,scene.nd_native_task,scene.nd_native_object_flag)
    if not force and signature==PLAYER_CACHE.get('signature'): return
    runtime=player_runtime();records=PLAYER_CACHE['records']
    active={v['region'] for v in PLAYER_CACHE['volumes'] if runtime.contains(v['shape'],point)}
    streaming=sorted(rid for rid in active if records[rid]['type']=='streaming_region')
    gameplay=sorted(active-set(streaming))
    state=runtime.select_active_sets([records[rid] for rid in streaming],variants)
    native_selection=None
    if native_mode:
        document=PLAYER_CACHE['native_document']
        native_selection=native_runtime().select_native(document,'world-home',(point[0],point[2],-point[1]),native_story_state(scene,document))
        state={**native_selection,'required':sorted(native_runtime().dependencies(document,
            native_selection['display']+native_selection['resident_only'])),
            'conditions':[{'region':native_selection['region_id'],'variant':native_selection['variant'],'manual':False}]}
        streaming=[native_selection['region_id']] if native_selection['region_id'] else []
    previous=json.loads(scene.get('nd_player_report','{}'))
    held=not streaming and scene.nd_player_hold_outside
    if held:
        for key in ('display','resident_only','required'):
            state[key]=previous.get(key,[])
        if not previous:
            preview=json.loads(scene.get('nd_display_levels','null'))
            state['display']=sorted(preview if preview is not None else
                                    PLAYER_CACHE['available'] if scene.nd_editor_level=='__ALL__' else [scene.nd_editor_level])
            state['required']=state['display']
    old_active=set(previous.get('active_regions',[]));old_required=set(previous.get('required',[]))
    crossed=[]
    if previous.get('position'):
        crossed=sorted({v['region'] for v in PLAYER_CACHE['volumes']
                        if v['region'] not in active|old_active and
                        runtime.segment_intersects(v['shape'],previous['position'],point)})
    report=dict(state,mode='position_volume_preview',position=list(point),active_regions=sorted(active),
                active_streaming=streaming,active_gameplay=gameplay,entered=sorted(active-old_active),
                exited=sorted(old_active-active),crossed_between_samples=crossed,
                request_load=sorted(set(state['required'])-old_required),
                request_unload=sorted(old_required-set(state['required'])),held_outside=held,
                visible_levels=sorted(set(state['display'])&PLAYER_CACHE['available']),
                without_visual_geometry=sorted(set(state['display'])-PLAYER_CACHE['available']),
                geometry_errors=PLAYER_CACHE['errors'],
                regions_of_unloaded_chapters=PLAYER_CACHE['skipped_regions'],
                multivolume_rule='native_union' if native_mode else 'experimental_union',
                interregion_rule='native_first_match' if native_mode else 'experimental_union',
                native_selection=native_selection,
                note='Point versus convex volumes. Visibility only; no RAM/disk streaming, wall physics or execution of gameplay events.')
    encoded=json.dumps(sorted(state['display']))
    if scene.get('nd_display_levels')!=encoded or force:
        scene['nd_display_levels']=encoded;scene['nd_story_active']=False
        update_visibility(scene)
    scene['nd_player_report']=json.dumps(report,ensure_ascii=False)
    text=bpy.data.texts.get('TLOU_PLAYER_PREVIEW.json') or bpy.data.texts.new('TLOU_PLAYER_PREVIEW.json')
    text.clear();text.write(json.dumps(report,ensure_ascii=False,indent=2))
    if report['entered'] or report['exited'] or crossed:
        print('[TLOU Player] Enter:',report['entered'],'Exit:',report['exited'],'Display:',report['visible_levels'],flush=True)
    PLAYER_CACHE['signature']=signature
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type=='VIEW_3D': area.tag_redraw()
    return report


def player_timer():
    scene=bpy.context.scene
    if not getattr(scene,'nd_player_sim_enabled',False): return None
    try: player_update(scene)
    except Exception as exc:
        scene['nd_player_error']=str(exc);print('[TLOU Player]',exc,flush=True)
        scene.nd_player_sim_enabled=False;return None
    return .15


def player_scope_changed(scene,context):
    PLAYER_CACHE['dirty']=True


def player_toggle(scene,context):
    if INITIALIZING: return
    if scene.nd_player_sim_enabled:
        scene['nd_player_error']='';PLAYER_CACHE['dirty']=True
        try:
            player_update(scene,force=True)
            if not bpy.app.timers.is_registered(player_timer): bpy.app.timers.register(player_timer,first_interval=.15)
        except Exception as exc:
            scene['nd_player_error']=str(exc);scene.nd_player_sim_enabled=False
    elif bpy.app.timers.is_registered(player_timer): bpy.app.timers.unregister(player_timer)


def player_geometry_updated(scene,depsgraph):
    for update in depsgraph.updates:
        item=update.id
        if isinstance(item,bpy.types.Object) and item.get('nd_type') in ('streaming_region','gameplay_region','region_volume'):
            if update.is_updated_transform or update.is_updated_geometry: PLAYER_CACHE['dirty']=True
        elif isinstance(item,bpy.types.Mesh) and item.as_pointer() in PLAYER_CACHE.get('mesh_ids',set()):
            PLAYER_CACHE['dirty']=True
player_geometry_updated._nd_player_preview=True


class ND_OT_player_create(bpy.types.Operator):
    bl_idname='nd.player_create'
    bl_label='Создать / выбрать игрока'
    def execute(self,context):
        obj=ensure_player(context.scene)
        for other in context.selected_objects: other.select_set(False)
        obj.hide_set(False);obj.select_set(True);context.view_layer.objects.active=obj
        return {'FINISHED'}


class ND_OT_player_place(bpy.types.Operator):
    bl_idname='nd.player_place'
    bl_label='Игрок в выбранную область'
    def execute(self,context):
        parent=parent_region(context.object)
        if not parent:
            self.report({'ERROR'},'Выберите область или её объём');return {'CANCELLED'}
        prepare_player_regions(context.scene)
        volume=next((v for v in PLAYER_CACHE['volumes'] if v['object']==context.object.name),None)
        if volume is None: volume=next((v for v in PLAYER_CACHE['volumes'] if v['region']==parent.get('nd_region_id')),None)
        if volume is None:
            self.report({'ERROR'},'Нет поддержанного объёма');return {'CANCELLED'}
        from mathutils import Matrix
        obj=ensure_player(context.scene);obj.matrix_world=Matrix.Translation(volume['shape']['center'])
        player_update(context.scene,force=True)
        return {'FINISHED'}


class ND_OT_player_refresh(bpy.types.Operator):
    bl_idname='nd.player_refresh'
    bl_label='Проверить / обновить объёмы'
    def execute(self,context):
        prepare_player_regions(context.scene);player_update(context.scene,force=True)
        return {'FINISHED'}


def hide_viewport(obj, hidden):
    if obj.hide_get() != hidden:
        obj.hide_set(hidden)


def is_editor_helper(obj):
    return obj.type == 'MESH' and any(
        mat and re.sub(r'\.\d{3}$', '', mat.name) in SERVICE_MATERIALS
        for mat in obj.data.materials)


def update_visibility(scene, context=None):
    if INITIALIZING:
        return
    selected = scene.nd_editor_level
    preview = json.loads(scene.get('nd_display_levels', 'null'))
    for obj in scene.objects:
        kind = obj.get('nd_type')
        owner = obj.get('nd_level_id', '')
        if kind == 'visual':
            visible = owner in preview if preview is not None else (selected == '__ALL__' or owner == selected)
            hide_viewport(obj, not visible or (is_editor_helper(obj) and not scene.nd_show_helpers))
            if obj.hide_render != (not visible):
                obj.hide_render = not visible
        elif kind == 'collision':
            obj.display_type = 'WIRE'
            obj.hide_render = True
            visible = (owner in preview or owner.removesuffix('-col') in preview) if preview is not None else (
                selected == '__ALL__' or owner in (selected, selected + '-col'))
            hide_viewport(obj, not (scene.nd_show_collisions and visible))
        elif kind in ('streaming_region', 'gameplay_region', 'region_volume'):
            region = parent_region(obj)
            streaming = region and region.get('nd_type') == 'streaming_region'
            visible = scene.nd_show_streaming if streaming else scene.nd_show_gameplay
            if not streaming and scene.nd_gameplay_filter!='__ALL__':
                category=region.get('nd_trigger_category','spatial') if region else 'spatial'
                selected_categories=('gameplay','dialogue') if scene.nd_gameplay_filter=='events' else (scene.nd_gameplay_filter,)
                visible=visible and category in selected_categories
            obj.display_type = 'WIRE'
            obj.hide_render = True
            hide_viewport(obj, not visible)
        elif kind == 'streaming_metadata':
            hide_viewport(obj, True)
            obj.hide_render = True


def select_level(scene, context):
    if INITIALIZING: return
    if getattr(scene,'nd_player_sim_enabled',False): scene.nd_player_sim_enabled=False
    scene['nd_display_levels'] = 'null'
    scene['nd_story_active'] = False
    update_visibility(scene, context)


def prepare_story_route():
    STORY_ROUTE.clear()
    STORY_ITEMS.clear()
    try:
        records = [r for r in metadata()['regions'] if r.get('type') == 'streaming_region' and r.get('sets')]
    except ValueError:
        records = []
    by_id = {r['id']: r for r in records}
    for name, label in AUSTIN_TOUR:
        record = by_id.get('world-home:' + name)
        if record:
            STORY_ROUTE.append((label, record))
    if not STORY_ROUTE:
        STORY_ROUTE.extend((r['name'], r) for r in records)
    STORY_ITEMS.extend((str(i), f'{i+1:02d} · {label}', record['id'])
                       for i, (label, record) in enumerate(STORY_ROUTE))
    if not STORY_ITEMS:
        STORY_ITEMS.append(('0', 'Нет областей стриминга', 'В сцене нет метаданных'))


def apply_story_step(scene):
    if getattr(scene,'nd_player_sim_enabled',False): scene.nd_player_sim_enabled=False
    if not STORY_ROUTE:
        raise ValueError('В сцене нет областей стриминга с наборами')
    index = int(scene.nd_story_step)
    label, record = STORY_ROUTE[index]
    variant = str(scene.nd_story_variant)
    state = record['sets'].get(variant)
    if state is None:
        raise ValueError('Допустимые варианты: ' + ', '.join(record['sets']))
    objects = list(scene.objects)
    available = {o['nd_level_id'] for o in objects if o.get('nd_type') == 'visual' and o.get('nd_level_id')}
    old = {o['nd_level_id'] for o in objects if o.get('nd_type') == 'visual'
           and o.get('nd_level_id') and not o.hide_get()}
    previous = json.loads(scene.get('nd_story_report', '{}')) if scene.get('nd_story_active') else {}
    display = set(state['display'])
    resident = set(state.get('resident_only', [])) - display
    required = display | resident
    old_required = set(previous.get('required', []))
    scene['nd_display_levels'] = json.dumps(sorted(display))
    update_visibility(scene)
    current = {o['nd_level_id'] for o in objects if o.get('nd_type') == 'visual'
               and o.get('nd_level_id') and not o.hide_get()}
    report = {'mode': 'authored_tour_visibility_preview', 'step': index + 1, 'label': label,
              'region_id': record['id'], 'variant': variant,
              'selector_kind': record.get('selector', {}).get('kind'),
              'shown': sorted(current - old), 'hidden': sorted(old - current),
              'kept_visible': sorted(current & old), 'visible': sorted(current),
              'display': sorted(display), 'resident_only': sorted(resident),
              'required': sorted(required), 'request_load': sorted(required - old_required),
              'request_unload': sorted(old_required - required),
              'without_visual_geometry': sorted(display - available),
              'note': 'Visibility only; no disk IO or RAM unloading. Tour order and conditional variant are manual.'}
    scene['nd_story_report'] = json.dumps(report, ensure_ascii=False)
    scene['nd_story_active'] = True
    text = bpy.data.texts.get('TLOU_STREAMING_PREVIEW.json') or bpy.data.texts.new('TLOU_STREAMING_PREVIEW.json')
    text.clear()
    text.write(json.dumps(report, ensure_ascii=False, indent=2))
    print(f'[TLOU] Шаг {index+1}: {label}, вариант {variant}; появились {report["shown"]}; скрылись {report["hidden"]}', flush=True)
    if scene.nd_story_follow:
        parent = next((o for o in objects if o.get('nd_region_id') == record['id']
                       and o.get('nd_type') == 'streaming_region'), None)
        if parent:
            for screen in bpy.data.screens:
                for area in screen.areas:
                    if area.type == 'VIEW_3D':
                        area.spaces.active.region_3d.view_location = parent.matrix_world.translation
                        area.spaces.active.region_3d.view_distance = 70
    return report


def story_selection(scene, context):
    if INITIALIZING or not STORY_ROUTE:
        return
    record = STORY_ROUTE[int(scene.nd_story_step)][1]
    preferred = str(record.get('selector', {}).get('value', 1))
    scene.nd_story_variant = int(preferred if preferred in record['sets'] else next(iter(record['sets'])))
    apply_story_step(scene)


class ND_OT_story_step(bpy.types.Operator):
    bl_idname = 'nd.story_step'
    bl_label = 'Следующий набор'
    direction: IntProperty(default=1)

    def execute(self, context):
        scene = context.scene
        if not STORY_ROUTE:
            self.report({'ERROR'}, 'Нет областей стриминга')
            return {'CANCELLED'}
        index = int(scene.nd_story_step)
        target = index + self.direction if scene.get('nd_story_active') else 0
        if not 0 <= target < len(STORY_ROUTE):
            self.report({'INFO'}, 'Конец маршрута' if target >= len(STORY_ROUTE) else 'Первый шаг маршрута')
            return {'CANCELLED'}
        if target == index:
            story_selection(scene, context)
        else:
            scene.nd_story_step = str(target)
        self.report({'INFO'}, f'Шаг {target+1}/{len(STORY_ROUTE)}; изменения — в панели и TLOU_STREAMING_PREVIEW.json')
        return {'FINISHED'}


class ND_OT_story_apply(bpy.types.Operator):
    bl_idname = 'nd.story_apply'
    bl_label = 'Применить вариант'

    def execute(self, context):
        try:
            apply_story_step(context.scene)
            return {'FINISHED'}
        except (ValueError, IndexError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


def setup_editor_view(preserve_scene=False):
    """Restore FBX display settings without deleting or changing export geometry."""
    global INITIALIZING
    scene = bpy.context.scene
    levels = sorted({o['nd_level_id'] for o in scene.objects
                     if o.get('nd_type') == 'visual' and o.get('nd_level_id')})
    LEVEL_ITEMS[:] = [('__ALL__', 'Все участки', 'Вся геометрия; высокая нагрузка')]
    LEVEL_ITEMS.extend((level, level, level) for level in levels)
    families=sorted({level.split('-',1)[0] for level in levels if not level.startswith('sky-')})
    PLAYER_FAMILY_ITEMS[:]=[('__ALL__','Все главы','Могут пересекаться в координатах')]
    PLAYER_FAMILY_ITEMS.extend((family,family,family) for family in families)
    if preserve_scene:
        return
    INITIALIZING = True
    try:
        scene.nd_player_family = max(families,key=lambda f:sum(level.startswith(f+'-') for level in levels)) if families else '__ALL__'
        scene.nd_show_streaming = False
        scene.nd_show_gameplay = False
        scene.nd_show_collisions = False
        scene.nd_show_helpers = False
        scene.nd_editor_level = ('hom-house-interior' if 'hom-house-interior' in levels
                                 else levels[0] if levels else '__ALL__')
        scene['nd_display_levels'] = 'null'
    finally:
        INITIALIZING = False
    update_visibility(scene)
    prepare_material_previews()
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                space = area.spaces.active
                space.shading.type = 'MATERIAL' if scene.get('nd_static_lighting_experimental') else 'SOLID'
                if scene.get('nd_static_lighting_experimental'):
                    space.shading.use_scene_world = True
                    space.shading.use_scene_lights = True
                space.shading.color_type = 'TEXTURE'
                space.shading.show_shadows = False
                space.shading.show_cavity = False
                space.overlay.show_extras = True


def prepare_material_previews():
    """Solid texture mode uses the active image node, not the BSDF graph."""
    for material in bpy.data.materials:
        if not material.use_nodes:
            continue
        nodes = material.node_tree.nodes
        shader = next((n for n in nodes if n.type == 'BSDF_PRINCIPLED'), None)
        if shader:
            pending = [link.from_node for link in shader.inputs['Base Color'].links]
            seen = set()
            while pending:
                node = pending.pop(0)
                if node in seen:
                    continue
                seen.add(node)
                if node.type == 'TEX_IMAGE' and node.image:
                    nodes.active = node
                    break
                pending.extend(link.from_node for socket in node.inputs for link in socket.links)


class ND_OT_focus_level(bpy.types.Operator):
    bl_idname = 'nd.focus_level'
    bl_label = 'Приблизить участок'

    def execute(self, context):
        from mathutils import Vector
        points = [o.matrix_world @ Vector(v) for o in context.scene.objects
                  if o.get('nd_type') == 'visual' and o.type == 'MESH' and not o.hide_get()
                  for v in o.bound_box]
        if not points:
            return {'CANCELLED'}
        low = Vector(tuple(min(p[a] for p in points) for a in range(3)))
        high = Vector(tuple(max(p[a] for p in points) for a in range(3)))
        for area in context.screen.areas if context.screen else []:
            if area.type == 'VIEW_3D':
                area.spaces.active.region_3d.view_location = (low + high) * .5
                area.spaces.active.region_3d.view_distance = max((high - low).length * .7, 2)
        return {'FINISHED'}


def collect_streaming():
    result = copy.deepcopy(metadata())
    records = {r['id']: r for r in result['regions']}
    exported = []
    seen = set()
    for obj in bpy.context.scene.objects:
        if obj.get('nd_type') not in ('streaming_region', 'gameplay_region'):
            continue
        rid = obj.get('nd_region_id')
        if rid in seen or rid not in records:
            raise ValueError(f'Duplicate or unknown region ID: {rid}')
        seen.add(rid)
        record = records[rid]
        record['port_binding']=trigger_runtime().binding_from_properties(obj)
        record['shapes'] = []
        record['prefetch_shapes'] = []
        for child in obj.children_recursive:
            if child.get('nd_type') != 'region_volume':
                continue
            if child.type != 'MESH':
                raise ValueError('Region volume must be a mesh')
            evaluated = child.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh = evaluated.to_mesh()
            try:
                points = [evaluated.matrix_world @ v.co for v in mesh.vertices]
                native = [[p.x, p.z, -p.y] for p in points]
                faces = [list(face.vertices) for face in mesh.polygons]
                if not native or not faces:
                    raise ValueError(f'Empty region volume: {child.name}')
                shape = {'vertices': native, 'faces': faces,
                         'bounds_min': [min(p[a] for p in native) for a in range(3)],
                         'bounds_max': [max(p[a] for p in native) for a in range(3)]}
                destination = 'prefetch_shapes' if child.get('nd_role') == 'prefetch' else 'shapes'
                record[destination].append(shape)
            finally:
                evaluated.to_mesh_clear()
        if not record['shapes']:
            raise ValueError(f'Region has no display/gameplay volumes: {obj.name}')
        point = obj.matrix_world.translation
        record['editor_origin'] = [point.x, point.z, -point.y]
        record['combination_rule'] = 'union' if result.get('native_grids') else ('unresolved_original_multivolume' if len(record['shapes']) > 1 else 'single_volume')
        exported.append(record)
    result['regions'] = exported
    result['deleted_region_ids'] = sorted(set(records) - seen)
    result['editor_format'] = 'world-space polygon volumes; native Y up'
    result['visual_level_ids'] = sorted({o['nd_level_id'] for o in bpy.context.scene.objects
                                        if o.get('nd_type') == 'visual' and o.get('nd_level_id')})
    return result


def write_streaming(path, level_files=None):
    path = Path(path)
    result = collect_streaming()
    if level_files is not None:
        result['binary_level_files'] = level_files
    payload = json.dumps(result, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    path.write_bytes(struct.pack('<4sII', b'TLST', 1, len(payload)) + payload)
    path.with_suffix('.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    return result


def write_level_binaries(folder):
    """Simple documented interchange binaries; no Vita-specific optimization.

    Expanded triangle corners preserve UV seams and split normals. Each corner
    is position3/normal3/UV0_2/LightmapUV_2 (40 bytes, little-endian floats).
    """
    from mathutils import Vector
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    owners = {}
    for obj in bpy.context.scene.objects:
        if obj.type == 'MESH' and obj.get('nd_type') in ('visual', 'collision'):
            owner = obj.get('nd_level_id')
            if not owner or any(c in owner for c in '/\\:') or owner in ('.','..'):
                raise ValueError(f'Missing/invalid nd_level_id: {obj.name}')
            owners.setdefault(owner, []).append(obj)
    exported = {}
    depsgraph = bpy.context.evaluated_depsgraph_get()
    for owner, objects in sorted(owners.items()):
        blob = bytearray()
        records = []
        for obj in objects:
            evaluated = obj.evaluated_get(depsgraph)
            mesh = evaluated.to_mesh(preserve_all_data_layers=True, depsgraph=depsgraph)
            try:
                mesh.calc_loop_triangles()
                normal_matrix = evaluated.matrix_world.to_3x3().inverted().transposed()
                mirrored = evaluated.matrix_world.to_3x3().determinant() < 0
                uv = mesh.uv_layers[0] if mesh.uv_layers else None
                lightmap = mesh.uv_layers.get('Lightmap')
                for material in sorted({t.material_index for t in mesh.loop_triangles}):
                    offset = len(blob)
                    count = 0
                    for tri in mesh.loop_triangles:
                        if tri.material_index != material:
                            continue
                        loops = list(tri.loops)
                        if mirrored:
                            loops[1], loops[2] = loops[2], loops[1]
                        for index in loops:
                            v = evaluated.matrix_world @ mesh.vertices[mesh.loops[index].vertex_index].co
                            n = normal_matrix @ mesh.corner_normals[index].vector
                            if n.length:
                                n.normalize()
                            tex = uv.data[index].uv if uv else (0,0)
                            lm = lightmap.data[index].uv if lightmap else (0,0)
                            blob.extend(struct.pack('<10f',v.x,v.z,-v.y,n.x,n.z,-n.y,tex[0],tex[1],lm[0],lm[1]))
                            count += 1
                    mat = obj.material_slots[material].material if material < len(obj.material_slots) else None
                    records.append({'name':obj.name,'type':obj['nd_type'],'offset':offset,'corner_count':count,
                                    'material':mat.name if mat else None,'has_lightmap_uv':bool(lightmap),
                                    'image_references':[n.image.name for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image]
                                    if mat and mat.use_nodes else []})
            finally:
                evaluated.to_mesh_clear()
        header = json.dumps({'level_id':owner,'coordinate_system':'native_y_up','corner_stride':40,
                             'topology':'triangle_list','meshes':records},ensure_ascii=False).encode('utf-8')
        destination = folder/(owner+'.bin')
        with destination.open('wb') as stream:
            stream.write(struct.pack('<4sIII',b'TLVL',1,len(header),len(blob)))
            stream.write(header)
            stream.write(blob)
        exported[owner] = destination.name
    (folder/'level_files.json').write_text(json.dumps(exported,indent=2),encoding='utf-8')
    write_streaming(folder/'streaming.bin', exported)
    return exported


class ND_OT_export_levels(bpy.types.Operator):
    bl_idname = 'nd.export_level_binaries'
    bl_label = 'Экспорт уровней + стриминга'
    directory: StringProperty(name='Выходная папка', subtype='DIR_PATH')

    def invoke(self, context, event):
        self.directory = bpy.path.abspath('//runtime/')
        context.window_manager.fileselect_add(self)
        return {'RUNNING_MODAL'}

    def execute(self, context):
        try:
            if not self.directory:
                raise ValueError('Выберите выходную папку')
            result = write_level_binaries(Path(self.directory))
            self.report({'INFO'}, f'Уровней: {len(result)}. Текстуры готовятся отдельно; формат описан в START_HERE.md')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class ND_OT_export_streaming(bpy.types.Operator, ExportHelper):
    bl_idname = 'nd.export_streaming'
    bl_label = 'Экспорт streaming.bin + JSON'
    filename_ext = '.bin'
    filter_glob: StringProperty(default='*.bin', options={'HIDDEN'})

    def execute(self, context):
        try:
            result = write_streaming(self.filepath)
            self.report({'INFO'}, f"Областей: {len(result['regions'])}; сценарные условия отмечены в JSON")
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}


class ND_OT_prefetch(bpy.types.Operator):
    bl_idname = 'nd.make_prefetch'
    bl_label = 'Добавить объёмы ранней загрузки'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        parent = parent_region(context.object)
        if parent is None or parent.get('nd_type') != 'streaming_region':
            self.report({'ERROR'}, 'Выберите область стриминга или её объём')
            return {'CANCELLED'}
        if any(o.get('nd_role') == 'prefetch' for o in parent.children_recursive):
            self.report({'ERROR'}, 'Объёмы ранней загрузки уже существуют; отредактируйте их')
            return {'CANCELLED'}
        for child in list(parent.children_recursive):
            if child.get('nd_type') == 'region_volume':
                obj = child.copy()
                obj.data = child.data.copy()
                child.users_collection[0].objects.link(obj)
                obj.name = 'PREFETCH_' + child.name
                obj['nd_role'] = 'prefetch'
                obj.color = (0.2, 0.6, 1.0, 0.25)
                obj.scale *= 1.2
        return {'FINISHED'}


class ND_OT_preview(bpy.types.Operator):
    bl_idname = 'nd.preview_region'
    bl_label = 'Показать выбранный набор'

    def execute(self, context):
        parent = parent_region(context.object)
        if parent is None:
            self.report({'ERROR'}, 'Выберите область')
            return {'CANCELLED'}
        record = next(r for r in metadata()['regions'] if r['id'] == parent['nd_region_id'])
        state = record.get('sets', {}).get(str(parent.get('nd_preview_set', 1)))
        if state is None:
            self.report({'ERROR'}, 'У области нет такого набора отображения')
            return {'CANCELLED'}
        context.scene.nd_player_sim_enabled = False
        context.scene['nd_display_levels'] = json.dumps(state['display'])
        context.scene['nd_story_active'] = False
        update_visibility(context.scene)
        found = set()
        for obj in context.scene.objects:
            if obj.get('nd_type') == 'visual':
                owner = obj.get('nd_level_id', '')
                if owner:
                    found.add(owner)
        missing = sorted(set(state['display']) - found)
        parent['nd_preview_missing_levels'] = json.dumps(missing)
        self.report({'INFO'}, f'Ручной предпросмотр; без объектов в сцене: {len(missing)} (включая контейнеры)')
        return {'FINISHED'}


class ND_OT_trigger_details(bpy.types.Operator):
    bl_idname='nd.trigger_details'
    bl_label='Полная карточка области'

    def execute(self,context):
        parent=parent_region(context.object)
        if parent is None or not parent.get('nd_trigger_info_json'):
            self.report({'ERROR'},'Обновите сцену через blender_native_streaming.py');return {'CANCELLED'}
        try:
            card=json.loads(parent['nd_trigger_info_json'])
            card['port_binding']=trigger_runtime().binding_from_properties(parent)
            text=bpy.data.texts.get('TLOU_TRIGGER_DETAILS.txt') or bpy.data.texts.new('TLOU_TRIGGER_DETAILS.txt')
            text.clear();text.write(trigger_runtime().card_text(card))
            for area in context.screen.areas if context.screen else []:
                if area.type=='TEXT_EDITOR':area.spaces.active.text=text
            self.report({'INFO'},'Карточка записана в Text Editor: TLOU_TRIGGER_DETAILS.txt')
        except (ValueError,KeyError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class ND_OT_show_all(bpy.types.Operator):
    bl_idname = 'nd.show_all_levels'
    bl_label = 'Показать всю геометрию'

    def execute(self, context):
        context.scene.nd_editor_level = '__ALL__'
        select_level(context.scene, context)
        return {'FINISHED'}


class ND_PT_streaming(bpy.types.Panel):
    bl_label = 'TLOU — редактор уровней'
    bl_idname = 'ND_PT_streaming'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'TLOU'

    def draw(self, context):
        layout = self.layout
        alpha=layout.box()
        alpha.label(text='Материалы: стекло и растительность')
        alpha.operator('nd.material_view')
        alpha.prop(context.scene,'nd_alpha_preview',text='Прозрачность из исходных масок')
        material=context.object.active_material if context.object else None
        if material and material.get('nd_transparency_image'):
            alpha.label(text=material.name)
            row=alpha.row(align=True)
            for mode,label in (('OPAQUE','Без'),('MASK','Отсечение'),('BLEND','Плавно')):
                row.operator('nd.alpha_mode',text=label,depress=material.get('nd_alpha_mode')==mode).mode=mode
            alpha.prop(material,'["nd_alpha_strength"]',text='Множитель непрозрачности')
            alpha.prop(material,'["nd_alpha_cutoff"]',text='Порог отсечения')
            alpha.operator('nd.alpha_mode',text='Применить параметры').mode='KEEP'
        alpha.label(text='Маски работают в Material Preview / Rendered')
        sim = layout.box()
        sim.label(text='Позиция игрока → стриминг (предпросмотр)')
        sim.prop(context.scene, 'nd_player_family', text='Глава (семейство PAK)')
        sim.operator('nd.player_create')
        sim.prop(context.scene, 'nd_player_sim_enabled', text='Симуляция позиции')
        sim.prop(context.scene, 'nd_player_follow_view', text='Позиция из камеры обзора')
        sim.prop(context.scene, 'nd_player_hold_outside', text='Вне областей сохранять последний набор')
        sim.prop(context.scene,'nd_native_enabled',text='Оригинальные правила выбора чанков')
        if context.scene.nd_native_enabled:
            sim.prop(context.scene,'nd_native_task',text='Активная задача')
            sim.prop(context.scene,'nd_native_object_flag',text='Флаг объекта 0x4f12da44')
            sim.label(text='Предыдущие задачи завершены; следующая ожидает')
        sim.operator('nd.player_refresh')
        sim.label(text='Двигайте TLOU_PLAYER_PREVIEW клавишей G')
        report = json.loads(context.scene.get('nd_player_report', '{}'))
        for key, label in (('active_streaming','Области стриминга'),('active_gameplay','Прочие области'),
                           ('visible_levels','Видимые чанки'),('request_load','Запрос загрузки'),
                           ('request_unload','Запрос выгрузки')):
            sim.label(text=f'{label}: {len(report.get(key, []))}')
        for rid in report.get('active_streaming', [])[:4]:
            sim.label(text=rid)
        if report.get('conditions'):
            sim.label(text='Сценарные условия: N задаётся вручную', icon='INFO')
        if report.get('held_outside'):
            sim.label(text='Вне объёмов: сохранён предыдущий набор')
        if report.get('geometry_errors'):
            sim.label(text=f"Пропущены объёмы: {len(report['geometry_errors'])}", icon='ERROR')
        if context.scene.get('nd_player_error'):
            sim.label(text=context.scene['nd_player_error'], icon='ERROR')
        sim.label(text='Отчёт: TLOU_PLAYER_PREVIEW.json')
        sim.label(text='Пересечения объединяются; сценарии не исполняются')
        tour = layout.box()
        tour.label(text='Пошаговый просмотр стриминга')
        tour.label(text='Маршрут задан вручную; наборы из PAK')
        tour.enabled = bool(STORY_ROUTE)
        tour.prop(context.scene, 'nd_story_step', text='Шаг')
        row = tour.row(align=True)
        row.operator('nd.story_step', text='Назад', icon='TRIA_LEFT').direction = -1
        row.operator('nd.story_step', text='Следующие чанки', icon='TRIA_RIGHT').direction = 1
        row = tour.row(align=True)
        row.prop(context.scene, 'nd_story_variant', text='Вариант N')
        row.operator('nd.story_apply', text='Применить')
        tour.prop(context.scene, 'nd_story_follow', text='Перемещать обзор к области')
        if STORY_ROUTE:
            record = STORY_ROUTE[int(context.scene.nd_story_step)][1]
            tour.label(text='Варианты: ' + ', '.join(record['sets']))
            if record.get('selector', {}).get('kind') == 'script_requires_game_state':
                tour.label(text='Сценарное условие: N выбирается вручную', icon='INFO')
        if context.scene.get('nd_story_active'):
            report = json.loads(context.scene.get('nd_story_report', '{}'))
            for key, label in (('shown', 'Появились'), ('hidden', 'Скрылись')):
                names = report.get(key, [])
                tour.label(text=f'{label}: {len(names)}')
                for name in names[:4]:
                    tour.label(text=name)
                if len(names) > 4:
                    tour.label(text=f'Ещё {len(names)-4} — в JSON')
            tour.label(text=f'Остались видимыми: {len(report.get("kept_visible", []))}')
            tour.label(text=f'Предзагрузка без показа: {len(report.get("resident_only", []))}')
            tour.label(text=f'Без визуальных мешей: {len(report.get("without_visual_geometry", []))}')
            tour.label(text='Полный отчёт: TLOU_STREAMING_PREVIEW.json')
        tour.label(text='Скрытие, без выгрузки из памяти Blender')
        layout.prop(context.scene, 'nd_editor_level', text='Участок')
        layout.operator('nd.focus_level')
        layout.prop(context.scene, 'nd_show_streaming', text='Области стриминга')
        layout.prop(context.scene, 'nd_show_gameplay', text='Сценарные области')
        if context.scene.nd_show_gameplay:layout.prop(context.scene,'nd_gameplay_filter',text='Тип областей')
        layout.prop(context.scene, 'nd_show_collisions', text='Коллизии участка')
        layout.prop(context.scene, 'nd_show_helpers', text='Служебная геометрия')
        layout.operator('nd.export_level_binaries')
        layout.operator('nd.export_streaming')
        layout.operator('nd.show_all_levels')
        region = parent_region(context.object)
        if region:
            layout.operator('nd.player_place')
            layout.label(text=region.get('nd_region_id', region.name))
            if region.get('nd_trigger_info_json'):
                card=json.loads(region['nd_trigger_info_json'])
                info=layout.box();info.label(text=card['category_label'])
                for callback in card['callbacks']:
                    info.label(text='Событие: '+callback['phase'])
                    for call in callback['calls'][:3]:info.label(text=call['text'][:110])
                    if callback['limitations']:info.label(text='Часть инструкций не расшифрована',icon='INFO')
                if not card['callbacks']:info.label(text='В REGION_TREE нет callback')
                info.operator('nd.trigger_details')
                port=layout.box();port.label(text='Действие C++ для порта')
                port.prop(region,'["nd_cpp_enabled"]',text='Использовать назначение')
                port.prop(region,'["nd_cpp_action"]',text='Имя обработчика')
                port.prop(region,'["nd_cpp_phase"]',text='enter / inside / exit')
                port.prop(region,'["nd_cpp_once"]',text='Однократно')
                port.prop(region,'["nd_cpp_target"]',text='ID цели (необязательно)')
                port.prop(region,'["nd_cpp_parameters"]',text='Параметры JSON')
                port.label(text='Это наше назначение; исходные события сохранены')
            if region.get('nd_type') == 'streaming_region':
                layout.prop(region, '["nd_preview_set"]', text='Набор (вручную)')
                layout.operator('nd.preview_region')
                layout.operator('nd.make_prefetch')
                layout.label(text='Это не симуляция сценария игры')


CLASSES = (ND_OT_export_streaming, ND_OT_export_levels, ND_OT_prefetch, ND_OT_preview, ND_OT_show_all,
           ND_OT_focus_level, ND_OT_story_step, ND_OT_story_apply,
           ND_OT_player_create, ND_OT_player_place, ND_OT_player_refresh,
           ND_OT_material_view, ND_OT_alpha_mode, ND_OT_trigger_details, ND_PT_streaming)


def register(preserve_scene=False):
    global INITIALIZING
    scene=bpy.context.scene
    preserved={}
    persisted=set()
    if preserve_scene:
        names=('nd_editor_level','nd_show_streaming','nd_show_gameplay',
               'nd_gameplay_filter',
               'nd_show_collisions','nd_show_helpers','nd_story_step',
               'nd_story_variant','nd_story_follow','nd_player_family',
               'nd_player_sim_enabled','nd_player_follow_view','nd_player_hold_outside',
               'nd_native_enabled','nd_native_task','nd_native_object_flag','nd_alpha_preview')
        preserved={name:getattr(scene,name) for name in names if hasattr(scene,name)}
        persisted={name for name in names if name in scene and name not in preserved}
    old_timer = bpy.app.driver_namespace.get('nd_player_timer')
    if old_timer and bpy.app.timers.is_registered(old_timer):
        bpy.app.timers.unregister(old_timer)
    for handler in list(bpy.app.handlers.depsgraph_update_post):
        if getattr(handler, '_nd_player_preview', False):
            bpy.app.handlers.depsgraph_update_post.remove(handler)
    bpy.app.driver_namespace['nd_player_timer'] = player_timer
    bpy.app.handlers.depsgraph_update_post.append(player_geometry_updated)
    PLAYER_CACHE['dirty'] = True
    for cls in CLASSES:
        old = getattr(bpy.types, cls.__name__, None)
        if not old and issubclass(cls, bpy.types.Operator):
            category, operation = cls.bl_idname.split('.', 1)
            old = getattr(bpy.types, category.upper() + '_OT_' + operation, None)
        if not old and getattr(cls, 'is_registered', False):
            old = cls
        if old:
            bpy.utils.unregister_class(old)
        bpy.utils.register_class(cls)
    bpy.types.Scene.nd_editor_level = EnumProperty(name='Участок', items=lambda self, context: LEVEL_ITEMS, update=select_level)
    for name in ('nd_show_streaming', 'nd_show_gameplay', 'nd_show_collisions', 'nd_show_helpers'):
        setattr(bpy.types.Scene, name, BoolProperty(default=False, update=update_visibility))
    bpy.types.Scene.nd_gameplay_filter=EnumProperty(items=[('__ALL__','Все области',''),
        ('events','События и диалоги',''),('audio_zone','Звуковые зоны',''),
        ('effects','Эффекты',''),('reflection','Отражения',''),
        ('spatial','Прочие объёмы','')],default='__ALL__',update=update_visibility)
    prepare_story_route()
    bpy.types.Scene.nd_story_step = EnumProperty(name='Шаг', items=lambda self, context: STORY_ITEMS, update=story_selection)
    bpy.types.Scene.nd_story_variant = IntProperty(name='Вариант N', default=1, min=1)
    bpy.types.Scene.nd_story_follow = BoolProperty(name='Перемещать обзор к области', default=True)
    bpy.types.Scene.nd_player_family = EnumProperty(items=lambda self,context:PLAYER_FAMILY_ITEMS,update=player_scope_changed)
    bpy.types.Scene.nd_player_sim_enabled = BoolProperty(default=False, update=player_toggle)
    bpy.types.Scene.nd_player_follow_view = BoolProperty(default=False)
    bpy.types.Scene.nd_player_hold_outside = BoolProperty(default=True)
    NATIVE_TASK_ITEMS.clear()
    graph=metadata().get('task_graphs',{}).get('home',{})
    if graph:
        edges={e['from']:e['to'] for e in graph['edges']}
        incoming={e['to'] for e in graph['edges']}
        roots=[e['from'] for e in graph['edges'] if e['from'] not in incoming]
        node=roots[0] if len(roots)==1 else None
        visited=set()
        while node in edges and node not in visited:
            visited.add(node);node=edges[node]
            if node in graph['nodes']:
                label=graph['nodes'][node]['name'];NATIVE_TASK_ITEMS.append((str(len(NATIVE_TASK_ITEMS)),label,label))
    if not NATIVE_TASK_ITEMS:NATIVE_TASK_ITEMS.append(('0','Нет графа задач','Обновите данные стриминга'))
    bpy.types.Scene.nd_native_enabled=BoolProperty(default=False)
    bpy.types.Scene.nd_native_task=EnumProperty(items=lambda self,context:NATIVE_TASK_ITEMS)
    bpy.types.Scene.nd_native_object_flag=BoolProperty(default=False)
    bpy.types.Scene.nd_alpha_preview = BoolProperty(default=True,update=alpha_toggle)
    if preserve_scene:
        setup_editor_view(preserve_scene=True)
        preserved.update({name:getattr(scene,name) for name in persisted})
        INITIALIZING=True
        try:
            for name,value in preserved.items():
                setattr(scene,name,value)
            if 'nd_editor_level' not in preserved: scene.nd_editor_level='__ALL__'
            if 'nd_player_family' not in preserved: scene.nd_player_family='__ALL__'
        finally:
            INITIALIZING=False
        if scene.nd_player_sim_enabled:
            bpy.app.timers.register(player_timer,first_interval=.15)
    else:
        INITIALIZING = True
        try:
            scene.nd_player_sim_enabled = False
            scene['nd_player_report'] = '{}'
            scene.nd_story_step = '0'
            scene.nd_story_variant = 1
            scene['nd_story_active'] = False
        finally:
            INITIALIZING = False
        setup_editor_view()


def startup_status(message, error=False):
    print('[TLOU] ' + message, flush=True)
    status = bpy.data.texts.get('TLOU_EDITOR_STATUS.txt') or bpy.data.texts.new('TLOU_EDITOR_STATUS.txt')
    status.clear()
    status.write(message)
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.show_region_ui = True
                area.tag_redraw()
    if not bpy.app.background:
        lines = message.splitlines()
        def draw(menu, context):
            for line in lines:
                menu.layout.label(text=line)
        bpy.context.window_manager.popup_menu(draw, title='TLOU — запуск скрипта', icon='ERROR' if error else 'INFO')


def run_interactive():
    print('[TLOU] Запуск редактора...', flush=True)
    try:
        register()
        scene = bpy.context.scene
        visuals = [o for o in scene.objects if o.get('nd_type') == 'visual']
        regions = sum(o.get('nd_type') in ('streaming_region', 'gameplay_region') for o in scene.objects)
        if not visuals:
            startup_status('Скрипт запущен, но визуальные объекты с тегами TLOU не найдены.\n'
                           'Откройте scene_editor.blend либо импортируйте FBX с Import Custom Properties.\n'
                           'Панель находится в 3D View: N → TLOU.', error=True)
        else:
            startup_status(f'Редактор запущен. Мешей: {len(visuals)}; областей: {regions}.\n'
                           f'Видимых мешей: {sum(not o.hide_get() for o in visuals)}.\n'
                           'Перейдите в 3D View: N → TLOU. Там выбирается участок.')
    except Exception:
        import traceback
        startup_status(traceback.format_exc(), error=True)
        raise


if __name__ == '__main__':
    run_interactive()
