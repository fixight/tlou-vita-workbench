"""Geometry and set-selection rules for the experimental position preview.

These rules are shared without bpy. Union of volumes/regions is a preview policy,
not a claim about the original game's unresolved overrides.
"""
import math


def dot(a,b): return sum(x*y for x,y in zip(a,b))
def sub(a,b): return tuple(x-y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def convex_volume(vertices,faces):
    if len(vertices)<4 or not all(math.isfinite(v) for p in vertices for v in p):
        raise ValueError('Invalid volume vertices')
    lower=tuple(min(p[a] for p in vertices) for a in range(3))
    upper=tuple(max(p[a] for p in vertices) for a in range(3))
    center=tuple(sum(p[a] for p in vertices)/len(vertices) for a in range(3))
    # Exported face corners are independent float32 world coordinates. At large
    # world offsets adjacent corners differ by several ULPs, even on native boxes.
    tolerance=max(1e-5,max(sub(upper,lower))*1e-6,
                  max(abs(v) for p in vertices for v in p)*8*2**-23)
    planes=[]
    for face in faces:
        if len(face)<3 or any(i<0 or i>=len(vertices) for i in face):
            raise ValueError('Invalid volume face')
        a=vertices[face[0]]; normal=None
        for i in range(1,len(face)-1):
            candidate=cross(sub(vertices[face[i]],a),sub(vertices[face[i+1]],a))
            length=math.sqrt(dot(candidate,candidate))
            if length>1e-12:
                normal=tuple(v/length for v in candidate);break
        if normal is None: raise ValueError('Degenerate volume face')
        distance=dot(normal,a)
        if dot(normal,center)>distance:
            normal=tuple(-v for v in normal);distance=-distance
        if any(dot(normal,p)>distance+tolerance for p in vertices):
            raise ValueError('Non-convex or inconsistent volume')
        planes.append((normal,distance))
    if len(planes)<4: raise ValueError('Not enough volume planes')
    return {'planes':planes,'lower':lower,'upper':upper,'center':center,'tolerance':tolerance}


def contains(volume,point):
    eps=volume['tolerance']
    return (all(lo-eps<=p<=hi+eps for p,lo,hi in zip(point,volume['lower'],volume['upper'])) and
            all(dot(n,point)<=d+eps for n,d in volume['planes']))


def segment_intersects(volume,start,end):
    """Detect a crossed volume even when both endpoint samples are outside."""
    enter,exit=0.0,1.0
    delta=sub(end,start);eps=volume['tolerance']
    for normal,distance in volume['planes']:
        origin=dot(normal,start)-distance-eps
        speed=dot(normal,delta)
        if abs(speed)<1e-12:
            if origin>0: return False
        else:
            t=-origin/speed
            if speed<0: enter=max(enter,t)
            else: exit=min(exit,t)
            if enter>exit: return False
    return True


def select_active_sets(records,manual_variants):
    display,resident=set(),set();conditions=[]
    for record in records:
        selector=record.get('selector',{})
        conditional=selector.get('kind')!='constant'
        variant=manual_variants.get(record['id'],1) if conditional else selector.get('value',1)
        state=record.get('sets',{}).get(str(variant))
        if variant==0: state={'display':[],'resident_only':[]}
        if conditional or state is None:
            conditions.append({'region':record['id'],'variant':variant,'manual':conditional,
                               'valid':state is not None,'selector_kind':selector.get('kind')})
        if state is not None:
            display.update(state['display']);resident.update(state.get('resident_only',[]))
    resident-=display
    return {'display':sorted(display),'resident_only':sorted(resident),
            'required':sorted(display|resident),'conditions':conditions}
