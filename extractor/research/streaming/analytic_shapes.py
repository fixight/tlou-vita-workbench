"""Native sphere/cylinder data with a tessellated editor display only.

Sphere: eboot 80f601; cylinder: 80f8d0..80fa53. Cylinder origin is
the base, local +Y axis, radius at +40 and length at +44.
"""
import math
import struct
import numpy as np


def read_analytic(data, offset, kind):
    center=list(struct.unpack_from('<3f',data,offset+0x20))
    if kind==0:
        radius=struct.unpack_from('<f',data,offset+0x2c)[0]
        rotation=np.eye(3);height=0
        params={'kind':'sphere','center':center,'radius':radius}
    elif kind==3:
        x,y,z,w=struct.unpack_from('<4f',data,offset+0x30)
        radius,height=struct.unpack_from('<2f',data,offset+0x40)
        if abs(x*x+y*y+z*z+w*w-1)>0.001:raise ValueError('Non-unit cylinder quaternion')
        rotation=np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
                           [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
                           [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])
        params={'kind':'cylinder','base':center,'radius':radius,'height':height,'axis':rotation[:,1].tolist()}
    else:raise ValueError('Unsupported analytic shape')
    if not all(math.isfinite(v) for v in [*center,radius,height]) or radius<=0 or height<0:raise ValueError('Invalid analytic dimensions')
    def point(r,y,angle):return (rotation@np.array([r*math.cos(angle),y,r*math.sin(angle)])+center).tolist()
    faces=[];segments=24
    if kind==0:
        rings=[[point(radius*math.sin(math.pi*j/12),radius*math.cos(math.pi*j/12),i*2*math.pi/segments) for i in range(segments)] for j in range(13)]
        for j in range(12):
            for i in range(segments):
                k=(i+1)%segments
                faces.append([rings[j][i],rings[j+1][k],rings[j+1][i]] if j==0 else
                             [rings[j][i],rings[j][k],rings[j+1][i]] if j==11 else
                             [rings[j][i],rings[j][k],rings[j+1][k],rings[j+1][i]])
    else:
        rings=[[point(radius,y,i*2*math.pi/segments) for i in range(segments)] for y in [0,height]]
        for i in range(segments):
            k=(i+1)%segments
            faces.append([rings[0][i],rings[0][k],rings[1][k],rings[1][i]])
            for j,y in enumerate([0,height]):faces.append([point(0,y,0),rings[j][i],rings[j][k]])
    points=np.array([p for face in faces for p in face])
    return {'offset':offset,'shape_type_raw':kind,'analytic':params,
            'bounds_min':points.min(axis=0).tolist(),'bounds_max':points.max(axis=0).tolist(),
            'faces':[{'world_vertices':face} for face in faces],
            'max_nearest_corner_error':0,'corner_validation':'analytic primitive; editor tessellation only',
            'max_normal_matrix_error':0}
