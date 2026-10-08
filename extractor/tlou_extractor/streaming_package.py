"""Compact TLTR v1 package for the portable C++ streaming selector.

Only native world streaming volumes go into TLTR. Story graph and gameplay
callback programs remain in JSON; unsupported world semantics fail export.
"""
import copy
import json
import struct
import math
import heapq
from pathlib import Path


def runtime_document(document, level_files=None):
    result = copy.deepcopy(document)
    if level_files is not None: result['binary_level_files'] = dict(level_files)
    files = result.get('binary_level_files',{})
    for level, record in result['levels'].items():
        record['engine_file'] = 'app0:/'+files[level] if level in files else None
    return result


def upgrade_document(document, bundle):
    """Keep edited volumes/deletions while updating proven properties/programs."""
    result=copy.deepcopy(bundle)
    original={r['id']:r for r in result['regions']}
    regions=[]
    for edited in document['regions']:
        record=copy.deepcopy(original.get(edited['id'],edited))
        for field in ('shapes','prefetch_shapes','editor_origin','port_binding'):
            if field in edited:record[field]=edited[field]
        regions.append(record)
    result['regions']=regions
    result['binary_level_files']=document.get('binary_level_files',{})
    result['visual_level_ids']=document.get('visual_level_ids',[])
    for world,grid in result['native_grids'].items():
        world_records=[r for r in regions if r['source_level']==world and r['type']=='streaming_region']
        if not world_records:continue
        # Original cell lists establish a partial priority order. A conservative
        # reindex handles moved/deleted editor volumes while retaining that order.
        names={r['name']:i for i,r in enumerate(world_records)}
        edges={n:set() for n in names};incoming={n:0 for n in names}
        for cell in grid['cells']:
            sequence=[n for n in cell.get('0x89335b6e',[]) if n in names]
            for a,b in zip(sequence,sequence[1:]):
                if b not in edges[a]:edges[a].add(b);incoming[b]+=1
        pending=[(names[n],n) for n,count in incoming.items() if not count];heapq.heapify(pending);ordered=[]
        while pending:
            _,n=heapq.heappop(pending);ordered.append(n)
            for target in edges[n]:
                incoming[target]-=1
                if not incoming[target]:heapq.heappush(pending,(names[target],target))
        if len(ordered)!=len(names):raise ValueError('Native region priority is not globally consistent; cannot reindex edited volumes')
        bounds={r['name']:([min(s['bounds_min'][a] for s in r['shapes']) for a in range(3)],
                           [max(s['bounds_max'][a] for s in r['shapes']) for a in range(3)]) for r in world_records}
        dims=grid['dimensions'];lower=grid['lower'];extent=grid['extent'];cells=[]
        for x in range(dims[0]):
            for y in range(dims[1]):
                for z in range(dims[2]):
                    xyz=(x,y,z);lo=[lower[a]+extent[a]*xyz[a]/dims[a] for a in range(3)]
                    hi=[lower[a]+extent[a]*(xyz[a]+1)/dims[a] for a in range(3)]
                    selected=[n for n in ordered if all(bounds[n][0][a]<=hi[a] and bounds[n][1][a]>=lo[a] for a in range(3))]
                    cells.append({'0x89335b6e':selected})
        cells.append({'0x89335b6e':ordered})
        grid['cells']=cells;grid['editor_reindexed']=True
    return result


