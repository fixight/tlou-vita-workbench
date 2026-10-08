"""Экспорт Сары: glTF -> SK16 v2 (16 байт/вершина, две кости, GPU-палитры).

На ПК: иерархия glTF, quaternion-интерполяция, inverse bind, root motion.
В движке: выбор клипа, интерполяция готовых матриц, скиннинг на GPU.
Порядок клипов и имена выходных файлов пока настроены на Сару.
"""

import argparse
import json
import math
import struct
from pathlib import Path

import numpy as np
from PIL import Image

PALETTE_LIMIT = 24
POSITION_STEP = 0.001  # Метры; XYZ хранится в int16 относительно origin батча.
VERTEX_STRIDE = 16
SAMPLE_RATE = 30
CLIP_NAMES = ('sar-p-relaxed-idle', 'sar-p-walk-fw', 'sar-p-run-fw')


def load_glb(path):
    """Прочитать JSON и предоставить чтение accessors с учётом stride."""
    binary = path.read_bytes()
    json_length = struct.unpack_from('<I', binary, 12)[0]
    document = json.loads(binary[20:20 + json_length])
    buffer_data = binary[28 + json_length:]

    def read_accessor(index):
        accessor = document['accessors'][index]
        view = document['bufferViews'][accessor['bufferView']]
        dtype = np.dtype({5126: '<f4', 5123: '<u2', 5121: 'u1', 5125: '<u4'}[
            accessor['componentType']])
        components = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4, 'MAT4': 16}[
            accessor['type']]
        offset = view.get('byteOffset', 0) + accessor.get('byteOffset', 0)
        stride = view.get('byteStride', dtype.itemsize * components)
        result = np.ndarray(
            (accessor['count'], components), dtype, buffer_data, offset,
            strides=(stride, dtype.itemsize),
        ).copy()
        if accessor.get('normalized'):
            result = result.astype(float) / np.iinfo(dtype).max
        return result

    return document, read_accessor


def compose_transform(translation, rotation, scale):
    """Локальная матрица T * R * S; quaternion glTF имеет порядок XYZW."""
    x, y, z, w = np.asarray(rotation) / np.linalg.norm(rotation)
    matrix = np.eye(4)
    matrix[:3, :3] = np.array([
        [1 - 2 * (y*y + z*z), 2 * (x*y - z*w), 2 * (x*z + y*w)],
        [2 * (x*y + z*w), 1 - 2 * (x*x + z*z), 2 * (y*z - x*w)],
        [2 * (x*z - y*w), 2 * (y*z + x*w), 1 - 2 * (x*x + y*y)],
    ]) * scale
    matrix[:3, 3] = translation
    return matrix


def interpolate_rotation(first, second, blend):
    """SLERP по короткой дуге; близкие quaternion интерполируются линейно."""
    dot = np.dot(first, second)
    if dot < 0:
        second = -second
        dot = -dot
    if dot > .9995:
        rotation = first * (1 - blend) + second * blend
        return rotation / np.linalg.norm(rotation)
    angle = np.arccos(np.clip(dot, -1, 1))
    return (first * np.sin((1 - blend) * angle)
            + second * np.sin(blend * angle)) / np.sin(angle)


def evaluate_world_transforms(document, read_accessor, animation, time_seconds):
    """Вычислить мировые матрицы всех узлов, включая промежуточные узлы скелета."""
    nodes = document['nodes']
    translations = [np.array(node.get('translation', [0, 0, 0]), float) for node in nodes]
    rotations = [np.array(node.get('rotation', [0, 0, 0, 1]), float) for node in nodes]
    scales = [np.array(node.get('scale', [1, 1, 1]), float) for node in nodes]

    if animation:
        for channel in animation['channels']:
            sampler = animation['samplers'][channel['sampler']]
            times = read_accessor(sampler['input']).ravel()
            values = read_accessor(sampler['output'])
            first = max(0, min(len(times) - 1, int(
                np.searchsorted(times, time_seconds, side='right') - 1)))
            second = min(first + 1, len(times) - 1)
            blend = 0 if first == second else float(np.clip(
                (time_seconds - times[first]) / (times[second] - times[first]), 0, 1))
            target_node = channel['target']['node']
            target_path = channel['target']['path']

            if sampler.get('interpolation', 'LINEAR') != 'LINEAR':
                raise ValueError('Unsupported interpolation')
            if target_path == 'rotation':
                rotations[target_node] = interpolate_rotation(values[first], values[second], blend)
            elif target_path == 'translation':
                translations[target_node] = values[first] * (1 - blend) + values[second] * blend
            elif target_path == 'scale':
                scales[target_node] = values[first] * (1 - blend) + values[second] * blend
            else:
                raise ValueError('Unsupported animation channel ' + target_path)

    parents = {child: index for index, node in enumerate(nodes)
               for child in node.get('children', [])}
    world_matrices = {}

    def calculate_world_matrix(index):
        if index not in world_matrices:
            node = nodes[index]
            if 'matrix' in node:
                local_matrix = np.array(node['matrix']).reshape(4, 4).T
            else:
                local_matrix = compose_transform(translations[index], rotations[index], scales[index])
            world_matrices[index] = (
                calculate_world_matrix(parents[index]) @ local_matrix
                if index in parents else local_matrix)
        return world_matrices[index]

    return np.array([calculate_world_matrix(index) for index in range(len(nodes))])


