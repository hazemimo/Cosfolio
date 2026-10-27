from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Callable
import hashlib
import io
import json
import os
import re
import sys
import time
import uuid
import zipfile
import copy

import numpy as np
from PIL import Image, ImageOps, ImageEnhance, ImageCms
from .catalog import TEMPLATES, MAX_SLOTS

ROOT = Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parents[1]
DATA = ROOT / 'workspace'
MODEL = ROOT / 'models' / 'birefnet-general-lite.onnx'


def prepare_directories():
    for name in ('sources', 'masks', 'previews', 'projects', 'exports', 'reports'):
        (DATA / name).mkdir(parents=True, exist_ok=True)


def managed_rgb(image: Image.Image) -> Image.Image:
    profile=image.info.get('icc_profile')
    if profile:
        try:
            source=ImageCms.ImageCmsProfile(io.BytesIO(profile))
            description=ImageCms.getProfileDescription(source).lower()
            if 'srgb' not in description:
                return ImageCms.profileToProfile(image,source,ImageCms.createProfile('sRGB'),outputMode='RGB')
        except (OSError,ValueError,ImageCms.PyCMSError):
            pass
    return image.convert('RGB')


def srgb_profile():
    return ImageCms.ImageCmsProfile(ImageCms.createProfile('sRGB')).tobytes()


def oriented_image(path: str | Path, limit: int | None = None) -> Image.Image:
    with Image.open(path) as im:
        if limit and im.format=='JPEG':
            factor=min(1,limit/max(im.size))
            im.draft(None,(max(1,round(im.width*factor)),max(1,round(im.height*factor))))
        result=managed_rgb(ImageOps.exif_transpose(im))
        if limit:
            result.thumbnail((limit,limit),Image.Resampling.LANCZOS)
        return result


@dataclass
class Asset:
    id: str
    name: str
    source: str
    mask: str = ''
    initial_mask: str = ''
    seconds: float = 0
    width: int = 0
    height: int = 0


@dataclass
class Placement:
    asset_id: str = ''
    x: float = 0
    y: float = 0
    zoom: float = 1
    rotation: float = 0
    brightness: float = 1
    contrast: float = 1
    saturation: float = 1
    warmth: float = 0
    flip: bool = False
    dehalo: bool = True
    shadow: bool = True
    fit: str = 'template'
    edge_shift: float = 0
    edge_softness: float = 0
    shadow_opacity: float = .22
    shadow_blur: float = 9
    shadow_x: float = 8
    shadow_y: float = 10


