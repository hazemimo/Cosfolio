"""Bounded local exemplar repair using only unmarked pixels from this frame."""
import numpy as np
from PIL import Image,ImageFilter


def patch_repair(image,mask,initial,cancelled=lambda:False):
    size=image.size;scale=min(1,384/max(size))
    work=(max(12,round(size[0]*scale)),max(12,round(size[1]*scale)))
    original=np.asarray(image.resize(work,Image.Resampling.LANCZOS).convert('RGB'),dtype=np.float32)
    hole=mask.resize(work,Image.Resampling.NEAREST)
    bad=np.asarray(hole)>0;h,w=bad.shape;r=4
    forbidden=np.asarray(hole.filter(ImageFilter.MaxFilter(2*r+3)))>0
    valid=~forbidden;valid[:r]=False;valid[-r:]=False;valid[:,:r]=False;valid[:,-r:]=False
    # Mirrored candidates can continue rounded decoration from its intact half.
    # Original visible pixels are never mirrored in the output.
    source=np.concatenate((original,original[:,::-1]),axis=1)
    valid=np.concatenate((valid,valid[:,::-1]),axis=1);sw=source.shape[1]
    sy,sx=np.nonzero(valid);ty,tx=np.nonzero(bad)
    if len(sy)<30 or not len(ty):return initial
    rng=np.random.default_rng(71)
    take=rng.integers(len(sy),size=len(ty));fy,fx=sy[take],sx[take]
    current=np.asarray(initial.resize(work,Image.Resampling.LANCZOS),dtype=np.float32).copy()
    offsets=[(dy,dx) for dy in (-r,0,r) for dx in (-r,0,r)]
    target_y=[np.clip(ty+dy,0,h-1) for dy,dx in offsets]
    target_x=[np.clip(tx+dx,0,w-1) for dy,dx in offsets]
    def cost(cy,cx):
        result=np.zeros(len(ty),np.float32)
        for yy,xx,(dy,dx) in zip(target_y,target_x,offsets):
            diff=current[yy,xx]-source[np.clip(cy+dy,0,h-1),np.clip(cx+dx,0,sw-1)]
            weight=np.where(bad[yy,xx],1.,3.).astype(np.float32)
            result+=np.sum(diff*diff,axis=1)*weight
        return result
    for iteration in range(12):
        if cancelled():raise InterruptedError('已结束背景修复')
        best=cost(fy,fx)
        def consider(cy,cx):
            nonlocal fy,fx,best
            cy=np.clip(cy,r,h-r-1);cx=np.clip(cx,r,sw-r-1)
            allowed=valid[cy,cx];score=cost(cy,cx)
            better=allowed&(score<best)
            fy[better]=cy[better];fx[better]=cx[better];best[better]=score[better]
        for _ in range(2):
            take=rng.integers(len(sy),size=len(ty));consider(sy[take],sx[take])
        gridy,gridx=np.indices((h,w));gridy[ty,tx]=fy;gridx[ty,tx]=fx
        for dy,dx in ((0,1),(1,0),(0,-1),(-1,0)):
            yy=np.clip(ty+dy,0,h-1);xx=np.clip(tx+dx,0,w-1)
            consider(gridy[yy,xx]-dy,gridx[yy,xx]-dx)
        radius=max(h,w)//2
        while radius>=1:
            consider(fy+rng.integers(-radius,radius+1,len(ty)),fx+rng.integers(-radius,radius+1,len(ty)))
            radius//=2
        # Patch voting shares coherent neighbors while keeping source pixels fixed.
        gridy[ty,tx]=fy;gridx[ty,tx]=fx
        voted=np.zeros((len(ty),3),np.float32);weights=np.zeros(len(ty),np.float32)
        for dy,dx in offsets:
            yy=np.clip(ty-dy,0,h-1);xx=np.clip(tx-dx,0,w-1)
            cy=np.clip(gridy[yy,xx]+dy,0,h-1);cx=np.clip(gridx[yy,xx]+dx,0,sw-1)
            weight=np.where(bad[yy,xx],1.,0.)
            voted+=source[cy,cx]*weight[:,None];weights+=weight
        current[ty,tx]=voted/np.maximum(weights[:,None],1)
    repaired=Image.fromarray(np.uint8(np.clip(np.rint(current),0,255))).resize(size,Image.Resampling.LANCZOS)
    result=image.convert('RGB').copy();result.paste(repaired,(0,0),mask)
    return result
