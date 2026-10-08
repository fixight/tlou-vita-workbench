import json

with open(r'sarah_test\sarah\sarah.gltf', 'r') as f:
    g = json.load(f)

print('Validating glTF structure:')
print(f'  Meshes: {len(g.get("meshes", []))}')
print(f'  Nodes: {len(g.get("nodes", []))}')
print(f'  Skins: {len(g.get("skins", []))}')
print(f'  Animations: {len(g.get("animations", []))}')
print(f'  Buffers: {len(g.get("buffers", []))}')

for anim in g.get('animations', [])[:5]:
    print(f'  Anim "{anim["name"]}": {len(anim["channels"])} channels, {len(anim["samplers"])} samplers')