@dataclass
class Project:
    template: str = 'party'
    title: str = 'XIAOXIAO'
    subtitle: str = '笑笑 / HALLOWEEN SPECIAL'
    footer: str = 'COSPLAY PHOTO COLLECTION   /   2026.10'
    body: str = ''
    accent: str = 'template'
    text_mode: str = 'original'
    assets: list[Asset] = field(default_factory=list)
    placements: list[Placement] = field(default_factory=lambda: [Placement() for _ in range(MAX_SLOTS)])
    layout: dict = field(default_factory=dict)
    pages: list[dict] = field(default_factory=list)
    active_page: int = 0
    page_numbers: bool = False
    credit: str = ''
    cover_page: int = 0

    def ensure_slots(self):
        while len(self.placements) < MAX_SLOTS:
            self.placements.append(Placement())

    def asset(self, key: str) -> Asset | None:
        return next((item for item in self.assets if item.id == key), None)

    def to_dict(self):
        data=asdict(self)
        data['pages']=self.page_records()
        return {'format': 'cosfolio', 'version': 4, **data}

    def capture_page(self):
        return {key:copy.deepcopy(getattr(self,key)) for key in
                ('template','title','subtitle','footer','body','accent','text_mode','placements','layout')}

    def page_records(self):
        records=copy.deepcopy(self.pages) or [self.capture_page()]
        records[self.active_page]=self.capture_page()
        for record in records:
            record['placements']=[asdict(p) if isinstance(p,Placement) else p for p in record['placements']]
        return records

    def select_page(self,index):
        if not 0<=index<self.page_count:raise ValueError('页面不存在')
        self.pages=self.page_records()
        self.active_page=index
        record=copy.deepcopy(self.pages[index])
        for key,value in record.items():
            setattr(self,key,[Placement(**p) for p in value] if key=='placements' else value)
        self.ensure_slots()

    @property
    def page_count(self):return max(1,len(self.pages))

    def add_page(self,duplicate=False):
        if self.page_count>=40:raise ValueError('每本写真最多支持 40 页')
        self.pages=self.page_records()
        record=self.capture_page() if duplicate else Project(template=self.template,title=self.title,subtitle=self.subtitle).capture_page()
        record['placements']=[asdict(p) if isinstance(p,Placement) else p for p in record['placements']]
        self.pages.insert(self.active_page+1,record)
        if self.cover_page>self.active_page:self.cover_page+=1
        self.select_page(self.active_page+1)

    def remove_page(self):
        if self.page_count==1:raise ValueError('至少保留一页')
        records=self.page_records()
        records.pop(self.active_page)
        index=min(self.active_page,len(records)-1)
        if self.cover_page==self.active_page:self.cover_page=index
        elif self.cover_page>self.active_page:self.cover_page-=1
        # select_page normally commits the current page. Install the target first.
        self.pages=records
        self.active_page=index
        for key,value in copy.deepcopy(records[index]).items():
            setattr(self,key,[Placement(**p) for p in value] if key=='placements' else value)

    def move_page(self,step):
        target=self.active_page+step
        if not 0<=target<self.page_count:return
        records=self.page_records()
        records[self.active_page],records[target]=records[target],records[self.active_page]
        if self.cover_page==self.active_page:self.cover_page=target
        elif self.cover_page==target:self.cover_page=self.active_page
        self.pages=records
        self.active_page=target

    def page_project(self,index):
        result=copy.deepcopy(self)
        result.select_page(index)
        return result

    def remap_asset(self,old,new):
        for place in self.placements:
            if place.asset_id==old:place.asset_id=new
        for record in self.pages:
            for place in record['placements']:
                if isinstance(place,Placement):
                    if place.asset_id==old:place.asset_id=new
                elif place['asset_id']==old:place['asset_id']=new

    @classmethod
    def from_dict(cls, data):
        if data.get('format') != 'cosfolio' or data.get('version') not in (1, 2, 3, 4):
            raise ValueError('不是受支持的 Cosfolio 工程文件')
        if data.get('template') not in TEMPLATES:
            raise ValueError('未知模板')
        # Old files without a shadow field keep their previous appearance.
        placements = [Placement(**({'shadow':False,**v})) for v in data['placements']]
        if not 1 <= len(placements) <= 20:
            raise ValueError('工程中的照片位置数量不正确')
        numeric = ('x','y','zoom','rotation','brightness','contrast','saturation','warmth',
                   'edge_shift','edge_softness','shadow_opacity','shadow_blur','shadow_x','shadow_y')
        for place in placements:
            if any(not np.isfinite(getattr(place, k)) for k in numeric):
                raise ValueError('工程中的位置参数不正确')
            if not .1 <= place.zoom <= 6 or not .1 <= place.brightness <= 3 or abs(place.rotation) > 180:
                raise ValueError('工程中的缩放或调色参数超出范围')
            if place.fit not in ('template','contain','cover'):
                raise ValueError('工程中的取景方式不正确')
            if not .1 <= place.contrast <= 3 or not 0 <= place.saturation <= 3 or not -1 <= place.warmth <= 1 or not isinstance(place.flip,bool):
                raise ValueError('工程中的人物调色参数不正确')
            if not (-8<=place.edge_shift<=8 and 0<=place.edge_softness<=8 and 0<=place.shadow_opacity<=1 and
                    0<=place.shadow_blur<=80 and abs(place.shadow_x)<=100 and abs(place.shadow_y)<=100):
                raise ValueError('工程中的边缘或投影参数不正确')
        while len(placements) < MAX_SLOTS:
            placements.append(Placement())
        accent=data.get('accent','template')
        if not isinstance(accent,str) or len(accent)>30:
            raise ValueError('工程中的配色设置不正确')
        # Earlier saved projects keep their existing typography. New projects and
        # the bundled demo use original page lettering until the user opts in.
        text_mode=data.get('text_mode','custom' if data.get('version')==1 else 'original')
        if text_mode not in ('original','custom'):
            raise ValueError('工程中的文字显示方式不正确')
        from .layout import validate_layout
        result=cls(template=data['template'], title=data.get('title', '')[:100],
                   subtitle=data.get('subtitle', '')[:150], footer=data.get('footer', '')[:200], accent=accent, text_mode=text_mode,
                   body=data.get('body','')[:4000],
                   assets=[Asset(**v) for v in data['assets']], placements=placements,
                   layout=validate_layout(data.get('layout',{}),data['template']),
                   page_numbers=bool(data.get('page_numbers',False)),credit=str(data.get('credit',''))[:200])
        records=data.get('pages',[])
        if not isinstance(records,list) or len(records)>40:raise ValueError('写真页数不正确')
        if records:
            for record in records:
                # Reuse single-page validation without recursive book structures.
                if not isinstance(record,dict):raise ValueError('写真页面数据不正确')
                single={**record,'format':'cosfolio','version':3,'assets':[],'pages':[]}
                page=cls.from_dict(single)
                result.pages.append(page.capture_page())
            active=data.get('active_page',0)
            if not isinstance(active,int) or not 0<=active<len(records):raise ValueError('当前页码不正确')
            result.active_page=active
        cover=data.get('cover_page',0)
        if type(cover)!=int or not 0<=cover<result.page_count:raise ValueError('工程封面页码不正确')
        result.cover_page=cover
        return result


