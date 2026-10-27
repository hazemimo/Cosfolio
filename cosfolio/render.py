from __future__ import annotations

from functools import lru_cache
from collections import OrderedDict
from pathlib import Path
import math
import json
import random
import uuid

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance, ImageOps,ImageChops

from .core import ROOT, Project, make_cutout, srgb_profile
from .catalog import TEMPLATES
from .workflow import ACCENTS
from .layout import frames,radii,pixel_box,frame_mask
from .composite import composite_tiles,fit_factor


def preview_cache(function):
    cached=lru_cache(maxsize=12)(function)
    def wrapped(style,long_edge,text_mode='original'):
        return cached(style,long_edge,text_mode) if long_edge<=1600 else function(style,long_edge,text_mode)
    wrapped.cache_clear=cached.cache_clear
    return wrapped


def scene_cache(function):
    cached=lru_cache(maxsize=18)(function)
    def wrapped(style,index,width,height):
        return cached(style,index,width,height) if max(width,height)<=1600 else function(style,index,width,height)
    return wrapped


def font(size: int, bold=False):
    files = ['msyhbd.ttc' if bold else 'msyh.ttc', 'segoeuib.ttf' if bold else 'segoeui.ttf']
    for name in files:
        path = Path('C:/Windows/Fonts') / name
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size=size)


def balloon(image, x, y, rx, ry, color):
    """Locally drawn latex balloon. No generative model or external assets."""
    w, h = image.size
    left, top = max(0,int(x-rx-3)), max(0,int(y-ry-3))
    right, bottom = min(w,int(x+rx+4)), min(h,int(y+ry+4))
    if right <= left or bottom <= top:
        return
    for row in range(top,bottom,128):
        yy, xx = np.mgrid[row:min(bottom,row+128),left:right].astype(np.float32)
        nx, ny = (xx-x)/rx, (yy-y)/ry
        d2 = nx*nx + ny*ny
        coverage = np.clip((1 - np.sqrt(d2)) * min(rx,ry), 0, 1)
        z = np.sqrt(np.clip(1-d2,0,1))
        # Broad diffuse reflection plus elongated softbox highlights.
        light = np.clip(-.23*nx-.34*ny+.86*z, 0, 1)
        tone = .83 + .17*light
        rgb = np.array(color,dtype=np.float32)[None,None,:] * tone[...,None]
        white = .18*z + .12*np.exp(-((nx+.32)**2/.08+(ny+.42)**2/.18))
        rgb = rgb*(1-white[...,None]) + 255*white[...,None]
        glint = np.exp(-((nx+.34)**2/.004+(ny+.54)**2/.003)) * .75
        rgb = rgb*(1-glint[...,None]) + 255*glint[...,None]
        rgba = np.dstack((np.clip(rgb,0,255),coverage*255)).astype(np.uint8)
        image.alpha_composite(Image.fromarray(rgba), (left,row))
    draw = ImageDraw.Draw(image)
    bx, by = x, y+ry
    draw.polygon([(bx,by-1),(bx-5,by+9),(bx+5,by+9)],fill=tuple(color)+(255,))
    draw.line([(bx,by+8),(bx+8,by+50),(bx-4,by+92)],fill=(164,157,170,100),width=1)


