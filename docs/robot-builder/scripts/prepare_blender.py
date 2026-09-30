"""Run with Blender --background --factory-startup --python scripts/prepare_blender.py.
Normalizes real CAD meshes for a deliberately non-dimensional concept builder.
"""
import bpy,bmesh,json,math,hashlib,sys
from pathlib import Path
from mathutils import Vector,Matrix
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from frame_preview import create_frame
CAD=ROOT.parent/'robot-parts-stores/cad'
parts=json.loads((ROOT/'public/catalog.json').read_text())
for folder in ['models','thumbnails']:(ROOT/'public'/folder).mkdir(parents=True,exist_ok=True)

def material(name,color,metallic=.18):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
 bsdf=m.node_tree.nodes.get('Principled BSDF');bsdf.inputs['Base Color'].default_value=(*color,1);bsdf.inputs['Metallic'].default_value=metallic;bsdf.inputs['Roughness'].default_value=.48
 return m

def bounds(objects):
 coords=[o.matrix_world@Vector(c) for o in objects if o.type=='MESH' for c in o.bound_box]
 low=Vector(tuple(min(v[i] for v in coords) for i in range(3)));high=Vector(tuple(max(v[i] for v in coords) for i in range(3)))
 return low,high

def scene_setup(center=Vector((0,0,0)),scale=1.55):
 scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=12;scene.cycles.use_denoising=True
 scene.render.resolution_x=320;scene.render.resolution_y=256;scene.render.resolution_percentage=100;scene.render.film_transparent=True
 if scene.world is None:scene.world=bpy.data.worlds.new('Studio world')
 scene.world.color=(.65,.65,.65)
 scene.view_settings.view_transform='AgX'
 bpy.ops.object.camera_add(location=center+Vector((1.3,-2.0,1.05)))
 cam=bpy.context.object;cam.rotation_euler=(center-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=scale;scene.camera=cam
 for pos,power,size in [((2,-3,4),300,4),((-3,-1,2),180,3),((0,3,3),220,3)]:
  bpy.ops.object.light_add(type='AREA',location=center+Vector(pos));o=bpy.context.object;o.data.energy=power;o.data.shape='DISK';o.data.size=size;o.rotation_euler=(center-o.location).to_track_quat('-Z','Y').to_euler()
 return scene

report_path=ROOT/'public/model-provenance.json'
records={r['id']:r for r in json.loads(report_path.read_text())} if report_path.exists() else {}
report=[]
for part in parts:
 output=ROOT/'public'/part['model'];thumb=ROOT/'public'/part['thumbnail']
 pipeline_version=5 if 'sourceMaxZ' in part else 4 if part.get('keepSourceAxes') else 3 if part.get('modelKind')=='approximate_preview' else 2
 if output.exists() and thumb.exists() and records.get(part['id'],{}).get('pipeline_version')==pipeline_version:
  print('Already prepared',part['id'],flush=True);continue
 source=CAD/part['source'];intermediate=ROOT/'blender/intermediate'/(part['id']+'.json')
 if source.suffix.lower() in {'.step','.stp'} and not intermediate.exists():
  print('Waiting for STEP conversion',part['id'],flush=True);continue
 bpy.ops.wm.read_factory_settings(use_empty=True)
 if part.get('modelKind')=='approximate_preview':create_frame()
 elif source.suffix.lower()=='.stl':bpy.ops.wm.stl_import(filepath=str(source))
 else:
  converted=json.loads(intermediate.read_text())
  colors={}
  def cad_material(color):
   key=tuple(color)
   if key not in colors:
    linear=tuple(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in color)
    colors[key]=material('CAD color '+str(key),linear)
   return colors[key]
  for data in converted['meshes']:
   positions=data['attributes']['position']['array'];indices=data['index']['array']
   mesh=bpy.data.meshes.new(data['name']);mesh.from_pydata([positions[i:i+3] for i in range(0,len(positions),3)],[],[indices[i:i+3] for i in range(0,len(indices),3)]);mesh.update()
   obj=bpy.data.objects.new(data['name'],mesh);bpy.context.collection.objects.link(obj)
   basecolor=data.get('color') or [.55,.59,.61];mesh.materials.append(cad_material(basecolor))
   for face in data.get('brep_faces',[]):
    if face.get('color'):
     mat=cad_material(face['color']);slot=mesh.materials.find(mat.name)
     if slot<0:mesh.materials.append(mat);slot=len(mesh.materials)-1
     for polygon in mesh.polygons[face['first']:face['last']+1]:polygon.material_index=slot
 objects=list(bpy.context.scene.objects);meshes=[o for o in objects if o.type=='MESH']
 if not meshes:raise RuntimeError('No mesh: '+part['id'])
 # Bake parent transforms to simplify and normalize imported CAD consistently.
 for obj in meshes:
  world=obj.matrix_world.copy();obj.parent=None;obj.matrix_world=world
 for obj in objects:
  if obj.type!='MESH':bpy.data.objects.remove(obj,do_unlink=True)
 if 'sourceMaxZ' in part:
  for obj in meshes:
   bm=bmesh.new();bm.from_mesh(obj.data)
   above=[v for v in bm.verts if (obj.matrix_world@v.co).z>part['sourceMaxZ']]
   if above:bmesh.ops.delete(bm,geom=above,context='VERTS')
   bm.to_mesh(obj.data);bm.free();obj.data.update()
  bpy.context.view_layer.update()
 low,high=bounds(meshes);original=list(high-low)
 # Largest axis becomes X, second-largest becomes Z (glTF Y), depth becomes Y.
 order=sorted(range(3),key=lambda i:original[i],reverse=True)
 rows=[]
 for axis in [order[0],order[2],order[1]]:
  row=[0,0,0];row[axis]=1;rows.append(row)
 orient=Matrix.Rotation(-math.pi/2,3,'Z') if part.get('keepSourceAxes') else Matrix(rows)
 if orient.determinant()<0:orient[1]*=-1
 for obj in meshes:obj.matrix_world=orient.to_4x4()@obj.matrix_world
 bpy.context.view_layer.update();low,high=bounds(meshes);center=(low+high)/2;factor=1/max(high-low)
 root=bpy.data.objects.new(part['id'],None);bpy.context.collection.objects.link(root)
 root['catalog_product_id']=part['id'];root['supplier']=part['supplier'];root['source_url']=part['sourceUrl'];root['concept_scale']=True
 root['model_kind']=part.get('modelKind','supplier_cad')
 srgb=tuple(int(part['color'][i:i+2],16)/255 for i in (1,3,5))
 color=tuple(v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4 for v in srgb)
 fallback=material(part['name'],color)
 total=sum(len(o.data.polygons) for o in meshes)
 for obj in meshes:
  obj.matrix_world=Matrix.Scale(factor,4)@Matrix.Translation(-center)@obj.matrix_world
  if not obj.data.materials or not any(obj.data.materials):
   obj.data.materials.clear();obj.data.materials.append(fallback)
  for mat in obj.data.materials:
   if mat and mat.use_nodes:
    shader=mat.node_tree.nodes.get('Principled BSDF')
    if shader:shader.inputs['Roughness'].default_value=.5
  bpy.ops.object.select_all(action='DESELECT')
  bpy.context.view_layer.objects.active=obj;obj.select_set(True)
  bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
  if total>75000 and len(obj.data.polygons)>500:
   mod=obj.modifiers.new('Browser mesh budget','DECIMATE');mod.ratio=max(.02,55000/total);bpy.ops.object.modifier_apply(modifier=mod.name)
  obj.data.validate();obj.data.update()
  bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40),keep_sharp_edges=True)
  obj.parent=root;obj.select_set(False)
 bpy.context.view_layer.update()
 bpy.ops.object.select_all(action='DESELECT');root.select_set(True)
 for obj in meshes:obj.select_set(True)
 bpy.ops.export_scene.gltf(filepath=str(output),export_format='GLB',use_selection=True,export_extras=True,export_yup=True)
 scene=scene_setup();scene.render.filepath=str(thumb);bpy.ops.render.render(write_still=True)
 count=sum(len(o.data.polygons) for o in meshes)
 report.append(dict(id=part['id'],pipeline_version=pipeline_version,model_kind=part.get('modelKind','supplier_cad'),source=part['source'] or part['sourceUrl'],source_sha256=hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else None,original_bounds=original,source_filter={'max_z':part['sourceMaxZ']} if 'sourceMaxZ' in part else None,normalization='longest side = 1; centered; concept units, not manufacturing scale',polygons=count,glb_bytes=output.stat().st_size))
 records[part['id']]=report[-1]
 report_path.write_text(json.dumps(list(records.values()),indent=2)+'\n')
 print('PREPARED',part['id'],count,output.stat().st_size,flush=True)
records.update({r['id']:r for r in report})
report_path.write_text(json.dumps(list(records.values()),indent=2)+'\n')