def export_basename(title: str, subtitle: str) -> str:
    """A Windows-safe title + subtitle filename without directory separators."""
    def clean(value):
        value=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', value)
        value=re.sub(r'\s+', ' ', value).strip(' ._')
        return value
    name='_'.join(filter(None,(clean(title),clean(subtitle))))[:120].rstrip(' .')
    if not name:
        name='我的成品'
    if name.split('.')[0].upper() in {'CON','PRN','AUX','NUL',*[f'COM{i}' for i in range(1,10)],*[f'LPT{i}' for i in range(1,10)]}:
        name='作品_'+name
    return name


class LocalSegmenter:
    """ONNX inference with an explicit local path; no Hub or download code."""
    def __init__(self):
        self.session = None

    def load(self):
        if self.session is not None:
            return
        if not MODEL.is_file():
            raise FileNotFoundError('缺少本地抠图模型，请把离线模型包放入 models 文件夹。程序不会联网下载。')
        import onnxruntime as ort
        ort.disable_telemetry_events()
        opts = ort.SessionOptions()
        opts.intra_op_num_threads = min(8, os.cpu_count() or 4)
        opts.inter_op_num_threads = 1
        opts.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
        self.session = ort.InferenceSession(str(MODEL), opts, providers=['CPUExecutionProvider'])

    def predict(self, image: Image.Image) -> Image.Image:
        self.load()
        sample = np.asarray(image.resize((1024, 1024), Image.Resampling.BILINEAR), dtype=np.float32) / 255
        sample = (sample - np.array([.485, .456, .406], np.float32)) / np.array([.229, .224, .225], np.float32)
        tensor = np.ascontiguousarray(sample.transpose(2, 0, 1)[None])
        logits = self.session.run(None, {self.session.get_inputs()[0].name: tensor})[0].squeeze()
        alpha = 1 / (1 + np.exp(-np.clip(logits, -50, 50)))
        lo, hi = float(alpha.min()), float(alpha.max())
        if hi - lo < 1e-6:
            raise RuntimeError('这张照片没有识别到可用主体，请更换照片或导入透明 PNG。')
        alpha = (alpha - lo) / (hi - lo)
        target = image.copy()
        target.thumbnail((3072, 3072), Image.Resampling.LANCZOS)
        mask = Image.fromarray(np.uint8(np.clip(alpha * 255, 0, 255)))
        return mask.resize(target.size, Image.Resampling.LANCZOS)