@scene_cache
def scene_background(style: str, index: int, width: int, height: int):
    if style == 'party':
        center = np.array([255,255,254],np.float32)
        edge = np.array([229,235,247],np.float32)
    else:
        center = np.array([58,39,88],np.float32)
        edge = np.array([21,19,45],np.float32)
    image=Image.new('RGBA',(width,height))
    for row in range(0,height,128):
        yy,xx=np.mgrid[row:min(height,row+128),0:width].astype(np.float32)
        radial = np.clip(((xx/width-.5)**2+(yy/height-.45)**2)*1.2,0,1)
        rgb = center[None,None,:]*(1-radial[...,None]) + edge[None,None,:]*radial[...,None]
        image.paste(Image.fromarray(rgb.astype(np.uint8)).convert('RGBA'),(0,row))
    if style == 'party':
        palette = [(255,216,34),(120,224,245),(251,82,96),(185,149,231),(164,226,94)]
    else:
        palette = [(248,130,30),(137,94,186),(245,188,58),(86,63,126),(215,121,202)]
    positions = [
        [(-.07,.16,.27,.30,1),(.87,-.02,.32,.28,0),(-.05,.89,.32,.24,0),(1.04,.72,.27,.32,3)],
        [(.24,-.05,.60,.25,0),(1.04,.35,.38,.27,2),(-.13,.74,.42,.26,4),(.92,1.02,.55,.29,3)],
        [(.12,.04,.29,.30,0),(.84,.22,.26,.37,2),(-.03,.70,.22,.31,1),(.27,1.02,.25,.25,0),(.97,.87,.23,.25,3)],
    ][index%3]
    for px,py,rx,ry,col in positions:
        balloon(image,px*width,py*height,rx*width,ry*height,palette[col])
    rng = random.Random(850+index)
    draw = ImageDraw.Draw(image)
    for _ in range(27):
        x,y = rng.randrange(width),rng.randrange(height)
        length = max(4,int(width*.013))
        c = palette[rng.randrange(len(palette))]
        draw.line((x,y,x+length//2,y+length),fill=c+(210,),width=max(1,int(width*.003)))
    return image


def star(draw, x,y,r, color):
    points=[]
    for i in range(10):
        angle = math.pi*i/5-math.pi/2
        radius = r if i%2==0 else r*.42
        points.append((x+math.cos(angle)*radius,y+math.sin(angle)*radius))
    draw.polygon(points,fill=color)


@lru_cache(maxsize=1)
def custom_text_overlays():
    path=ROOT/'resources'/'templates'/'v04'/'text-edits'/'index.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}


@preview_cache
def template_plate(style: str, long_edge: int, text_mode: str = 'original'):
    template = TEMPLATES[style]
    bw,bh = template['size']
    scale = long_edge/max(bw,bh)
    w,h = round(bw*scale),round(bh*scale)
    if template.get('plate'):
        path=ROOT/'resources'/'templates'/template['plate']
        with Image.open(path) as source:
            image=source.convert('RGBA')
        edit=custom_text_overlays().get(style) if text_mode=='custom' else None
        if edit:
            with Image.open(ROOT/'resources'/'templates'/'v04'/'text-edits'/edit['file']) as overlay:
                image.alpha_composite(overlay.convert('RGBA'),tuple(edit['xy']))
        return image.resize((w,h),Image.Resampling.LANCZOS)
    reference = ROOT/'resources'/'reference.jpg'
    if style == 'party' and reference.exists():
        source = Image.open(reference).convert('RGBA')
        image = source.resize((w,h),Image.Resampling.LANCZOS)
        # Replace the printed name with a clean texture sampled from the same page.
        patch = source.crop((1910,200,1990,500)).resize((round(1030*scale),round(110*scale)))
        image.paste(patch,(round(55*scale),round(45*scale)))
        patch2=source.crop((1910,200,1990,500)).resize((round(1940*scale),round(75*scale)))
        image.paste(patch2,(round(20*scale),round(2750*scale)))
    else:
        image = Image.new('RGBA',(w,h),'#27213f' if style=='halloween' else '#16142f')
        draw=ImageDraw.Draw(image)
        rng=random.Random(62)
        for _ in range(140):
            x,y=rng.randrange(w),rng.randrange(h)
            star(draw,x,y,max(2,round(rng.uniform(4,13)*scale)),rng.choice(['#f1c379','#a191c2','#765f9e']))
        for x,y,rx,ry,col in [(.94,.07,.12,.10,(236,126,37)),(.03,.78,.12,.15,(102,75,144))]:
            balloon(image,x*w,y*h,rx*w,ry*h,col)
    draw=ImageDraw.Draw(image)
    for index,(x,y,sw,sh) in enumerate(template['slots']):
        px,py,pw,ph=[round(v*scale) for v in (x,y,sw,sh)]
        if style != 'party':
            pad=max(2,round(13*scale))
            draw.rectangle((px-pad,py-pad,px+pw+pad,py+ph+pad),fill='#a97535')
            draw.rectangle((px-pad+max(1,round(3*scale)),py-pad+max(1,round(3*scale)),
                            px+pw+pad-max(1,round(3*scale)),py+ph+pad-max(1,round(3*scale))),outline='#f5d993',width=max(1,round(3*scale)))
        bg=scene_background('party' if style=='party' else 'halloween',index,pw,ph)
        image.alpha_composite(bg,(px,py))
    return image


def foreground_mask(project):
    template=TEMPLATES[project.template]
    path=project.layout.get('foreground_mask')
    if path:
        with Image.open(path) as source:return source.convert('L').resize(template['size'],Image.Resampling.LANCZOS)
    mask=Image.new('L',template['size'])
    draw=ImageDraw.Draw(mask)
    for x,y,w,h in template.get('foreground_regions',[]):draw.rectangle((x,y,x+w-1,y+h-1),fill=255)
    return mask


def foreground_layer(project,long_edge):
    if not project.layout.get('foreground',True):return None
    mask=foreground_mask(project)
    if not mask.getbbox():return None
    source=template_plate(project.template,max(TEMPLATES[project.template]['size']),project.text_mode).copy()
    source.putalpha(mask)
    ratio=long_edge/max(source.size)
    return source.resize((round(source.width*ratio),round(source.height*ratio)),Image.Resampling.LANCZOS)


def adjust_photo(photo, placement):
    """Small local RGB operations; never change the cutout's alpha channel."""
    if any((placement.brightness!=1,placement.contrast!=1,placement.saturation!=1,placement.warmth!=0)):
        alpha=photo.getchannel('A')
        rgb=photo.convert('RGB')
        if placement.brightness!=1:
            rgb=ImageEnhance.Brightness(rgb).enhance(placement.brightness)
        if placement.contrast!=1:
            # A fixed midpoint avoids transparent background pixels influencing
            # the subject's contrast as its crop or template changes.
            lut=[max(0,min(255,round((v-128)*placement.contrast+128))) for v in range(256)]
            rgb=rgb.point(lut*3)
        if placement.saturation!=1:
            rgb=ImageEnhance.Color(rgb).enhance(placement.saturation)
        if placement.warmth:
            delta=round(24*placement.warmth)
            lut=lambda offset:[max(0,min(255,v+offset)) for v in range(256)]
            rgb=rgb.point(lut(delta)+lut(0)+lut(-delta))
        photo=rgb.convert('RGBA')
        photo.putalpha(alpha)
    return ImageOps.mirror(photo) if placement.flip else photo


class Renderer:
    def __init__(self):
        self.cache={}
        self.layers=OrderedDict()
        self.layer_bytes=0
        self.layer_budget=64*1024**2

    def invalidate(self,asset_id=None):
        if asset_id is None:
            self.cache.clear()
        else:
            self.cache={k:v for k,v in self.cache.items() if k[0]!=asset_id}
        self.layers.clear()
        self.layer_bytes=0

    def cutout(self,asset,limit,dehalo,edge_shift=0,edge_softness=0):
        if limit>1600:return make_cutout(asset,limit,dehalo,edge_shift,edge_softness)
        key=(asset.id,asset.mask,limit,dehalo,edge_shift,edge_softness)
        if key not in self.cache:
            if len(self.cache)>15:
                self.cache.clear()
            self.cache[key]=make_cutout(asset,limit,dehalo,edge_shift,edge_softness)
        return self.cache[key]

    def photo_layer(self,asset,placement,template_key,index,long_edge,project=None):
        """Cache transformed pixels; x/y are intentionally absent from the key."""
        template=TEMPLATES[template_key]
        ratio=long_edge/max(template['size'])
        rect=frames(project)[index] if project is not None else template['slots'][index]
        _,_,pw,ph=pixel_box(rect,ratio)
        key=(asset.id,asset.mask,template_key,index,long_edge,placement.zoom,placement.rotation,placement.fit,
             placement.brightness,placement.contrast,placement.saturation,placement.warmth,placement.flip,
             placement.dehalo,placement.shadow,placement.edge_shift,placement.edge_softness,
             placement.shadow_opacity,placement.shadow_blur,tuple(rect))
        if long_edge<=1600 and key in self.layers:
            self.layers.move_to_end(key)
            return self.layers[key]
        photo=self.cutout(asset,1400 if long_edge<=1600 else max(4000,long_edge),placement.dehalo,placement.edge_shift,placement.edge_softness)
        factor=fit_factor(photo,placement,template,index,pw,ph,template_key)
        nw,nh=max(1,round(photo.width*factor)),max(1,round(photo.height*factor))
        if nw*nh>180_000_000:
            raise ValueError('当前放大比例过大，请缩小人物后导出')
        photo=photo.resize((nw,nh),Image.Resampling.BICUBIC if long_edge<=1600 else Image.Resampling.LANCZOS)
        photo=adjust_photo(photo,placement)
        if placement.rotation:
            photo=photo.rotate(-placement.rotation,Image.Resampling.BICUBIC,expand=True)
        shadow=None
        if placement.shadow:
            pad=math.ceil(placement.shadow_blur*ratio*3)+2
            shadow=Image.new('RGBA',(photo.width+pad*2,photo.height+pad*2),(33,22,48,0))
            alpha=Image.new('L',shadow.size)
            alpha.paste(photo.getchannel('A').point(lambda a:round(a*placement.shadow_opacity)),(pad,pad))
            shadow.putalpha(alpha)
            shadow=shadow.filter(ImageFilter.GaussianBlur(placement.shadow_blur*ratio))
        result=(photo,shadow)
        if long_edge<=1600:
            size=sum(im.width*im.height*4 for im in result if im is not None)
            if size<=self.layer_budget:
                while self.layers and (self.layer_bytes+size>self.layer_budget or len(self.layers)>=24):
                    _,old=self.layers.popitem(last=False)
                    self.layer_bytes-=sum(im.width*im.height*4 for im in old if im is not None)
                self.layers[key]=result
                self.layer_bytes+=size
        return result

    def render(self, project: Project, long_edge=1200, selected=-1, placeholders=False, only_foreground=False,
               cancelled=lambda:False,progress=lambda value:None):
        project.ensure_slots()
        template=TEMPLATES[project.template]
        bw,bh=template['size']
        ratio=long_edge/max(bw,bh)
        progress('绘制模板背景')
        if only_foreground or not project.layout.get('background',True):
            page=Image.new('RGBA',(round(bw*ratio),round(bh*ratio)),(255,255,255,0 if only_foreground else 255))
        else:
            page=template_plate(project.template,long_edge,project.text_mode)
            if long_edge<=1600:page=page.copy()
        for index,(x,y,sw,sh) in enumerate([] if only_foreground or not project.layout.get('photos',True) else frames(project)):
            if cancelled():raise InterruptedError('已取消导出')
            progress(f'合成照片 {index+1}/{len(frames(project))}')
            box=pixel_box((x,y,sw,sh),ratio)
            px,py,pw,ph=box
            placement=project.placements[index]
            asset=project.asset(placement.asset_id)
            if asset:
                if long_edge>1600:
                    composite_tiles(page,project,index,long_edge,adjust_photo,cancelled)
                    continue
                photo,shadow=self.photo_layer(asset,placement,project.template,index,long_edge,project)
                dx=round((pw-photo.width)/2+placement.x*pw)
                # Anchor the cutout near its top: missing feet may be cropped,
                # while the subject's head must remain visible by default.
                dy=round(((ph-photo.height)/2 if placement.fit=='contain' else ph*.025)+placement.y*ph)
                layer=Image.new('RGBA',(pw,ph))
                if shadow is not None:
                    pad=math.ceil(placement.shadow_blur*ratio*3)+2
                    layer.alpha_composite(shadow,(dx+round(placement.shadow_x*ratio)-pad,dy+round(placement.shadow_y*ratio)-pad))
                layer.alpha_composite(photo,(dx,dy))
                radius=round(radii(project)[index]*ratio)
                if radius:layer.putalpha(ImageChops.multiply(layer.getchannel('A'),frame_mask(pw,ph,radius)))
                page.alpha_composite(layer,(px,py))
            elif placeholders:
                draw=ImageDraw.Draw(page)
                cx,cy=px+pw/2,py+ph/2
                radius=max(12,round(30*ratio))
                draw.ellipse((cx-radius,cy-radius,cx+radius,cy+radius),fill='#fffdfb',outline='#bca7c5',width=max(1,round(2*ratio)))
                draw.text((cx,cy),str(index+1),font=font(max(13,round(31*ratio)),True),fill='#72507e',anchor='mm')
        progress('叠放前景与文字')
        needs_foreground=(project.layout.get('photos',True) and any(p.asset_id for p in project.placements[:len(frames(project))])) or not project.layout.get('background',True)
        foreground=foreground_layer(project,long_edge) if needs_foreground else None
        if foreground is not None:page.alpha_composite(foreground)
        del foreground
        draw=ImageDraw.Draw(page)
        custom_text=project.text_mode=='custom' or not template.get('plate')
        if custom_text and (template.get('text_style') or template.get('text_fields')):
            self.template_text(page,project,ratio)
        elif custom_text and project.template!='card':
            draw.text((round(74*ratio),round(128*ratio)),project.title,font=font(max(12,round(56*ratio)),True),fill='#ffffff',stroke_width=0,anchor='ls')
            # Subtitle starts after the actual name width, with a safe right boundary.
            right=draw.textbbox((0,0),project.title,font=font(max(12,round(56*ratio)),True))[2]
            sx=round(94*ratio)+right
            subtitle_font=font(max(9,round(24*ratio)))
            text=project.subtitle
            available=page.width-round(95*ratio)-sx
            while text and draw.textlength(text,font=subtitle_font)>available:
                text=text[:-1]
            draw.text((sx,round(128*ratio)),text,font=subtitle_font,fill='#f9eee1',anchor='ls')
            footer_font=font(max(8,round(16*ratio)))
            footer=project.footer
            while footer and draw.textlength(footer,font=footer_font)>page.width-round(100*ratio):
                footer=footer[:-1]
            draw.text((round(48*ratio),round(2782*ratio)),footer,font=footer_font,fill='#ffffff')
        elif project.template=='card':
            # Foreground ornament and typography remain above the photograph.
            y=round(2110*ratio)
            if project.layout.get('foreground',True):
                draw.rectangle((round(45*ratio),y,page.width-round(45*ratio),page.height-round(45*ratio)),fill='#211b39',outline='#e9bc70',width=max(1,round(6*ratio)))
            title_font=font(max(13,round(73*ratio)),True)
            title=project.title
            while title and draw.textlength(title,font=title_font)>page.width-round(180*ratio):
                title=title[:-1]
            draw.text((round(100*ratio),round(2160*ratio)),title,font=title_font,fill='#fff2d8')
            subfont=font(max(10,round(29*ratio)))
            subtitle=project.subtitle
            while subtitle and draw.textlength(subtitle,font=subfont)>page.width-round(180*ratio):
                subtitle=subtitle[:-1]
            draw.text((round(100*ratio),round(2275*ratio)),subtitle,font=subfont,fill='#d3bfdc')
            if project.layout.get('foreground',True):
                for i in range(6):
                    star(draw,round((125+i*100)*ratio),round(2015*ratio),round(35*ratio),'#ffe4a0')
        accent=ACCENTS.get(project.accent,ACCENTS['template'])[1]
        if accent and project.layout.get('foreground',True):
            for index,(x,y,sw,sh) in enumerate(frames(project)):
                inset=max(1,round(2*ratio))
                draw.rounded_rectangle(tuple(round(v*ratio) for v in (x,y,x+sw-1,y+sh-1)),radius=radii(project)[index]*ratio,outline=accent,width=max(2,round(5*ratio)))
        if 0<=selected<len(template['slots']):
            x,y,sw,sh=frames(project)[selected]
            draw.rounded_rectangle(tuple(round(v*ratio) for v in (x,y,x+sw-1,y+sh-1)),radius=radii(project)[selected]*ratio,outline='#c978ed',width=max(2,round(8*ratio)))
        if project.page_numbers or project.credit:
            text='  ·  '.join(filter(None,[project.credit,f'{project.active_page+1:02d} / {project.page_count:02d}' if project.page_numbers else '']))
            face=font(max(10,round(13*ratio)))
            width=draw.textlength(text,font=face)
            x=max(round(12*ratio),(page.width-width)/2)
            y=page.height-round(25*ratio)
            draw.rectangle((x-round(7*ratio),y-round(3*ratio),x+width+round(7*ratio),page.height),fill=(255,255,255,235))
            draw.text((x,y),text,font=face,fill='#51455c')
        return page if only_foreground else page.convert('RGB')

    @staticmethod
    def template_text(page,project,ratio):
        draw=ImageDraw.Draw(page)
        template=TEMPLATES[project.template]
        w,h=template['size']
        def text(value,x,y,size,width,color='#ffffff',bold=False):
            value=value.replace('\n',' ')
            fsize=max(8,round(size*ratio))
            face=font(fsize,bold)
            while draw.textlength(value,font=face)>width*ratio and fsize>9:
                fsize-=1
                face=font(fsize,bold)
            while value and draw.textlength(value,font=face)>width*ratio:
                value=value[:-1]
            draw.text((round(x*ratio),round(y*ratio)),value,font=face,fill=color,anchor='ls')
        def paragraph(value,x,y,size,width,height,color='#ffffff'):
            face=font(max(8,round(size*ratio)))
            leading=max(10,round(size*1.55*ratio))
            lines=[]
            for paragraph in value.split('\n'):
                line=''
                for char in paragraph:
                    if line and draw.textlength(line+char,font=face)>width*ratio:
                        lines.append(line)
                        line=''
                    line+=char
                lines.append(line)
            for i,line in enumerate(lines[:max(0,int(height*ratio//leading))]):
                draw.text((round(x*ratio),round(y*ratio)+i*leading),line,font=face,fill=color)
        if template.get('text_fields'):
            for spec in template['text_fields']:
                value=getattr(project,spec['field'])
                x,y,width,height=spec['rect']
                if spec['field'] in ('body','footer'):
                    paragraph(value,x,y,spec['size'],width,height,spec['color'])
                else:
                    text(value,x,y+spec['size'],spec['size'],width,spec['color'],spec['bold'])
            return
        style=template['text_style']
        if style=='top':
            text(project.title,w*.035,h*.046,w*.04,w*.52,bold=True)
            text(project.subtitle,w*.60,h*.046,w*.017,w*.36)
            text(project.footer,w*.025,h*.989,w*.010,w*.95)
        elif style=='band':
            # Use the existing narrow blue margin; a new footer band would
            # overwrite the original black photo regions.
            text(project.title,45,h-9,24,w*.48,bold=True)
            text(project.subtitle,w*.54,h-9,13,w*.43)
        elif style=='qa':
            text('Q & A',42,609,44,438,bold=True)
            text(project.title,42,675,33,438,bold=True)
            text(project.subtitle,42,713,17,438)
            paragraph(project.body,42,748,16,438,238)
            text(project.footer,42,1008,10,438)
        elif style in ('bottom','message'):
            text(project.title,45,h-57,52,w*.65,'#427daf',True)
            text(project.subtitle,45,h-20,22,w*.92,'#496378')
            if style=='message':
                text('MESSAGE',920,92,36,430)
                text(project.title,920,155,38,430,bold=True)
                paragraph(project.body or project.subtitle,920,190,23,430,930)
        elif style=='minimal':
            draw.rectangle((0,round((h-110)*ratio),page.width,page.height),fill='#fafaf9')
            paragraph(project.body,85,85,17,170,440,'#738195')
            text(project.title,60,h-57,49,w*.88,'#4b6c91',True)
            text(project.subtitle,60,h-20,20,w*.88,'#738195')
        elif style=='sidebar':
            text('PHOTO',110,1048,21,190)
            text(project.title,110,1110,33,190,bold=True)
            text(project.subtitle,110,1160,18,190)
            text(project.footer,45,h-20,12,w*.90,'#7392ab')

    def export(self,project,filename,long_edge=6000,cancelled=lambda:False,progress=lambda value:None):
        if not 256<=long_edge<=8000:raise ValueError('导出长边须在 256～8000 像素之间')
        image=self.render(project,long_edge,cancelled=cancelled,progress=progress)
        if cancelled():raise InterruptedError('已取消导出')
        target=Path(filename)
        suffix=target.suffix.lower()
        temporary=target.with_name(f'.{target.stem}.{uuid.uuid4().hex[:8]}.tmp{suffix}')
        try:
            progress('写入高清图片')
            if suffix in ('.jpg','.jpeg'):
                image.save(temporary,quality=96,subsampling=0,dpi=(300,300),icc_profile=srgb_profile())
            else:
                image.save(temporary,format='PNG',dpi=(300,300),icc_profile=srgb_profile())
            if cancelled():raise InterruptedError('已取消导出')
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        return image.size
