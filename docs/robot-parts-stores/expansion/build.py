"""Normalize the five research batches into uniform company and product exports."""
import csv,html,json
from pathlib import Path
ROOT=Path(__file__).resolve().parent
companies=[c for p in sorted((ROOT/'research').glob('*.json')) for c in json.loads(p.read_text())]
companies.sort(key=lambda c:(c['china_based'],c['company_name'].casefold()))
assert len(companies)==20 and len({c['company_id'] for c in companies})==20
FIELDS=['company_id','company_name','country','china_based','company_url','activity_evidence','activity_url','product_id','name','product_url','primary_role','catalog_group','part_type','assembly_level','purchased_scope','price','currency','availability','cad_status','cad_url','cad_formats','image_url','notes','evidence_urls','researched_at','browser_ready']
prepared=json.loads((ROOT.parents[1]/'robot-builder/public/catalog.json').read_text())
ready={p['id'] for p in prepared if all((ROOT.parents[1]/'robot-builder/public'/p[key]).is_file() for key in ['model','thumbnail'])}
rows=[]
def write(path,values,fields):
 path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(values)
for c in companies:
 current=[]
 for p in c['products']:
  assert p['evidence_urls'] and p['product_url'].startswith('https://')
  assert p['primary_role'] in ['arms','torso','head','legs','whole_robot']
  r={k:c.get(k,p.get(k,'')) for k in FIELDS}
  r['catalog_group']='whole_robot' if p['primary_role']=='whole_robot' else 'body'
  r['browser_ready']=p['product_id'] in ready
  r['cad_formats']='|'.join(sorted({x.upper() for x in p.get('cad_formats',[])}))
  r['evidence_urls']='|'.join(p['evidence_urls'])
  if r['price'] is None:r['price']=''
  current.append(r)
 rows+=current
 write(ROOT/'by-company'/f"{c['company_id']}.csv",current,FIELDS)
write(ROOT/'all_parts.csv',rows,FIELDS)
summary=[{k:c[k] for k in ['company_id','company_name','country','china_based','company_url','activity_evidence','activity_url']}|{'product_count':len(c['products'])} for c in companies]
write(ROOT/'companies.csv',summary,list(summary[0]))
(ROOT/'schema.json').write_text(json.dumps({'version':1,'encoding':'UTF-8','delimiter':',','list_separator':'|','columns':FIELDS,'missing_price':'blank; never zero; currencies not converted','ordering':'Non-China companies alphabetically, then China-based companies alphabetically; no popularity ranking','cad_status':'Source availability only, not a claim of a downloaded or browser-ready model','browser_ready':'True only if a matching product ID is in the prepared builder catalog','scope':'Selected products from 20 companies; not full inventories'},indent=2)+'\n')
counts={role:sum(p['primary_role']==role for p in rows) for role in sorted({p['primary_role'] for p in rows})}
readme=f'''# Complete robot sections — 20-company research\n\nResearch date: 2026-09-29. Five research agents; three simultaneous agents allowed\nby this workspace, followed by two overlapping tasks. Research began at 22:59:17\nUTC with a deadline of 23:09:17 UTC. See `research-run.json` for completion time.\n\n{len(rows)} selected products across 20 companies. Roles: {counts}.\nChina-based companies appear last, as requested. Country is company location,\nnot a claim about every product's manufacturing origin. Recent official activity\nis recorded for each company; this is a relevance shortlist, not a popularity ranking.\n\n- [All products](all_parts.csv) — consistent schema across all company files.\n- [Companies and activity evidence](companies.csv)\n- [Schema and field semantics](schema.json)\n- [Existing eight-store database](../classified/README.md) — includes small components.\n\nAn **arm** includes the structural links and joints. A **torso** is a body frame\nor shell; an empty shell is explicitly labeled. **Whole robots** are references\nand complete-system purchases, not separately orderable torsos. Bare motors,\nservos, electronics, sensors and wheels are component categories in the original\ndatabase. Prices retain their currencies; blank means no verified public price.\nCAD links may be source repositories or gated downloads. A source link does not\nmean that a complete assembled mesh is ready; check `browser_ready` separately.\n\n| Company | Location | Products | CSV |\n|---|---|---:|---|\n'''
for c in companies:readme+=f"| [{c['company_name']}]({c['company_url']}) | {c['country']} | {len(c['products'])} | [{c['company_id']}](by-company/{c['company_id']}.csv) |\n"
readme+='\nProduct rows include official product, availability, CAD and purchasing-scope evidence.\nNo compatibility between companies is implied.\n'
(ROOT/'README.md').write_text(readme)
# A read-only source browser accessible beside the 3D workshop.
e=html.escape
page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Robot sections — 20 companies</title><style>body{font:16px system-ui;background:#f4f5ef;color:#25332a;max-width:1100px;margin:auto;padding:28px}a{color:#476221}article{background:white;padding:20px;margin:16px 0;border-radius:16px}li{margin:18px 0}small{display:block;color:#52624f;margin:6px 0}h1{font-size:32px}button,select{padding:12px;font:inherit}a:focus,select:focus{outline:3px solid #78944c}</style><a href="./">← Robot workshop</a><h1>Robot sections from 20 companies</h1><p>Complete arms, structural bodies, and whole robot references. China-based companies appear last. Only prepared models are selectable in the 3D workshop.</p><label>Show <select id="role"><option value="">All products</option><option value="arms">Arm assemblies</option><option value="torso">Body frames and shells</option><option value="whole_robot">Whole robot references</option></select></label>'''
for c in companies:
 page+=f'<article><h2><a href="{e(c["company_url"])}">{e(c["company_name"])}</a> · {e(c["country"])}</h2><small>{e(c["activity_evidence"])} <a href="{e(c["activity_url"])}">Activity source</a></small><ul>'
 for p in c['products']:
  price=f'{p["currency"]} {p["price"]:,.2f}' if isinstance(p['price'],(int,float)) else 'Price: inquire / not verified'
  page+=f'<li data-role="{e(p["primary_role"])}"><strong><a href="{e(p["product_url"])}">{e(p["name"])}</a></strong> · {e(price)}<small>{e(p["primary_role"].replace("_"," "))} · {e(p["availability"])}</small>{e(p["purchased_scope"])}'
  if p.get('cad_url'):page+=f' <a href="{e(p["cad_url"])}">Model source</a>'
  page+=f'<small>{e(p["notes"])}</small></li>'
 page+='</ul></article>'
page+='''<script>document.querySelector('#role').onchange=e=>{for(const li of document.querySelectorAll('li'))li.hidden=!!e.target.value&&li.dataset.role!==e.target.value;for(const a of document.querySelectorAll('article'))a.hidden=![...a.querySelectorAll('li')].some(li=>!li.hidden)}</script></html>'''
(ROOT.parents[1]/'robot-builder/public/research.html').write_text(page)
print(json.dumps({'companies':len(companies),'products':len(rows),'roles':counts,'china_companies':sum(c['china_based'] for c in companies)}))