def import_asset(path: str | Path, segmenter: LocalSegmenter, notify: Callable[[str], None] = lambda _: None) -> Asset:
    prepare_directories()
    path = Path(path)
    key = uuid.uuid4().hex[:16]
    notify('读取照片')
    # Original JPEG bytes are kept. EXIF orientation is applied consistently at render time.
    original = path.read_bytes()
    suffix = path.suffix.lower() if path.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp', '.tif', '.tiff') else '.img'
    source = DATA / 'sources' / (key + suffix)
    with Image.open(io.BytesIO(original)) as loaded:
        oriented = ImageOps.exif_transpose(loaded)
        alpha = oriented.getchannel('A') if 'A' in oriented.getbands() else None
        rgb = managed_rgb(oriented)
    start = time.monotonic()
    if alpha is None or alpha.getextrema() == (255, 255):
        notify('本机抠图中')
        # Decode the original, then release the large buffer after inference input is prepared.
        mask = segmenter.predict(rgb)
    else:
        notify('读取透明图层')
        mask = alpha.copy()
        mask.thumbnail((3072, 3072), Image.Resampling.LANCZOS)
    mask_file = DATA / 'masks' / (key + '.png')
    baseline = DATA / 'masks' / (key + '.original.png')
    # Commit local copies only after decoding and inference succeeded.
    try:
        source.write_bytes(original)
        mask.save(mask_file)
        mask.save(baseline)
    except OSError:
        for staged in (source,mask_file,baseline):
            staged.unlink(missing_ok=True)
        raise
    asset = Asset(key, path.name, str(source), str(mask_file), str(baseline),
                  round(time.monotonic() - start, 2), rgb.width, rgb.height)
    rgb.thumbnail((300, 360), Image.Resampling.LANCZOS)
    rgb.save(DATA / 'previews' / (key + '.jpg'), quality=88)
    return asset


def make_cutout(asset: Asset, limit: int, dehalo=True,edge_shift=0,edge_softness=0) -> Image.Image:
    image = oriented_image(asset.source,limit)
    from .finish import edge_alpha
    with Image.open(asset.mask) as loaded:
        mask=edge_alpha(loaded.convert('L'),edge_shift,edge_softness)
        mask=mask.resize(image.size, Image.Resampling.LANCZOS)
    if dehalo:
        # Only unmix a consistently bright studio backdrop. Other backgrounds are untouched.
        a = np.asarray(mask)
        rgb = np.array(image)
        corners = np.concatenate([rgb[:12, :12].reshape(-1, 3), rgb[:12, -12:].reshape(-1, 3),
                                  rgb[-12:, :12].reshape(-1, 3), rgb[-12:, -12:].reshape(-1, 3)])
        # Some subjects reach the bottom corners; use the brighter half of corner samples.
        corners = corners[np.mean(corners, axis=1) > 170]
        if len(corners) > 100 and corners.std(axis=0).max() < 28:
            bg = np.median(corners, axis=0)
            # Operate only on soft-edge pixels in small strips. A 60MP source
            # must not allocate multiple full-size float RGB intermediates.
            for y in range(0,image.height,256):
                coverage=a[y:y+256]
                edge=(coverage>6)&(coverage<250)
                if not edge.any():
                    continue
                alpha=coverage[edge].astype(np.float32)[:,None]/255
                tile=rgb[y:y+256]
                colors=tile[edge].astype(np.float32)
                corrected=(colors-(1-alpha)*bg)/np.maximum(alpha,.05)
                tile[edge]=np.clip(corrected,0,255).astype(np.uint8)
            image = Image.fromarray(rgb)
    image.putalpha(mask)
    bbox = mask.point(lambda p: 255 if p > 8 else 0).getbbox()
    return image.crop(bbox) if bbox else image


