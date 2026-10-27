"""Synchronized photo comparison with lightweight previews and native-pixel detail tiles."""
from __future__ import annotations
import math
from PIL import Image
from PySide6.QtCore import Qt,QPointF,QRectF,Signal,QThread,QTimer
from PySide6.QtGui import QPixmap,QImage,QPainter,QColor
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QCheckBox,QSplitter,QWidget
from .core import oriented_image,managed_rgb
from .viewer import ImageViewport
from .history import bind_history


def oriented_size(path):
    with Image.open(path) as image:
        w,h=image.size;orientation=image.getexif().get(274,1)
    return (h,w) if orientation in (5,6,7,8) else (w,h)


def preview_image(asset, originals=True):
    result=oriented_image(asset.source,1600)
    if not originals:
        with Image.open(asset.mask) as image:alpha=image.convert('L').resize(result.size,Image.Resampling.LANCZOS)
        result.putalpha(alpha)
    return result


def native_region(asset, box, originals=True):
    """Crop before color conversion/rotation, avoiding full-size RGB/Qt copies."""
    with Image.open(asset.source) as source:
        w,h=source.size;orientation=source.getexif().get(274,1)
        ow,oh=(h,w) if orientation in (5,6,7,8) else (w,h)
        left,top,right,bottom=box
        def inverse(x,y):
            return {1:(x,y),2:(w-x,y),3:(w-x,h-y),4:(x,h-y),
                    5:(y,x),6:(y,h-x),7:(w-y,h-x),8:(w-y,x)}.get(orientation,(x,y))
        corners=[inverse(x,y) for x in (left,right) for y in (top,bottom)]
        raw=(min(x for x,y in corners),min(y for x,y in corners),max(x for x,y in corners),max(y for x,y in corners))
        region=source.crop(raw)
        operation={2:Image.Transpose.FLIP_LEFT_RIGHT,3:Image.Transpose.ROTATE_180,
                   4:Image.Transpose.FLIP_TOP_BOTTOM,5:Image.Transpose.TRANSPOSE,
                   6:Image.Transpose.ROTATE_270,7:Image.Transpose.TRANSVERSE,8:Image.Transpose.ROTATE_90}.get(orientation)
        if operation is not None:region=region.transpose(operation)
        region=managed_rgb(region)
    if not originals:
        with Image.open(asset.mask) as image:
            mw,mh=image.size
            mb=(max(0,math.floor(left*mw/ow)),max(0,math.floor(top*mh/oh)),
                min(mw,math.ceil(right*mw/ow)),min(mh,math.ceil(bottom*mh/oh)))
            alpha=image.convert('L').crop(mb).resize(region.size,Image.Resampling.LANCZOS)
        region.putalpha(alpha)
    return region


def qt_pixmap(image):
    image=image.convert('RGBA')
    qimage=QImage(image.tobytes(),image.width,image.height,image.width*4,QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage)


class ImageReadJob(QThread):
    ready=Signal(object)
    failed=Signal(str,int)

    def __init__(self,asset,originals,box,generation,parent):
        super().__init__(parent);self.asset=asset;self.originals=originals;self.box=box;self.generation=generation

    def run(self):
        try:
            if self.isInterruptionRequested():return
            image=native_region(self.asset,self.box,self.originals) if self.box else preview_image(self.asset,self.originals)
            if self.isInterruptionRequested():image.close();return
            self.ready.emit((image,self.box,self.generation))
        except Exception as exc:self.failed.emit(str(exc),self.generation)


