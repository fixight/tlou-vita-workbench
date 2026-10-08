"""Native REGION_TREE candidate order, volume union and first-match selection.

The original game VM is not emulated. Query inputs belong to the host engine;
missing inputs fail explicitly. Disk scheduling below is a port policy.
"""
import math
import struct
from research.streaming.visibility_base import evaluate_selector

CAMERA = '0x89335b6e'


def read_grid(pak, resource_offset, regions):
    address = pak.read_ptr(resource_offset+0x20)
    if not address: raise ValueError('REGION_TREE spatial grid absent')
    lower = struct.unpack_from('<3f', pak.data, address)
    extent = struct.unpack_from('<3f', pak.data, address+16)
    dims = struct.unpack_from('<3I', pak.data, address+32)
    count = math.prod(dims)
    if not 0 < count <= 1000000 or not all(math.isfinite(v) and v>0 for v in extent):
        raise ValueError('Invalid region grid bounds')
    names = {r['offset']: r['name'] for r in regions}
    cells = []
    for i in range(count+1):  # Final cell is the out-of-bounds bucket.
        cell = pak.read_ptr(address+48+i*8)
        rows = pak.read_ptr(cell)
        size = struct.unpack_from('<I', pak.data, cell+8)[0]
        if size > 10000: raise ValueError('Invalid region category count')
        categories = {}
        for j in range(size):
            row = rows+j*16
            key = struct.unpack_from('<I', pak.data, row)[0]
            vector = pak.read_ptr(row+8)
            array = pak.read_ptr(vector)
            n = struct.unpack_from('<I', pak.data, vector+8)[0]
            if n > len(regions): raise ValueError('Invalid region candidate count')
            categories[f'0x{key:08x}'] = [names[pak.read_ptr(array+k*8)] for k in range(n)]
        cells.append(categories)
    return {'lower': list(lower), 'extent': list(extent), 'dimensions': list(dims),
            'cells': cells, 'selection': 'first_matching_positive_selector',
            'evidence': 'eboot: 0x7a4a60, 0x79e390; original per-cell order preserved'}


def candidates(grid, point, category=CAMERA):
    normalized = [(p-lo)/size for p,lo,size in zip(point,grid['lower'],grid['extent'])]
    dims = grid['dimensions']
    if all(0 <= v < 1 for v in normalized):
        x,y,z = (math.floor(v*n) for v,n in zip(normalized,dims))
        index = (x*dims[1]+y)*dims[2]+z
    else:
        index = math.prod(dims)
    return grid['cells'][index].get(category, [])


def native_contains(region, point):
    """Any convex part; strict signed-plane comparison matches zero-radius query."""
    for shape in region['shapes']:
        if 'analytic' in shape:
            a=shape['analytic']
            center=a.get('center',a.get('base'));delta=[point[i]-center[i] for i in range(3)]
            distance=sum(v*v for v in delta)
            if a['kind']=='sphere':
                if distance<=a['radius']**2:return True
            elif a['kind']=='cylinder':
                along=sum(delta[i]*a['axis'][i] for i in range(3))
                if 0<=along<=a['height'] and distance-along*along<=a['radius']**2:return True
            else:raise ValueError('Unsupported analytic region')
            continue
        if 'planes' in shape:
            planes = shape['planes']
        elif shape.get('faces') and isinstance(shape['faces'][0], dict):
            # Serialized normal_raw.w is zero. Plane translation lives in the
            # fourth row of the original world-to-face matrix.
            planes = [[row[2] for row in face['world_to_face_matrix_rows']] for face in shape['faces']]
        else:
            from .region_runtime import convex_volume
            volume = convex_volume(shape['vertices'], shape['faces'])
            # Authored planes use the same float32 storage and strict boundary
            # comparison as the exported TLTR, rather than editor hit tolerance.
            planes = [struct.unpack('<4f',struct.pack('<4f',*n,-d)) for n,d in volume['planes']]
        if planes and all(sum(n[i]*point[i] for i in range(3))+n[3] < 0 for n in planes):
            return True
    return False


