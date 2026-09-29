"""Create the browser's starter combination as an editable Blender scene."""
import bpy, json, math
from pathlib import Path
from mathutils import Vector, Matrix, Euler

ROOT = Path(__file__).resolve().parents[1]
plan = json.loads((ROOT/'blender/intermediate/starter-plan.json').read_text())
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
robot = bpy.data.objects.new('Mixed supplier robot — visual concept', None)
bpy.context.collection.objects.link(robot)
robot['concept_only'] = True
robot['compatibility_verified'] = False
robot['dimensions'] = 'Resized for visual composition; use original CAD for physical dimensions.'
for pose in plan:
    slot,part = pose['slot'],pose['part']
    before = set(scene.objects)
    bpy.ops.import_scene.gltf(filepath=str(ROOT/'public'/part['model']))
    imported = set(scene.objects) - before
    roots = [o for o in imported if o.parent not in imported]
    group = bpy.data.objects.new(f"{slot} · {part['name']}", None)
    bpy.context.collection.objects.link(group)
    for obj in roots: obj.parent = group
    basis=Matrix(((1,0,0),(0,0,-1),(0,1,0)))
    group.rotation_euler=(basis@Euler(pose['rotation'],'XYZ').to_matrix()@basis.inverted()).to_euler()
    bpy.context.view_layer.update()
    vertices = [o.matrix_world @ Vector(c) for o in imported if o.type == 'MESH' for c in o.bound_box]
    low = Vector(tuple(min(p[i] for p in vertices) for i in range(3)))
    high = Vector(tuple(max(p[i] for p in vertices) for i in range(3)))
    center, dimensions = (low+high)/2, high-low
    # Use a separate wrapper to scale in Blender's world axes after rotation.
    wrapper = bpy.data.objects.new(slot+' placement', None)
    bpy.context.collection.objects.link(wrapper)
    group.location = -center
    group.parent = wrapper
    size = pose['size']
    wrapper.scale = (size[0]/dimensions.x, size[2]/dimensions.y, size[1]/dimensions.z)
    x,y,z = pose['position']; wrapper.location = (x,-z,y)
    wrapper.parent = robot
    for key,value in {'slot':slot,'slots':pose['slots'],'product_id':part['id'],'supplier':part['supplier'],'source_url':part['sourceUrl'],'product_url':part['productUrl'],'note':part['note'],'model_kind':part['modelKind']}.items(): wrapper[key]=value

def material(name, color, roughness=.65):
    mat=bpy.data.materials.new(name);mat.diffuse_color=(*color,1);mat.use_nodes=True
    bsdf=mat.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=(*color,1);bsdf.inputs['Roughness'].default_value=roughness
    return mat

bpy.ops.mesh.primitive_cylinder_add(vertices=96,radius=1.35,depth=.06,location=(0,0,-.045))
plinth=bpy.context.object;plinth.name='Display plinth — preview only';plinth.data.materials.append(material('Soft sage',(.68,.73,.57)))
bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.08))
floor=bpy.context.object;floor.name='Studio floor — preview only';floor.data.materials.append(material('Warm background',(.83,.86,.75)))
target=Vector((0,0,1.25))
bpy.ops.object.camera_add(location=(3.6,-6.2,2.8))
camera=bpy.context.object;camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.type='ORTHO';camera.data.ortho_scale=3.7;scene.camera=camera
for location,power,size in [((3,-4,6),650,5),((-4,-2,3),380,4),((0,4,5),700,3)]:
    bpy.ops.object.light_add(type='AREA',location=location)
    light=bpy.context.object;light.data.energy=power;light.data.shape='DISK';light.data.size=size;light.rotation_euler=(target-light.location).to_track_quat('-Z','Y').to_euler()
scene.world=bpy.data.worlds.new('Studio ambient');scene.world.color=(.5,.5,.5)
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=32;scene.cycles.use_denoising=True
scene.render.resolution_x=1000;scene.render.resolution_y=1000;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX'
bpy.ops.object.select_all(action='DESELECT');robot.select_set(True);bpy.context.view_layer.objects.active=robot
for screen in bpy.data.screens:
    for area in screen.areas:
        if area.type=='VIEW_3D':
            area.spaces.active.region_3d.view_distance=5
            area.spaces.active.region_3d.view_location=target
            area.spaces.active.region_3d.view_rotation=camera.rotation_euler.to_quaternion()
            area.spaces.active.shading.type='MATERIAL'
            area.spaces.active.overlay.show_floor=False
output=ROOT/'blender';output.mkdir(exist_ok=True)
scene.render.filepath=str(output/'mixed-supplier-robot-v2.png')
bpy.ops.wm.save_as_mainfile(filepath=str(output/'mixed-supplier-robot-v2.blend'))
bpy.ops.render.render(write_still=True)
print('Saved corrected starter robot with one shared mobile base.',flush=True)