def select_two_influences(joints, weights):
    """Объединить повторные кости, оставить два наибольших веса и нормализовать."""
    bone_ids = np.zeros((len(joints), 2), int)
    first_weights = np.ones(len(joints))
    for vertex in range(len(joints)):
        combined = {}
        for joint, weight in zip(joints[vertex], weights[vertex]):
            if weight > 0:
                combined[int(joint)] = combined.get(int(joint), 0) + float(weight)
        strongest = sorted(combined.items(), key=lambda item: (-item[1], item[0]))[:2]
        strongest = strongest or [(int(joints[vertex, 0]), 1)]
        if len(strongest) == 1:
            strongest.append((strongest[0][0], 0))
        bone_ids[vertex] = [item[0] for item in strongest]
        first_weights[vertex] = strongest[0][1] / sum(item[1] for item in strongest)
    return bone_ids, first_weights


def export_material_texture(document, source, destination, material_id, max_texture):
    """RGBA8: заголовок width/height/bytes, затем пиксели без переворота строк."""
    material = document['materials'][material_id].get('pbrMetallicRoughness', {})
    factor = material.get('baseColorFactor', [1]*4)
    texture = material.get('baseColorTexture')
    image = Image.new('RGBA', (1, 1), (255, 255, 255, 255))
    if texture:
        image_info = document['images'][document['textures'][texture['index']]['source']]
        image = Image.open(source.parent / image_info['uri']).convert('RGBA')
    image.thumbnail((max_texture, max_texture), Image.Resampling.LANCZOS)
    pixels = np.array(image)
    pixels = np.rint(pixels.astype(float) * np.array(factor)).clip(0, 255).astype('u1')
    # glTF UV и PNG согласованы: сохраняем исходный порядок строк.
    filename = f'sarah_m{material_id}.bin'
    (destination / filename).write_bytes(
        struct.pack('<III', image.width, image.height, pixels.nbytes) + pixels.tobytes())
    return 'app0:/characters/sarah16/' + filename


def group_triangles_by_palette(triangles, bone_ids):
    """Best-fit на ПК: выбрать палитру с минимальным числом добавляемых костей.

    Материалы обрабатываются отдельно; winding треугольников сохраняется.
    Каждый draw может передать в шейдер не более 24 матриц.
    """
    groups = []
    for triangle in triangles:
        needed = {int(joint) for vertex in triangle for joint in bone_ids[vertex]}
        candidates = [(len(needed - palette), len(palette), index)
                      for index, (_, palette) in enumerate(groups)
                      if len(palette | needed) <= PALETTE_LIMIT]
        if candidates:
            group_index = min(candidates)[2]
            groups[group_index][0].append(triangle)
            groups[group_index][1].update(needed)
        else:
            groups.append(([triangle], needed))
    return groups


