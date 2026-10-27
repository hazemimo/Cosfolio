"""Local image viewport shared by precise mask editing and original references."""
from PySide6.QtCore import Qt, QPointF, QRectF, Signal
from PySide6.QtGui import QPainter,QColor,QImage,QBrush
from PySide6.QtWidgets import QWidget


class ImageViewport(QWidget):
    zoomChanged=Signal(float)

    def __init__(self,parent=None):
        super().__init__(parent)
        self.picture=None
        self.image_size=(1,1)
        self.paper=QRectF()
        self.zoom=1.0
        self.pan=QPointF()
        self.panning=False
        self.pan_previous=None
        self.fit_scale=1.0
        self._last_zoom=None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        tile=QImage(24,24,QImage.Format.Format_RGB32)
        tile.fill(QColor('#d7dfe7'))
        painter=QPainter(tile)
        painter.fillRect(0,0,12,12,QColor('#f0f4f8'))
        painter.fillRect(12,12,12,12,QColor('#f0f4f8'))
        painter.end()
        self.checker=QBrush(tile)

    def set_picture(self,picture,reset=True):
        self.picture=picture
        self.image_size=(picture.width(),picture.height())
        if reset:
            self.zoom=1.0
            self.pan=QPointF()
        self.update_transform()
        self.update()

    def update_transform(self):
        iw,ih=self.image_size
        self.fit_scale=max(.0001,min(max(1,self.width()-24)/iw,max(1,self.height()-24)/ih))
        w,h=iw*self.fit_scale*self.zoom,ih*self.fit_scale*self.zoom
        self.paper=QRectF((self.width()-w)/2+self.pan.x(),(self.height()-h)/2+self.pan.y(),w,h)
        percent=self.fit_scale*self.zoom*100
        if percent!=self._last_zoom:
            self._last_zoom=percent
            self.zoomChanged.emit(percent)

    def point(self,position):
        self.update_transform()
        return ((position.x()-self.paper.x())/self.paper.width()*self.image_size[0],
                (position.y()-self.paper.y())/self.paper.height()*self.image_size[1])

    def zoom_at(self,value,anchor=None):
        self.update_transform()
        anchor=QPointF(self.rect().center()) if anchor is None else anchor
        x,y=self.point(anchor)
        self.zoom=max(.1,min(80,float(value)))
        scale=self.fit_scale*self.zoom
        w,h=self.image_size[0]*scale,self.image_size[1]*scale
        self.pan=QPointF(anchor.x()-x*scale-(self.width()-w)/2,
                         anchor.y()-y*scale-(self.height()-h)/2)
        self.update_transform()
        self.update()

    def fit_view(self):
        self.zoom=1.0
        self.pan=QPointF()
        self.update_transform()
        self.update()

    def actual_size(self):
        self.update_transform()
        self.zoom_at(1/self.fit_scale)

    def paintEvent(self,event):
        self.update_transform()
        painter=QPainter(self)
        painter.fillRect(self.rect(),QColor('#e6e9ed'))
        if self.picture is not None:
            painter.setBrushOrigin(self.paper.topLeft())
            painter.fillRect(self.paper,self.checker)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.drawPixmap(self.paper,self.picture,QRectF(self.picture.rect()))

    def wheelEvent(self,event):
        delta=event.angleDelta().y() or event.pixelDelta().y()
        if delta:
            self.zoom_at(self.zoom*1.2**(delta/120),event.position())
        event.accept()

    def mousePressEvent(self,event):
        if event.button()==Qt.MouseButton.MiddleButton or (
            event.button()==Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.AltModifier):
            self.setFocus()
            self.panning=True
            self.pan_previous=event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self,event):
        if self.panning:
            self.pan+=event.position()-self.pan_previous
            self.pan_previous=event.position()
            self.update_transform()
            self.update()
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self,event):
        if self.panning:
            self.panning=False
            self.pan_previous=None
            self.unsetCursor()
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self,event):
        if event.key()==Qt.Key.Key_Alt and not self.panning:
            self.setCursor(Qt.CursorShape.OpenHandCursor)
        super().keyPressEvent(event)

    def keyReleaseEvent(self,event):
        if event.key()==Qt.Key.Key_Alt and not self.panning:
            self.unsetCursor()
        super().keyReleaseEvent(event)

    def resizeEvent(self,event):
        old=self.fit_scale
        self.update_transform()
        if old and self.zoom!=1:
            self.pan*=self.fit_scale/old
            self.update_transform()
        self.update()