class CompareViewport(ImageViewport):
    viewChanged=Signal()
    detailChanged=Signal(str)

    def __init__(self,asset,parent=None):
        super().__init__(parent);self.asset=asset;self.originals=True;self.native_size=oriented_size(asset.source)
        self.image_size=self.native_size;self.worker=None;self.pending=None;self.generation=0;self.closing=False
        self.tile=None;self.tile_box=None;self.tile_timer=QTimer(self);self.tile_timer.setSingleShot(True)
        self.tile_timer.setInterval(100);self.tile_timer.timeout.connect(self.request_detail)
        self.setMinimumSize(280,300)

    def load_mode(self,originals):
        self.originals=originals;self.tile=None;self.tile_box=None;self.picture=None;self.update()
        self.queue_read(None)

    def queue_read(self,box):
        if self.closing:return
        self.generation+=1
        request=(self.originals,box,self.generation)
        if self.worker is not None:
            self.pending=request;self.worker.requestInterruption();return
        self.begin_read(request)

    def begin_read(self,request):
        originals,box,generation=request;worker=ImageReadJob(self.asset,originals,box,generation,self);self.worker=worker
        self.detailChanged.emit('读取原始像素…' if box else '载入照片…')
        worker.ready.connect(self.received)
        worker.failed.connect(lambda message,token:self.detailChanged.emit('无法读取：'+message) if token==self.generation else None)
        def done():
            self.worker=None;worker.deleteLater()
            if not self.closing and self.pending is not None:
                pending=self.pending;self.pending=None;self.begin_read(pending)
        worker.finished.connect(done);worker.start()

    def received(self,result):
        image,box,generation=result
        try:
            if self.closing or generation!=self.generation:return
            if box:
                self.tile=qt_pixmap(image);self.tile_box=box;self.detailChanged.emit('原始像素')
            else:
                self.picture=qt_pixmap(image);self.image_size=self.native_size;self.update_transform()
                self.detailChanged.emit('快速预览');self.tile_timer.start()
            self.update()
        finally:image.close()

    def request_detail(self):
        if self.closing or self.picture is None:return
        self.update_transform();scale=self.fit_scale*self.zoom
        if self.paper.width()<=self.picture.width()*1.02:
            self.detailChanged.emit('原始像素' if (self.picture.width(),self.picture.height())==self.native_size else '快速预览');return
        iw,ih=self.native_size
        left=max(0,math.floor((-32-self.paper.left())/scale));top=max(0,math.floor((-32-self.paper.top())/scale))
        right=min(iw,math.ceil((self.width()+32-self.paper.left())/scale));bottom=min(ih,math.ceil((self.height()+32-self.paper.top())/scale))
        if right<=left or bottom<=top:return
        box=(left,top,right,bottom)
        if box!=self.tile_box:self.queue_read(box)
        else:self.detailChanged.emit('原始像素')

    def view_state(self):
        self.update_transform();x,y=self.point(QPointF(self.rect().center()));w,h=self.native_size
        return (self.fit_scale*self.zoom,x/w,y/h)

    def apply_view(self,state):
        scale,x,y=state;self.update_transform();self.zoom=max(.05,min(1000,scale/self.fit_scale))
        scale=self.fit_scale*self.zoom;w,h=self.native_size
        self.pan=QPointF(self.width()/2-x*w*scale-(self.width()-w*scale)/2,
                        self.height()/2-y*h*scale-(self.height()-h*scale)/2)
        self.update_transform();self.update();self.tile_timer.start()

    def zoom_at(self,value,anchor=None):
        self.update_transform();anchor=QPointF(self.rect().center()) if anchor is None else anchor
        x,y=self.point(anchor);self.zoom=max(.05,min(1000,float(value)));scale=self.fit_scale*self.zoom
        w,h=self.native_size
        self.pan=QPointF(anchor.x()-x*scale-(self.width()-w*scale)/2,anchor.y()-y*scale-(self.height()-h*scale)/2)
        self.update_transform();self.update();self.tile_timer.start();self.viewChanged.emit()

    def fit_view(self):
        super().fit_view();self.tile_timer.start();self.viewChanged.emit()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.setFocus();self.panning=True;self.pan_previous=event.position();self.setCursor(Qt.CursorShape.ClosedHandCursor);event.accept()
        else:super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        was_panning=self.panning;super().mouseMoveEvent(event)
        if was_panning:self.tile_timer.start();self.viewChanged.emit()

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'tile_timer'):self.tile_timer.start()

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.tile is not None and self.tile_box:
            scale=self.fit_scale*self.zoom;l,t,r,b=self.tile_box
            target=QRectF(self.paper.left()+l*scale,self.paper.top()+t*scale,(r-l)*scale,(b-t)*scale)
            painter=QPainter(self);painter.setBrushOrigin(self.paper.topLeft());painter.fillRect(target,self.checker)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(target,self.tile,QRectF(self.tile.rect()));painter.end()

    def stop(self):
        self.closing=True;self.pending=None;self.tile_timer.stop()
        if self.worker is not None:self.worker.requestInterruption();self.worker.wait()
        self.picture=None;self.tile=None