def save_project(project: Project, filename: str | Path):
    """Portable archive: source photos and masks travel with the project."""
    data = project.to_dict()
    target = Path(filename)
    temporary = target.with_suffix(target.suffix + '.writing')
    try:
        with zipfile.ZipFile(temporary, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=2) as archive:
            from .render import Renderer
            from .template_store import embed_templates
            cover=Renderer().render(project.page_project(project.cover_page),640)
            preview=io.BytesIO()
            cover.save(preview,format='JPEG',quality=80,icc_profile=srgb_profile())
            archive.writestr('cover.jpg',preview.getvalue())
            embed_templates(archive,[data['template']]+[page['template'] for page in data['pages']])
            for record in data['assets']:
                for field_name in ('source', 'mask', 'initial_mask'):
                    source = Path(record[field_name])
                    inner = f"assets/{record['id']}/{field_name}{source.suffix}"
                    archive.write(source, inner)
                    record[field_name] = inner
            masks={}
            for layout in [data['layout']]+[page['layout'] for page in data['pages']]:
                source=layout.get('foreground_mask')
                if source:
                    if source not in masks:
                        inner=f'layers/foreground-{len(masks):03d}.png'
                        archive.write(source,inner)
                        masks[source]=inner
                    layout['foreground_mask']=masks[source]
            archive.writestr('project.json', json.dumps(data, ensure_ascii=False, indent=2))
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def load_project(filename: str | Path) -> Project:
    prepare_directories()
    with zipfile.ZipFile(filename) as archive:
        raw = archive.read('project.json')
        if len(raw) > 2 * 1024 * 1024:
            raise ValueError('工程信息过大')
        from .template_store import restore_templates
        mapping=restore_templates(archive)
        data=json.loads(raw)
        for page in [data]+data.get('pages',[]):
            page['template']=mapping.get(page['template'],page['template'])
        project = Project.from_dict(data)
        if len(project.assets) > 100:
            raise ValueError('照片数量超出初版限制（100 张）')
        # Use our own destinations rather than extracting arbitrary archive paths.
        for asset in project.assets:
            new_id = uuid.uuid4().hex[:16]
            old_id = asset.id
            for field_name in ('source', 'mask', 'initial_mask'):
                member = getattr(asset, field_name)
                info = archive.getinfo(member)
                if info.file_size > 512 * 1024**2:
                    raise ValueError('工程中的素材过大')
                folder = 'sources' if field_name == 'source' else 'masks'
                suffix = Path(member).suffix
                dest = DATA / folder / f'{new_id}.{field_name}{suffix}'
                dest.write_bytes(archive.read(member))
                setattr(asset, field_name, str(dest))
            asset.id = new_id
            project.remap_asset(old_id,new_id)
        masks={}
        for layout in [project.layout]+[page['layout'] for page in project.pages]:
            member=layout.get('foreground_mask')
            if member:
                if member not in masks:
                    info=archive.getinfo(member)
                    if info.file_size>64*1024**2:raise ValueError('前景蒙版文件过大')
                    content=archive.read(member)
                    with Image.open(io.BytesIO(content)) as image:
                        if max(image.size)>10000:raise ValueError('前景蒙版尺寸过大')
                        image.verify()
                    dest=DATA/'masks'/f'foreground-{uuid.uuid4().hex[:16]}.png'
                    dest.write_bytes(content)
                    masks[member]=str(dest)
                layout['foreground_mask']=masks[member]
    return project
