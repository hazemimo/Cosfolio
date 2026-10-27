"""Local user-template storage and portable project embedding. No AI downloads."""
from pathlib import Path
import hashlib
import io
import json
import math
import re
import shutil
import sys
import uuid
from PIL import Image

ROOT=Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).resolve().parents[1]
LIBRARY=ROOT/'workspace'/'templates'
MAX_TEMPLATE_SLOTS=5


def validate_spec(spec):
    if not isinstance(spec,dict) or spec.get('format')!='cosfolio-template' or spec.get('version')!=1:
        raise ValueError('模板格式不受支持')
    if not re.fullmatch(r'user_[a-f0-9]{16,32}',str(spec.get('key',''))):raise ValueError('模板编号不正确')
    if not isinstance(spec.get('name'),str) or not 1<=len(spec['name'])<=80:raise ValueError('请填写模板名称')
    size=spec.get('size')
    if not isinstance(size,list) or len(size)!=2 or any(type(n)!=int or not 1<=n<=3072 for n in size):
        raise ValueError('试用模板工作底图的最长边不超过 3072 像素')
    slots=spec.get('slots')
    if not isinstance(slots,list) or not 1<=len(slots)<=MAX_TEMPLATE_SLOTS:raise ValueError('模板支持 1～5 个照片位置')
    for rect in slots:
        if not isinstance(rect,(list,tuple)) or len(rect)!=4 or any(type(v) not in (int,float) or not math.isfinite(v) for v in rect):
            raise ValueError('模板画框坐标不正确')
        x,y,w,h=rect
        if min(x,y)<0 or min(w,h)<1 or x+w>size[0]+.01 or y+h>size[1]+.01:raise ValueError('模板画框超出底图')
    if spec.get('plate')!='plate.webp' or spec.get('mask')!='removal.png' or spec.get('preview')!='preview.jpg':
        raise ValueError('模板文件名不正确')
    reference=spec.get('reference','')
    if not re.fullmatch(r'original\.(jpg|jpeg|png|webp|tif|tiff)',reference):raise ValueError('原页文件名不正确')
    return spec


def register(spec,folder,registry=None):
    validate_spec(spec)
    if registry is None:
        from .catalog import TEMPLATES
        registry=TEMPLATES
    folder=Path(folder)
    for name in ('plate','reference','mask','preview'):
        if not (folder/spec[name]).is_file():raise FileNotFoundError('自建模板缺少文件：'+spec[name])
    with Image.open(folder/spec['plate']) as plate:
        if plate.size!=tuple(spec['size']):raise ValueError('模板底图尺寸不匹配')
    w,h=spec['size']
    config={'name':'自建 · '+spec['name'],'size':tuple(spec['size']),
            'slots':[tuple(rect) for rect in spec['slots']],
            'labels':[f'位置 {i+1} · 自建画框' for i in range(len(spec['slots']))],
            'note':'自建模板 · 原页文字保留。可在“分层”页继续校准画框和前景。\n源页：'+str(spec.get('source_name',''))[:150],
            'plate':str((folder/spec['plate']).resolve()),'reference':str((folder/spec['reference']).resolve()),
            'preview':str((folder/spec['preview']).resolve()),'custom':True,'store':str(folder.resolve()),'fit':'height',
            'text_fields':[{'field':'title','rect':(w*.03,h*.945,w*.94,h*.035),'size':max(10,w*.025),'color':'#2b6098','bold':True}]}
    registry[spec['key']]=config
    return spec['key']


def load_library(registry=None):
    errors=[]
    if LIBRARY.exists():
        for path in sorted(LIBRARY.glob('user_*/template.json')):
            try:
                if path.stat().st_size>128*1024:raise ValueError('模板说明过大')
                register(json.loads(path.read_text(encoding='utf-8')),path.parent,registry)
            except (OSError,ValueError,TypeError,KeyError) as exc:errors.append((str(path),str(exc)))
    return errors