def pack_mesh_batch(triangles, palette, positions, normals, texcoords,
                    bone_ids, first_weights, texture_path):
    """Один индексированный батч; индексы костей локальны относительно палитры.

    0..5: int16 XYZ; 6..9: half UV; 10..11: oct-normal snorm8;
    12..13: uint8 bone IDs; 14: unorm8 первый вес; 15: reserved.
    """
    vertices, index_remap = np.unique(np.array(triangles).ravel(), return_inverse=True)
    palette = sorted(palette)
    palette_lookup = {joint: index for index, joint in enumerate(palette)}
    origin = np.rint((positions[vertices].min(0) + positions[vertices].max(0)) / .002) * POSITION_STEP
    packed_positions = np.rint((positions[vertices] - origin) / POSITION_STEP)
    assert packed_positions.min() >= -32768 and packed_positions.max() <= 32767 and len(vertices) <= 65535

    packed_vertices = bytearray()
    for vertex, xyz in zip(vertices, packed_positions):
        normal = normals[vertex].astype(float)
        normal /= max(1e-20, np.abs(normal).sum())
        oct_normal = normal[:2].copy()
        if normal[2] < 0:
            oct_normal = (1 - np.abs(oct_normal[::-1])) * np.where(oct_normal >= 0, 1, -1)
        oct_normal = np.floor(np.clip(oct_normal, -1, 1) * 127 + .5).astype(int)
        packed_vertices.extend(struct.pack(
            '<3h2e2b4B', *xyz.astype(int), *texcoords[vertex], *oct_normal,
            palette_lookup[int(bone_ids[vertex, 0])],
            palette_lookup[int(bone_ids[vertex, 1])],
            int(math.floor(first_weights[vertex] * 255 + .5)), 0))
    return (bytes(packed_vertices), index_remap.astype('<u2').tobytes(),
            palette, texture_path, origin)


def bake_animation_clips(document, read_accessor, skin, inverse_bind, used_joints, feet_offset, clip_names=CLIP_NAMES, preserve_root_motion=False):
    """Запечь skin matrices при 30 Hz: world bone * inverse bind.

    XZ root motion удаляется: перемещение выполняет Character::HandleMovement.
    Вертикальная анимация сохраняется. Матрицы записываются column-major.
    """
    clips = []
    for name in clip_names:
        animation = next(clip for clip in document['animations'] if clip['name'] == name)
        duration = max(float(read_accessor(sampler['input'])[-1, 0])
                       for sampler in animation['samplers'])
        frame_count = max(2, (round(duration * SAMPLE_RATE) if preserve_root_motion else math.ceil(duration * SAMPLE_RATE)) + 1)
        initial = evaluate_world_transforms(document, read_accessor, animation, 0)
        root_node = int(skin['joints'][0])
        initial_root_position = initial[root_node, :3, 3].copy()
        samples = []
        for time_seconds in np.linspace(0, duration, frame_count):
            world = evaluate_world_transforms(document, read_accessor, animation, float(time_seconds))
            matrices = world[np.array(skin['joints'])[used_joints]] @ inverse_bind[used_joints]
            root_drift = world[root_node, :3, 3] - initial_root_position
            if not preserve_root_motion:
                matrices[:, 0, 3] -= root_drift[0]
                matrices[:, 2, 3] -= root_drift[2]
            matrices[:, 1, 3] -= feet_offset
            samples.append(matrices.transpose(0, 2, 1).astype('<f4'))
        clips.append((name, duration, frame_count, np.array(samples).tobytes()))
    return clips


def write_character_package(destination, batches, used_joints, clips, bind_pivots=None):
    """SK16 v2: header -> bind-space joint pivots -> batches -> clips."""
    joint_remap = {joint: index for index, joint in enumerate(used_joints)}
    package = bytearray(struct.pack('<4s4I', b'SK16', 2 if bind_pivots is not None else 1, len(batches), len(used_joints), len(clips)))
    if bind_pivots is not None:
        pivots = np.asarray(bind_pivots, dtype='<f4')
        if pivots.shape != (len(used_joints), 3) or not np.all(np.isfinite(pivots)):
            raise ValueError('Invalid bind-space joint pivots')
        package.extend(pivots.tobytes())
    for vertices, indices, palette, texture_path, origin in batches:
        encoded_path = texture_path.encode()
        package.extend(struct.pack(
            '<4I4f', len(vertices) // VERTEX_STRIDE, len(indices) // 2,
            len(palette), len(encoded_path), *origin, POSITION_STEP))
        package.extend(encoded_path)
        package.extend(np.array([joint_remap[joint] for joint in palette], '<u2').tobytes())
        package.extend(vertices)
        package.extend(indices)
    for name, duration, frame_count, matrices in clips:
        encoded_name = name.encode()
        package.extend(struct.pack('<IIf', len(encoded_name), frame_count, duration))
        package.extend(encoded_name)
        package.extend(matrices)
    (destination / 'sarah.sk16').write_bytes(package)
    return len(package)


