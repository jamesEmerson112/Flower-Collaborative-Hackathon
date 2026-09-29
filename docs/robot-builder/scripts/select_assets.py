"""Map the visual demo palette to the existing supplier catalog and CAD provenance."""
import json,csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CAD=ROOT.parent/'robot-parts-stores/cad'
source=json.loads((CAD.parent/'stores.json').read_text())
manifest=json.loads((CAD/'manifest.json').read_text())
items={i['id']:(s,i) for s in source['stores'] for i in s['items']}
with (CAD.parent/'classified/all_parts.csv').open(newline='') as f:
 classifications={r['product_id']:r for r in csv.DictReader(f)}
# id, short name, initial slots, source path selector, display color
choices=[
 ('sparkfun-rob-13301','Shadow chassis',['torso'],None,'#646b61'),
 ('pololu-3500','Romi chassis',[],'romi-chassis-kit.step','#dae0bc'),
 ('waveshare-wave-rover','WAVE ROVER',['leftLeg','rightLeg'],'WAVE ROVER_MODEL_STL.stl','#a8bac5'),
 ('robotis-903-0257-000','OpenCR controller',[],'OpenCR_REVH.stl','#587c65'),
 ('adafruit-4754','BNO085 IMU',[],'4754 BNO085 STEMMA QT.stl','#657e5b'),
 ('pololu-3415','Time-of-flight sensor',['head'],'vl53l0x-vl53l1x-vl53l3cx-vl53l4cd-carrier-model.step','#576d9a'),
 ('robotis-902-0135-000','DYNAMIXEL XL430',['leftArm'],'XL430_new(stp).stp','#647184'),
 ('servocity-2002-0180-0002','Proton servo',['rightArm'],'2002-0180-0002.step','#cfab66'),
 ('waveshare-21568','SC15 bus servo',[],'SC15_not-bracket.stp','#647989'),
 ('sparkfun-rob-09238','NEMA 17 stepper',[],'9238.stl','#8b9399'),
 ('adafruit-3777','TT gearbox motor',[],'3777 TT Motor.stl','#d6af44'),
 ('sparkfun-rob-09065','Micro servo',[],'9065.STL','#739ba5'),
 ('pololu-3036','Micro gearmotor',[],'mmgm-cb.step','#b19a6c'),
 ('seeed-114993667','SO-101 arm',[],'SO101 Assembly.stl','#cfb080'),
]
palette=[]
for ident,label,default,filename,color in choices:
 classification=classifications[ident]
 roles=[classification['primary_role']]
 store,item=items[ident]
 assets=[a for a in manifest['assets'] if a['product_id']==ident]
 candidates=[(a,a['path']) for a in assets]+[(a,f['path']) for a in assets for f in a['extracted_files']]
 if filename:
  a,path=next((a,p) for a,p in candidates if p.endswith('/'+filename))
  assert (CAD/path).exists(),path
 else:
  a,path={'source_url':item['url']},''
 note={
  'sparkfun-rob-13301':'Approximate frame preview based on the listed chassis envelope; no supplier CAD was found. Mounting details are illustrative.',
  'seeed-114993667':'SO-101 assembly includes printed structure, which is not supplied in the listed servo kit.',
  'pololu-3500':'The vendor CAD includes a second caster; the listed chassis kit includes one caster.',
 }.get(ident,'')
 palette.append(dict(id=ident,name=label,fullName=item['name'],supplier={'adafruit':'Adafruit','sparkfun':'SparkFun','pololu':'Pololu','servocity':'ServoCity','seeed':'Seeed Studio','robotis':'ROBOTIS','waveshare':'Waveshare'}[store['id']],storeId=store['id'],price=item['price'],currency=item['currency'],sku=item['sku'],productUrl=item['url'],roles=roles,secondaryRoles=classification['secondary_roles'].split('|') if classification['secondary_roles'] else [],partType=classification['part_type'],assemblyLevel=classification['assembly_level'],classificationReason=classification['classification_reason'],modelKind='supplier_cad' if filename else 'approximate_preview',defaultSlots=default,source=path,sourceUrl=a['source_url'],color=color,note=note,model=f'models/{ident}.glb',thumbnail=f'thumbnails/{ident}.png'))
for part in palette:
 if part['id']=='waveshare-wave-rover':part['baseRotation']=[1.5707963267948966,0,0]
 if part['id']=='pololu-3415':part['slotRotations']={'head':[0,3.141592653589793,0]}
(ROOT/'public/catalog.json').write_text(json.dumps(palette,indent=2)+'\n')
print('Selected',len(palette),'models from',len({p['supplier'] for p in palette}),'suppliers')