def save_template(name,source,plate,mask,slots,recipe=None):
    name=name.strip()
    key='user_'+uuid.uuid4().hex[:16]
    suffix=Path(source).suffix.lower()
    if suffix not in ('.jpg','.jpeg','.png','.webp','.tif','.tiff'):raise ValueError('请选择支持的图片文件')
    spec={'format':'cosfolio-template','version':1,'key':key,'name':name,'size':list(plate.size),
          'slots':[list(rect) for rect in slots],'plate':'plate.webp','reference':'original'+suffix,
          'mask':'removal.png','preview':'preview.jpg','source_name':Path(source).name,'recipe':recipe or {}}
    validate_spec(spec)
    LIBRARY.mkdir(parents=True,exist_ok=True)
    stage=LIBRARY/('.creating-'+uuid.uuid4().hex)
    stage.mkdir()
    try:
        plate.convert('RGB').save(stage/spec['plate'],format='WEBP',lossless=True,method=4)
        mask.convert('L').save(stage/spec['mask'])
        shutil.copy2(source,stage/spec['reference'])
        preview=plate.copy();preview.thumbnail((450,600));preview.convert('RGB').save(stage/spec['preview'],quality=86)
        (stage/'template.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
        dest=LIBRARY/key;stage.replace(dest)
        return register(spec,dest)
    finally:
        if stage.exists() and stage.parent.resolve()==LIBRARY.resolve() and stage.name.startswith('.creating-'):
            shutil.rmtree(stage)


def embed_templates(archive,keys):
    from .catalog import TEMPLATES
    specs=[]
    for key in sorted(set(keys)):
        config=TEMPLATES[key]
        if not config.get('custom'):continue
        folder=Path(config['store'])
        spec=validate_spec(json.loads((folder/'template.json').read_text(encoding='utf-8')))
        members={}
        for field in ('plate','reference','mask','preview'):
            inner=f'templates/{key}/{spec[field]}'
            archive.write(folder/spec[field],inner)
            members[field]=inner
        specs.append({'spec':spec,'members':members})
    if specs:archive.writestr('templates.json',json.dumps(specs,ensure_ascii=False))


def restore_templates(archive):
    if 'templates.json' not in archive.namelist():return {}
    if archive.getinfo('templates.json').file_size>1024**2:raise ValueError('工程内模板说明过大')
    records=json.loads(archive.read('templates.json'))
    if not isinstance(records,list) or len(records)>40:raise ValueError('工程内自建模板数量不正确')
    mapping={}
    for record in records:
        spec=validate_spec(record['spec'])
        old=spec['key'];blobs={}
        for field in ('plate','reference','mask','preview'):
            member=record['members'][field]
            if member!=f'templates/{old}/{spec[field]}':raise ValueError('工程内模板路径不正确')
            if archive.getinfo(member).file_size>128*1024**2:raise ValueError('工程内模板图片过大')
            blobs[field]=archive.read(member)
            with Image.open(io.BytesIO(blobs[field])) as image:
                if image.width*image.height>110_000_000:raise ValueError('工程内模板图片尺寸过大')
                if field in ('plate','mask') and image.size!=tuple(spec['size']):raise ValueError('模板蒙版或底图尺寸不匹配')
                image.verify()
        folder=LIBRARY/old
        if folder.exists():
            try:same=(folder/'template.json').is_file() and json.loads((folder/'template.json').read_text(encoding='utf-8'))==spec
            except (OSError,ValueError):same=False
            same=same and all((folder/spec[f]).is_file() and hashlib.sha256((folder/spec[f]).read_bytes()).digest()==hashlib.sha256(blobs[f]).digest() for f in blobs)
            if same:
                mapping[old]=register(spec,folder);continue
            spec={**spec,'key':'user_'+uuid.uuid4().hex[:16]}
            folder=LIBRARY/spec['key']
        LIBRARY.mkdir(parents=True,exist_ok=True)
        stage=LIBRARY/('.creating-'+uuid.uuid4().hex);stage.mkdir()
        try:
            for field,content in blobs.items():(stage/spec[field]).write_bytes(content)
            (stage/'template.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
            stage.replace(folder)
            mapping[old]=register(spec,folder)
        finally:
            if stage.exists() and stage.parent.resolve()==LIBRARY.resolve() and stage.name.startswith('.creating-'):shutil.rmtree(stage)
    return mapping
