"""Local workflow helpers: recovery snapshots and repeatable batch plans."""
from pathlib import Path
import copy
import json
import os
import time

from .core import ROOT, DATA, Project, Placement, export_basename
from .catalog import TEMPLATES

# These are design palettes inspired by μ's, not claims of official RGB values.
ACCENTS={
    'template':('保留模板配色',None),
    'honoka':('穗乃果 · 橙','#ef913e'),
    'eli':('绘里 · 浅蓝','#78c8e5'),
    'kotori':('小鸟 · 银灰','#a5acb5'),
    'umi':('海未 · 蓝','#437cce'),
    'rin':('凛 · 黄','#e8c74d'),
    'maki':('真姬 · 红','#d95565'),
    'nozomi':('希 · 紫','#9d76bc'),
    'hanayo':('花阳 · 绿','#66ad7a'),
    'nico':('妮可 · 粉','#e785b1'),
}


def read_preferences():
    path=DATA/'preferences.json'
    try:
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict):
            return {}
        result={key:value for key,value in data.items() if key in ('last_project','export_directory','project_directory') and isinstance(value,str)}
        result['recent_projects']=[v for v in data.get('recent_projects',[]) if isinstance(v,str)][:20] if isinstance(data.get('recent_projects',[]),list) else []
        return result
    except (OSError,ValueError):
        return {}


def save_preferences(data):
    DATA.mkdir(parents=True,exist_ok=True)
    path=DATA/'preferences.json'
    temporary=path.with_suffix(f'.{os.getpid()}.writing')
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)


def recovery_record(project: Project):
    record=project.to_dict()
    for asset in record['assets']:
        for key in ('source','mask','initial_mask'):
            path=Path(asset[key])
            try:
                asset[key]=str(path.relative_to(ROOT))
            except ValueError:
                asset[key]=str(path)
    for layout in [record['layout']]+[page['layout'] for page in record.get('pages',[])]:
        if layout.get('foreground_mask'):
            path=Path(layout['foreground_mask'])
            try:layout['foreground_mask']=str(path.relative_to(ROOT))
            except ValueError:layout['foreground_mask']=str(path)
    return record


def write_recovery(project: Project, instance: str) -> Path:
    folder=DATA/'drafts'
    folder.mkdir(parents=True,exist_ok=True)
    target=folder/f'{instance}.json'
    tmp=target.with_suffix('.writing')
    record={'kind':'cosfolio-draft','saved_at':time.time(),'pid':os.getpid(),'project':recovery_record(project)}
    tmp.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    tmp.replace(target)
    return target


def read_recovery(path: str | Path) -> Project:
    record=json.loads(Path(path).read_text(encoding='utf-8'))
    if record.get('kind')!='cosfolio-draft':
        raise ValueError('草稿格式不正确')
    project=Project.from_dict(record['project'])
    for asset in project.assets:
        for key in ('source','mask','initial_mask'):
            value=ROOT/getattr(asset,key)
            if not value.is_file():
                raise FileNotFoundError(f'找不到草稿素材：{asset.name}')
            setattr(asset,key,str(value))
    for layout in [project.layout]+[page['layout'] for page in project.pages]:
        if layout.get('foreground_mask'):
            value=ROOT/layout['foreground_mask']
            if not value.is_file():raise FileNotFoundError('找不到前景蒙版')
            layout['foreground_mask']=str(value)
    return project


def list_recoveries(exclude=''):
    folder=DATA/'drafts'
    if not folder.exists():
        return []
    result=[]
    for path in folder.glob('*.json'):
        if path.stem==exclude:
            continue
        try:
            record=json.loads(path.read_text(encoding='utf-8'))
            if record.get('kind')=='cosfolio-draft':
                result.append((record.get('saved_at',0),path,record['project'].get('title','未命名排版')))
        except (OSError,ValueError,KeyError):
            continue
    return sorted(result,reverse=True)


def batch_project(project: Project, template: str) -> Project:
    result=copy.deepcopy(project)
    result.template=template
    if template!=project.template:result.layout={}
    result.ensure_slots()
    for i in range(len(TEMPLATES[template]['slots'])):
        old=result.placements[i]
        key=old.asset_id
        if not key and result.assets:
            key=result.assets[i%len(result.assets)].id
        if template!=project.template:
            result.placements[i]=copy.deepcopy(old)
            result.placements[i].asset_id=key
            result.placements[i].x=result.placements[i].y=result.placements[i].rotation=0
            result.placements[i].zoom=1
            result.placements[i].fit='template'
        else:
            result.placements[i].asset_id=key
    return result


def batch_filename(project: Project, template: str, extension='.png') -> str:
    stem=export_basename(project.title,project.subtitle)[:70].rstrip(' .')
    from .template_preferences import display_name
    name=export_basename(display_name(template),'')
    return f'{stem}_{name}{extension}'
