"""Trial local template wizard: regions, editable removal mask and sampled fill."""
import copy
from pathlib import Path
from tempfile import TemporaryDirectory
from PIL import Image,ImageChops
from PySide6.QtCore import Qt,QRectF,QPointF,Signal,QThread
from PySide6.QtGui import QPainter,QColor,QPen
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QComboBox,
                              QTabWidget,QWidget,QLineEdit,QFileDialog,QMessageBox,QCheckBox,
                              QProgressBar,QColorDialog)
from .viewer import ImageViewport
from .core import oriented_image,Asset
from .template_fill import infer_removal,fill_background,constrained_mask
from .template_store import save_template
from .history import bind_history


class RegionCanvas(ImageViewport):
    editStarted=Signal()
    fileDropped=Signal(str)
    regionsChanged=Signal()
    selected=Signal(int)
    sampled=Signal(object)

    def __init__(self):
        super().__init__()
        self.regions=[];self.index=0;self.mode='move';self.drag=None;self.drag_rect=None
        self.setMinimumSize(500,360)
        self.setAcceptDrops(True)

    def dragEnterEvent(self,event):
        from .app import dropped_images
        if self.isEnabled() and dropped_images(event.mimeData()):event.acceptProposedAction()

    def dragMoveEvent(self,event):self.dragEnterEvent(event)

    def dropEvent(self,event):
        from .app import dropped_images
        paths=dropped_images(event.mimeData())
        if self.isEnabled() and paths:self.fileDropped.emit(paths[0]);event.acceptProposedAction()

    def image_point(self,position):
        x,y=self.point(position)
        return max(0,min(self.image_size[0],x)),max(0,min(self.image_size[1],y))

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.picture is None:
            p=QPainter(self);p.setPen(QColor('#75889c'));p.drawText(self.rect(),Qt.AlignmentFlag.AlignCenter,'把场刊图片拖到这里导入\n或点击上方“导入”按钮');return
        painter=QPainter(self);painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale=self.paper.width()/self.image_size[0]
        for i,(x,y,w,h) in enumerate(self.regions):
            rect=QRectF(self.paper.x()+x*scale,self.paper.y()+y*scale,w*scale,h*scale)
            painter.setPen(QPen(QColor('#2878bf' if i==self.index else '#29a99b'),2))
            painter.setBrush(Qt.BrushStyle.NoBrush);painter.drawRect(rect)
            painter.drawText(rect.topLeft()+QPointF(7,21),str(i+1))
            if i==self.index:painter.fillRect(QRectF(rect.right()-5,rect.bottom()-5,10,10),QColor('#2878bf'))
        if self.drag_rect:
            x,y,w,h=self.drag_rect
            painter.setPen(QPen(QColor('#f0b341'),2,Qt.PenStyle.DashLine));painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(self.paper.x()+x*scale,self.paper.y()+y*scale,w*scale,h*scale))

    def mousePressEvent(self,event):
        super().mousePressEvent(event)
        if self.panning or self.picture is None or event.button()!=Qt.MouseButton.LeftButton or not self.paper.contains(event.position()):return
        x,y=self.image_point(event.position());self.setFocus()
        if self.mode in ('add','sample'):
            if self.mode=='add':self.editStarted.emit()
            self.drag=(x,y,None,self.mode);return
        scale=self.paper.width()/self.image_size[0]
        for i,(sx,sy,w,h) in reversed(list(enumerate(self.regions))):
            handle=abs(x-sx-w)<12/scale and abs(y-sy-h)<12/scale
            if handle or sx<=x<=sx+w and sy<=y<=sy+h:
                self.editStarted.emit()
                self.index=i;self.selected.emit(i)
                self.drag=(x,y,(sx,sy,w,h),'resize' if handle else 'move');self.update();return

    def mouseMoveEvent(self,event):
        if self.panning:return super().mouseMoveEvent(event)
        if not self.drag or not event.buttons()&Qt.MouseButton.LeftButton:return
        x,y=self.image_point(event.position());ox,oy,old,mode=self.drag
        if mode in ('add','sample'):self.drag_rect=(min(x,ox),min(y,oy),abs(x-ox),abs(y-oy))
        else:
            sx,sy,w,h=old;bw,bh=self.image_size
            if mode=='resize':w,h=max(2,min(bw-sx,w+x-ox)),max(2,min(bh-sy,h+y-oy))
            else:sx,sy=max(0,min(bw-w,sx+x-ox)),max(0,min(bh-h,sy+y-oy))
            self.regions[self.index]=[round(v) for v in (sx,sy,w,h)]
        self.update()

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        if not self.drag:return
        mode=self.drag[3];rect=self.drag_rect
        self.drag=None;self.drag_rect=None
        if mode in ('add','sample'):
            if rect and min(rect[2:])>=3:
                rect=[round(v) for v in rect]
                if mode=='sample':self.sampled.emit(rect)
                elif len(self.regions)<5:
                    if self.regions==[[0,0,*self.image_size]]:self.regions=[rect]
                    else:self.regions.append(rect)
                    self.index=len(self.regions)-1;self.regionsChanged.emit()
        else:self.regionsChanged.emit()
        self.update()


