"""Shared page geometry for native preview, hit testing and final compositing."""
from functools import lru_cache
from PIL import Image,ImageDraw
from .catalog import TEMPLATES


def frames(project):
    return project.layout.get('frames') or TEMPLATES[project.template]['slots']


def radii(project):
    return project.layout.get('radii') or TEMPLATES[project.template].get('radii',[0]*len(frames(project)))


def pixel_box(rect,ratio):
    x,y,w,h=rect
    # Round endpoints, not widths separately: adjacent edges share one coordinate.
    left,top=round(x*ratio),round(y*ratio)
    return left,top,max(1,round((x+w)*ratio)-left),max(1,round((y+h)*ratio)-top)


def _frame_mask(width,height,radius):
    mask=Image.new('L',(width,height),255)
    if radius:
        # Supersample only small masks; high-resolution export is already smooth.
        factor=3 if max(width,height)<1800 else 1
        mask=Image.new('L',(width*factor,height*factor))
        ImageDraw.Draw(mask).rounded_rectangle((0,0,width*factor-1,height*factor-1),
                                               radius=min(radius,width/2,height/2)*factor,fill=255)
        if factor>1:mask=mask.resize((width,height),Image.Resampling.LANCZOS)
    return mask


_preview_mask=lru_cache(maxsize=24)(_frame_mask)
def frame_mask(width,height,radius):
    return _preview_mask(width,height,radius) if max(width,height)<=1600 else _frame_mask(width,height,radius)


def validate_layout(layout,template):
    import math
    if not isinstance(layout,dict):raise ValueError('分层模板设置不正确')
    size=TEMPLATES[template]['size']
    rectangles=layout.get('frames',[])
    if rectangles:
        if len(rectangles)!=len(TEMPLATES[template]['slots']):raise ValueError('照片画框数量不正确')
        for rect in rectangles:
            if not isinstance(rect,(list,tuple)) or len(rect)!=4 or any(not isinstance(v,(int,float)) or not math.isfinite(v) for v in rect):
                raise ValueError('照片画框坐标不正确')
            x,y,w,h=rect
            if min(x,y)<0 or min(w,h)<1 or x+w>size[0]+.01 or y+h>size[1]+.01:
                raise ValueError('照片画框超出页面')
    values=layout.get('radii',[])
    if values and (len(values)!=len(TEMPLATES[template]['slots']) or any(not isinstance(v,(int,float)) or not math.isfinite(v) or v<0 or v>max(size) for v in values)):
        raise ValueError('画框圆角设置不正确')
    for key in ('background','photos','foreground'):
        if key in layout and not isinstance(layout[key],bool):raise ValueError('图层显示设置不正确')
    if not isinstance(layout.get('foreground_mask',''),str):raise ValueError('前景蒙版路径不正确')
    return layout