class GameState:
    """Explicit task statuses and object queries supplied by the port's story code."""
    def __init__(self, tasks=None, spawned=None, booleans=None):
        self.tasks = dict(tasks or {}) # (chapter hash, task hash) -> pending/active/complete
        self.spawned = dict(spawned or {}) # object hash -> bool
        self.booleans = dict(booleans or {}) # (property hash, object hash) -> bool

    def status(self, chapter, task):
        key = (chapter,task)
        if key not in self.tasks: raise ValueError(f'Missing task state: {key}')
        if self.tasks[key] not in ('pending','active','complete'):raise ValueError('Unsupported task status: '+str(self.tasks[key]))
        return self.tasks[key]

    def queries(self):
        def spawned(obj):
            if obj not in self.spawned: raise ValueError(f'Missing object-spawned state: {obj}')
            return self.spawned[obj]
        def boolean(prop, obj):
            if (prop,obj) not in self.booleans: raise ValueError(f'Missing object boolean: {(prop,obj)}')
            return self.booleans[prop,obj]
        return {('call_script','0xf1360136'): lambda c,t: self.status(c,t)=='complete',
                ('call_script','0x13e68c9f'): lambda c,t: self.status(c,t)=='active',
                ('call_script','0x4d2bf414'): lambda c,t: self.status(c,t)=='pending',
                ('call_native','0xa93d2926'): spawned,
                ('call_native','0xf307e431'): boolean}


def select_native(document, world, point, state, overrides=None):
    if len(point)!=3 or not all(math.isfinite(p) for p in point): raise ValueError('Invalid camera position')
    grid = document['native_grids'][world]
    records = {r['name']:r for r in document['regions'] if r['source_level']==world}
    for name in candidates(grid,point):
        region = records[name]
        if region.get('native_flags',0) & 1: continue
        if not native_contains(region,point): continue
        # These property gates query original runtime groups, not task selectors.
        if any(p['key_raw']=='0xe1a8c886' for p in region['properties']):
            raise ValueError('Region activation group requires host implementation: '+region['id'])
        if overrides and region['id'] in overrides:
            return dict(overrides[region['id']], region_id=region['id'], variant='override')
        variant = evaluate_selector(region['selector'],state.queries())
        if variant <= 0: continue
        selected = region['sets'].get(str(variant))
        if selected is None: raise ValueError('Unknown selector result: '+str(variant))
        return dict(selected, region_id=region['id'], variant=variant)
    return {'region_id':None, 'variant':0, 'display':[], 'resident_only':[]}


def dependencies(document, roots):
    result = set(); pending = list(roots)
    while pending:
        name = pending.pop()
        if name in result: continue
        result.add(name)
        if name not in document['levels']: raise ValueError('Missing dependency record: '+name)
        pending.extend(document['levels'][name].get('cache_dependencies',[]))
    return result


class StreamPlanner:
    """Two-phase port policy: request -> wait -> atomic visibility switch -> release.

    Physical unload requires host reference counts (actors/audio/etc.). Resident
    caches do not automatically become visible geometry.
    """
    def __init__(self, document):
        self.document = document
        self.visible = set()
        self.required = set()

    def update(self, selection, loaded, pinned=()):
        if not selection.get('region_id'):
            return {'status':'outside_regions_hold', 'load':[], 'show':[], 'hide':[], 'release':[]}
        visible = set(selection['display'])
        required = dependencies(self.document,visible | set(selection['resident_only'])) | set(pinned)
        missing = required-set(loaded)
        if missing:
            return {'status':'waiting_for_resources', 'load':sorted(missing), 'show':[], 'hide':[], 'release':[]}
        result = {'status':'commit', 'load':[], 'show':sorted(visible-self.visible),
                  'hide':sorted(self.visible-visible), 'release':sorted(self.required-required)}
        self.visible,self.required = visible,required
        return result