class RemovalWorker(QThread):
    ready=Signal(object)
    error=Signal(str)
    progress=Signal(str)
    cancelled=Signal()

    def __init__(self,image,regions,segmenter,parent=None):
        super().__init__(parent)
        self.image=image.copy();self.regions=copy.deepcopy(regions);self.segmenter=segmenter

    def run(self):
        try:self.ready.emit(infer_removal(self.image,self.regions,self.segmenter,self.isInterruptionRequested,self.progress.emit))
        except InterruptedError:self.cancelled.emit()
        except Exception as exc:self.error.emit(str(exc))


class FillWorker(RemovalWorker):
    def __init__(self,image,mask,regions,recipes,parent):
        super().__init__(image,regions,None,parent);self.mask=mask.copy();self.recipes=copy.deepcopy(recipes)
    def run(self):
        try:self.ready.emit(fill_background(self.image,self.mask,self.regions,self.recipes,self.isInterruptionRequested,self.progress.emit))
        except InterruptedError:self.cancelled.emit()
        except Exception as exc:self.error.emit(str(exc))


class TemplateWizard(QDialog):
    def __init__(self,segmenter,parent=None):
        super().__init__(parent)
        self.segmenter=segmenter;self.worker=None;self.busy=False;self.closing_result=None
        self.temp=TemporaryDirectory(prefix='cosfolio-template-');self.work=Path(self.temp.name)
        self.source_path=None;self.image=None;self.mask=None;self.prepared=None;self.plate=None
        self.recipes=[];self.sample_target=0;self.created_key=None;self.syncing=False
        self.history=[];self.redo_history=[];self.restoring=False
        self.setAcceptDrops(True)
        self.setWindowTitle('新建模板 · 离线试用向导');self.resize(1120,920);self.setMinimumSize(900,720)
        root=QVBoxLayout(self)
        title=QLabel('把新的场刊扫描页制作成模板');title.setObjectName('section');root.addWidget(title)
        hint=QLabel('先划定照片区域，再识别主体、校正绿色蒙版和填补背景。原页会保留作参考。')
        hint.setWordWrap(True);root.addWidget(hint)
        self.tabs=QTabWidget();root.addWidget(self.tabs,1)
        pages=[]
        for text in ('1 · 导入与照片位置','2 · 去人蒙版','3 · 底图预览'):
            page=QWidget();layout=QVBoxLayout(page);pages.append(layout);self.tabs.addTab(page,text)
        first=pages[0]
        bar=QHBoxLayout();self.import_btn=QPushButton('导入场刊扫描页 / 照片…');self.import_btn.clicked.connect(self.choose_source)
        bar.addWidget(self.import_btn);bar.addStretch();first.addLayout(bar)
        self.source_note=QLabel('可直接拖入 JPG、PNG、WebP 或 TIFF 图片；一次导入一页。');self.source_note.setWordWrap(True);first.addWidget(self.source_note)
        bar=QHBoxLayout();self.region_selector=QComboBox();self.region_selector.currentIndexChanged.connect(self.select_region);bar.addWidget(self.region_selector,1)
        self.mode=QComboBox();self.mode.addItem('移动 / 调整画框','move');self.mode.addItem('拖动绘制新画框','add')
        self.mode.currentIndexChanged.connect(lambda _:setattr(self.source_canvas,'mode',self.mode.currentData()));bar.addWidget(self.mode)
        self.remove_btn=QPushButton('删除画框');self.remove_btn.clicked.connect(self.remove_region);bar.addWidget(self.remove_btn)
        self.full_btn=QPushButton('恢复整页单框');self.full_btn.clicked.connect(self.full_region);bar.addWidget(self.full_btn);first.addLayout(bar)
        self.source_canvas=RegionCanvas();self.source_canvas.regionsChanged.connect(self.regions_changed)
        self.source_canvas.selected.connect(self.region_selector.setCurrentIndex);self.source_canvas.sampled.connect(self.sample_selected)
        self.source_canvas.fileDropped.connect(self.import_path);self.source_canvas.editStarted.connect(self.push_history)
        first.addWidget(self.source_canvas,1)
        hint=QLabel('多格页请分别画框，最多 5 个位置；首次绘制会替换整页默认框。拖右下角调尺寸，滚轮缩放，Alt＋拖动画面。')
        hint.setWordWrap(True);first.addWidget(hint)
        self.already_clean=QCheckBox('这张底图已经去人，跳过自动识别');self.already_clean.toggled.connect(self.clean_toggled);first.addWidget(self.already_clean)
        second=pages[1]
        hint=QLabel('绿色表示将移除的内容。识别可能包含道具或插图，请结合原页检查；文字和边框应保留。')
        hint.setWordWrap(True);second.addWidget(hint)
        bar=QHBoxLayout()
        self.infer_btn=QPushButton('自动识别主体');self.infer_btn.clicked.connect(self.start_inference)
        self.mask_btn=QPushButton('手动添加/减去蒙版');self.mask_btn.clicked.connect(self.edit_mask)
        self.clear_btn=QPushButton('清除标记');self.clear_btn.clicked.connect(self.clear_mask)
        self.subject_btn=QPushButton('另存透明主体 PNG…');self.subject_btn.clicked.connect(self.export_subject)
        for button in (self.infer_btn,self.mask_btn,self.clear_btn,self.subject_btn):bar.addWidget(button)
        second.addLayout(bar)
        self.mask_canvas=ImageViewport();self.mask_canvas.setMinimumHeight(360);second.addWidget(self.mask_canvas,1)
        self.show_original=QCheckBox('对照原页');self.show_original.toggled.connect(self.refresh_mask);second.addWidget(self.show_original)
        third=pages[2]
        bar=QHBoxLayout();bar.addWidget(QLabel('模板名称'));self.name=QLineEdit();self.name.setMaxLength(80);self.name.textChanged.connect(self.update_state);bar.addWidget(self.name,1);third.addLayout(bar)
        bar=QHBoxLayout();self.fill_selector=QComboBox();self.fill_selector.currentIndexChanged.connect(self.select_fill);bar.addWidget(self.fill_selector,1)
        self.auto_btn=QPushButton('周围底色过渡');self.auto_btn.clicked.connect(self.use_auto)
        self.repair_btn=QPushButton('细节图块修复');self.repair_btn.clicked.connect(self.use_repair)
        self.color_btn=QPushButton('指定底色…');self.color_btn.clicked.connect(self.choose_color)
        self.sample_btn=QPushButton('框选纹理取样区');self.sample_btn.clicked.connect(self.choose_sample)
        for button in (self.repair_btn,self.auto_btn,self.color_btn,self.sample_btn):bar.addWidget(button)
        third.addLayout(bar)
        self.recipe_note=QLabel('');self.recipe_note.setWordWrap(True);third.addWidget(self.recipe_note)
        bar=QHBoxLayout();self.preview_btn=QPushButton('更新底图预览');self.preview_btn.clicked.connect(self.build_preview)
        self.prepared_btn=QPushButton('导入已去人底图…');self.prepared_btn.clicked.connect(self.choose_prepared)
        bar.addWidget(self.preview_btn);bar.addWidget(self.prepared_btn);bar.addStretch();third.addLayout(bar)
        self.clone_btn=QPushButton('仿制修补接缝…');self.clone_btn.clicked.connect(self.clone_repair);bar.addWidget(self.clone_btn)
        self.preview_canvas=ImageViewport();self.preview_canvas.setMinimumHeight(360);third.addWidget(self.preview_canvas,1)
        hint=QLabel('填补用于简单底色和重复纹理，不会推测被遮住的文字或复杂图案。结果不理想时，可返回修正蒙版或导入处理好的底图。')
        hint.setWordWrap(True);third.addWidget(hint)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.hide();root.addWidget(self.progress)
        self.status=QLabel('工作底图最长边 3072 像素，原扫描文件保留。');self.status.setWordWrap(True);root.addWidget(self.status)
        bar=QHBoxLayout()
        self.undo_btn=QPushButton('撤销 · Ctrl+Z');self.undo_btn.clicked.connect(self.undo);bar.addWidget(self.undo_btn)
        self.redo_btn=QPushButton('重做');self.redo_btn.clicked.connect(self.redo);bar.addWidget(self.redo_btn)
        for title,callback in [('适合窗口',lambda:self.current_canvas().fit_view()),('100%',lambda:self.current_canvas().actual_size())]:
            button=QPushButton(title);button.clicked.connect(callback);bar.addWidget(button)
        self.stop_btn=QPushButton('结束识别');self.stop_btn.clicked.connect(self.stop_inference);self.stop_btn.hide();bar.addWidget(self.stop_btn)
        bar.addStretch()
        self.back_btn=QPushButton('上一步');self.back_btn.clicked.connect(lambda:self.tabs.setCurrentIndex(max(0,self.tabs.currentIndex()-1)));bar.addWidget(self.back_btn)
        self.next_btn=QPushButton('下一步');self.next_btn.clicked.connect(self.next_step);bar.addWidget(self.next_btn)
        self.save_btn=QPushButton('保存到模板库并使用');self.save_btn.setObjectName('primary');self.save_btn.clicked.connect(self.save_result);bar.addWidget(self.save_btn)
        self.cancel_btn=QPushButton('取消');self.cancel_btn.clicked.connect(self.reject);bar.addWidget(self.cancel_btn);root.addLayout(bar)
        self.tabs.currentChanged.connect(self.update_state)
        bind_history(self,self.undo,self.redo)
        self.update_state()

    def current_canvas(self):return (self.source_canvas,self.mask_canvas,self.preview_canvas)[self.tabs.currentIndex()]

    def choose_source(self):
        path,_=QFileDialog.getOpenFileName(self,'导入新的原页','','图片 (*.jpg *.jpeg *.png *.webp *.tif *.tiff)')
        if path:self.import_path(path)

    def import_path(self,path):
        if self.busy:return
        try:self.load_source(path)
        except Exception as exc:QMessageBox.warning(self,'无法导入原页',str(exc))

    def dragEnterEvent(self,event):
        from .app import dropped_images
        if not self.busy and dropped_images(event.mimeData()):event.acceptProposedAction()

    def dragMoveEvent(self,event):self.dragEnterEvent(event)

    def dropEvent(self,event):
        from .app import dropped_images
        paths=dropped_images(event.mimeData())
        if not self.busy and paths:self.import_path(paths[0]);event.acceptProposedAction()

    def snapshot(self):
        return dict(image=self.image,source_path=self.source_path,mask=self.mask,prepared=self.prepared,plate=self.plate,
                    regions=copy.deepcopy(self.source_canvas.regions),recipes=copy.deepcopy(self.recipes),
                    index=self.source_canvas.index,clean=self.already_clean.isChecked(),name=self.name.text())

    def push_history(self):
        if self.restoring or self.busy:return
        self.history.append(self.snapshot());self.history=self.history[-20:];self.redo_history.clear()
        while len(self.history)>1:
            images={id(s[k]):s[k] for s in self.history for k in ('image','mask','prepared','plate') if s[k] is not None}
            if sum(v.width*v.height*len(v.getbands()) for v in images.values())<=128*1024**2:break
            self.history.pop(0)

    def restore(self,state):
        from .app import pixmap
        self.restoring=True;self.syncing=True
        for key in ('image','source_path','mask','prepared','plate','recipes'):setattr(self,key,state[key])
        self.source_canvas.regions=copy.deepcopy(state['regions']);self.source_canvas.index=state['index']
        self.already_clean.setChecked(state['clean']);self.name.setText(state['name'])
        for combo in (self.region_selector,self.fill_selector):
            combo.clear();combo.addItems([f'照片位置 {i+1}' for i in range(len(self.recipes))]);combo.setCurrentIndex(state['index'])
        if self.image is not None:
            self.source_canvas.set_picture(pixmap(self.image),reset=False);self.refresh_mask()
            self.source_note.setText(f'{self.source_path.name} · 工作底图 {self.image.width} × {self.image.height}')
        else:
            self.source_canvas.picture=None;self.mask_canvas.picture=None;self.source_canvas.update();self.mask_canvas.update()
            self.source_note.setText('可直接拖入 JPG、PNG、WebP 或 TIFF 图片；一次导入一页。')
        self.preview_canvas.picture=None
        if self.plate is not None:self.preview_canvas.set_picture(pixmap(self.plate),reset=False)
        self.syncing=False;self.restoring=False;self.select_fill(state['index']);self.update_state()

    def undo(self):
        if not self.busy and self.history:
            self.redo_history.append(self.snapshot());self.restore(self.history.pop())

    def redo(self):
        if not self.busy and self.redo_history:
            self.history.append(self.snapshot());self.restore(self.redo_history.pop())

    def load_source(self,path):
        from .app import pixmap
        if Path(path).stat().st_size>128*1024**2:raise ValueError('试用版请使用 128 MB 以内的扫描图片')
        image=oriented_image(path,3072)
        if min(image.size)<32:raise ValueError('图片尺寸过小')
        self.push_history()
        self.image=image;self.source_path=Path(path)
        self.image.save(self.work/'source.png')
        self.name.setText(Path(path).stem[:80]);self.source_canvas.set_picture(pixmap(image))
        self.source_note.setText(f'{Path(path).name} · 工作底图 {image.width} × {image.height}；原扫描文件保留作参考。')
        self.already_clean.blockSignals(True);self.already_clean.setChecked(False);self.already_clean.blockSignals(False)
        self.prepared=None;self.source_canvas.regions=[[0,0,*self.image.size]];self.source_canvas.index=0;self.regions_changed();self.tabs.setCurrentIndex(0)

    def full_region(self):
        if self.image is None:return
        self.push_history()
        self.source_canvas.regions=[[0,0,*self.image.size]];self.source_canvas.index=0;self.regions_changed()

    def remove_region(self):
        if self.busy or not self.source_canvas.regions:return
        self.push_history()
        self.source_canvas.regions.pop(self.source_canvas.index)
        self.source_canvas.index=max(0,min(self.source_canvas.index,len(self.source_canvas.regions)-1));self.regions_changed()

    def regions_changed(self):
        self.recipes=[{'mode':'repair'} for _ in self.source_canvas.regions]
        self.mask=Image.new('L',self.image.size) if self.image else None;self.prepared=None;self.plate=None
        self.syncing=True
        for combo in (self.region_selector,self.fill_selector):
            combo.clear();combo.addItems([f'照片位置 {i+1}' for i in range(len(self.recipes))]);combo.setCurrentIndex(self.source_canvas.index)
        if self.already_clean.isChecked():self.prepared=self.image.copy()
        self.syncing=False;self.refresh_mask();self.select_fill(self.fill_selector.currentIndex());self.source_canvas.update();self.update_state()

    def select_region(self,index):
        if self.syncing or index<0:return
        self.source_canvas.index=index;self.source_canvas.update()
        self.fill_selector.setCurrentIndex(index)

    def select_fill(self,index):
        if self.syncing or not 0<=index<len(self.recipes):return
        self.region_selector.setCurrentIndex(index)
        recipe=self.recipes[index]
        description={'repair':'匹配本画框的未标记背景图块，减少颜色涂抹；复杂装饰仍需检查，可用仿制修补收尾。','auto':'根据当前画框周围的可见背景平滑过渡底色，不重建被遮挡的图案。','color':'指定底色：'+str(recipe.get('color','')),
                     'sample':'重复使用原页取样区的纹理，适合纸纹、布纹等简单背景。'}
        self.recipe_note.setText(description[recipe['mode']])

    def clean_toggled(self,checked):
        if self.image is None or self.restoring:return
        self.push_history()
        self.history[-1]['clean']=not checked
        self.prepared=self.image.copy() if checked else None;self.plate=None;self.update_state()

    def next_step(self):
        if self.tabs.currentIndex()==0:
            if self.image is None or not self.source_canvas.regions:return
            if self.already_clean.isChecked():self.tabs.setCurrentIndex(2);self.build_preview()
            else:
                self.tabs.setCurrentIndex(1)
                if self.mask is not None and not self.mask.getbbox():self.start_inference()
        elif self.tabs.currentIndex()==1:
            self.tabs.setCurrentIndex(2);self.build_preview()

    def start_inference(self):
        if self.busy or self.image is None or not self.source_canvas.regions:return
        self.busy=True;self.progress.show();self.stop_btn.show();self.closing_result=None
        self.worker=RemovalWorker(self.image,self.source_canvas.regions,self.segmenter,self)
        self.worker.ready.connect(self.inferred);self.worker.error.connect(self.inference_error)
        self.worker.progress.connect(self.status.setText);self.worker.cancelled.connect(lambda:self.status.setText('已结束自动识别，可重试或手工标记'))
        self.worker.finished.connect(self.inference_finished);self.update_state();self.worker.start()

    def inferred(self,mask):
        if self.closing_result is not None:return
        self.busy=False;self.push_history();self.busy=True
        self.mask=mask;self.prepared=None;self.plate=None;self.refresh_mask()
        self.status.setText('识别完成，请检查绿色区域，再到下一步预览背景填补。' if mask.getbbox() else '未找到主体，可手工标记或调整照片区域后重试。')

    def inference_error(self,message):
        if self.closing_result is None:self.status.setText('识别未完成：'+message+'；仍可手工标记。')

    def inference_finished(self):
        self.busy=False;self.progress.hide();self.stop_btn.hide();self.update_state()
        if self.closing_result is not None:self.done(self.closing_result)

    def stop_inference(self):
        if self.worker and self.worker.isRunning():
            self.worker.requestInterruption();self.status.setText('正在完成当前区域后结束识别…')

    def refresh_mask(self,*_):
        from .app import pixmap
        if self.image is None:return
        image=self.image.convert('RGBA')
        if self.mask is not None and not self.show_original.isChecked():
            tint=Image.new('RGBA',image.size,(45,215,140,0));tint.putalpha(self.mask.point(lambda v:round(v*.52)));image.alpha_composite(tint)
        self.mask_canvas.set_picture(pixmap(image),reset=False)

    def edit_mask(self):
        if self.busy or self.image is None or not self.source_canvas.regions:return
        from .app import MaskDialog
        self.image.save(self.work/'source.png')
        mask_path=self.work/'removal.png';self.mask.save(mask_path)
        asset=Asset('removal','待移除的主体',str(self.work/'source.png'),str(mask_path),str(mask_path))
        dialog=MaskDialog(asset,self);dialog.setWindowTitle('手动添加/减去蒙版 · 绿色内容将被移除')
        dialog.layout().itemAt(0).widget().setText('保留文字、边框与装饰，标记需要移除的人物')
        dialog.layout().itemAt(1).widget().setText('画笔添加绿色蒙版；橡皮擦减去误识别的气球、文字或装饰。Ctrl＋Z 撤销，Ctrl＋Y 重做。')
        dialog.erase.setText('减去蒙版 · 橡皮擦');dialog.keep.setText('添加蒙版 · 画笔')
        for button in dialog.findChildren(QPushButton):
            if button.text()=='恢复自动抠图':button.setText('恢复本次修改前')
        dialog.canvas.overlay_mode=True;dialog.canvas.rebuild();dialog.mode('keep')
        try:
            if dialog.exec()==QDialog.DialogCode.Accepted:
                self.push_history()
                self.mask=constrained_mask(dialog.canvas.mask,self.source_canvas.regions)
                self.prepared=None;self.plate=None;self.refresh_mask();self.update_state()
        finally:dialog.deleteLater()

    def clear_mask(self):
        if self.image is not None:
            self.push_history()
            self.mask=Image.new('L',self.image.size);self.prepared=None;self.plate=None;self.refresh_mask();self.update_state()

    def use_auto(self):
        index=self.fill_selector.currentIndex()
        if index>=0:self.push_history();self.recipes[index]={'mode':'auto'};self.prepared=None;self.plate=None;self.select_fill(index);self.update_state()

    def use_repair(self):
        index=self.fill_selector.currentIndex()
        if index>=0:self.push_history();self.recipes[index]={'mode':'repair'};self.prepared=None;self.plate=None;self.select_fill(index);self.update_state()

    def choose_color(self):
        index=self.fill_selector.currentIndex()
        if index<0:return
        color=QColorDialog.getColor(QColor('#eeeeee'),self,'为当前照片区域指定底色')
        if color.isValid():
            self.push_history()
            self.recipes[index]={'mode':'color','color':[color.red(),color.green(),color.blue()]}
            self.prepared=None;self.plate=None;self.select_fill(index);self.update_state()

    def choose_sample(self):
        if not self.recipes:return
        self.sample_target=self.fill_selector.currentIndex();self.source_canvas.mode='sample';self.tabs.setCurrentIndex(0)
        self.status.setText('在原页拖动框选一块无人物、无文字的背景纹理，供当前照片位置填补。')

    def sample_selected(self,rect):
        if not 0<=self.sample_target<len(self.recipes):return
        x,y,w,h=rect
        if self.mask is not None and self.mask.crop((x,y,x+w,y+h)).getbbox():
            self.status.setText('取样区包含已标记主体，请另选一块干净背景纹理。');return
        self.push_history();self.recipes[self.sample_target]={'mode':'sample','sample':rect}
        self.prepared=None;self.plate=None;self.source_canvas.mode=self.mode.currentData();self.tabs.setCurrentIndex(2)
        self.select_fill(self.sample_target);self.build_preview()

    def choose_prepared(self):
        if self.image is None:return
        path,_=QFileDialog.getOpenFileName(self,'导入已经去人的同版底图','','图片 (*.jpg *.jpeg *.png *.webp *.tif *.tiff)')
        if path:
            try:
                image=oriented_image(path,3072)
                if abs(image.width/image.height-self.image.width/self.image.height)>.01:raise ValueError('底图宽高比与原页不同，请使用同一版面的去人底图')
                self.push_history()
                self.prepared=image.resize(self.image.size,Image.Resampling.LANCZOS);self.build_preview()
            except Exception as exc:QMessageBox.warning(self,'无法导入底图',str(exc))

    def build_preview(self):
        if self.image is None or self.busy:return
        try:
            if self.prepared is not None:self.preview_ready(self.prepared.copy())
            elif self.mask is not None and self.mask.getbbox():
                self.busy=True;self.closing_result=None;self.progress.show();self.stop_btn.show();self.status.setText('正在本机匹配背景图块…')
                self.worker=FillWorker(self.image,self.mask,self.source_canvas.regions,self.recipes,self)
                self.worker.ready.connect(self.preview_ready);self.worker.progress.connect(self.status.setText)
                self.worker.error.connect(lambda message:self.status.setText('背景修复未完成：'+message))
                self.worker.cancelled.connect(lambda:self.status.setText('已结束背景修复，可修改蒙版后重试'))
                self.worker.finished.connect(self.inference_finished);self.worker.start()
            else:raise ValueError('请先自动识别或手工标记主体；已去人的底图可勾选跳过识别')
        except Exception as exc:self.plate=None;self.status.setText('尚不能生成底图：'+str(exc))
        self.update_state()

    def preview_ready(self,plate):
        if self.closing_result is not None:return
        from .app import pixmap
        self.plate=plate;self.preview_canvas.set_picture(pixmap(self.plate),reset=False)
        self.status.setText('修复完成。检查气球和文字；有接缝时可用“仿制修补接缝”局部取样收尾。');self.update_state()

    def clone_repair(self):
        if self.plate is None or self.busy:return
        from .clone_editor import CloneDialog
        from .app import pixmap
        dialog=CloneDialog(self.image,self.plate,self.mask,self.source_canvas.regions,self)
        try:
            if dialog.exec()==QDialog.DialogCode.Accepted:
                self.push_history();self.plate=dialog.canvas.result.copy();self.prepared=self.plate
                self.preview_canvas.set_picture(pixmap(self.plate),reset=False);self.update_state()
        finally:dialog.deleteLater()

    def export_subject(self):
        if self.mask is None or not self.mask.getbbox():return
        path,_=QFileDialog.getSaveFileName(self,'另存被移除的主体','主体.png','PNG 图片 (*.png)')
        if path:
            try:
                if not path.lower().endswith('.png'):path+='.png'
                image=self.image.convert('RGBA');image.putalpha(self.mask);image.crop(self.mask.getbbox()).save(path)
                self.status.setText('透明主体已保存：'+path)
            except Exception as exc:QMessageBox.warning(self,'无法保存主体',str(exc))

    def save_result(self):
        if self.busy or self.plate is None or not self.name.text().strip():return
        try:
            self.created_key=save_template(self.name.text(),self.source_path,self.plate,self.mask,self.source_canvas.regions,
                                           {'fills':self.recipes,'prepared':self.prepared is not None})
            self.accept()
        except Exception as exc:QMessageBox.warning(self,'无法保存模板',str(exc))

    def update_state(self,*_):
        if not hasattr(self,'save_btn'):return
        has=self.image is not None;regions=bool(self.source_canvas.regions)
        if self.plate is None and self.preview_canvas.picture is not None:
            self.preview_canvas.picture=None;self.preview_canvas.update()
        for widget in (self.import_btn,self.region_selector,self.mode,self.remove_btn,self.full_btn,self.already_clean,
                       self.infer_btn,self.mask_btn,self.clear_btn,self.subject_btn,self.fill_selector,self.auto_btn,
                       self.color_btn,self.sample_btn,self.repair_btn,self.preview_btn,self.prepared_btn,self.name,self.show_original):
            widget.setEnabled(not self.busy and (has or widget is self.import_btn))
        for widget in (self.infer_btn,self.mask_btn,self.fill_selector,self.auto_btn,self.color_btn,self.sample_btn):widget.setEnabled(not self.busy and regions)
        self.back_btn.setEnabled(not self.busy and self.tabs.currentIndex()>0)
        self.next_btn.setVisible(self.tabs.currentIndex()<2);self.next_btn.setEnabled(not self.busy and has and regions)
        self.save_btn.setVisible(self.tabs.currentIndex()==2)
        self.save_btn.setEnabled(not self.busy and self.plate is not None and regions and bool(self.name.text().strip()))
        self.subject_btn.setEnabled(not self.busy and self.mask is not None and bool(self.mask.getbbox()))
        self.source_canvas.setEnabled(not self.busy)
        self.clone_btn.setEnabled(not self.busy and self.plate is not None)
        self.undo_btn.setEnabled(not self.busy and bool(self.history));self.redo_btn.setEnabled(not self.busy and bool(self.redo_history))

    def done(self,result):
        if self.worker and self.worker.isRunning():
            self.closing_result=result;self.stop_inference();return
        for canvas in (self.source_canvas,self.mask_canvas,self.preview_canvas):canvas.picture=None
        self.temp.cleanup();super().done(result)

    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.closing_result=QDialog.DialogCode.Rejected;self.stop_inference();event.ignore()
        else:super().closeEvent(event)
