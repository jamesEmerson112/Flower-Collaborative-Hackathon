"""Export the exact demo palette, with model paths and source checksums."""
import csv,json,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
CAD=ROOT.parent/'robot-parts-stores/cad'
parts=json.loads((ROOT/'public/catalog.json').read_text())
fields=['id','name','body_role','supplier','model_path','thumbnail_path','source_path','source_url','source_sha256','model_sha256','model_bytes','model_kind','notes']
rows=[]
for p in parts:
 assert p['catalogGroup']=='body'
 model=ROOT/'public'/p['model'];thumb=ROOT/'public'/p['thumbnail'];source=CAD/p['source']
 assert model.is_file() and thumb.is_file() and source.is_file(),p['id']
 rows.append(dict(id=p['id'],name=p['name'],body_role=p['roles'][0],supplier=p['supplier'],model_path=p['model'],thumbnail_path=p['thumbnail'],source_path=p['source'],source_url=p['sourceUrl'],source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),model_sha256=hashlib.sha256(model.read_bytes()).hexdigest(),model_bytes=model.stat().st_size,model_kind=p['modelKind'],notes=p['note']))
with (ROOT/'public/body-parts.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
(ROOT/'public/body-models.json').write_text(json.dumps(rows,indent=2)+'\n')
print(len(rows),'prepared body models;',round(sum(r['model_bytes'] for r in rows)/1e6,2),'MB')
