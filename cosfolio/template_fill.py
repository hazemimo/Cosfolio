"""Constrained, deterministic background filling. No generative restoration."""
from PIL import Image,ImageDraw,ImageFilter
import numpy as np


def region_union(size,regions):
    mask=Image.new('L',size)
    draw=ImageDraw.Draw(mask)
    for x,y,w,h in regions:draw.rectangle((round(x),round(y),round(x+w)-1,round(y+h)-1),fill=255)
    return mask


def constrained_mask(mask,regions):
    from PIL import ImageChops
    return ImageChops.multiply(mask.convert('L'),region_union(mask.size,regions))


def infer_removal(image,regions,segmenter,cancelled=lambda:False,progress=lambda text:None):
    mask=Image.new('L',image.size)
    for i,(x,y,w,h) in enumerate(regions):
        if cancelled():raise InterruptedError('已结束自动识别')
        progress(f'本机识别照片区域 {i+1}/{len(regions)}')
        box=(round(x),round(y),round(x+w),round(y+h))
        part=segmenter.predict(image.crop(box)).resize((box[2]-box[0],box[3]-box[1]),Image.Resampling.LANCZOS)
        # Include the pale fringe around a detected person; the editor can
        # remove over-selected text/props before filling the background.
        part=part.point(lambda p:255 if p>=100 else 0).filter(ImageFilter.MaxFilter(7))
        from PIL import ImageChops
        mask.paste(ImageChops.lighter(mask.crop(box),part),(box[0],box[1]))
    if cancelled():raise InterruptedError('已结束自动识别')
    return constrained_mask(mask,regions)


def estimate_color(image,mask,rect):
    x,y,w,h=[round(v) for v in rect]
    region=image.crop((x,y,x+w,y+h)).convert('RGB')
    region.thumbnail((320,320),Image.Resampling.LANCZOS)
    alpha=mask.crop((x,y,x+w,y+h)).resize(region.size,Image.Resampling.NEAREST)
    a=np.asarray(region);keep=np.asarray(alpha)<8
    # Prefer the outer band to avoid selecting skin or clothing accidentally.
    border=np.zeros(keep.shape,bool)
    band=max(2,min(keep.shape)//8)
    border[:band]=True;border[-band:]=True;border[:,:band]=True;border[:,-band:]=True
    pixels=a[keep&border]
    if len(pixels)<20:pixels=a[keep]
    if len(pixels)<20:raise ValueError('可取样背景太少，请手动选底色或框选纹理取样区')
    return tuple(int(v) for v in np.median(pixels,axis=0))


def diffuse_background(image,coverage,color):
    """Coarse-to-fine harmonic colors; fills gradients, never invents texture."""
    visible=image.convert('RGBA')
    visible.putalpha(coverage.point(lambda v:0 if v else 255))
    longest=max(image.size)
    limit=min(512,longest)
    levels=[];edge=min(32,limit)
    while True:
        levels.append(edge)
        if edge==limit:break
        edge=min(limit,edge*2)
    current=None
    for level,edge in enumerate(levels):
        size=(max(1,round(image.width*edge/longest)),max(1,round(image.height*edge/longest)))
        # BOX keeps constant colors constant; a ringing filter can brighten
        # nearly transparent boundary pixels when RGBA is unpremultiplied.
        small=visible.resize(size,Image.Resampling.BOX)
        known=np.asarray(small.getchannel('A'))==255
        values=np.asarray(small.convert('RGB'),dtype=np.float32)
        if current is None:
            current=np.empty((size[1],size[0],3),dtype=np.float32);current[:]=color
        else:
            current=np.asarray(Image.fromarray(np.uint8(np.clip(np.rint(current),0,255))).resize(size,Image.Resampling.BICUBIC),dtype=np.float32).copy()
        current[known]=values[known]
        for _ in range(320 if level==0 else 70):
            padded=np.pad(current,((1,1),(1,1),(0,0)),mode='edge')
            average=(padded[:-2,1:-1]+padded[2:,1:-1]+padded[1:-1,:-2]+padded[1:-1,2:])*.25
            average[known]=values[known]
            current=average
    return Image.fromarray(np.uint8(np.clip(np.rint(current),0,255))).resize(image.size,Image.Resampling.BICUBIC)


def fill_background(image,mask,regions,recipes,cancelled=lambda:False,progress=lambda text:None):
    if len(regions)!=len(recipes):raise ValueError('背景填补设置与画框数量不匹配')
    page=image.convert('RGB').copy()
    mask=constrained_mask(mask,regions)
    for index,(rect,recipe) in enumerate(zip(regions,recipes)):
        if cancelled():raise InterruptedError('已结束背景修复')
        progress(f'本机修复背景 {index+1}/{len(regions)}')
        x,y,w,h=[round(v) for v in rect]
        coverage=mask.crop((x,y,x+w,y+h))
        if not coverage.getbbox():continue
        mode=recipe.get('mode','auto')
        if mode=='sample':
            sample=recipe.get('sample')
            if not sample:raise ValueError('请先为纹理填补框选一个无人物、无文字的取样区')
            sx,sy,sw,sh=[round(v) for v in sample]
            if min(sw,sh)<2 or min(sx,sy)<0 or sx+sw>image.width or sy+sh>image.height:raise ValueError('纹理取样区不正确')
            patch=image.crop((sx,sy,sx+sw,sy+sh)).convert('RGB')
            texture=Image.new('RGB',(w,h))
            for py in range(0,h,sh):
                for px in range(0,w,sw):texture.paste(patch,(px,py))
        else:
            color=recipe.get('color') if mode=='color' else estimate_color(image,mask,rect)
            if not isinstance(color,(list,tuple)) or len(color)!=3 or any(type(v)!=int or not 0<=v<=255 for v in color):
                raise ValueError('请选择有效底色')
            texture=Image.new('RGB',(w,h),tuple(color))
            if mode in ('auto','repair'):
                texture=diffuse_background(image.crop((x,y,x+w,y+h)),coverage,color)
                if mode=='repair':
                    from .repair import patch_repair
                    texture=patch_repair(image.crop((x,y,x+w,y+h)),coverage,texture,cancelled)
        # Pixels outside the removal mask are preserved exactly, including text
        # and frames. No blanket white fill or reconstruction of hidden lettering.
        page.paste(texture,(x,y),coverage)
    return page
