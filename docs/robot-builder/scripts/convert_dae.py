"""Convert official COLLADA triangle meshes, transforms and colors for Blender.
Ignores source cameras, lights and annotation lines. Does not load external URLs.
"""
import json,xml.etree.ElementTree as ET
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CAD=ROOT.parent/'robot-parts-stores/cad'
NS={'c':'http://www.collada.org/2005/11/COLLADASchema'}
IDENTITY=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1]
def mul(a,b):return [sum(a[i*4+k]*b[k*4+j] for k in range(4)) for i in range(4) for j in range(4)]
def transform(m,p):return [sum(m[i*4+j]*p[j] for j in range(3))+m[i*4+3] for i in range(3)]
def convert(source):
 root=ET.parse(source).getroot()
 effects={}
 for effect in root.findall('.//c:library_effects/c:effect',NS):
  color=effect.find('.//c:diffuse/c:color',NS)
  effects[effect.attrib['id']]=list(map(float,color.text.split()))[:3] if color is not None else [.6,.6,.6]
 materials={m.attrib['id']:effects.get(m.find('c:instance_effect',NS).attrib['url'][1:],[.6,.6,.6]) for m in root.findall('.//c:library_materials/c:material',NS)}
 geometries={g.attrib['id']:g.find('c:mesh',NS) for g in root.findall('.//c:library_geometries/c:geometry',NS)}
 output=[]
 def walk(node,parent):
  local=node.find('c:matrix',NS)
  matrix=mul(parent,list(map(float,local.text.split())) if local is not None else IDENTITY)
  for inst in node.findall('c:instance_geometry',NS):
   mesh=geometries[inst.attrib['url'][1:]]
   binding={b.attrib['symbol']:b.attrib['target'][1:] for b in inst.findall('.//c:instance_material',NS)}
   sources={s.attrib['id']:s for s in mesh.findall('c:source',NS)}
   vertices={v.attrib['id']:v for v in mesh.findall('c:vertices',NS)}
   for tri in mesh.findall('c:triangles',NS):
    inputs=tri.findall('c:input',NS);stride=1+max(int(i.attrib.get('offset',0)) for i in inputs)
    vertex=next(i for i in inputs if i.attrib['semantic']=='VERTEX');offset=int(vertex.attrib.get('offset',0))
    pos=next(i for i in vertices[vertex.attrib['source'][1:]].findall('c:input',NS) if i.attrib['semantic']=='POSITION')
    src=sources[pos.attrib['source'][1:]];values=list(map(float,src.find('c:float_array',NS).text.split()));access=src.find('.//c:accessor',NS);step=int(access.attrib.get('stride',3));start=int(access.attrib.get('offset',0));count=int(access.attrib['count'])
    coords=[transform(matrix,values[start+i*step:start+i*step+3]) for i in range(count)]
    ids=list(map(int,tri.find('c:p',NS).text.split()))[offset::stride]
    assert len(ids)==3*int(tri.attrib['count']) and all(0<=i<count for i in ids)
    output.append({'name':node.attrib.get('name','body')+'_'+str(len(output)),'attributes':{'position':{'array':[v for p in coords for v in p]}},'index':{'array':ids},'color':materials.get(binding.get(tri.attrib.get('material','')),[.6,.6,.6])})
  for child in node.findall('c:node',NS):walk(child,matrix)
 scene_ref=root.find('c:scene/c:instance_visual_scene',NS).attrib['url'][1:]
 scene=next(s for s in root.findall('.//c:visual_scene',NS) if s.attrib['id']==scene_ref)
 for node in scene.findall('c:node',NS):walk(node,IDENTITY)
 assert output
 return {'success':True,'meshes':output}
if __name__=='__main__':
 for part in json.loads((ROOT/'public/catalog.json').read_text()):
  if not part['source'].lower().endswith('.dae'):continue
  source=CAD/part['source'];dest=ROOT/'blender/intermediate'/(part['id']+'.json')
  dest.parent.mkdir(parents=True,exist_ok=True);result=convert(source);dest.write_text(json.dumps(result));print(part['id'],len(result['meshes']),'meshes')
