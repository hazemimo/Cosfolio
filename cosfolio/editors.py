"""Project-local frame editing with the same coordinates used for delivery."""
import copy
from PySide6.QtCore import Qt,QPointF,QRectF,Signal
from PySide6.QtGui import QPainter,QPen,QColor
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QComboBox,
                              QDoubleSpinBox,QDialogButtonBox,QPushButton)
from .viewer import ImageViewport
from .catalog import TEMPLATES
from .layout import frames,radii
from .history import bind_history


class FrameViewport(ImageViewport):
    editStarted=Signal()
    edited=Signal()
    selected=Signal(int)

    def __init__(self,project):
        super().__init__()
        self.project=project
        self.index=0
        self.drag=None
        self.setMinimumSize(540,450)

    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale=self.paper.width()/self.image_size[0]
        for i,(x,y,w,h) in enumerate(frames(self.project)):
            rect=QRectF(self.paper.x()+x*scale,self.paper.y()+y*scale,w*scale,h*scale)
            painter.setPen(QPen(QColor('#377fbc' if i==self.index else '#24b9ab'),2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            r=radii(self.project)[i]*scale
            painter.drawRoundedRect(rect,r,r)
            painter.drawText(rect.topLeft()+QPointF(6,20),str(i+1))
            if i==self.index:painter.fillRect(QRectF(rect.right()-6,rect.bottom()-6,12,12),QColor('#377fbc'))

    def mousePressEvent(self,event):
        super().mousePressEvent(event)
        if self.panning or event.button()!=Qt.MouseButton.LeftButton:return
        x,y=self.point(event.position())
        scale=self.paper.width()/self.image_size[0]
        for i,(sx,sy,w,h) in reversed(list(enumerate(frames(self.project)))):
            handle=abs(x-sx-w)<12/scale and abs(y-sy-h)<12/scale
            if handle or sx<=x<=sx+w and sy<=y<=sy+h:
                self.editStarted.emit()
                self.index=i
                self.drag=(x,y,(sx,sy,w,h),handle)
                self.selected.emit(i)
                self.update()
                return

    def mouseMoveEvent(self,event):
        if self.panning:return super().mouseMoveEvent(event)
        if not self.drag or not event.buttons() & Qt.MouseButton.LeftButton:return
        x,y=self.point(event.position())
        ox,oy,(sx,sy,w,h),resize=self.drag
        bw,bh=self.image_size
        if resize:w,h=max(1,min(bw-sx,w+x-ox)),max(1,min(bh-sy,h+y-oy))
        else:sx,sy=max(0,min(bw-w,sx+x-ox)),max(0,min(bh-h,sy+y-oy))
        self.project.layout['frames'][self.index]=[round(sx,2),round(sy,2),round(w,2),round(h,2)]
        self.edited.emit()
        self.update()

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        self.drag=None


class FrameDialog(QDialog):
    def __init__(self,project,parent=None):
        super().__init__(parent)
        from .app import pixmap
        from .render import template_plate
        self.project=copy.deepcopy(project)
        self.project.layout['frames']=[list(rect) for rect in frames(project)]
        self.project.layout['radii']=list(radii(project))
        self.syncing=False
        self.history=[];self.redo_history=[]
        self.setWindowTitle('校准照片画框 · 当前写真页')
        self.resize(1000,850)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('拖动画框移动，拖右下角方块调整尺寸；滚轮缩放，Alt＋拖动画面。'))
        layout.addWidget(QLabel('仅修改当前页，原版底图保留。照片裁切、选中框和导出共用这些边界。'))
        row=QHBoxLayout()
        self.selector=QComboBox()
        self.selector.addItems(TEMPLATES[project.template]['labels'])
        row.addWidget(self.selector)
        self.fields=[]
        for title,maximum in [('X',TEMPLATES[project.template]['size'][0]),('Y',TEMPLATES[project.template]['size'][1]),
                              ('宽',TEMPLATES[project.template]['size'][0]),('高',TEMPLATES[project.template]['size'][1]),('圆角',300)]:
            row.addWidget(QLabel(title))
            spin=QDoubleSpinBox()
            spin.setRange(0,maximum)
            spin.setDecimals(1)
            spin.valueChanged.connect(self.update_rect)
            row.addWidget(spin)
            self.fields.append(spin)
        layout.addLayout(row)
        self.canvas=FrameViewport(self.project)
        self.canvas.set_picture(pixmap(template_plate(project.template,max(TEMPLATES[project.template]['size']),project.text_mode)))
        self.canvas.edited.connect(self.sync_fields)
        self.canvas.editStarted.connect(self.push_history)
        self.canvas.selected.connect(self.selector.setCurrentIndex)
        self.selector.currentIndexChanged.connect(self.select)
        layout.addWidget(self.canvas,1)
        row=QHBoxLayout()
        for title,callback in [('撤销 · Ctrl+Z',self.undo),('重做',self.redo)]:
            button=QPushButton(title);button.clicked.connect(callback);row.addWidget(button)
        for title,callback in [('适合窗口',self.canvas.fit_view),('100%',self.canvas.actual_size),('恢复模板画框',self.reset)]:
            button=QPushButton(title);button.clicked.connect(callback);row.addWidget(button)
        row.addStretch()
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('应用画框')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject)
        row.addWidget(buttons);layout.addLayout(row)
        self.sync_fields()
        bind_history(self,self.undo,self.redo)

    def push_history(self):
        self.history.append(copy.deepcopy(self.project.layout));self.history=self.history[-40:];self.redo_history.clear()

    def undo(self):
        if self.history:
            self.redo_history.append(copy.deepcopy(self.project.layout));self.project.layout=self.history.pop();self.sync_fields();self.canvas.update()

    def redo(self):
        if self.redo_history:
            self.history.append(copy.deepcopy(self.project.layout));self.project.layout=self.redo_history.pop();self.sync_fields();self.canvas.update()

    def select(self,index):
        self.canvas.index=index
        self.sync_fields();self.canvas.update()

    def sync_fields(self):
        self.syncing=True
        i=self.selector.currentIndex()
        for spin,value in zip(self.fields,[*frames(self.project)[i],radii(self.project)[i]]):spin.setValue(value)
        self.syncing=False

    def update_rect(self):
        if self.syncing:return
        self.push_history()
        x,y,w,h,r=[spin.value() for spin in self.fields]
        bw,bh=TEMPLATES[self.project.template]['size']
        x,y=min(x,bw-1),min(y,bh-1)
        self.project.layout['frames'][self.selector.currentIndex()]=[x,y,max(1,min(w,bw-x)),max(1,min(h,bh-y))]
        self.project.layout['radii'][self.selector.currentIndex()]=r
        self.sync_fields();self.canvas.update()

    def reset(self):
        self.push_history()
        t=TEMPLATES[self.project.template]
        self.project.layout['frames']=[list(rect) for rect in t['slots']]
        self.project.layout['radii']=list(t.get('radii',[0]*len(t['slots'])))
        self.sync_fields();self.canvas.update()

    def done(self,result):
        self.canvas.picture=None
        super().done(result)
