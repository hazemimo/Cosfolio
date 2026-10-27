"""Bounded tile compositing for high-resolution photo placement."""
import math
from PIL import Image,ImageFilter,ImageChops
from .core import make_cutout
from .layout import frames,radii,pixel_box,frame_mask


def fit_factor(photo,placement,template,index,pw,ph,key):
    if placement.fit=='contain':factor=min(pw/photo.width,ph/photo.height)*.95
    elif placement.fit=='cover':factor=max(pw/photo.width,ph/photo.height)
    elif template.get('fit')=='height':factor=ph/photo.height*1.04
    else:
        factor=max(pw/photo.width,ph/photo.height) if index==0 and key!='card' else min(pw/photo.width,ph/photo.height)*1.13
        if index==2:factor=ph/photo.height*1.10
        if key=='card':factor=ph/photo.height*1.08
    return factor*placement.zoom


def composite_tiles(page,project,index,long_edge,adjust,cancelled=lambda:False):
    from .catalog import TEMPLATES
    template=TEMPLATES[project.template]
    placement=project.placements[index]
    asset=project.asset(placement.asset_id)
    ratio=long_edge/max(template['size'])
    px,py,pw,ph=pixel_box(frames(project)[index],ratio)
    photo=make_cutout(asset,max(4000,long_edge),placement.dehalo,placement.edge_shift,placement.edge_softness)
    factor=fit_factor(photo,placement,template,index,pw,ph,project.template)
    nw,nh=max(1,round(photo.width*factor)),max(1,round(photo.height*factor))
    # Antialias reductions before affine sampling; enlargements never allocate
    # an enormous off-page image, even with a 6x placement in an 8000px page.
    if factor<1:photo=photo.resize((nw,nh),Image.Resampling.LANCZOS)
    photo=adjust(photo,placement)
    fx,fy=nw/photo.width,nh/photo.height
    angle=math.radians(placement.rotation)
    co,si=math.cos(angle),math.sin(angle)
    rw=math.ceil(abs(nw*co)+abs(nh*si))
    rh=math.ceil(abs(nw*si)+abs(nh*co))
    dx=round((pw-rw)/2+placement.x*pw)
    dy=round(((ph-rh)/2 if placement.fit=='contain' else ph*.025)+placement.y*ph)
    cx,cy=dx+rw/2,dy+rh/2
    radius=round(radii(project)[index]*ratio)
    clip=frame_mask(pw,ph,radius) if radius else None
    def sample(x,y,w,h,offset_x=0,offset_y=0):
        tx,ty=x-cx-offset_x,y-cy-offset_y
        coeff=(co/fx,si/fx,(co*tx+si*ty)/fx+photo.width/2,
               -si/fy,co/fy,(-si*tx+co*ty)/fy+photo.height/2)
        return photo.transform((w,h),Image.Transform.AFFINE,coeff,Image.Resampling.BICUBIC)
    for y in range(0,ph,1024):
        for x in range(0,pw,1024):
            if cancelled():raise InterruptedError('已取消导出')
            w,h=min(1024,pw-x),min(1024,ph-y)
            tile=sample(x,y,w,h)
            if placement.shadow:
                blur=placement.shadow_blur*ratio
                pad=math.ceil(blur*3)+2
                shadow_alpha=sample(x-pad,y-pad,w+pad*2,h+pad*2,
                                    round(placement.shadow_x*ratio),round(placement.shadow_y*ratio)).getchannel('A')
                shadow_alpha=shadow_alpha.filter(ImageFilter.GaussianBlur(blur)).crop((pad,pad,pad+w,pad+h))
                shadow=Image.new('RGBA',(w,h),(33,22,48,0))
                shadow.putalpha(shadow_alpha.point(lambda a:round(a*placement.shadow_opacity)))
                shadow.alpha_composite(tile)
                tile=shadow
            if clip is not None:
                tile.putalpha(ImageChops.multiply(tile.getchannel('A'),clip.crop((x,y,x+w,y+h))))
            page.alpha_composite(tile,(px+x,py+y))
