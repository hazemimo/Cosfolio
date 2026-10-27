"""Local clone brush for remaining repair seams, bounded to photo frames."""
import math
import numpy as np
from PIL import Image
from PySide6.QtCore import Qt,QPointF,Signal
from PySide6.QtGui import QPainter,QPen,QColor
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QSlider,QDialogButtonBox
from .viewer import ImageViewport
from .history import bind_history
from .template_fill import region_union


class CloneCanvas(ImageViewport):
    status=Signal(str)
    def __init__(self,original,result,mask,regions):
        super().__init__()
        self.original=original.convert('RGB');self.result=result.convert('RGB').copy();self.mask=mask.copy()
        self.allowed=region_union(result.size,regions)
        self.radius=36;self.source=None;self.offset=None;self.previous=None;self.original_view=False
        self.history=[];self.redo_history=[];self.cursor_point=None;self.rebuild()

    def rebuild(self):
        from .app import pixmap
        self.set_picture(pixmap(self.original if self.original_view else self.result),reset=False)

    def remember(self):
        self.history.append(self.result.copy());self.redo_history.clear()
        while len(self.history)>1 and (len(self.history)>20 or len(self.history)*self.result.width*self.result.height*3>96*1024**2):self.history.pop(0)

    def undo(self):
        if self.history:self.redo_history.append(self.result);self.result=self.history.pop();self.rebuild()

    def redo(self):
        if self.redo_history:self.history.append(self.result);self.result=self.redo_history.pop();self.rebuild()

    def stamp(self,x,y):
        if self.offset is None:return
        r=self.radius;w,h=self.result.size
        x0,y0=max(0,round(x-r)),max(0,round(y-r));x1,y1=min(w,round(x+r+1)),min(h,round(y+r+1))
        if x1<=x0 or y1<=y0:return
        dx,dy=self.offset;sx0,sy0=x0+dx,y0+dy;sx1,sy1=x1+dx,y1+dy
        yy,xx=np.mgrid[y0:y1,x0:x1]
        weight=np.clip((1-np.sqrt((xx-x)**2+(yy-y)**2)/r)/.35,0,1)
        weight*=np.asarray(self.allowed.crop((x0,y0,x1,y1)))/255
        # Never copy marked people back into the repaired background.
        weight*=1-np.asarray(self.mask.crop((sx0,sy0,sx1,sy1)))/255
        weight*=(xx+dx>=0)&(xx+dx<w)&(yy+dy>=0)&(yy+dy<h)
        patch=self.original.crop((sx0,sy0,sx1,sy1))
        self.result.paste(patch,(x0,y0),Image.fromarray(np.uint8(np.rint(weight*255))))

    def paintEvent(self,event):
        super().paintEvent(event)
        p=QPainter(self);p.setPen(QPen(QColor('#2878bf'),2))
        if self.source:
            x,y=self.source;s=self.fit_scale*self.zoom
            at=QPointF(self.paper.x()+x*s,self.paper.y()+y*s)
            p.drawLine(at+QPointF(-8,0),at+QPointF(8,0));p.drawLine(at+QPointF(0,-8),at+QPointF(0,8))
        if self.cursor_point and not self.panning:
            p.drawEllipse(self.cursor_point,self.radius*self.fit_scale*self.zoom,self.radius*self.fit_scale*self.zoom)

    def mousePressEvent(self,event):
        super().mousePressEvent(event)
        if self.panning or event.button()!=Qt.MouseButton.LeftButton or not self.paper.contains(event.position()):return
        self.setFocus();x,y=self.point(event.position())
        if event.modifiers()&Qt.KeyboardModifier.ControlModifier:
            if self.mask.getpixel((min(self.mask.width-1,int(x)),min(self.mask.height-1,int(y)))):
                self.status.emit('取样点位于移除蒙版内，请选择干净的背景。');return
            self.source=(x,y);self.offset=None;self.status.emit('已取样。回到修复结果，在接缝上涂抹；Ctrl＋单击可重新取样。');self.update();return
        if self.original_view or self.source is None:return
        self.remember()
        if self.offset is None:self.offset=(round(self.source[0]-x),round(self.source[1]-y))
        self.previous=(x,y);self.stamp(x,y);self.rebuild()

    def mouseMoveEvent(self,event):
        self.cursor_point=event.position()
        if self.panning:return super().mouseMoveEvent(event)
        if self.previous and event.buttons()&Qt.MouseButton.LeftButton:
            x,y=self.point(event.position());ox,oy=self.previous
            steps=max(1,math.ceil(math.hypot(x-ox,y-oy)/max(1,self.radius*.2)))
            for t in range(1,steps+1):self.stamp(ox+(x-ox)*t/steps,oy+(y-oy)*t/steps)
            self.previous=(x,y);self.rebuild()
        self.update()

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event);self.previous=None


class CloneDialog(QDialog):
    def __init__(self,original,result,mask,regions,parent=None):
        super().__init__(parent);self.setWindowTitle('仿制修补 · 原页取样');self.resize(1060,900)
        layout=QVBoxLayout(self)
        layout.addWidget(QLabel('Ctrl＋单击干净背景取样，再在修复结果上涂抹。Alt＋拖动平移，滚轮缩放。'))
        layout.addWidget(QLabel('适合修补气球边缘、白底接缝和局部残留；仅在照片画框内落笔，不复制绿色蒙版内的人物。'))
        row=QHBoxLayout()
        self.canvas=CloneCanvas(original,result,mask,regions)
        for name,callback in [('撤销 · Ctrl+Z',self.canvas.undo),('重做',self.canvas.redo),('适合窗口',self.canvas.fit_view)]:
            button=QPushButton(name);button.clicked.connect(callback);row.addWidget(button)
        toggle=QPushButton('查看原页 / 返回结果');toggle.clicked.connect(self.toggle);row.addWidget(toggle)
        row.addWidget(QLabel('笔刷'));brush=QSlider(Qt.Orientation.Horizontal);brush.setRange(4,300);brush.setValue(72)
        brush.valueChanged.connect(lambda v:setattr(self.canvas,'radius',v/2));row.addWidget(brush)
        layout.addLayout(row);layout.addWidget(self.canvas,1)
        self.note=QLabel('先用 Ctrl＋单击取样。取样始终来自未修改的原页。');self.note.setWordWrap(True);self.canvas.status.connect(self.note.setText);layout.addWidget(self.note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('应用修补');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);layout.addWidget(buttons)
        bind_history(self,self.canvas.undo,self.canvas.redo)

    def toggle(self):
        self.canvas.original_view=not self.canvas.original_view;self.canvas.rebuild()

    def done(self,result):
        self.canvas.picture=None;super().done(result)
