"""Focused-wheel and double-click reset interaction for photo sliders."""
from PySide6.QtCore import Qt,Signal
from PySide6.QtWidgets import QSlider


class ResetSlider(QSlider):
    resetRequested=Signal()

    def __init__(self,default,parent=None):
        super().__init__(Qt.Orientation.Horizontal,parent)
        self.default=default
        self.wheel_remainder=0
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setToolTip('双击恢复默认值；点击后可用滚轮逐格微调')

    def mousePressEvent(self,event):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self,event):
        if event.button()==Qt.MouseButton.LeftButton:
            self.setSliderDown(False)
            self.resetRequested.emit()
            event.accept()
        else:super().mouseDoubleClickEvent(event)

    def wheelEvent(self,event):
        if not self.hasFocus():
            event.ignore()
            return
        self.wheel_remainder+=event.angleDelta().y() or event.pixelDelta().y()*3
        steps=int(self.wheel_remainder/120)
        if steps:
            self.wheel_remainder-=steps*120
            self.setValue(self.value()+steps*self.singleStep())
        event.accept()

    def focusOutEvent(self,event):
        self.wheel_remainder=0
        super().focusOutEvent(event)