def export(source, dest, max_texture=512, interaction_clip=None, *, clip_names=None, cinematic=False, runtime_root=None):
    """Координация экспорта; обработка мешей отделена от запекания клипов."""
    document, raw_accessor = load_glb(source)
    accessor_cache = {}

    def read_accessor(index):
        if index not in accessor_cache:
            accessor_cache[index] = raw_accessor(index)
        return accessor_cache[index]

    assert len(document['skins']) == 1, 'One skin per package supported'
    skin = document['skins'][0]
    inverse_bind = read_accessor(skin['inverseBindMatrices']).reshape(-1, 4, 4).transpose(0, 2, 1)
    rest_pose = evaluate_world_transforms(document, read_accessor, None, 0)
    bind_matrices = rest_pose[skin['joints']] @ inverse_bind
    batches = []
    used_joints = set()
    feet_offset = math.inf
    texture_paths = {}
    dest.mkdir(parents=True, exist_ok=True)

    for mesh in document['meshes']:
        for primitive in mesh['primitives']:
            attributes = primitive['attributes']
            assert primitive.get('mode', 4) == 4
            positions = read_accessor(attributes['POSITION'])
            normals = read_accessor(attributes['NORMAL'])
            texcoords = read_accessor(attributes['TEXCOORD_0'])
            joints = read_accessor(attributes['JOINTS_0'])
            weights = read_accessor(attributes['WEIGHTS_0'])
            bone_ids, first_weights = select_two_influences(joints, weights)

            # Нижняя точка bind pose становится локальным уровнем стоп персонажа.
            homogeneous_positions = np.c_[positions, np.ones(len(positions))]
            world_positions = (
                np.einsum('nij,nj->ni', bind_matrices[bone_ids[:, 0]], homogeneous_positions)
                * first_weights[:, None]
                + np.einsum('nij,nj->ni', bind_matrices[bone_ids[:, 1]], homogeneous_positions)
                * (1 - first_weights[:, None]))
            feet_offset = min(feet_offset, float(world_positions[:, 1].min()))

            material_id = primitive.get('material', 0)
            if material_id not in texture_paths:
                texture_paths[material_id] = export_material_texture(
                    document, source, dest, material_id, max_texture)
            if runtime_root:
                texture_paths[material_id] = runtime_root.rstrip('/') + '/' + Path(texture_paths[material_id]).name
            triangles = (read_accessor(primitive['indices']).ravel().reshape(-1, 3)
                         if 'indices' in primitive else np.arange(len(positions)).reshape(-1, 3))
            for group_triangles, palette in group_triangles_by_palette(triangles, bone_ids):
                batches.append(pack_mesh_batch(
                    group_triangles, palette, positions, normals, texcoords,
                    bone_ids, first_weights, texture_paths[material_id]))
                used_joints.update(palette)

    used_joints = sorted(used_joints)
    names = tuple(clip_names) if clip_names is not None else CLIP_NAMES + (tuple(interaction_clip) if isinstance(interaction_clip,(list,tuple)) else ((interaction_clip,) if interaction_clip else ()))
    clips = bake_animation_clips(document, read_accessor, skin, inverse_bind, used_joints, 0.0 if cinematic else feet_offset, names, preserve_root_motion=cinematic)
    bind_pivots = np.linalg.inv(inverse_bind[used_joints])[:, :3, 3]
    package_bytes = write_character_package(dest, batches, used_joints, clips, bind_pivots)
    report = {
        'format': 'SK16 v2', 'stride': VERTEX_STRIDE, 'step_metres': POSITION_STEP,
        'batches': len(batches), 'vertices': sum(len(batch[0]) // VERTEX_STRIDE for batch in batches),
        'triangles': sum(len(batch[1]) // 6 for batch in batches),
        'used_skin_matrices': len(used_joints), 'palette_limit': PALETTE_LIMIT,
        'clips': [{'name': name, 'frames': frames, 'duration': duration}
                  for name, duration, frames, _ in clips],
        'texture_limit': max_texture, 'feet_offset_metres': feet_offset,
        'package_bytes': package_bytes,
    }
    (dest / 'export_report.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('destination', type=Path)
    parser.add_argument('--max-texture', type=int, default=512)
    parser.add_argument('--interaction-clip', action='append', help='Validated one-shot clip; repeat for additional interactions')
    args = parser.parse_args()
    export(args.source, args.destination, args.max_texture, args.interaction_clip)
