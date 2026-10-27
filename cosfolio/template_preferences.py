"""Local template labels and favorites; stable template IDs and plates never change."""
from __future__ import annotations
import json
import os
import uuid
from pathlib import Path
from .core import DATA
from .catalog import TEMPLATES

PATH = DATA / 'template-preferences.json'


def read():
    try:
        data = json.loads(PATH.read_text(encoding='utf-8'))
        names = data.get('names', {})
        favorites = data.get('favorites', [])
        return {'names': {k:v for k,v in names.items() if isinstance(k,str) and isinstance(v,str) and v.strip() and len(v)<=100},
                'favorites': list(dict.fromkeys(k for k in favorites if isinstance(k,str)))}
    except (OSError, ValueError, AttributeError, TypeError):
        return {'names': {}, 'favorites': []}


def write(data):
    PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = PATH.with_name(PATH.name + '.' + uuid.uuid4().hex + '.writing')
    try:
        temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,PATH)
    finally:
        temporary.unlink(missing_ok=True)


def display_name(key, settings=None):
    return (settings if settings is not None else read())['names'].get(key,TEMPLATES[key]['name'])


def rename(key, value):
    if key not in TEMPLATES: raise ValueError('模板不存在')
    value = value.strip()
    if not value or len(value)>100 or any(ord(c)<32 for c in value):
        raise ValueError('请输入 1～100 字的模板名称')
    data = read()
    if any(other!=key and display_name(other,data).casefold()==value.casefold() for other in TEMPLATES):
        raise ValueError('已有模板使用这个名称，请换一个便于区分的名字')
    if value==TEMPLATES[key]['name']:data['names'].pop(key,None)
    else:data['names'][key]=value
    write(data)


def favorite(key, value):
    if key not in TEMPLATES:raise ValueError('模板不存在')
    data=read();items=set(data['favorites'])
    if value:items.add(key)
    else:items.discard(key)
    data['favorites']=sorted(items);write(data)
