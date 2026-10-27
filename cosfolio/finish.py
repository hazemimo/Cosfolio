"""Small offline finishing operations; no extra model or package is required."""
from PIL import Image,ImageFilter,ImageChops
import numpy as np
from .layout import frames


def edge_alpha(alpha,shift=0,softness=0,scale=1):
    if shift:
        # Filter size is odd; scale settings against source mask pixels.
        radius=max(1,round(abs(shift)*scale))
        alpha=alpha.filter((ImageFilter.MaxFilter if shift>0 else ImageFilter.MinFilter)(radius*2+1))
    if softness:alpha=alpha.filter(ImageFilter.GaussianBlur(softness*scale))
    return alpha


def match_lighting(photo,background):
    """Conservative suggested brightness/warmth, applied only after a user click."""
    sample=photo.copy()
    sample.thumbnail((180,180))
    rgba=np.asarray(sample.convert('RGBA'))
    foreground=rgba[:,:,:3][rgba[:,:,3]>220]
    if len(foreground)<20:raise ValueError('主体有效区域过少，无法匹配')
    bg=background.convert('RGB')
    bg.thumbnail((180,180))
    target=np.asarray(bg).reshape(-1,3)
    fg=np.median(foreground,axis=0)
    dest=np.median(target,axis=0)
    brightness=float(np.clip((dest.mean()+50)/(fg.mean()+50),.85,1.15))
    warmth=float(np.clip(((dest[0]-dest[2])-(fg[0]-fg[2]))/96,-.35,.35))
    return brightness,warmth


def quality_report(project,long_edge):
    """Report geometric sampling estimates, without promising recovered detail."""
    from .catalog import TEMPLATES
    t=TEMPLATES[project.template]
    scale=long_edge/max(t['size'])
    records=[]
    for i,(_,_,w,h) in enumerate(frames(project)):
        place=project.placements[i]
        asset=project.asset(place.asset_id)
        if not asset:continue
        # Dimensions of opaque subject, not the unused original photo backdrop.
        with Image.open(asset.mask) as mask:
            box=mask.point(lambda v:255 if v>8 else 0).getbbox()
            sx=(box[2]-box[0])/mask.width if box else 1
            sy=(box[3]-box[1])/mask.height if box else 1
        source_w,source_h=max(1,asset.width*sx),max(1,asset.height*sy)
        fit=place.fit
        if fit=='contain':factor=min(w*scale/source_w,h*scale/source_h)*.95
        elif fit=='cover':factor=max(w*scale/source_w,h*scale/source_h)
        elif t.get('fit')=='height':factor=h*scale/source_h*1.04
        else:
            factor=max(w*scale/source_w,h*scale/source_h) if i==0 and project.template!='card' else min(w*scale/source_w,h*scale/source_h)*1.13
            if i==2:factor=h*scale/source_h*1.10
            if project.template=='card':factor=h*scale/source_h*1.08
        enlargement=factor*place.zoom
        records.append({'slot':i+1,'name':asset.name,'scale':round(enlargement,2),
                        'status':'建议换更清晰的原图' if enlargement>1.5 else '有放大' if enlargement>1 else '原图像素充足'})
    return {'size':(round(t['size'][0]*scale),round(t['size'][1]*scale)),
            'template_size':t['size'],'template_enlarged':bool(t.get('plate') and scale>1),
            'photos':records}