def encode_runtime(document, world):
    records = [r for r in document['regions'] if r['source_level']==world and r['type']=='streaming_region']
    if not records: raise ValueError('No streaming regions for '+world)
    grid = document['native_grids'][world]
    names = {r['name']:i for i,r in enumerate(records)}
    levels = sorted(document['levels'])
    indices = {name:i for i,name in enumerate(levels)}
    data = bytearray(b'TLTR'+struct.pack('<I',1))
    def u(value): data.extend(struct.pack('<I',value))
    def f(values): data.extend(struct.pack('<'+'f'*len(values),*values))
    def text(value):
        raw=value.encode('utf-8');u(len(raw));data.extend(raw)
    def array(values):
        u(len(values))
        for value in values:u(value)
    text(world)
    u(len(levels))
    for name in levels:
        record=document['levels'][name]
        text(name);text(record.get('engine_file') or '')
        array([indices[d] for d in record.get('cache_dependencies',[])])
    u(len(records))
    for r in records:
        if any(p['key_raw']=='0xe1a8c886' for p in r['properties']):
            raise ValueError('Unsupported native activation group: '+r['id'])
        text(r['id']);u(r.get('native_flags',0));u(len(r['shapes']))
        for shape in r['shapes']:
            if 'planes' in shape: planes=shape['planes']
            elif shape['faces'] and isinstance(shape['faces'][0],dict):
                planes=[[row[2] for row in face['world_to_face_matrix_rows']] for face in shape['faces']]
            else:
                from .region_runtime import convex_volume
                v=convex_volume(shape['vertices'],shape['faces'])
                planes=[[*n,-d] for n,d in v['planes']]
            u(len(planes))
            for plane in planes:f(plane)
        selector=r['selector']
        if selector['kind']=='constant':
            value=selector['value']
            code=[(0x0c,0,value&255,value>>8,0),(0,0,0,0,0)]
        else:
            code=[]
            for inst in selector['instructions']:
                if inst['operation']=='unknown': raise ValueError('Unsupported opcode in '+r['id'])
                code.append((int(inst['opcode'],16),*inst['raw_operands'],int(inst.get('symbol_id','0'),16)))
        u(len(code))
        for op,a,b,c,symbol in code:data.extend(struct.pack('<4BI',op,a,b,c,symbol))
        u(len(r['sets']))
        for variant,state in r['sets'].items():
            u(int(variant));array([indices[n] for n in state['display']]);array([indices[n] for n in state['resident_only']])
    f(grid['lower']);f(grid['extent'])
    for dimension in grid['dimensions']:u(dimension)
    u(len(grid['cells']))
    for cell in grid['cells']:
        candidates=cell.get('0x89335b6e',[])
        if any(n not in names for n in candidates):raise ValueError('Camera category contains unclassified region')
        array([names[n] for n in candidates])
    return bytes(data)


def write_package(document, destination, level_files=None):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    result=runtime_document(document,level_files)
    packages={}
    for world in sorted({r['source_level'] for r in result['regions'] if r['type']=='streaming_region'}):
        filename=world+'.tltr'
        payload=encode_runtime(result,world)
        (destination/filename).write_bytes(payload)
        packages[world]=filename
    result['runtime_packages']=packages
    result['runtime_ready']=bool(packages)
    direct={n for r in result['regions'] for s in r.get('sets',{}).values() for n in s['display']+s['resident_only']}
    result['coverage']['direct_targets_without_exported_chunk']=sorted(n for n in direct if not result['levels'][n].get('engine_file'))
    result['coverage']['chunk_files_complete']=bool(level_files) and all(result['levels'][n].get('engine_file') for n in direct)
    result['runtime_scope']='Static chunk selection with explicit host story state; not the original gameplay VM.'
    result['limitations']=['Original scripted actors, movies, audio and task completion logic require host handlers.',
        'Disk prefetch timing, readiness barrier and reference-counted release are port policies.',
        'Runtime overrides must be supplied explicitly by the host; absent overrides use native region selectors.']
    from .trigger_catalog import build_catalog
    result['trigger_catalog']=build_catalog(result)
    from .trigger_aabb import encode_aabb_triggers
    (destination/'triggers.bin').write_bytes(encode_aabb_triggers(result,level_files))
    result['diagnostic_triggers']={'file':'triggers.bin','format':'VTGR','version':1,
        'scope':'Callback gameplay/dialogue/effect areas and authored bindings in exported chapter families; AABB overlap only.'}
    (destination/'trigger_catalog.json').write_text(json.dumps(result['trigger_catalog'],ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'trigger_bindings.json').write_text(json.dumps({
        'schema':'tlou.port_trigger_bindings','version':1,'coordinate_system':'native_y_up',
        'bindings':[{'region_id':r['id'],'source_id':r['name_id_raw'],'source_level':r['source_level'],
                     'volumes':r['shapes'],'action':r['port_binding']} for r in result['regions'] if r.get('port_binding')],
        'note':'Authored port actions; not executed by the native static streaming selector.'},
        ensure_ascii=False,indent=2),encoding='utf-8')
    (destination/'streaming_runtime.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    support=Path(__file__).parent
    for name in ('NativeStreaming.h','StreamingIntegrationExample.cpp'):
        (destination/name).write_bytes((support/name).read_bytes())
    home=result.get('task_graphs',{}).get('home')
    if home:
        header=['#pragma once','#include "NativeStreaming.h"','namespace TlouStreaming {',
                'inline StoryState InitialHomeState(){','    StoryState state;']
        header.extend('    state.SetTask("home",'+json.dumps(n['name'])+',TaskStatus::Pending);' for n in home['nodes'].values())
        header.extend(['    state.SetTask("home","hom-house-daughter-room-phone",TaskStatus::Active);',
                       '    state.spawned[0x69c85a6du]=true;',
                       '    state.SetSarahCarStarted(false);','    return state;','}','}'])
        (destination/'HomeStory.h').write_text('\n'.join(header),encoding='utf-8')
    return result