class CompareDialog(QDialog):
    favoriteRequested=Signal(str)

    def __init__(self,library,keys,parent=None):
        if len(keys)!=2:raise ValueError('请选择两张照片进行对比')
        super().__init__(parent);self.library=library;self.keys=list(keys);self.syncing=False;self.chosen=None
        self.setWindowTitle('Cosfolio · 双图对比选片');self.resize(1280,850);self.setMinimumSize(900,620)
        root=QVBoxLayout(self);root.setContentsMargins(22,18,22,16);root.setSpacing(12)
        title=QLabel('双图对比 · 把喜欢的那一张留下来');title.setObjectName('section');root.addWidget(title)
        bar=QHBoxLayout();self.linked=QCheckBox('同步缩放与移动');self.linked.setChecked(True);bar.addWidget(self.linked)
        self.originals=QCheckBox('查看原照片');self.originals.setChecked(True);self.originals.toggled.connect(self.change_mode);bar.addWidget(self.originals);bar.addStretch()
        for name,callback in [('适合窗口',self.fit_all),('100% 原始像素',self.actual_all)]:
            button=QPushButton(name);button.clicked.connect(callback);bar.addWidget(button)
        root.addLayout(bar);split=QSplitter(Qt.Orientation.Horizontal);split.setChildrenCollapsible(False);root.addWidget(split,1)
        self.views=[];self.favorite_buttons=[];self.details=[]
        for index,key in enumerate(keys):
            asset=library.asset_view(key);pane=QWidget();layout=QVBoxLayout(pane);layout.setContentsMargins(0,0,0,0)
            row=QHBoxLayout();name=QLabel(('A' if index==0 else 'B')+'  /  '+asset.name);name.setWordWrap(True);name.setToolTip(asset.name);row.addWidget(name,1)
            favorite=QPushButton('收藏');favorite.setMinimumWidth(120);favorite.clicked.connect(lambda checked=False,k=key:self.toggle_favorite(k));row.addWidget(favorite);self.favorite_buttons.append(favorite);layout.addLayout(row)
            view=CompareViewport(asset,self);layout.addWidget(view,1);self.views.append(view)
            info=QLabel('载入照片…');info.setObjectName('muted');layout.addWidget(info);self.details.append(info)
            view.zoomChanged.connect(lambda percent,i=index:self.update_info(i))
            view.detailChanged.connect(lambda value,i=index:self.update_info(i,value))
            view.viewChanged.connect(lambda i=index:self.synchronize(i));split.addWidget(pane)
        footer=QHBoxLayout();hint=QLabel('滚轮缩放 · 拖动平移 · 高倍放大在后台读取原始像素');hint.setObjectName('muted');hint.setWordWrap(True);footer.addWidget(hint,1)
        for index in range(2):
            b=QPushButton('选中 '+('A' if index==0 else 'B'));b.clicked.connect(lambda checked=False,k=keys[index]:self.choose(k));footer.addWidget(b)
        close=QPushButton('结束对比');close.clicked.connect(self.reject);footer.addWidget(close);root.addLayout(footer)
        self.detail_text=['载入照片…','载入照片…'];self.refresh_favorites()
        bind_history(self,self.undo,self.redo)
        self.linked.toggled.connect(lambda checked:self.synchronize(0) if checked else None)
        self.change_mode(True)

    def update_info(self,index,value=None):
        if value is not None:self.detail_text[index]=value
        view=self.views[index];self.details[index].setText(f'{view.fit_scale*view.zoom*100:.0f}% · {self.detail_text[index]}')

    def refresh_favorites(self):
        for key,button in zip(self.keys,self.favorite_buttons):
            row=self.library.get(key);button.setText('★ 已收藏' if row and row['favorite'] else '☆ 收藏')

    def toggle_favorite(self,key):
        self.favoriteRequested.emit(key);self.refresh_favorites()

    def synchronize(self,index):
        if self.syncing or not self.linked.isChecked():return
        self.syncing=True
        try:self.views[1-index].apply_view(self.views[index].view_state())
        finally:self.syncing=False

    def fit_all(self):
        self.syncing=True
        try:
            for view in self.views:view.fit_view()
        finally:self.syncing=False

    def actual_all(self):
        self.syncing=True
        try:
            for view in self.views:view.actual_size()
        finally:self.syncing=False

    def change_mode(self,value):
        for view in self.views:view.load_mode(value)

    def choose(self,key):self.chosen=key;self.accept()

    def undo(self):
        parent=self.parent()
        if parent is not None and hasattr(parent,'undo'):parent.undo();self.refresh_favorites()

    def redo(self):
        parent=self.parent()
        if parent is not None and hasattr(parent,'redo'):parent.redo();self.refresh_favorites()

    def done(self,result):
        for view in self.views:view.stop()
        super().done(result)
