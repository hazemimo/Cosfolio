"""Cancellable local photo delivery. Outputs never overwrite older batches."""
from __future__ import annotations
import csv
import json
import math
import os
import uuid
from datetime import datetime,timezone,timedelta
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from .core import make_cutout,oriented_image,export_basename,srgb_profile
from .library import STATUSES


def shanghai_now():return datetime.now(timezone(timedelta(hours=8)))


def batch_folder(parent, prefix):
    parent=Path(parent)
    if not parent.is_dir():raise ValueError('请选择已有的导出文件夹')
    folder=parent/(prefix+'_'+shanghai_now().strftime('%Y%m%d-%H%M%S')+'_'+uuid.uuid4().hex[:6])
    folder.mkdir();return folder


def save_png(image, path, cancelled=lambda:False):
    path=Path(path);temporary=path.with_name('.'+path.stem+'.'+uuid.uuid4().hex+'.writing.png')
    try:
        if cancelled():raise InterruptedError('导出已取消')
        image.save(temporary,format='PNG',dpi=(300,300),icc_profile=srgb_profile())
        if cancelled():raise InterruptedError('导出已取消')
        os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def finish_report(folder, result):
    (folder/'导出清单.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


def export_cutouts(library, keys, parent, long_edge=0, notify=lambda _:None, cancelled=lambda:False):
    keys=list(dict.fromkeys(keys))
    if not keys:raise ValueError('没有可导出的照片')
    if long_edge not in (0,3000,6000,8000):raise ValueError('导出尺寸不正确')
    folder=batch_folder(parent,'透明主体')
    result={'kind':'transparent-png','folder':str(folder),'requested':len(keys),'files':[],'errors':[],'cancelled':False}
    for i,key in enumerate(keys):
        if cancelled():result['cancelled']=True;break
        try:
            row=library.get(key)
            if not row:raise ValueError('照片不存在')
            notify(f'导出透明主体 {i+1}/{len(keys)} · {row["name"]}')
            asset=library.asset_view(key)
            with Image.open(asset.source) as image:native=max(image.size)
            cutout=make_cutout(asset,long_edge or native)
            name=f'{i+1:03d}_'+export_basename(Path(row['name']).stem,'')[:80]+'_抠图.png'
            save_png(cutout,folder/name,cancelled)
            result['files'].append({'number':i+1,'photo_id':key,'name':row['name'],'file':name,
                                    'width':cutout.width,'height':cutout.height,'mask_version':row['current_version']})
            cutout.close()
        except InterruptedError:result['cancelled']=True;break
        except Exception as exc:result['errors'].append({'photo_id':key,'error':str(exc)})
    return finish_report(folder,result)


def font(size):
    for path in ('C:/Windows/Fonts/msyh.ttc','C:/Windows/Fonts/simhei.ttf'):
        if Path(path).exists():return ImageFont.truetype(path,size)
    return ImageFont.load_default(size=size)


def fit_label(draw, value, face, width):
    if draw.textlength(value,font=face)<=width:return value
    text=value
    while text and draw.textlength(text+'…',font=face)>width:text=text[:-1]
    return text+'…'


def export_contact_sheets(library, keys, parent, title='选片联系表', columns=4,
                          originals=True, notify=lambda _:None, cancelled=lambda:False):
    keys=list(dict.fromkeys(keys))
    if not keys:raise ValueError('没有可导出的照片')
    if columns not in (3,4,5):raise ValueError('联系表列数不正确')
    title=str(title).strip()[:100] or '选片联系表'
    folder=batch_folder(parent,'选片联系表');per_page=columns*5;pages=math.ceil(len(keys)/per_page)
    result={'kind':'contact-sheet','folder':str(folder),'requested':len(keys),'files':[],'photos':[],
            'errors':[],'cancelled':False,'columns':columns,'originals':bool(originals)}
    albums={a['id']:a['name'] for a in library.albums()}
    heading=font(48);normal=font(25);small=font(22)
    for page in range(pages):
        if cancelled():result['cancelled']=True;break
        image=Image.new('RGB',(2400,3300),'white');draw=ImageDraw.Draw(image)
        draw.text((90,55),fit_label(draw,title,heading,1900),font=heading,fill='#173f70')
        draw.text((90,125),f'COSFOLIO / {"原照片" if originals else "透明主体"} / {len(keys)} 张',font=small,fill='#5d7084')
        draw.line((90,185,2310,185),fill='#d5dfeb',width=2)
        page_records=[];cell_w=2220/columns;cell_h=596
        for slot,key in enumerate(keys[page*per_page:(page+1)*per_page]):
            if cancelled():result['cancelled']=True;break
            number=page*per_page+slot+1;row=library.get(key)
            x=90+int(slot%columns*cell_w);y=220+int(slot//columns*cell_h)
            target=(int(cell_w)-24,480)
            draw.rounded_rectangle((x,y,x+target[0],y+target[1]),radius=10,fill='#f1f4f8')
            notify(f'制作选片联系表 {number}/{len(keys)}')
            name=row['name'] if row else '照片不存在'
            try:
                if not row:raise ValueError('照片不存在')
                if originals:picture=oriented_image(library.root/row['source'],1000)
                else:picture=make_cutout(library.asset_view(key),1000)
                picture.thumbnail((target[0]-16,target[1]-16),Image.Resampling.LANCZOS)
                point=(x+(target[0]-picture.width)//2,y+(target[1]-picture.height)//2)
                image.paste(picture,point,picture if picture.mode=='RGBA' else None);picture.close()
            except Exception as exc:
                result['errors'].append({'photo_id':key,'error':str(exc)})
                draw.text((x+18,y+200),'无法读取照片',font=normal,fill='#7c5260')
            draw.text((x,y+492),f'{number:03d}',font=normal,fill='#174d8b')
            draw.text((x+67,y+492),fit_label(draw,name,normal,target[0]-70),font=normal,fill='#253c53')
            tags=' · '.join(row['tags']) if row else ''
            draw.text((x,y+535),fit_label(draw,tags,small,target[0]),font=small,fill='#617489')
            page_records.append({'number':number,'photo_id':key,'name':name,'page':page+1,
                                 'album':albums.get(row['album'],'未分类') if row else '',
                                 'tags':tags,'favorite':bool(row['favorite']) if row else False,
                                 'status':STATUSES.get(row['status'],'') if row else ''})
        if result['cancelled']:image.close();break
        draw.line((90,3205,2310,3205),fill='#d5dfeb',width=2)
        draw.text((90,3225),'COSFOLIO / '+shanghai_now().strftime('%Y-%m-%d'),font=small,fill='#617489')
        draw.text((2100,3225),f'{page+1} / {pages}',font=small,fill='#617489')
        filename=f'{page+1:03d}_'+export_basename(title,'')[:80]+'.png'
        try:save_png(image,folder/filename,cancelled)
        except InterruptedError:result['cancelled']=True;image.close();break
        image.close();result['files'].append({'file':filename,'page':page+1,'width':2400,'height':3300})
        result['photos'].extend(page_records)
    with (folder/'选片编号.csv').open('w',encoding='utf-8-sig',newline='') as stream:
        writer=csv.writer(stream);writer.writerow(['编号','照片名称','联系表页码','专辑','标签','收藏','状态'])
        def cell(value):
            value=str(value)
            return "'"+value if value[:1] in ('=','+','-','@') else value
        for row in result['photos']:
            writer.writerow([f'{row["number"]:03d}',cell(row['name']),row['page'],cell(row['album']),
                             cell(row['tags']),'★' if row['favorite'] else '',row['status']])
    return finish_report(folder,result)
