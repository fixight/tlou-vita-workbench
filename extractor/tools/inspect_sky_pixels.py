import bpy
from pathlib import Path
folder=Path(r'D:\TLOUPS4\AustinStaticLighting\sky_textures')
for name in ('sky-hometown-night-color-3','sky-hometown-moon','sky-hometown-moon-trans'):
 i=bpy.data.images.load(str(folder/(name+'.png')),check_existing=False)
 print('IMAGE',name,i.colorspace_settings.name,i.channels,i.is_float,i.alpha_mode, 'first',list(i.pixels[:4]),flush=True)
 i.colorspace_settings.name='Non-Color'
 print('NONCOLOR',list(i.pixels[:4]), 'middle',list(i.pixels[(i.size[1]//2*i.size[0]+i.size[0]//2)*4:][:4]),flush=True)
