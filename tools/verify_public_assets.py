from pathlib import Path
import sys,hashlib,json,ast
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from cosfolio.catalog import TEMPLATES
def main():
    for source in (ROOT/'cosfolio').glob('*.py'):ast.parse(source.read_text(encoding='utf-8'))
    for key,config in TEMPLATES.items():
        assert (ROOT/'resources/templates/previews'/f'{key}.jpg').is_file(),key
        for field in ('plate','reference'):
            if config.get(field):assert (ROOT/'resources/templates'/config[field]).is_file(),(key,field)
    records=json.loads((ROOT/'resources/templates/v04/index.json').read_text(encoding='utf-8'))
    for record in records:
        ref=ROOT/'resources/templates'/TEMPLATES[record['template']]['reference']
        assert hashlib.sha256(ref.read_bytes()).hexdigest()==record['reference_sha256']
    for name in ('LICENSE','NOTICE','LICENSE-SCOPE.md','ASSET_RIGHTS.md','THIRD_PARTY_NOTICES.md','licenses/LGPL-3.0.txt','licenses/GPL-3.0.txt'):
        assert (ROOT/name).is_file(),name
    assert 'PolyForm Noncommercial' in (ROOT/'LICENSE').read_text(encoding='utf-8')
    assert 'Haze' in (ROOT/'ASSET_RIGHTS.md').read_text(encoding='utf-8')
    assert len(TEMPLATES)==22
    print(json.dumps({'templates':len(TEMPLATES),'paired_references':len(records),'licenses_present':True,'passed':True}))
if __name__=='__main__':main()
