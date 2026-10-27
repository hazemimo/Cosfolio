from __future__ import annotations

import copy
import json
import sys
import time
import uuid
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter
from PySide6.QtCore import Qt, QSize, QPointF, QRectF, Signal, QThread, QTimer, QMimeData
from PySide6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QDrag, QKeySequence, QShortcut, QFontDatabase, QFont, QIcon,QPainterPath
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QAbstractItemView, QComboBox, QSlider, QLineEdit,
    QCheckBox, QFileDialog, QMessageBox, QFrame, QDialog, QDialogButtonBox,
    QSizePolicy, QProgressBar, QScrollArea,
    QTabWidget, QMenu, QPlainTextEdit, QInputDialog,
)

from .core import (ROOT, DATA, MODEL, Asset, Project, Placement, LocalSegmenter,
                   import_asset, save_project, load_project, oriented_image, prepare_directories, export_basename, make_cutout, srgb_profile)
from .render import Renderer, TEMPLATES, template_plate
from .workflow import ACCENTS, batch_project, batch_filename, write_recovery, read_recovery, list_recoveries, read_preferences, save_preferences
from .viewer import ImageViewport
from .layout import frames,radii,pixel_box
from .finish import match_lighting,quality_report
from .controls import ResetSlider
from .history import bind_history
from .template_preferences import display_name
from . import template_preferences


APP_TITLE='Cosfolio · 偶像写真工房 0.9'

STYLE = '''
QWidget { font-family: "Microsoft YaHei UI", "Microsoft YaHei"; font-size: 13px; color: #293e55; }
QMainWindow, QDialog { background: #f1f6fb; }
QFrame#panel { background: #ffffff; border: 1px solid #d9e5f0; border-radius: 12px; }
QLabel#brand { font-size: 25px; font-weight: 700; color: #173f70; }
QLabel#section { font-size: 14px; font-weight: 600; color: #234c79; }
QLabel#muted { color: #637b93; font-size: 12px; }
QLabel#pill { background: #e4eff9; color: #356793; padding: 7px 11px; border-radius: 12px; font-size: 12px; }
QPushButton { background: #ffffff; border: 1px solid #d4e0ec; padding: 9px 14px; border-radius: 7px; }
QPushButton:hover { background: #eaf3fc; border-color: #8eb5d8; }
QPushButton:pressed { background: #d8eafa; }
QPushButton:disabled { color: #a7b5c4; border-color: #e1e9f1; background: #f4f7fa; }
QPushButton#primary { background: #174d8b; color: white; border: 1px solid #174d8b; font-weight: 600; }
QPushButton#primary:hover { background: #235e9c; }
QPushButton#primary:disabled { background: #9fb8d1; border-color: #9fb8d1; }
QPushButton#quiet { background: transparent; border: 0; color: #537da5; padding: 7px; }
QComboBox, QLineEdit, QPlainTextEdit { background: white; border: 1px solid #d3dfeb; border-radius: 6px; padding: 8px; selection-background-color: #4f8fc5; }
QComboBox:focus, QLineEdit:focus { border-color: #5998cb; }
QComboBox QAbstractItemView { background: white; selection-background-color: #dfedfa; color: #293e55; }
QListWidget { background: transparent; border: 0; outline: 0; }
QListWidget::item { border: 1px solid #e4edf5; background: #f7fafd; margin: 4px 0; border-radius: 8px; padding: 7px; }
QListWidget::item:selected { background: #e1effc; border: 1px solid #8fb8df; color: #234c79; }
QSlider::groove:horizontal { height: 4px; background: #dce7f2; border-radius: 2px; }
QSlider::sub-page:horizontal { background: #6a9dcc; border-radius: 2px; }
QSlider::handle:horizontal { width: 14px; margin: -6px 0; border: 2px solid #ffffff; border-radius: 9px; background: #24588e; }
QCheckBox { spacing: 8px; }
QCheckBox::indicator { width: 15px; height: 15px; }
QProgressBar { border: 0; background: #e1ebf4; height: 4px; border-radius: 2px; }
QProgressBar::chunk { background: #5d96c8; }
QStatusBar { color: #667f98; background: #e7eff7; }
QScrollArea { background: transparent; border: 0; }
QToolTip { background: #294964; color: white; padding: 6px; border: 0; }
QScrollBar:vertical { background: #edf2f7; width: 10px; margin: 0; border-radius: 4px; }
QScrollBar::handle:vertical { background: #9db7cf; min-height: 30px; border-radius: 4px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
QTabWidget::pane { border: 0; background: transparent; }
QTabBar::tab { padding: 9px 13px; color: #7289a0; background: #edf4fb; border: 0; }
QTabBar::tab:selected { color: #174d8b; background: #ffffff; border-bottom: 2px solid #24588e; }
QTabWidget#settings QTabBar::tab { padding: 9px 7px; }
QWidget#settingsPage { background: #ffffff; }
QMenu { background: #ffffff; border: 1px solid #d4e0ec; padding: 5px; }
QMenu::item { padding: 8px 18px; }
QMenu::item:selected { background: #e1effc; }
'''


def pixmap(image,preserve_alpha=False):
    image = image.convert('RGBA')
    qimage = QImage(image.tobytes(), image.width, image.height, image.width*4, QImage.Format.Format_RGBA8888).copy()
    return QPixmap.fromImage(qimage,Qt.ImageConversionFlag.NoOpaqueDetection) if preserve_alpha else QPixmap.fromImage(qimage)


def label(text, name=''):
    item = QLabel(text)
    if name:
        item.setObjectName(name)
    return item


IMAGE_SUFFIXES={'.jpg','.jpeg','.png','.webp','.tif','.tiff'}


def dropped_images(mime):
    return [url.toLocalFile() for url in mime.urls() if url.isLocalFile()
            and Path(url.toLocalFile()).suffix.lower() in IMAGE_SUFFIXES and Path(url.toLocalFile()).is_file()]


class AssetPanel(QFrame):
    filesDropped=Signal(list)

    def __init__(self):
        super().__init__()
        self.setAcceptDrops(True)

    def dragEnterEvent(self,event):
        if dropped_images(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self,event):
        if dropped_images(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self,event):
        paths=dropped_images(event.mimeData())
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()


class PhotoList(QListWidget):
    filesDropped=Signal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setIconSize(QSize(84,105))
        self.setDragEnabled(True)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDropIndicatorShown(False)

    def dragEnterEvent(self,event):
        if dropped_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self,event):
        if dropped_images(event.mimeData()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self,event):
        paths=dropped_images(event.mimeData())
        if paths:
            self.filesDropped.emit(paths)
            event.acceptProposedAction()
        else:
            event.ignore()

    def startDrag(self, actions):
        item = self.currentItem()
        if not item:
            return
        mime = QMimeData()
        mime.setData('application/x-cosfolio-asset', item.data(Qt.ItemDataRole.UserRole).encode())
        drag=QDrag(self)
        drag.setMimeData(mime)
        drag.setPixmap(item.icon().pixmap(70,90))
        drag.exec(Qt.DropAction.CopyAction)


_TEMPLATE_IMAGES={}
_REFERENCE_IMAGES={}


def template_thumbnail(key):
    # Keep plain image pixels in the module cache, not native QPixmaps. Static
    # native images can otherwise outlive QApplication during interpreter exit.
    if key not in _TEMPLATE_IMAGES:
        path=Path(TEMPLATES[key]['preview']) if TEMPLATES[key].get('custom') else ROOT/'resources'/'templates'/'previews'/f'{key}.jpg'
        if len(_TEMPLATE_IMAGES)>=32:_TEMPLATE_IMAGES.pop(next(iter(_TEMPLATE_IMAGES)))
        if path.exists():
            with Image.open(path) as image:
                _TEMPLATE_IMAGES[key]=image.convert('RGB')
        else:
            project=Project(template=key,title='YOUR NAME',subtitle='PHOTO COLLECTION',footer='')
            _TEMPLATE_IMAGES[key]=Renderer().render(project,450,placeholders=True)
    return pixmap(_TEMPLATE_IMAGES[key])


def reference_thumbnail(key):
    path=TEMPLATES[key].get('reference')
    if not path:
        return QPixmap()
    if key not in _REFERENCE_IMAGES:
        if len(_REFERENCE_IMAGES)>=6:
            _REFERENCE_IMAGES.pop(next(iter(_REFERENCE_IMAGES)))
        _REFERENCE_IMAGES[key]=oriented_image(ROOT/'resources'/'templates'/path,900)
    return pixmap(_REFERENCE_IMAGES[key])


class ReferenceDialog(QDialog):
    def __init__(self,key,parent=None):
        super().__init__(parent)
        self.resize(900,900)
        self.setMinimumSize(560,520)
        root=QVBoxLayout(self)
        self.heading=label('','section')
        self.heading.setWordWrap(True)
        root.addWidget(self.heading)
        self.canvas=ImageViewport()
        root.addWidget(self.canvas,1)
        bar=QHBoxLayout()
        hint=label('滚轮缩放 · Alt＋拖动画面 · 仅作对照，不放入成品','muted')
        hint.setWordWrap(True)
        bar.addWidget(hint,1)
        self.zoom_label=label('','muted')
        self.canvas.zoomChanged.connect(lambda v:self.zoom_label.setText(f'{v:.0f}%'))
        bar.addWidget(self.zoom_label)
        for name,action in [('适合窗口',self.canvas.fit_view),('100%',self.canvas.actual_size)]:
            button=QPushButton(name)
            button.clicked.connect(action)
            bar.addWidget(button)
        root.addLayout(bar)
        self.set_template(key)

    def set_template(self,key):
        if getattr(self,'key',None)==key and self.canvas.picture is not None and getattr(self,'display_label',None)==display_name(key):
            return
        self.key=key
        self.display_label=display_name(key)
        config=TEMPLATES[key]
        self.setWindowTitle('原场刊参考 · '+self.display_label)
        path=config.get('reference')
        if path:
            self.heading.setText(self.display_label+'\n'+Path(path).name)
            self.canvas.set_picture(pixmap(oriented_image(ROOT/'resources'/'templates'/path)))
        else:
            self.heading.setText(self.display_label+' · 原创模板，没有对应原场刊')
            self.canvas.picture=None
            self.canvas.update()
            self.zoom_label.setText('')

    def done(self,result):
        self.canvas.picture=None
        super().done(result)


class TemplateDialog(QDialog):
    def __init__(self,current,parent=None,batch=False):
        super().__init__(parent)
        self.setWindowTitle('选择模板 · 可视化图库')
        self.resize(1050,800)
        self.chosen=current
        self.reference_window=None
        self.batch=batch
        self.template_settings=template_preferences.read()
        self.metadata_undo=[];self.metadata_redo=[]
        root=QVBoxLayout(self)
        root.addWidget(label(('勾选需要批量导出的模板' if batch else '选择适合这组照片的版式')+f' · {len(TEMPLATES)} 款','section'))
        root.addWidget(label('点击查看大图；数字对应照片位置。'+('未分配的位置会按素材顺序补齐。' if batch else '同一张照片可以重复使用。'),'muted'))
        filters=QHBoxLayout()
        self.search=QLineEdit();self.search.setPlaceholderText('搜索模板名称、原名或说明');filters.addWidget(self.search,1)
        self.slot_filter=QComboBox();self.slot_filter.addItem('全部照片位置',None)
        for count in range(1,6):self.slot_filter.addItem(f'{count} 个照片位置',count)
        filters.addWidget(self.slot_filter)
        self.favorites_only=QCheckBox('只看收藏');filters.addWidget(self.favorites_only);root.addLayout(filters)
        self.filter_count=label('','muted');root.addWidget(self.filter_count)
        if batch:
            actions=QHBoxLayout()
            for title,checked in [('全选',True),('清空',False)]:
                button=QPushButton(title)
                button.clicked.connect(lambda _,c=checked:self.check_all(c))
                actions.addWidget(button)
            actions.addStretch()
            root.addLayout(actions)
        content=QHBoxLayout()
        self.gallery=QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setIconSize(QSize(138,190))
        self.gallery.setGridSize(QSize(185,252))
        self.gallery.setSpacing(4)
        self.gallery.setWordWrap(True)
        self.gallery.setUniformItemSizes(True)
        self.gallery.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.gallery.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        for key,value in TEMPLATES.items():
            item=QListWidgetItem(QIcon(template_thumbnail(key)),f'{display_name(key,self.template_settings)}\n{len(value["slots"])} 个照片位置')
            item.setData(Qt.ItemDataRole.UserRole,key)
            item.setToolTip(value['note'])
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            if batch:
                item.setFlags(item.flags()|Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if key==current else Qt.CheckState.Unchecked)
            self.gallery.addItem(item)
        content.addWidget(self.gallery,1)
        detail_widget=QWidget();detail=QVBoxLayout(detail_widget);detail.setContentsMargins(8,0,8,0)
        self.preview=QLabel()
        self.preview.setFixedSize(310,370)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.detail_tabs=QTabWidget()
        self.detail_tabs.addTab(self.preview,'模板底图')
        self.reference_preview=QLabel()
        self.reference_preview.setFixedSize(310,370)
        self.reference_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.reference_preview.setWordWrap(True)
        self.detail_tabs.addTab(self.reference_preview,'原场刊')
        detail.addWidget(self.detail_tabs)
        self.reference_button=QPushButton('放大查看原场刊')
        self.reference_button.clicked.connect(self.open_reference)
        detail.addWidget(self.reference_button)
        self.name=label('','section')
        self.name.setWordWrap(True)
        detail.addWidget(self.name)
        naming=QHBoxLayout();self.favorite_button=QPushButton('☆ 收藏');self.favorite_button.clicked.connect(self.toggle_template_favorite);naming.addWidget(self.favorite_button)
        self.rename_button=QPushButton('重命名…');self.rename_button.clicked.connect(self.rename_template);naming.addWidget(self.rename_button);detail.addLayout(naming)
        self.reset_name_button=QPushButton('恢复模板原名');self.reset_name_button.clicked.connect(self.reset_template_name);detail.addWidget(self.reset_name_button)
        self.note=label('','muted')
        self.note.setWordWrap(True)
        self.note.setMaximumWidth(310)
        detail.addWidget(self.note)
        self.layout_info=label('')
        self.layout_info.setWordWrap(True)
        self.layout_info.setMaximumWidth(310)
        detail.addWidget(self.layout_info)
        detail.addStretch()
        detail.removeWidget(self.name);detail.insertWidget(0,self.name)
        detail.removeItem(naming);detail.insertLayout(1,naming)
        detail.removeWidget(self.reset_name_button);detail.insertWidget(2,self.reset_name_button)
        detail_scroll=QScrollArea();detail_scroll.setWidgetResizable(True);detail_scroll.setMinimumWidth(345)
        detail_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);detail_scroll.setWidget(detail_widget)
        content.addWidget(detail_scroll)
        root.addLayout(content,1)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('使用这个模板')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self.ok_button=buttons.button(QDialogButtonBox.StandardButton.Ok)
        self.search.textChanged.connect(self.filter_templates)
        self.slot_filter.currentIndexChanged.connect(self.filter_templates)
        self.favorites_only.toggled.connect(self.filter_templates)
        bind_history(self,self.undo_metadata,self.redo_metadata)
        if batch:
            self.gallery.itemChanged.connect(self.update_batch_count)
            self.update_batch_count()
        self.gallery.currentItemChanged.connect(self.update_preview)
        if not batch:
            self.gallery.itemDoubleClicked.connect(lambda _:self.accept())
        self.gallery.setCurrentRow(list(TEMPLATES).index(current))
        if TEMPLATES[current].get('reference'):
            self.detail_tabs.setCurrentIndex(1)
        self.refresh_template_metadata()

    def update_preview(self,item,previous=None):
        if item is None:
            return
        key=item.data(Qt.ItemDataRole.UserRole)
        self.chosen=key
        self.ok_button.setEnabled(bool(self.selected_keys()) if self.batch else True)
        self.favorite_button.setEnabled(True);self.rename_button.setEnabled(True);self.reset_name_button.setEnabled(True)
        template=TEMPLATES[key]
        self.preview.setPixmap(template_thumbnail(key).scaled(self.preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        self.name.setText(display_name(key,self.template_settings))
        self.favorite_button.setText('★ 已收藏' if key in self.template_settings['favorites'] else '☆ 收藏')
        self.reset_name_button.setEnabled(key in self.template_settings['names'])
        self.name.setMinimumHeight(self.name.heightForWidth(310))
        self.note.setText(template['note'])
        self.note.setMinimumHeight(self.note.heightForWidth(310))
        w,h=template['size']
        self.layout_info.setText(f'{w} × {h} · {len(template["slots"])} 个照片位置\n\n'+' / '.join(template['labels']))
        has_reference=bool(template.get('reference'))
        self.reference_button.setEnabled(has_reference)
        if has_reference:
            self.reference_preview.setPixmap(reference_thumbnail(key).scaled(self.reference_preview.size(),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        else:
            self.reference_preview.clear()
            self.reference_preview.setText('原创模板，没有对应原场刊')
        if self.reference_window is not None and self.reference_window.isVisible():
            self.reference_window.set_template(key)

    def open_reference(self):
        if self.reference_window is None:
            self.reference_window=ReferenceDialog(self.chosen,self)
        else:
            self.reference_window.set_template(self.chosen)
        self.reference_window.show()
        self.reference_window.raise_()

    def selected_keys(self):
        return [self.gallery.item(i).data(Qt.ItemDataRole.UserRole) for i in range(self.gallery.count())
                if self.gallery.item(i).checkState()==Qt.CheckState.Checked]

    def check_all(self,checked):
        for i in range(self.gallery.count()):
            if not self.gallery.item(i).isHidden():
                self.gallery.item(i).setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

    def update_batch_count(self,*_):
        count=len(self.selected_keys())
        self.ok_button.setText(f'导出所选 {count} 个模板')
        self.ok_button.setEnabled(count>0)
        self.update_filter_count()

    def update_filter_count(self):
        visible=sum(not self.gallery.item(i).isHidden() for i in range(self.gallery.count()))
        value=f'显示 {visible} / {self.gallery.count()} 款'
        if self.batch:
            hidden=sum(self.gallery.item(i).isHidden() and self.gallery.item(i).checkState()==Qt.CheckState.Checked for i in range(self.gallery.count()))
            value+=f' · 已勾选 {len(self.selected_keys())} 款'+(f'（筛选外 {hidden} 款）' if hidden else '')
        self.filter_count.setText(value)

    def filter_templates(self,*_):
        query=self.search.text().strip().casefold();slots=self.slot_filter.currentData();favorites=set(self.template_settings['favorites'])
        visible=[]
        for i in range(self.gallery.count()):
            item=self.gallery.item(i);key=item.data(Qt.ItemDataRole.UserRole);config=TEMPLATES[key]
            name=display_name(key,self.template_settings)
            matches=(not query or query in (name+' '+config['name']+' '+config['note']+' '+key).casefold())
            matches=matches and (slots is None or len(config['slots'])==slots) and (not self.favorites_only.isChecked() or key in favorites)
            item.setHidden(not matches)
            if matches:visible.append(item)
        current=self.gallery.currentItem()
        if visible:
            if current not in visible:self.gallery.setCurrentItem(visible[0])
            self.update_preview(self.gallery.currentItem())
        else:
            self.name.setText('没有匹配的模板');self.note.setText('修改搜索词或筛选条件后再试');self.layout_info.setText('')
            self.preview.clear();self.reference_preview.clear();self.reference_button.setEnabled(False)
            for button in (self.favorite_button,self.rename_button,self.reset_name_button):button.setEnabled(False)
            if not self.batch:self.ok_button.setEnabled(False)
        self.update_filter_count()

    def refresh_template_metadata(self):
        self.template_settings=template_preferences.read()
        for i in range(self.gallery.count()):
            item=self.gallery.item(i);key=item.data(Qt.ItemDataRole.UserRole);config=TEMPLATES[key]
            star='★ ' if key in self.template_settings['favorites'] else ''
            item.setText(f'{star}{display_name(key,self.template_settings)}\n{len(config["slots"])} 个照片位置')
            item.setToolTip('原名：'+config['name']+'\n'+config['note'])
        self.filter_templates()

    def metadata_change(self,callback):
        before=template_preferences.read()
        try:
            callback();after=template_preferences.read()
            if before!=after:self.metadata_undo.append(before);self.metadata_undo=self.metadata_undo[-30:];self.metadata_redo.clear()
            self.refresh_template_metadata()
        except Exception as exc:QMessageBox.warning(self,'模板信息',str(exc))

    def toggle_template_favorite(self):
        self.metadata_change(lambda:template_preferences.favorite(self.chosen,self.chosen not in self.template_settings['favorites']))

    def rename_template(self):
        value,ok=QInputDialog.getText(self,'重命名模板','给这个模板起一个便于寻找的名称：',text=display_name(self.chosen,self.template_settings))
        if ok:self.metadata_change(lambda:template_preferences.rename(self.chosen,value))

    def reset_template_name(self):
        self.metadata_change(lambda:template_preferences.rename(self.chosen,TEMPLATES[self.chosen]['name']))

    def undo_metadata(self):
        if self.metadata_undo:
            self.metadata_redo.append(template_preferences.read());template_preferences.write(self.metadata_undo.pop());self.refresh_template_metadata()

    def redo_metadata(self):
        if self.metadata_redo:
            self.metadata_undo.append(template_preferences.read());template_preferences.write(self.metadata_redo.pop());self.refresh_template_metadata()

    def done(self,result):
        if self.reference_window is not None:
            self.reference_window.close()
        self.preview.clear()
        self.reference_preview.clear()
        for index in range(self.gallery.count()):
            self.gallery.item(index).setIcon(QIcon())
        parent=self.parent()
        if parent is not None and hasattr(parent,'refresh_template_labels'):parent.refresh_template_labels()
        super().done(result)


class ImportWorker(QThread):
    progress=Signal(str)
    ready=Signal(object)
    error=Signal(str)

    def __init__(self,paths,segmenter):
        super().__init__()
        self.paths=paths
        self.segmenter=segmenter
        self.cancelled=False

    def run(self):
        for i,path in enumerate(self.paths):
            if self.isInterruptionRequested():
                self.cancelled=True
                break
            try:
                self.progress.emit(f'{i+1}/{len(self.paths)} · {Path(path).name} · 正在本机处理')
                asset=import_asset(path,self.segmenter)
                self.ready.emit(asset)
            except Exception as exc:
                self.error.emit(f'{Path(path).name}：{exc}')
        self.cancelled=self.cancelled or self.isInterruptionRequested()


class ExportWorker(QThread):
    ready=Signal(str,object)
    error=Signal(str)
    progress=Signal(str)
    cancelled=Signal()

    def __init__(self,project,path,long_edge):
        super().__init__()
        self.project=copy.deepcopy(project)
        self.path=path
        self.long_edge=long_edge

    def run(self):
        try:
            size=Renderer().export(self.project,self.path,self.long_edge,
                                   cancelled=self.isInterruptionRequested,progress=self.progress.emit)
            self.ready.emit(self.path,size)
        except InterruptedError:
            self.cancelled.emit()
        except Exception as exc:
            self.error.emit(str(exc))


class BatchWorker(QThread):
    progress=Signal(int,int,str)
    ready=Signal(object)

    def __init__(self,project,templates,folder,long_edge):
        super().__init__()
        self.project=copy.deepcopy(project)
        self.templates=templates
        self.folder=Path(folder)
        self.long_edge=long_edge

    def run(self):
        renderer=Renderer()
        results=[]
        for i,key in enumerate(self.templates):
            if self.isInterruptionRequested():
                break
            self.progress.emit(i,len(self.templates),display_name(key))
            path=self.folder/batch_filename(self.project,key)
            try:
                renderer.export(batch_project(self.project,key),path,self.long_edge)
                results.append({'template':key,'file':path.name,'ok':True})
            except Exception as exc:
                results.append({'template':key,'file':path.name,'ok':False,'error':str(exc)})
        report={'results':results,'cancelled':self.isInterruptionRequested(),'folder':str(self.folder)}
        try:
            (self.folder/'导出记录.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError as exc:
            report['report_error']=str(exc)
        self.ready.emit(report)


class CutoutWorker(QThread):
    ready=Signal(str,object)
    error=Signal(str)

    def __init__(self,asset,path):
        super().__init__()
        self.asset=copy.deepcopy(asset)
        self.path=Path(path)

    def run(self):
        temporary=self.path.with_name(f'.{self.path.stem}.{uuid.uuid4().hex[:8]}.tmp.png')
        try:
            image=make_cutout(self.asset,max(self.asset.width,self.asset.height,4000))
            image.save(temporary,dpi=(300,300),icc_profile=srgb_profile())
            temporary.replace(self.path)
            self.ready.emit(str(self.path),image.size)
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            temporary.unlink(missing_ok=True)


class BookWorker(QThread):
    progress=Signal(int,int,str)
    ready=Signal(object)

    def __init__(self,project,folder,long_edge):
        super().__init__()
        self.project=copy.deepcopy(project)
        self.folder=Path(folder)
        self.long_edge=long_edge

    def run(self):
        results=[]
        renderer=Renderer()
        for i in range(self.project.page_count):
            if self.isInterruptionRequested():break
            page=self.project.page_project(i)
            name=f'{i+1:03d}_'+export_basename(page.title,page.subtitle)+'.png'
            self.progress.emit(i,self.project.page_count,f'第 {i+1} 页 · '+display_name(page.template))
            try:
                renderer.export(page,self.folder/name,self.long_edge,cancelled=self.isInterruptionRequested)
                results.append({'page':i+1,'file':name,'ok':True})
            except InterruptedError:break
            except Exception as exc:results.append({'page':i+1,'file':name,'ok':False,'error':str(exc)})
        report={'results':results,'cancelled':self.isInterruptionRequested(),'folder':str(self.folder)}
        try:
            (self.folder/'写真页清单.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        except OSError as exc:report['report_error']=str(exc)
        self.ready.emit(report)


class PageCanvas(QWidget):
    selected=Signal(int)
    changed=Signal()
    dragStarted=Signal()
    assigned=Signal(int,str)

    def __init__(self,window):
        super().__init__()
        self.window=window
        self.setAcceptDrops(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumSize(330,420)
        self.setSizePolicy(QSizePolicy.Policy.Expanding,QSizePolicy.Policy.Expanding)
        self.paper=QRectF()
        self.image=None
        self.foreground=None
        self.layers=[]
        self.signature=None
        self.geometry_key=None
        self.build_count=0
        self.long_edge=1200
        self.press=None
        self.origin=None
        self.moved=False
        self.timer=QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.render_page)

    def refresh(self):
        # Do not restart a debounce timer for every mouse event: high-rate mice
        # can otherwise postpone the next frame until the drag stops.
        if not self.timer.isActive():
            self.timer.start(0)
        self.update()

    def render_page(self):
        try:
            long_edge=min(1400,max(800,round(self.height()*1.4)))
            project=self.window.project
            template=TEMPLATES[project.template]
            signature=(project.template,long_edge,project.title,project.subtitle,project.footer,project.body,project.accent,project.text_mode,
                       json.dumps(project.layout,sort_keys=True),project.active_page,project.page_count,project.page_numbers,project.credit,
                       tuple((place.asset_id, project.asset(place.asset_id).mask if project.asset(place.asset_id) else '',
                              place.zoom,place.rotation,place.brightness,place.contrast,place.saturation,place.warmth,place.flip,
                              place.dehalo,place.shadow,place.fit,place.edge_shift,place.edge_softness,
                              place.shadow_opacity,place.shadow_blur,place.shadow_x,place.shadow_y)
                             for place in project.placements[:len(template['slots'])]))
            if signature==self.signature:
                self.update()
                return
            self.long_edge=long_edge
            ratio=long_edge/max(template['size'])
            self.image=pixmap(template_plate(project.template,long_edge,project.text_mode) if project.layout.get('background',True)
                              else Image.new('RGB',(round(template['size'][0]*ratio),round(template['size'][1]*ratio)),'white'))
            self.foreground=pixmap(self.window.renderer.render(project,long_edge,only_foreground=True))
            self.layers=[]
            for index,(x,y,sw,sh) in enumerate(frames(project)):
                place=project.placements[index]
                asset=project.asset(place.asset_id)
                photo=shadow=None
                if asset and project.layout.get('photos',True):
                    pil_photo,pil_shadow=self.window.renderer.photo_layer(asset,place,project.template,index,long_edge,project)
                    photo=pixmap(pil_photo)
                    shadow=pixmap(pil_shadow) if pil_shadow is not None else None
                self.layers.append((index,photo,shadow,*pixel_box((x,y,sw,sh),ratio)))
            self.signature=signature
            self.geometry_key=(project.template,tuple(tuple(rect) for rect in frames(project)),tuple(radii(project)))
            self.build_count+=1
            self.update()
        except Exception as exc:
            self.window.statusBar().showMessage(f'预览失败：{exc}')

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.fillRect(self.rect(),QColor(getattr(self,'workspace_color','#e6e9ed')))
        template=TEMPLATES[self.window.project.template]
        w,h=template['size']
        ratio=min((self.width()-44)/w,(self.height()-36)/h)
        pw,ph=w*ratio,h*ratio
        self.paper=QRectF((self.width()-pw)/2,(self.height()-ph)/2,pw,ph)
        painter.fillRect(self.paper.translated(4,6),QColor('#bec8d2'))
        geometry_key=(self.window.project.template,tuple(tuple(rect) for rect in frames(self.window.project)),tuple(radii(self.window.project)))
        if self.image and self.geometry_key==geometry_key:
            painter.save()
            painter.translate(self.paper.topLeft())
            painter.scale(self.paper.width()/self.image.width(),self.paper.height()/self.image.height())
            painter.drawPixmap(0,0,self.image)
            ratio=self.long_edge/max(template['size'])
            for index,photo,shadow,x,y,sw,sh in self.layers:
                place=self.window.project.placements[index]
                painter.save()
                clip=QPainterPath()
                radius=radii(self.window.project)[index]*ratio
                clip.addRoundedRect(QRectF(x,y,sw,sh),radius,radius)
                painter.setClipPath(clip)
                if photo is not None:
                    dx=round((sw-photo.width())/2+place.x*sw)
                    dy=round(((sh-photo.height())/2 if place.fit=='contain' else sh*.025)+place.y*sh)
                    if shadow is not None:
                        pad=math.ceil(place.shadow_blur*ratio*3)+2
                        painter.drawPixmap(x+dx+round(place.shadow_x*ratio)-pad,y+dy+round(place.shadow_y*ratio)-pad,shadow)
                    painter.drawPixmap(x+dx,y+dy,photo)
                else:
                    painter.setPen(QColor('#8f7d9a'))
                    f=QFont('Microsoft YaHei UI')
                    f.setPixelSize(max(12,round(26*ratio)))
                    painter.setFont(f)
                    painter.drawText(QRectF(x,y,sw,sh),Qt.AlignmentFlag.AlignCenter,f'{index+1}\n拖入照片')
                painter.restore()
            if self.foreground:
                painter.drawPixmap(0,0,self.foreground)
            if 0<=self.window.selected<len(template['slots']):
                x,y,sw,sh=frames(self.window.project)[self.window.selected]
                painter.setPen(QPen(QColor('#4c9de0'),max(2,8*ratio)))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                radius=radii(self.window.project)[self.window.selected]*ratio
                px,py,pw,ph=pixel_box((x,y,sw,sh),ratio)
                painter.drawRoundedRect(QRectF(px,py,pw,ph),radius,radius)
                if self.window.guides.isChecked():
                    pen=QPen(QColor(110,170,225,180),max(1,2*ratio),Qt.PenStyle.DashLine)
                    painter.setPen(pen)
                    for fraction in (1/3,2/3):
                        gx=(x+sw*fraction)*ratio
                        gy=(y+sh*fraction)*ratio
                        painter.drawLine(QPointF(gx,y*ratio),QPointF(gx,(y+sh)*ratio))
                        painter.drawLine(QPointF(x*ratio,gy),QPointF((x+sw)*ratio,gy))
            painter.restore()

    def slot_at(self,position):
        if self.paper.width()<=0:
            return -1
        template=TEMPLATES[self.window.project.template]
        x=(position.x()-self.paper.x())/self.paper.width()*template['size'][0]
        y=(position.y()-self.paper.y())/self.paper.height()*template['size'][1]
        for i,(sx,sy,sw,sh) in enumerate(frames(self.window.project)):
            if sx<=x<=sx+sw and sy<=y<=sy+sh:
                path=QPainterPath()
                r=radii(self.window.project)[i]
                path.addRoundedRect(QRectF(sx,sy,sw,sh),r,r)
                if path.contains(QPointF(x,y)):return i
        return -1

    def mousePressEvent(self,event):
        if event.button()!=Qt.MouseButton.LeftButton or self.window.busy:
            return
        self.setFocus()
        index=self.slot_at(event.position())
        if index>=0:
            self.selected.emit(index)
            self.press=event.position()
            place=self.window.project.placements[index]
            self.origin=(place.x,place.y)
            self.moved=False

    def mouseMoveEvent(self,event):
        if self.press is None or self.window.busy:
            return
        delta=event.position()-self.press
        if not self.moved and abs(delta.x())+abs(delta.y())>2:
            self.dragStarted.emit()
            self.moved=True
        if self.moved:
            template=TEMPLATES[self.window.project.template]
            slot=frames(self.window.project)[self.window.selected]
            scale=self.paper.width()/template['size'][0]
            place=self.window.project.placements[self.window.selected]
            place.x=self.origin[0]+delta.x()/(slot[2]*scale)
            place.y=self.origin[1]+delta.y()/(slot[3]*scale)
            self.changed.emit()

    def mouseReleaseEvent(self,event):
        self.press=None

    def wheelEvent(self,event):
        if self.window.busy:
            return
        index=self.slot_at(event.position())
        if index>=0:
            self.selected.emit(index)
            self.window.history_push()
            place=self.window.project.placements[index]
            place.zoom=max(.4,min(2.5,place.zoom*(1.06 if event.angleDelta().y()>0 else 1/1.06)))
            self.window.sync_controls()
            self.changed.emit()

    def keyPressEvent(self,event):
        vectors={Qt.Key.Key_Left:(-1,0),Qt.Key.Key_Right:(1,0),Qt.Key.Key_Up:(0,-1),Qt.Key.Key_Down:(0,1)}
        if event.key() in vectors and not self.window.busy:
            self.window.history_push()
            dx,dy=vectors[event.key()]
            amount=10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 2
            slot=frames(self.window.project)[self.window.selected]
            place=self.window.project.placements[self.window.selected]
            place.x+=dx*amount/slot[2]
            place.y+=dy*amount/slot[3]
            self.changed.emit()
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat('application/x-cosfolio-asset') or event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self,event):
        event.acceptProposedAction()

    def dropEvent(self,event):
        if self.window.busy:
            return
        index=self.slot_at(event.position())
        if event.mimeData().hasFormat('application/x-cosfolio-asset') and index>=0:
            key=bytes(event.mimeData().data('application/x-cosfolio-asset')).decode()
            self.assigned.emit(index,key)
            event.acceptProposedAction()
        elif event.mimeData().hasUrls():
            paths=[url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
            self.window.import_paths(paths)
            event.acceptProposedAction()

    def resizeEvent(self,event):
        self.refresh()


class MaskCanvas(ImageViewport):
    brushChanged=Signal(int)

    def __init__(self,asset):
        super().__init__()
        self.mask=Image.open(asset.mask).convert('L')
        self.original=oriented_image(asset.source,max(self.mask.size))
        self.original=self.original.resize(self.mask.size,Image.Resampling.LANCZOS)
        self.initial=Image.open(asset.initial_mask).convert('L').resize(self.mask.size)
        self.mode='erase'
        self.radius=16
        self.history=[]
        self.redo_history=[]
        self.previous=None
        self.cursor_position=None
        self.show_original=False
        self.overlay_mode=False
        self.setMinimumSize(450,490)
        self.rebuild()

    def rebuild(self):
        image=self.preview_image()
        # Keep full mask-resolution pixels for accurate magnified edges. The
        # native viewport clips the visible region instead of shrinking to 950px.
        self.set_picture(pixmap(image,preserve_alpha=True),reset=False)

    def preview_image(self,box=None):
        original=self.original.crop(box) if box else self.original
        mask=self.mask.crop(box) if box else self.mask
        image=original.convert('RGBA')
        if self.overlay_mode and not self.show_original:
            tint=Image.new('RGBA',image.size,(50,220,155,0))
            tint.putalpha(mask.point(lambda v:round(v*.55)))
            image.alpha_composite(tint)
        elif not self.show_original:image.putalpha(mask)
        return image

    def paintEvent(self,event):
        super().paintEvent(event)
        if self.cursor_position is None or self.panning or self.show_original:
            return
        painter=QPainter(self)
        radius=self.radius*self.fit_scale*self.zoom
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#ffffff'),2))
        painter.drawEllipse(self.cursor_position,radius,radius)
        painter.setPen(QPen(QColor('#302338'),1))
        painter.drawEllipse(self.cursor_position,radius+1,radius+1)

    def set_brush_size(self,diameter):
        diameter=max(1,min(256,round(diameter)))
        self.radius=diameter/2
        self.brushChanged.emit(diameter)
        self.update()

    def wheelEvent(self,event):
        dx=event.angleDelta().x() or event.pixelDelta().x()
        dy=event.angleDelta().y() or event.pixelDelta().y()
        horizontal=abs(dx)>abs(dy)
        if horizontal or event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            delta=dx if horizontal else dy
            if delta:
                diameter=self.radius*2
                change=max(1,round(diameter*.12*abs(delta)/120))
                self.set_brush_size(diameter+(change if delta>0 else -change))
            event.accept()
        else:
            super().wheelEvent(event)

    def stroke(self,position):
        if self.show_original or not self.paper.width():
            return
        x,y=self.point(position)
        radius=self.radius
        draw=ImageDraw.Draw(self.mask)
        fill=0 if self.mode=='erase' else 255
        previous=self.previous or (x,y)
        if self.previous:
            draw.line((*self.previous,x,y),fill=fill,width=max(1,round(radius*2)))
        diameter=max(1,round(radius*2))
        left,top=round(x)-diameter//2,round(y)-diameter//2
        if diameter==1:
            draw.point((round(x),round(y)),fill=fill)
        else:
            draw.ellipse((left,top,left+diameter-1,top+diameter-1),fill=fill)
        self.previous=(x,y)
        # Replace only the edited pixels in the displayed image. Large magnified
        # masks can then be painted without rebuilding a whole 3072px composite.
        pad=radius+3
        box=(max(0,int(min(previous[0],x)-pad)),max(0,int(min(previous[1],y)-pad)),
             min(self.mask.width,int(max(previous[0],x)+pad+1)),min(self.mask.height,int(max(previous[1],y)+pad+1)))
        if box[2]>box[0] and box[3]>box[1]:
            tile=self.preview_image(box)
            painter=QPainter(self.picture)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
            painter.drawPixmap(box[0],box[1],pixmap(tile))
            painter.end()
        self.update()

    def mousePressEvent(self,event):
        super().mousePressEvent(event)
        if self.panning or self.show_original:
            return
        self.setFocus()
        self.update_transform()
        if event.button()==Qt.MouseButton.LeftButton and self.paper.contains(event.position()):
            self.remember()
            self.previous=None
            self.stroke(event.position())
            event.accept()

    def mouseMoveEvent(self,event):
        self.cursor_position=event.position() if self.paper.contains(event.position()) else None
        if self.panning:
            super().mouseMoveEvent(event)
            return
        if event.buttons() & Qt.MouseButton.LeftButton and self.previous:
            if self.paper.contains(event.position()) and not self.show_original:
                self.stroke(event.position())
        self.update()

    def mouseReleaseEvent(self,event):
        super().mouseReleaseEvent(event)
        self.previous=None

    def leaveEvent(self,event):
        self.cursor_position=None
        self.update()
        super().leaveEvent(event)

    def undo(self):
        if self.history:
            self.redo_history.append(self.mask.copy())
            self.mask=self.history.pop()
            self.rebuild()

    def remember(self):
        self.history.append(self.mask.copy());self.redo_history.clear()
        while len(self.history)>1 and (len(self.history)>15 or len(self.history)*self.mask.width*self.mask.height>64*1024**2):self.history.pop(0)

    def redo(self):
        if self.redo_history:
            self.history.append(self.mask.copy());self.mask=self.redo_history.pop();self.rebuild()


class MaskDialog(QDialog):
    def __init__(self,asset,parent=None):
        super().__init__(parent)
        self.setWindowTitle('修正抠图 · '+asset.name)
        self.resize(880,840)
        self.canvas=MaskCanvas(asset)
        layout=QVBoxLayout(self)
        layout.addWidget(label('修正发丝、披风与道具','section'))
        layout.addWidget(label('擦除多余背景，保留误删部分；修改只影响蒙版，原照片保持完整。','muted'))
        layout.addWidget(label('滚轮缩放 · 横向滚轮调笔刷（或 Shift＋滚轮）· Alt＋拖动画面','muted'))
        toolbar=QHBoxLayout()
        self.erase=QPushButton('擦除背景')
        self.keep=QPushButton('保留主体')
        self.erase.setObjectName('primary')
        self.erase.clicked.connect(lambda:self.mode('erase'))
        self.keep.clicked.connect(lambda:self.mode('keep'))
        toolbar.addWidget(self.erase)
        toolbar.addWidget(self.keep)
        undo=QPushButton('撤销笔画 · Ctrl+Z')
        undo.clicked.connect(self.canvas.undo)
        toolbar.addWidget(undo)
        redo=QPushButton('重做');redo.clicked.connect(self.canvas.redo);toolbar.addWidget(redo)
        reset=QPushButton('恢复自动抠图')
        reset.clicked.connect(self.reset)
        toolbar.addWidget(reset)
        toolbar.addStretch()
        toolbar.addWidget(label('笔刷'))
        self.brush=QSlider(Qt.Orientation.Horizontal)
        self.brush.setRange(1,256)
        self.brush.setValue(32)
        self.brush.setFixedWidth(110)
        self.brush.valueChanged.connect(self.canvas.set_brush_size)
        self.brush_label=label('32 px','muted')
        self.canvas.brushChanged.connect(lambda v:(self.brush.setValue(v),self.brush_label.setText(f'{v} px')))
        toolbar.addWidget(self.brush)
        toolbar.addWidget(self.brush_label)
        layout.addLayout(toolbar)
        layout.addWidget(self.canvas,1)
        original=QCheckBox('查看原照')
        original.toggled.connect(self.toggle_original)
        viewbar=QHBoxLayout()
        viewbar.addWidget(original)
        viewbar.addStretch()
        self.zoom_label=label('','muted')
        self.canvas.zoomChanged.connect(lambda v:self.zoom_label.setText(f'{v:.0f}%'))
        viewbar.addWidget(self.zoom_label)
        for name,action in [('适合窗口',self.canvas.fit_view),('100%',self.canvas.actual_size)]:
            button=QPushButton(name)
            button.clicked.connect(action)
            viewbar.addWidget(button)
        layout.addLayout(viewbar)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('应用修正')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        bind_history(self,self.canvas.undo,self.canvas.redo)

    def mode(self,mode):
        self.canvas.mode=mode
        for button,active in ((self.erase,mode=='erase'),(self.keep,mode=='keep')):
            button.setObjectName('primary' if active else '')
            button.style().unpolish(button)
            button.style().polish(button)

    def done(self,result):
        self.canvas.picture=None
        super().done(result)

    def reset(self):
        self.canvas.remember()
        self.canvas.mask=self.canvas.initial.copy()
        self.canvas.rebuild()

    def toggle_original(self,state):
        self.canvas.show_original=state
        self.canvas.rebuild()


class Studio(QMainWindow):
    def __init__(self,project=None):
        super().__init__()
        prepare_directories()
        self.preferences=read_preferences()
        startup_path=None
        if project is None and self.preferences.get('last_project'):
            try:
                path=ROOT/self.preferences['last_project']
                if path.is_file():
                    project=load_project(path)
                    startup_path=path
            except Exception:
                pass
        self.project=project or self.initial_project()
        self.project.ensure_slots()
        self.renderer=Renderer()
        self.segmenter=LocalSegmenter()
        self.selected=0
        self.syncing=False
        self.busy=False
        self.dirty=False
        self.undo_stack=[]
        self.redo_stack=[]
        self.project_path=startup_path
        export_dir=ROOT/self.preferences.get('export_directory','workspace/exports')
        self.last_export_dir=export_dir if export_dir.is_dir() else DATA/'exports'
        self.thumbnail_icons={}
        self.reference_window=None
        self.copied_tuning=None
        self.worker=None
        self.errors=[]
        self.pending_imports=[]
        self.instance=uuid.uuid4().hex
        self.recovery_path=None
        self.recovered_from=None
        self.last_recovery_signature=None
        self.text_timer=QTimer(self)
        self.text_timer.setSingleShot(True)
        self.text_timer.timeout.connect(self.commit_text)
        self.draft_timer=QTimer(self)
        self.draft_timer.setSingleShot(True)
        self.draft_timer.timeout.connect(self.autosave)
        self.draft_guard=QTimer(self)
        self.draft_guard.setInterval(12000)
        self.draft_guard.timeout.connect(self.autosave)
        self.draft_guard.start()
        self.resize(1440,980)
        self.setMinimumSize(1120,740)
        self.setWindowTitle(APP_TITLE)
        root=QWidget()
        self.setCentralWidget(root)
        layout=QVBoxLayout(root)
        layout.setContentsMargins(22,18,22,12)
        layout.setSpacing(16)
        header=QHBoxLayout()
        brand=QVBoxLayout()
        brand.setSpacing(2)
        brand.addWidget(label('Cosfolio · 偶像写真工房','brand'))
        brand.addWidget(label('把照片做成你的写真杂志与卡面','muted'))
        header.addLayout(brand)
        header.addStretch()
        header.addWidget(label('本机处理 · 完全离线','pill'))
        self.new_btn=QPushButton('新建')
        self.open_btn=QPushButton('工程图库')
        self.save_btn=QPushButton('保存工程')
        self.export_btn=QPushButton('导出成品')
        self.batch_btn=QPushButton('批量导出')
        self.batch_btn.clicked.connect(self.batch_dialog)
        self.export_btn.setObjectName('primary')
        for button,callback in ((self.new_btn,self.new_project),(self.open_btn,self.project_gallery),
                                (self.save_btn,self.save),(self.export_btn,self.export_dialog)):
            button.clicked.connect(callback)
            header.addWidget(button)
        layout.addLayout(header)
        header.insertWidget(header.count()-1,self.batch_btn)
        pagebar=QHBoxLayout()
        pagebar.addWidget(label('写真页','section'))
        self.page_selector=QComboBox()
        self.page_selector.setMinimumWidth(230)
        self.page_selector.currentIndexChanged.connect(self.switch_page)
        pagebar.addWidget(self.page_selector,1)
        self.page_buttons=[]
        for title,callback in [('＋ 新页',lambda:self.add_page(False)),('复制本页',lambda:self.add_page(True)),
                               ('前移',lambda:self.move_page(-1)),('后移',lambda:self.move_page(1)),('删除本页',self.remove_page)]:
            button=QPushButton(title);button.clicked.connect(callback);pagebar.addWidget(button);self.page_buttons.append(button)
        self.book_btn=QPushButton('导出整本写真')
        self.book_btn.clicked.connect(self.export_book)
        pagebar.addWidget(self.book_btn)
        layout.addLayout(pagebar)
        self.recovery_banner=QFrame()
        banner_layout=QHBoxLayout(self.recovery_banner)
        self.recovery_label=label('发现可恢复的排版草稿')
        banner_layout.addWidget(self.recovery_label,1)
        recover_button=QPushButton('恢复草稿')
        recover_button.clicked.connect(self.recover_draft)
        banner_layout.addWidget(recover_button)
        dismiss_button=QPushButton('稍后')
        dismiss_button.clicked.connect(self.recovery_banner.hide)
        banner_layout.addWidget(dismiss_button)
        self.recovery_banner.hide()
        layout.addWidget(self.recovery_banner)
        body=QHBoxLayout()
        body.setSpacing(16)
        layout.addLayout(body,1)
        left=AssetPanel()
        left.filesDropped.connect(self.import_paths)
        left.setObjectName('panel')
        left.setFixedWidth(245)
        ll=QVBoxLayout(left)
        ll.setContentsMargins(14,16,14,12)
        top=QHBoxLayout()
        top.addWidget(label('照片素材','section'))
        top.addStretch()
        self.count_label=label('0 张','muted')
        top.addWidget(self.count_label)
        ll.addLayout(top)
        self.import_btn=QPushButton('＋ 导入照片')
        self.import_btn.setObjectName('primary')
        self.import_btn.clicked.connect(self.import_dialog)
        ll.addWidget(self.import_btn)
        self.library_btn=QPushButton('照片库 · 专辑与精修素材')
        self.library_btn.clicked.connect(self.photo_library)
        ll.addWidget(self.library_btn)
        hint=label('可从电脑文件夹拖入照片\n素材可再拖入画面指定位置','muted')
        hint.setWordWrap(True)
        ll.addWidget(hint)
        self.photos=PhotoList()
        self.photos.filesDropped.connect(self.import_paths)
        self.photos.itemDoubleClicked.connect(lambda item:self.assign(self.selected,item.data(Qt.ItemDataRole.UserRole)))
        self.photos.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.photos.customContextMenuRequested.connect(self.asset_menu)
        ll.addWidget(self.photos,1)
        ll.addWidget(label('照片和工程只保存在本机','muted'))
        body.addWidget(left)
        center=QVBoxLayout()
        center.setSpacing(8)
        center_header=QHBoxLayout()
        self.preview_label=label('版面预览','section')
        center_header.addWidget(self.preview_label)
        center_header.addStretch()
        self.guides=QCheckBox('辅助线')
        self.guides.toggled.connect(lambda _:self.canvas.update())
        center_header.addWidget(self.guides)
        self.undo_btn=QPushButton('撤销')
        self.redo_btn=QPushButton('重做')
        self.undo_btn.clicked.connect(self.undo)
        self.redo_btn.clicked.connect(self.redo)
        center_header.addWidget(self.undo_btn)
        center_header.addWidget(self.redo_btn)
        center.addLayout(center_header)
        self.canvas=PageCanvas(self)
        self.canvas.selected.connect(self.select_slot)
        self.canvas.selected.connect(lambda _:self.settings_tabs.setCurrentIndex(1))
        self.canvas.changed.connect(self.changed)
        self.canvas.dragStarted.connect(self.history_push)
        self.canvas.assigned.connect(self.assign)
        center.addWidget(self.canvas,1)
        caption=label('拖动画面中的人物调整位置 · 滚轮缩放 · 方向键微调','muted')
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        center.addWidget(caption)
        body.addLayout(center,1)
        scroll=QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(275)
        right=QFrame()
        right.setObjectName('panel')
        scroll.setWidget(right)
        right_root=QVBoxLayout(right)
        right_root.setContentsMargins(10,12,10,12)
        self.settings_tabs=QTabWidget()
        self.settings_tabs.setObjectName('settings')
        self.settings_layouts=[]
        for name in ('版式','照片','文字','分层','交付'):
            page=QWidget()
            page.setObjectName('settingsPage')
            page_layout=QVBoxLayout(page)
            page_layout.setContentsMargins(5,12,5,10)
            page_layout.setSpacing(9)
            self.settings_layouts.append(page_layout)
            tab_scroll=QScrollArea()
            tab_scroll.setWidgetResizable(True)
            tab_scroll.setFrameShape(QFrame.Shape.NoFrame)
            tab_scroll.setWidget(page)
            self.settings_tabs.addTab(tab_scroll,name)
        right_root.addWidget(self.settings_tabs)
        rl=self.settings_layouts[0]
        rl.setSpacing(9)
        rl.addWidget(label('模板与排版','section'))
        self.templates=QComboBox()
        for key,value in TEMPLATES.items():
            self.templates.addItem(display_name(key),key)
        self.templates.currentIndexChanged.connect(self.change_template)
        self.templates.setVisible(False)
        self.template_picture=QLabel()
        self.template_picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.template_picture.setFixedHeight(180)
        rl.addWidget(self.template_picture)
        self.template_picker=QPushButton(f'选择模板 · {len(TEMPLATES)} 款')
        self.template_picker.clicked.connect(self.choose_template)
        rl.addWidget(self.template_picker)
        self.create_template_btn=QPushButton('＋ 新建模板 · 试用')
        self.create_template_btn.clicked.connect(self.create_template)
        rl.addWidget(self.create_template_btn)
        self.reference_button=QPushButton('查看原场刊参考')
        self.reference_button.clicked.connect(self.open_reference)
        rl.addWidget(self.reference_button)
        self.template_note=label('','muted')
        self.template_note.setWordWrap(True)
        rl.addWidget(self.template_note)
        rl.addStretch()
        rl=self.settings_layouts[1]
        rl.addWidget(label('当前照片位置','section'))
        self.slots=QComboBox()
        self.slots.currentIndexChanged.connect(self.select_slot)
        rl.addWidget(self.slots)
        self.assignments=QComboBox()
        self.assignments.currentIndexChanged.connect(self.change_assignment)
        rl.addWidget(self.assignments)
        self.fit_mode=QComboBox()
        for name,key in [('取景 · 模板推荐','template'),('取景 · 完整主体','contain'),('取景 · 填满画框','cover')]:
            self.fit_mode.addItem(name,key)
        self.fit_mode.currentIndexChanged.connect(self.change_fit)
        rl.addWidget(self.fit_mode)
        self.sliders={}
        self.value_labels={}
        for key,title,low,high,value in [('zoom','人物大小',40,250,100),('rotation','旋转角度',-30,30,0),
                                       ('brightness','人物亮度',70,130,100),('contrast','人物对比度',60,140,100),
                                       ('saturation','人物饱和度',0,160,100),('warmth','人物冷暖',-100,100,0),
                                       ('shadow_opacity','投影浓度',0,100,22),('shadow_blur','投影柔和程度',0,80,9),
                                       ('shadow_x','投影左右方向',-100,100,8),('shadow_y','投影上下方向',-100,100,10)]:
            row=QHBoxLayout()
            row.addWidget(label(title))
            row.addStretch()
            val=label('','muted')
            row.addWidget(val)
            rl.addLayout(row)
            slider=ResetSlider(value)
            slider.setRange(low,high)
            slider.setValue(value)
            slider.sliderPressed.connect(self.history_push)
            slider.resetRequested.connect(lambda k=key:self.reset_slider(k))
            slider.valueChanged.connect(lambda v,k=key:self.slider_changed(k,v))
            self.sliders[key]=slider
            self.value_labels[key]=val
            rl.addWidget(slider)
        self.dehalo=QCheckBox('减轻浅色背景的边缘白边')
        self.shadow=QCheckBox('添加柔和投影')
        self.dehalo.toggled.connect(lambda v:self.toggle('dehalo',v))
        self.shadow.toggled.connect(lambda v:self.toggle('shadow',v))
        rl.addWidget(self.dehalo)
        rl.addWidget(self.shadow)
        self.flip=QCheckBox('水平翻转人物')
        self.flip.setToolTip('仅翻转当前位置的人物，服装上的文字也会反向。')
        self.flip.toggled.connect(lambda v:self.toggle('flip',v))
        rl.addWidget(self.flip)
        self.reset_color_btn=QPushButton('重置调色')
        self.reset_color_btn.clicked.connect(self.reset_color)
        rl.addWidget(self.reset_color_btn)
        self.match_btn=QPushButton('匹配背景亮度与冷暖')
        self.match_btn.clicked.connect(self.match_background)
        rl.addWidget(self.match_btn)
        row=QHBoxLayout()
        self.copy_tuning_btn=QPushButton('复制调色')
        self.paste_tuning_btn=QPushButton('粘贴调色')
        self.copy_tuning_btn.clicked.connect(self.copy_tuning)
        self.paste_tuning_btn.clicked.connect(self.paste_tuning)
        row.addWidget(self.copy_tuning_btn);row.addWidget(self.paste_tuning_btn);rl.addLayout(row)
        row=QHBoxLayout()
        self.mask_btn=QPushButton('修正抠图')
        self.mask_btn.clicked.connect(self.edit_mask)
        reset=QPushButton('重置位置')
        reset.clicked.connect(self.reset_place)
        row.addWidget(self.mask_btn)
        row.addWidget(reset)
        rl.addLayout(row)
        self.settings_layouts[0].addWidget(label('μ’s 灵感配色点缀','muted'))
        self.accents=QComboBox()
        for key,(name,color) in ACCENTS.items():
            if color:
                swatch=QPixmap(18,18)
                swatch.fill(QColor(color))
                self.accents.addItem(QIcon(swatch),name,key)
            else:
                self.accents.addItem(name,key)
        self.accents.currentIndexChanged.connect(self.change_accent)
        self.settings_layouts[0].addWidget(self.accents)
        rl.addStretch()
        rl=self.settings_layouts[2]
        rl.addWidget(label('文字内容','section'))
        self.text_mode=QComboBox()
        self.text_mode.addItem('保留原页文字（默认）','original')
        self.text_mode.addItem('使用我的文字','custom')
        self.text_mode.currentIndexChanged.connect(self.change_text_mode)
        rl.addWidget(self.text_mode)
        self.text_note=label('','muted')
        self.text_note.setWordWrap(True)
        rl.addWidget(self.text_note)
        self.text_inputs={}
        for key,title in [('title','姓名 / 主标题'),('subtitle','副标题'),('footer','页脚')]:
            rl.addWidget(label(title,'muted'))
            edit=QLineEdit()
            edit.setMaxLength(100 if key=='title' else 150)
            edit.editingFinished.connect(lambda k=key:self.text_changed(k))
            edit.textEdited.connect(lambda _:self.text_timer.start(180))
            self.text_inputs[key]=edit
            rl.addWidget(edit)
        self.body_label=label('正文 / 寄语','muted')
        self.body_input=QPlainTextEdit()
        self.body_input.setPlaceholderText('在这里输入自己的访谈内容、拍摄感想或寄语，支持换行。')
        self.body_input.setFixedHeight(130)
        self.body_input.textChanged.connect(lambda:self.text_timer.start(180) if not self.syncing else None)
        rl.addWidget(self.body_label)
        rl.addWidget(self.body_input)
        rl.addSpacing(6)
        rl.addStretch()
        rl=self.settings_layouts[4]
        rl.addWidget(label('高清交付','section'))
        row=QHBoxLayout()
        row.addWidget(label('导出长边'))
        self.export_size=QComboBox()
        for size in (2000,2831,4000,6000,8000):
            self.export_size.addItem(f'{size} 像素',size)
        self.export_size.setCurrentIndex(3)
        row.addWidget(self.export_size)
        rl.addLayout(row)
        self.quality_btn=QPushButton('检查交付清晰度')
        self.quality_btn.clicked.connect(self.check_quality)
        rl.addWidget(self.quality_btn)
        self.page_numbers=QCheckBox('整本统一显示页码')
        self.page_numbers.toggled.connect(self.change_page_numbers)
        rl.addWidget(self.page_numbers)
        rl.addWidget(label('整本摄影 / 出镜署名（可留空）','muted'))
        self.credit_input=QLineEdit()
        self.credit_input.setMaxLength(200)
        self.credit_input.setPlaceholderText('摄影：…  /  出镜：…')
        self.credit_input.editingFinished.connect(self.change_credit)
        rl.addWidget(self.credit_input)
        self.cover_note=label('工程封面：第 1 页','muted')
        rl.addWidget(self.cover_note)
        self.cover_btn=QPushButton('用当前页作工程封面')
        self.cover_btn.clicked.connect(self.set_cover_page)
        rl.addWidget(self.cover_btn)
        rl.addStretch()
        note=label('参考图外框为原图分辨率；放大导出不会增加底图细节。','muted')
        note.setWordWrap(True)
        rl.addWidget(note)
        rl=self.settings_layouts[3]
        rl.addWidget(label('当前页图层','section'))
        hint=label('由下到上：原版背景 → 人物照片 → 原版前景装饰 → 文字。','muted')
        hint.setWordWrap(True);rl.addWidget(hint)
        self.layer_checks={}
        for key,title in [('background','显示原版背景'),('photos','显示人物照片'),('foreground','显示前景装饰')]:
            check=QCheckBox(title)
            check.toggled.connect(lambda v,k=key:self.toggle_layer(k,v))
            self.layer_checks[key]=check;rl.addWidget(check)
        self.frame_btn=QPushButton('校准照片画框与圆角')
        self.frame_btn.clicked.connect(self.edit_frames)
        rl.addWidget(self.frame_btn)
        self.foreground_btn=QPushButton('标记前景遮挡区域')
        self.foreground_btn.clicked.connect(self.edit_foreground)
        rl.addWidget(self.foreground_btn)
        self.reset_layer_btn=QPushButton('恢复本页原版分层')
        self.reset_layer_btn.clicked.connect(self.reset_layers)
        rl.addWidget(self.reset_layer_btn)
        hint=label('前景标记会把原底图中选定的气球、签名或装饰放到人物前面。绿色标记仅用于编辑，不会导出。设置随工程保存，可撤销。','muted')
        hint.setWordWrap(True);rl.addWidget(hint)
        rl.addStretch()
        body.addWidget(scroll)
        self.progress=QProgressBar()
        self.progress.setRange(0,0)
        self.progress.setVisible(False)
        layout.addWidget(self.progress)
        self.cancel_batch_btn=QPushButton('结束批量导出（当前图片完成后停止）')
        self.cancel_batch_btn.clicked.connect(self.cancel_processing)
        self.cancel_batch_btn.hide()
        layout.addWidget(self.cancel_batch_btn)
        self.statusBar().showMessage('就绪 · 本地模型已准备 · 照片不会上传')
        for sequence,callback in [('Ctrl+S',self.save),('Ctrl+Shift+S',lambda:self.save(True)),('Ctrl+O',self.open_project),('Ctrl+Z',self.undo),('Ctrl+Y',self.redo),('Ctrl+Shift+Z',self.redo)]:
            shortcut=QShortcut(QKeySequence(sequence),self)
            shortcut.activated.connect(callback)
        self.rebuild_ui()
        recoveries=list_recoveries(self.instance)
        if recoveries:
            stamp,path,title=recoveries[0]
            self.available_recovery=path
            self.recovery_label.setText(f'可恢复草稿：{title}')
            self.recovery_banner.show()

        from .editor_visual import apply_editor_visual
        apply_editor_visual(self)

    def refresh_pages(self):
        # Position-only drags must not deepcopy every placement on all 40 pages.
        records=self.project.pages or [{}]
        names=[]
        for i,record in enumerate(records):
            title=self.project.title if i==self.project.active_page else record['title']
            template=self.project.template if i==self.project.active_page else record['template']
            names.append(f'{i+1:02d} · {title or "未命名"} · {display_name(template)}')
        if names!=[self.page_selector.itemText(i) for i in range(self.page_selector.count())]:
            self.page_selector.blockSignals(True)
            self.page_selector.clear();self.page_selector.addItems(names)
            self.page_selector.blockSignals(False)
        self.page_selector.blockSignals(True)
        self.page_selector.setCurrentIndex(self.project.active_page)
        self.page_selector.blockSignals(False)

    def switch_page(self,index):
        if self.syncing or self.busy or index==self.project.active_page or index<0:return
        self.commit_text();self.history_push()
        self.project.select_page(index)
        self.selected=0
        self.rebuild_ui();self.changed()

    def add_page(self,duplicate=False):
        if self.busy:return
        if self.project.page_count>=40:
            QMessageBox.information(self,'写真页数','每本写真最多支持 40 页。');return
        self.commit_text();self.history_push()
        self.project.add_page(duplicate)
        self.selected=0
        self.rebuild_ui();self.changed()

    def remove_page(self):
        if self.busy:return
        if self.project.page_count==1:
            self.statusBar().showMessage('至少保留一页写真');return
        self.commit_text();self.history_push()
        self.project.remove_page();self.selected=0
        self.rebuild_ui();self.changed()
        self.statusBar().showMessage('已删除本页，可撤销恢复')

    def move_page(self,step):
        if self.busy or not 0<=self.project.active_page+step<self.project.page_count:return
        self.commit_text();self.history_push();self.project.move_page(step)
        self.rebuild_ui();self.changed()

    def change_page_numbers(self,value):
        if self.syncing or self.busy:return
        self.history_push();self.project.page_numbers=value;self.changed()

    def change_credit(self):
        if self.syncing or self.busy or not hasattr(self,'credit_input'):return
        value=self.credit_input.text()
        if value!=self.project.credit:
            self.history_push();self.project.credit=value;self.changed()

    def toggle_layer(self,key,value):
        if self.syncing or self.busy:return
        self.history_push();self.project.layout[key]=value;self.changed()

    def reset_layers(self):
        if self.busy:return
        self.history_push();self.project.layout={};self.changed()

    def edit_frames(self):
        if self.busy:return
        from .editors import FrameDialog
        dialog=FrameDialog(self.project,self)
        try:
            if dialog.exec()==QDialog.DialogCode.Accepted:
                self.history_push();self.project.layout=copy.deepcopy(dialog.project.layout);self.changed()
        finally:dialog.deleteLater()

    def edit_foreground(self):
        if self.busy or not TEMPLATES[self.project.template].get('plate'):return
        from tempfile import TemporaryDirectory
        from .render import foreground_mask
        with TemporaryDirectory(prefix='cosfolio-layers-') as folder:
            folder=Path(folder)
            mask_path=folder/'foreground.png'
            source=folder/'plate.png'
            foreground_mask(self.project).save(mask_path)
            template_plate(self.project.template,max(TEMPLATES[self.project.template]['size']),self.project.text_mode).convert('RGB').save(source)
            asset=Asset('foreground','原版前景装饰',str(source),str(mask_path),str(mask_path))
            dialog=MaskDialog(asset,self)
            dialog.setWindowTitle('标记前景遮挡区域 · 当前写真页')
            dialog.layout().itemAt(0).widget().setText('把原版装饰放到人物前面')
            dialog.layout().itemAt(1).widget().setText('绿色表示前景遮挡；涂选气球、签名或花边，导出会保留其原本颜色。')
            dialog.erase.setText('移出前景');dialog.keep.setText('加入前景')
            for button in dialog.findChildren(QPushButton):
                if button.text()=='恢复自动抠图':button.setText('恢复本次修改前')
            dialog.canvas.overlay_mode=True
            dialog.canvas.rebuild();dialog.mode('keep')
            try:
                if dialog.exec()==QDialog.DialogCode.Accepted:
                    path=DATA/'masks'/f'foreground-{uuid.uuid4().hex[:16]}.png'
                    dialog.canvas.mask.save(path)
                    self.history_push();self.project.layout['foreground_mask']=str(path)
                    self.project.layout['foreground']=True;self.changed()
            finally:dialog.deleteLater()

    def copy_tuning(self):
        place=self.project.placements[self.selected]
        self.copied_tuning={key:getattr(place,key) for key in ('brightness','contrast','saturation','warmth')}
        self.sync_controls();self.statusBar().showMessage('已复制当前人物调色，可粘贴到其他照片或写真页')

    def paste_tuning(self):
        if self.busy or self.copied_tuning is None:return
        self.history_push()
        for key,value in self.copied_tuning.items():setattr(self.project.placements[self.selected],key,value)
        self.changed()

    def match_background(self):
        if self.busy:return
        place=self.project.placements[self.selected]
        asset=self.project.asset(place.asset_id)
        if not asset:return
        try:
            t=TEMPLATES[self.project.template]
            background=template_plate(self.project.template,max(t['size']),self.project.text_mode)
            x,y,w,h=frames(self.project)[self.selected]
            background=background.crop((round(x),round(y),round(x+w),round(y+h)))
            photo=make_cutout(asset,700,place.dehalo,place.edge_shift,place.edge_softness)
            brightness,warmth=match_lighting(photo,background)
            self.history_push();place.brightness=brightness;place.warmth=warmth;self.changed()
            self.statusBar().showMessage('已温和匹配背景亮度与冷暖，可继续微调或撤销')
        except Exception as exc:QMessageBox.warning(self,'无法匹配背景',str(exc))

    def check_quality(self):
        if self.busy:return
        try:
            report=quality_report(self.project,self.export_size.currentData())
            w,h=report['size'];tw,th=report['template_size']
            lines=[f'成品：{w} × {h} 像素，附 300 PPI 和 sRGB 色彩信息。',f'模板底图：{tw} × {th} 像素。']
            if report['template_enlarged']:lines.append('模板底图会放大；原有扫描文字与装饰不会凭空增加细节。')
            lines+=['',*[f'位置 {p["slot"]} · {p["name"]}：{p["status"]}（约 {p["scale"]:.2f} 倍）' for p in report['photos']],
                    '', '照片检查根据主体像素与当前取景估算，不包含对焦、噪点和发丝边缘质量。']
            QMessageBox.information(self,'交付清晰度检查','\n'.join(lines))
        except Exception as exc:QMessageBox.warning(self,'无法检查清晰度',str(exc))

    def export_book(self):
        if self.busy:return
        self.commit_text()
        if not any(p.asset_id for i in range(self.project.page_count) for p in self.project.page_project(i).placements):
            QMessageBox.information(self,'先放入照片','请先把照片放进写真页。');return
        folder=QFileDialog.getExistingDirectory(self,'选择整本写真的导出位置',str(self.last_export_dir))
        if not folder:return
        from datetime import datetime
        target=Path(folder)/(export_basename(self.project.title,self.project.subtitle)[:75]+'_写真_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:4])
        try:target.mkdir()
        except OSError as exc:QMessageBox.warning(self,'无法创建导出目录',str(exc));return
        self.last_export_dir=Path(folder);self.remember_preferences();self.set_busy(True)
        self.cancel_batch_btn.setText('取消整本导出（保留已完成页面）')
        self.cancel_batch_btn.setEnabled(True);self.cancel_batch_btn.show()
        worker=BookWorker(self.project,target,self.export_size.currentData());self.worker=worker
        worker.progress.connect(lambda i,n,name:self.statusBar().showMessage(f'整本导出 {i+1}/{n} · {name}'))
        worker.ready.connect(self.batch_finished)
        worker.finished.connect(lambda:self.set_busy(False));worker.start()

    @staticmethod
    def initial_project():
        return Project(title='YOUR NAME',subtitle='COSPLAY PHOTO COLLECTION')

    def rebuild_ui(self):
        self.syncing=True
        if [self.templates.itemData(i) for i in range(self.templates.count())]!=list(TEMPLATES):
            self.templates.clear()
            for key,value in TEMPLATES.items():self.templates.addItem(display_name(key),key)
        for i in range(self.templates.count()):self.templates.setItemText(i,display_name(self.templates.itemData(i)))
        self.refresh_pages()
        self.templates.setCurrentIndex(list(TEMPLATES).index(self.project.template))
        self.slots.clear()
        self.slots.addItems(TEMPLATES[self.project.template]['labels'])
        self.selected=min(self.selected,self.slots.count()-1)
        self.slots.setCurrentIndex(self.selected)
        self.template_note.setText(TEMPLATES[self.project.template]['note'])
        self.template_picture.setPixmap(template_thumbnail(self.project.template).scaled(220,180,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))
        self.template_picker.setText(display_name(self.project.template)+' · 图库')
        if self.reference_window is not None and self.reference_window.isVisible():
            self.reference_window.set_template(self.project.template)
        self.photos.clear()
        self.assignments.clear()
        self.assignments.addItem('此位置留空','')
        for asset in self.project.assets:
            if asset.source not in self.thumbnail_icons:
                thumb=oriented_image(asset.source,180)
                thumb.thumbnail((100,125),Image.Resampling.LANCZOS)
                self.thumbnail_icons[asset.source]=QIcon(pixmap(thumb))
            item=QListWidgetItem(self.thumbnail_icons[asset.source],asset.name+'\n已抠图 · 可重复使用')
            item.setData(Qt.ItemDataRole.UserRole,asset.id)
            item.setToolTip(f'{asset.name}\n原图 {asset.width} × {asset.height}\n本机处理 {asset.seconds:.1f} 秒')
            self.photos.addItem(item)
            self.assignments.addItem(asset.name,asset.id)
        self.count_label.setText(f'{len(self.project.assets)} 张')
        for key,edit in self.text_inputs.items():
            edit.setText(getattr(self.project,key))
            edit.setCursorPosition(0)
        self.body_input.setPlainText(self.project.body)
        self.syncing=False
        self.sync_controls()
        self.canvas.refresh()

    def select_slot(self,index):
        if self.syncing or not 0<=index<len(TEMPLATES[self.project.template]['slots']):
            return
        self.selected=index
        self.sync_controls()
        self.canvas.refresh()

    def sync_controls(self):
        self.syncing=True
        self.slots.setCurrentIndex(self.selected)
        place=self.project.placements[self.selected]
        self.fit_mode.setCurrentIndex(max(0,self.fit_mode.findData(place.fit)))
        has_original=bool(TEMPLATES[self.project.template].get('plate'))
        self.text_mode.setCurrentIndex(self.text_mode.findData(self.project.text_mode if has_original else 'custom'))
        self.text_mode.setEnabled(has_original and not self.busy)
        original=has_original and self.project.text_mode=='original'
        if original:
            self.text_note.setText('原页文字按底图原样保留。下方主标题、副标题仅用于导出文件名；选择“使用我的文字”后才会替换到页面。')
        elif TEMPLATES[self.project.template].get('custom'):
            self.text_note.setText('自建模板原文继续保留；我的文字仅在页脚添加主标题，不自动识别或覆盖原文。')
        elif has_original:
            self.text_note.setText('下面的文字会替换模板预设区域。原页文字是图片像素，暂不支持自动识别后逐字编辑；可随时切回原样。')
        else:
            self.text_note.setText('这是原创模板，没有原页文字。下面的文字会直接显示在页面上。')
        for key,edit in self.text_inputs.items():
            edit.setEnabled(not self.busy and (key!='footer' or not original))
        has_body=(TEMPLATES[self.project.template].get('text_style') in ('qa','message','minimal') or
                  any(spec['field']=='body' for spec in TEMPLATES[self.project.template].get('text_fields',[])))
        self.body_label.setVisible(has_body)
        self.body_input.setVisible(has_body)
        self.body_input.setEnabled(not original and not self.busy)
        self.reference_button.setEnabled(bool(TEMPLATES[self.project.template].get('reference')) and not self.busy)
        self.accents.setCurrentIndex(max(0,self.accents.findData(self.project.accent)))
        self.assignments.setCurrentIndex(max(0,self.assignments.findData(place.asset_id)))
        for key in self.sliders:
            value=getattr(place,key)
            direct=('rotation','edge_shift','edge_softness','shadow_blur','shadow_x','shadow_y')
            shown=round(value) if key in direct else round(value*100)
            self.sliders[key].setValue(shown)
            self.value_labels[key].setText((f'{shown}°' if key=='rotation' else f'{shown} px' if key in direct else
                                          ('中性' if shown==0 else f'{"偏暖" if shown>0 else "偏冷"} {abs(shown)}') if key=='warmth' else f'{shown}%'))
        self.dehalo.setChecked(place.dehalo)
        self.shadow.setChecked(place.shadow)
        self.flip.setChecked(place.flip)
        self.page_numbers.setChecked(self.project.page_numbers)
        self.cover_note.setText(f'工程封面：第 {self.project.cover_page+1} 页 · 保存时更新预览')
        if not self.credit_input.hasFocus():self.credit_input.setText(self.project.credit)
        for key,check in self.layer_checks.items():check.setChecked(self.project.layout.get(key,True))
        self.match_btn.setEnabled(bool(place.asset_id) and not self.busy)
        self.copy_tuning_btn.setEnabled(bool(place.asset_id) and not self.busy)
        self.paste_tuning_btn.setEnabled(bool(place.asset_id) and self.copied_tuning is not None and not self.busy)
        self.foreground_btn.setEnabled(bool(TEMPLATES[self.project.template].get('plate')) and not self.busy)
        self.reset_color_btn.setEnabled(bool(place.asset_id) and not self.busy)
        self.mask_btn.setEnabled(bool(place.asset_id) and not self.busy)
        self.undo_btn.setEnabled(bool(self.undo_stack) and not self.busy)
        self.redo_btn.setEnabled(bool(self.redo_stack) and not self.busy)
        self.syncing=False

    def history_push(self):
        if self.busy:
            return
        self.undo_stack.append(copy.deepcopy(self.project))
        self.undo_stack=self.undo_stack[-40:]
        self.redo_stack.clear()

    def changed(self):
        self.dirty=True
        self.setWindowTitle(APP_TITLE+' *')
        self.canvas.refresh()
        self.sync_controls()
        self.refresh_pages()
        self.draft_timer.start(1800)

    def undo(self):
        if not self.undo_stack or self.busy:
            return
        self.redo_stack.append(copy.deepcopy(self.project))
        self.project=self.undo_stack.pop()
        self.rebuild_ui()
        self.changed()

    def redo(self):
        if not self.redo_stack or self.busy:
            return
        self.undo_stack.append(copy.deepcopy(self.project))
        self.project=self.redo_stack.pop()
        self.rebuild_ui()
        self.changed()

    def assign(self,index,key):
        if self.busy or (key and not self.project.asset(key)):
            return
        self.history_push()
        self.selected=index
        self.project.placements[index]=Placement(asset_id=key)
        self.settings_tabs.setCurrentIndex(1)
        self.changed()

    def change_assignment(self,index):
        if not self.syncing:
            self.assign(self.selected,self.assignments.currentData() or '')

    def change_template(self,index):
        if self.syncing or self.busy:
            return
        self.history_push()
        self.project.template=self.templates.currentData()
        self.project.layout={}
        self.selected=0
        self.rebuild_ui()
        self.changed()

    def choose_template(self):
        if self.busy:
            return
        dialog=TemplateDialog(self.project.template,self)
        try:
            if dialog.exec()==QDialog.DialogCode.Accepted:
                self.templates.setCurrentIndex(list(TEMPLATES).index(dialog.chosen))
        finally:
            dialog.deleteLater()

    def refresh_template_labels(self):
        for i in range(self.templates.count()):self.templates.setItemText(i,display_name(self.templates.itemData(i)))
        self.template_picker.setText(display_name(self.project.template)+' · 图库')
        self.refresh_pages()
        if self.reference_window is not None and self.reference_window.isVisible():self.reference_window.set_template(self.project.template)

    def open_reference(self):
        if self.busy or not TEMPLATES[self.project.template].get('reference'):
            return
        if self.reference_window is None:
            self.reference_window=ReferenceDialog(self.project.template,self)
        else:
            self.reference_window.set_template(self.project.template)
        self.reference_window.show()
        self.reference_window.raise_()

    def change_fit(self,index):
        if self.syncing or self.busy:
            return
        self.history_push()
        place=self.project.placements[self.selected]
        place.fit=self.fit_mode.currentData()
        place.x=place.y=0
        place.zoom=1
        self.changed()

    def change_accent(self,index):
        if self.syncing or self.busy:
            return
        self.history_push()
        self.project.accent=self.accents.currentData()
        self.changed()

    def change_text_mode(self,index):
        if self.syncing or self.busy:
            return
        mode=self.text_mode.currentData()
        self.commit_text()
        self.history_push()
        self.project.text_mode=mode
        self.changed()

    def slider_changed(self,key,value):
        if self.syncing or self.busy:
            return
        # Keyboard / track clicks also get an undo boundary.
        if not self.sliders[key].isSliderDown():
            self.history_push()
        direct=('rotation','edge_shift','edge_softness','shadow_blur','shadow_x','shadow_y')
        setattr(self.project.placements[self.selected],key,value if key in direct else value/100)
        self.changed()

    def reset_slider(self,key):
        if self.syncing or self.busy:return
        value=self.sliders[key].default
        direct=('rotation','shadow_blur','shadow_x','shadow_y')
        target=value if key in direct else value/100
        place=self.project.placements[self.selected]
        if getattr(place,key)!=target:
            self.history_push();setattr(place,key,target);self.changed()

    def toggle(self,key,value):
        if self.syncing or self.busy:
            return
        self.history_push()
        setattr(self.project.placements[self.selected],key,value)
        self.changed()

    def text_changed(self,key):
        if self.syncing or self.busy:
            return
        text=self.text_inputs[key].text()
        if text!=getattr(self.project,key):
            self.history_push()
            setattr(self.project,key,text)
            self.changed()

    def commit_text(self):
        self.change_credit()
        for key in self.text_inputs:
            self.text_changed(key)
        if not self.syncing and not self.busy:
            body=self.body_input.toPlainText()[:4000]
            if body!=self.project.body:
                self.history_push()
                self.project.body=body
                self.changed()

    def reset_place(self):
        if not self.busy:
            self.assign(self.selected,self.project.placements[self.selected].asset_id)

    def reset_color(self):
        if self.busy:
            return
        self.history_push()
        place=self.project.placements[self.selected]
        place.brightness=place.contrast=place.saturation=1
        place.warmth=0
        self.changed()

    def edit_mask(self):
        if self.busy:
            return
        asset=self.project.asset(self.project.placements[self.selected].asset_id)
        if not asset:
            return
        dialog=MaskDialog(asset,self)
        try:
            if dialog.exec()==QDialog.DialogCode.Accepted:
                # Version masks so page undo/redo can restore a previous mask path.
                self.history_push()
                new_path=DATA/'masks'/f'{asset.id}.{uuid.uuid4().hex[:8]}.png'
                dialog.canvas.mask.save(new_path)
                asset.mask=str(new_path)
                self.renderer.invalidate(asset.id)
                self.changed()
        finally:
            dialog.deleteLater()

    def set_busy(self,busy):
        self.busy=busy
        self.progress.setVisible(busy)
        if not busy:
            self.cancel_batch_btn.hide()
        for item in (self.import_btn,self.library_btn,self.new_btn,self.open_btn,self.save_btn,self.export_btn,self.batch_btn,
                     self.templates,self.template_picker,self.slots,self.assignments,self.photos,self.fit_mode,self.accents,
                     self.page_selector,*self.page_buttons,self.book_btn,self.quality_btn,self.frame_btn,self.reset_layer_btn,
                     self.page_numbers,self.credit_input,self.cover_btn,self.create_template_btn,*self.layer_checks.values()):
            item.setEnabled(not busy)
        for item in (*self.sliders.values(),*self.text_inputs.values(),self.dehalo,self.shadow,self.flip,self.reset_color_btn,self.text_mode):
            item.setEnabled(not busy)
        self.sync_controls()
        if not busy and self.pending_imports:
            queued=self.pending_imports
            self.pending_imports=[]
            QTimer.singleShot(0,lambda:self.import_paths(queued))

    def import_dialog(self):
        paths,_=QFileDialog.getOpenFileNames(self,'导入照片','','照片 (*.jpg *.jpeg *.png *.webp *.tif *.tiff)')
        if paths:
            self.import_paths(paths)

    def asset_menu(self,position):
        if self.busy:
            return
        item=self.photos.itemAt(position)
        if not item:
            return
        key=item.data(Qt.ItemDataRole.UserRole)
        asset=self.project.asset(key)
        menu=QMenu(self)
        menu.addAction('放入当前位置',lambda:self.assign(self.selected,key))
        menu.addAction('导出透明 PNG…',lambda:self.export_cutout(asset))
        menu.addAction('收录到照片库…',lambda:self.photo_library(collect=[asset]))
        menu.addSeparator()
        menu.addAction('从素材框移除',lambda:self.remove_asset(key))
        menu.exec(self.photos.viewport().mapToGlobal(position))

    def remove_asset(self,key):
        if self.busy or not self.project.asset(key):
            return
        self.history_push()
        self.project.assets=[asset for asset in self.project.assets if asset.id!=key]
        for place in self.project.placements:
            if place.asset_id==key:
                place.asset_id=''
        self.project.remap_asset(key,'')
        self.rebuild_ui()
        self.changed()
        self.statusBar().showMessage('素材已从当前工程移除，可撤销恢复；原文件保留')

    def export_cutout(self,asset):
        if self.busy or not asset:
            return
        path,_=QFileDialog.getSaveFileName(self,'导出透明背景主体',
                                         str(self.last_export_dir/(Path(asset.name).stem+'_抠图.png')),'PNG 图片 (*.png)')
        if not path:
            return
        if not path.lower().endswith('.png'):
            path+='.png'
        self.set_busy(True)
        self.statusBar().showMessage('正在本机导出原分辨率透明主体…')
        self.worker=CutoutWorker(asset,path)
        self.worker.ready.connect(self.export_finished)
        self.worker.error.connect(self.export_error)
        self.worker.finished.connect(lambda:self.set_busy(False))
        self.worker.start()

    def import_paths(self,paths):
        if not paths:
            return
        paths=[p for p in paths if Path(p).suffix.lower() in IMAGE_SUFFIXES and Path(p).is_file()]
        if not paths:
            return
        if self.busy:
            self.pending_imports.extend(paths)
            self.statusBar().showMessage(f'已排队 {len(self.pending_imports)} 张照片，当前处理完成后自动导入')
            return
        if len(self.project.assets)+len(paths)>100:
            QMessageBox.information(self,'照片数量','初版每个工程最多支持 100 张照片。')
            return
        self.history_push()
        self.errors=[]
        self.set_busy(True)
        self.cancel_batch_btn.setText('结束导入（当前照片完成后停止）')
        self.cancel_batch_btn.setEnabled(True)
        self.cancel_batch_btn.show()
        worker=ImportWorker(paths,self.segmenter)
        self.worker=worker
        worker.progress.connect(self.statusBar().showMessage)
        worker.ready.connect(self.asset_imported)
        worker.error.connect(self.errors.append)
        worker.finished.connect(self.import_finished)
        worker.start()

    def asset_imported(self,asset):
        self.project.assets.append(asset)
        # Fill the next empty position; all assignments remain editable.
        for place in self.project.placements[:len(TEMPLATES[self.project.template]['slots'])]:
            if not place.asset_id:
                place.asset_id=asset.id
                break
        self.rebuild_ui()
        self.changed()

    def import_finished(self):
        cancelled=self.worker.cancelled
        self.set_busy(False)
        self.statusBar().showMessage('导入已停止，已完成的照片保留' if cancelled else '导入完成 · 拖入照片可更换各个位置')
        if self.errors:
            QMessageBox.warning(self,'部分照片未能导入','\n'.join(self.errors))

    def check_unsaved(self):
        self.commit_text()
        if not self.dirty:
            return True
        answer=QMessageBox.question(self,'保存修改','当前排版有未保存的修改，是否保存工程？',
                                   QMessageBox.StandardButton.Save|QMessageBox.StandardButton.Discard|QMessageBox.StandardButton.Cancel)
        if answer==QMessageBox.StandardButton.Cancel:
            return False
        return self.save() if answer==QMessageBox.StandardButton.Save else True

    def replace_project(self,project,path=None):
        self.clear_recovery()
        self.project=project
        self.project.ensure_slots()
        self.project_path=path
        self.selected=0
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.renderer.invalidate()
        self.dirty=False
        self.setWindowTitle(APP_TITLE)
        self.rebuild_ui()

    def new_project(self):
        if not self.busy and self.check_unsaved():
            self.replace_project(Project(title='YOUR NAME',subtitle='COSPLAY PHOTO COLLECTION'))

    def remember_preferences(self):
        try:
            for key,value in (('last_project',self.project_path),('export_directory',self.last_export_dir)):
                if value:
                    path=Path(value)
                    try:
                        self.preferences[key]=str(path.relative_to(ROOT))
                    except ValueError:
                        self.preferences[key]=str(path)
            if self.project_path:
                value=str(Path(self.project_path).resolve())
                recent=self.preferences.get('recent_projects',[])
                self.preferences['recent_projects']=[value]+[p for p in recent if str((ROOT/p).resolve()).casefold()!=value.casefold()][:19]
            save_preferences(self.preferences)
        except OSError:
            pass

    def save(self,save_as=False):
        if self.busy:
            return False
        self.commit_text()
        if self.project_path and not save_as:
            path=str(self.project_path)
        else:
            default=export_basename(self.project.title,self.project.subtitle)+'.cosfolio'
            path,_=QFileDialog.getSaveFileName(self,'保存可继续编辑的工程',
                                             str(self.project_path or DATA/'projects'/default),'Cosfolio 工程 (*.cosfolio)')
        if not path:
            return False
        if not path.lower().endswith('.cosfolio'):
            path+='.cosfolio'
        try:
            save_project(self.project,path)
            self.project_path=path
            self.remember_preferences()
            self.dirty=False
            self.clear_recovery()
            self.setWindowTitle(APP_TITLE)
            self.statusBar().showMessage('工程已保存，包含原照片和抠图，可复制到另一台电脑继续编辑')
            return True
        except Exception as exc:
            QMessageBox.critical(self,'保存失败',str(exc))
            return False

    def open_project(self):
        if self.busy or not self.check_unsaved():
            return
        path,_=QFileDialog.getOpenFileName(self,'打开工程',str(DATA/'projects'),'Cosfolio 工程 (*.cosfolio)')
        if path:
            try:
                self.replace_project(load_project(path),path)
                self.remember_preferences()
                self.statusBar().showMessage('工程已打开')
            except Exception as exc:
                QMessageBox.critical(self,'无法打开工程',str(exc))

    def project_gallery(self):
        if self.busy:return
        from .projects_ui import ProjectGallery
        paths=[ROOT/p for p in self.preferences.get('recent_projects',[])]
        if self.preferences.get('last_project'):paths.insert(0,ROOT/self.preferences['last_project'])
        folder=ROOT/self.preferences.get('project_directory','workspace/projects')
        dialog=ProjectGallery(paths,folder,self)
        try:
            accepted=dialog.exec()==QDialog.DialogCode.Accepted
            if dialog.folder:
                self.preferences['project_directory']=str(dialog.folder);save_preferences(self.preferences)
            if accepted and dialog.chosen and self.check_unsaved():
                try:
                    self.replace_project(load_project(dialog.chosen),Path(dialog.chosen));self.remember_preferences()
                    self.statusBar().showMessage('工程已打开 · 封面仅用于图库预览')
                except Exception as exc:QMessageBox.warning(self,'无法打开工程',str(exc))
        finally:dialog.deleteLater()

    def photo_library(self,checked=False,collect=None):
        if self.busy:return
        from .library_ui import PhotoLibraryDialog
        dialog=PhotoLibraryDialog(self.segmenter,collect or self.project.assets,self)
        if collect:QTimer.singleShot(0,dialog.collect_project)
        try:
            if dialog.exec()==QDialog.DialogCode.Accepted and dialog.added_assets:
                self.history_push()
                for asset in dialog.added_assets:
                    self.asset_imported(asset)
                self.statusBar().showMessage(f'已从照片库加入 {len(dialog.added_assets)} 张照片，沿用精修蒙版，无需重新抠图')
        finally:dialog.deleteLater()

    def set_cover_page(self):
        if self.busy or self.project.cover_page==self.project.active_page:return
        self.history_push();self.project.cover_page=self.project.active_page;self.changed()
        self.statusBar().showMessage('已选择工程封面，保存工程时更新预览图')

    def create_template(self):
        if self.busy:return
        from .template_wizard import TemplateWizard
        dialog=TemplateWizard(self.segmenter,self)
        try:
            if dialog.exec()==QDialog.DialogCode.Accepted and dialog.created_key:
                self.commit_text();self.history_push()
                self.project.template=dialog.created_key;self.project.layout={};self.project.text_mode='original';self.selected=0
                self.rebuild_ui();self.changed()
                self.statusBar().showMessage('自建模板已加入图库，原页参考已保留；可拖入自己的照片验证效果')
        finally:dialog.deleteLater()

    def export_dialog(self):
        if self.busy:
            return
        self.commit_text()
        count=len(TEMPLATES[self.project.template]['slots'])
        if not any(p.asset_id for p in self.project.placements[:count]):
            QMessageBox.information(self,'先放入照片','请先把至少一张照片放进版面。')
            return
        default=export_basename(self.project.title,self.project.subtitle)+'.png'
        path,_=QFileDialog.getSaveFileName(self,'导出成品',str(self.last_export_dir/default),
                                         'PNG 图片 (*.png);;JPEG 图片 (*.jpg)')
        if not path:
            return
        if Path(path).suffix.lower() not in ('.png','.jpg','.jpeg'):
            path+='.png'
        self.last_export_dir=Path(path).parent
        self.remember_preferences()
        self.set_busy(True)
        self.statusBar().showMessage('正在本机合成高清图片，请稍候…')
        self.cancel_batch_btn.setText('取消高清导出')
        self.cancel_batch_btn.setEnabled(True);self.cancel_batch_btn.show()
        worker=ExportWorker(self.project,path,self.export_size.currentData())
        self.worker=worker
        worker.progress.connect(self.statusBar().showMessage)
        worker.cancelled.connect(lambda:self.statusBar().showMessage('导出已取消，原有成品保留'))
        worker.ready.connect(self.export_finished)
        worker.error.connect(self.export_error)
        worker.finished.connect(lambda:self.set_busy(False))
        worker.start()

    def export_finished(self,path,size):
        self.statusBar().showMessage(f'已导出 {size[0]} × {size[1]} 像素 · {path}')
        QMessageBox.information(self,'导出完成',f'图片已保存到：\n{path}\n\n尺寸：{size[0]} × {size[1]} 像素')

    def export_error(self,message):
        QMessageBox.critical(self,'导出失败',message)

    def autosave(self):
        if not self.dirty:
            return
        if self.busy:
            self.draft_timer.start(2000)
            return
        try:
            signature=json.dumps(self.project.to_dict(),sort_keys=True,ensure_ascii=False)
            if signature==self.last_recovery_signature and self.recovery_path and self.recovery_path.exists():
                return
            self.recovery_path=write_recovery(self.project,self.instance)
            self.last_recovery_signature=signature
            if self.recovered_from:
                self.recovered_from.unlink(missing_ok=True)
                self.recovered_from=None
        except OSError as exc:
            self.statusBar().showMessage(f'草稿暂未保存：{exc}')

    def clear_recovery(self):
        self.draft_timer.stop()
        self.last_recovery_signature=None
        if self.recovery_path:
            self.recovery_path.unlink(missing_ok=True)
            self.recovery_path=None

    def recover_draft(self):
        if self.busy or not self.check_unsaved():
            return
        try:
            project=read_recovery(self.available_recovery)
            self.replace_project(project)
            self.recovered_from=self.available_recovery
            self.recovery_banner.hide()
            self.changed()
            self.autosave()
            self.statusBar().showMessage('已恢复草稿，建议保存为工程文件')
        except Exception as exc:
            QMessageBox.warning(self,'无法恢复草稿',str(exc))

    def batch_dialog(self):
        if self.busy or not self.project.assets:
            return
        self.commit_text()
        dialog=TemplateDialog(self.project.template,self,batch=True)
        try:
            accepted=dialog.exec()==QDialog.DialogCode.Accepted
            selected_keys=dialog.selected_keys()
        finally:
            dialog.deleteLater()
        if not accepted:
            return
        folder=QFileDialog.getExistingDirectory(self,'选择批量导出的文件夹',str(self.last_export_dir))
        if not folder:
            return
        from datetime import datetime,timezone,timedelta
        stamp=datetime.now(timezone(timedelta(hours=8))).strftime('%Y%m%d_%H%M%S')
        target=Path(folder)/f'批量_{stamp}_{uuid.uuid4().hex[:4]}'
        try:
            target.mkdir()
        except OSError as exc:
            QMessageBox.warning(self,'无法创建导出目录',str(exc))
            return
        self.set_busy(True)
        self.cancel_batch_btn.setText('结束批量导出（当前图片完成后停止）')
        self.cancel_batch_btn.setEnabled(True)
        self.cancel_batch_btn.show()
        worker=BatchWorker(self.project,selected_keys,target,self.export_size.currentData())
        self.worker=worker
        worker.progress.connect(lambda i,n,name:self.statusBar().showMessage(f'批量导出 {i+1}/{n} · {name}'))
        worker.ready.connect(self.batch_finished)
        worker.finished.connect(lambda:(self.set_busy(False),self.cancel_batch_btn.hide()))
        worker.start()

    def cancel_processing(self):
        if isinstance(self.worker,(ImportWorker,BatchWorker,ExportWorker,BookWorker)) and self.worker.isRunning():
            if isinstance(self.worker,ImportWorker):
                self.pending_imports=[]
            self.worker.requestInterruption()
            self.cancel_batch_btn.setEnabled(False)
            self.cancel_batch_btn.setText('正在完成当前图片…')

    def batch_finished(self,report):
        ok=sum(item['ok'] for item in report['results'])
        failed=sum(not item['ok'] for item in report['results'])
        message=f'已导出 {ok} 张图片'+(f'，{failed} 张未成功' if failed else '')
        if report['cancelled']:
            message+='，已停止后续任务'
        if report.get('report_error'):
            message+='\n导出记录暂未保存：'+report['report_error']
        self.statusBar().showMessage(message+' · '+report['folder'])
        QMessageBox.information(self,'批量导出完成',message+'\n\n'+report['folder'])

    def closeEvent(self,event):
        if self.busy:
            QMessageBox.information(self,'正在处理','请等待当前照片处理或导出结束后再关闭。')
            event.ignore()
        elif self.check_unsaved():
            self.syncing=True
            self.busy=True
            if self.reference_window is not None:
                self.reference_window.close()
            self.clear_recovery()
            self.draft_guard.stop()
            self.text_timer.stop()
            self.canvas.timer.stop()
            self.thumbnail_icons.clear()
            self.canvas.layers.clear()
            self.canvas.image=None
            self.canvas.foreground=None
            self.template_picture.clear()
            self.photos.clear()
            for index in range(self.accents.count()):
                self.accents.setItemIcon(index,QIcon())
            self.renderer.invalidate()
            event.accept()
        else:
            event.ignore()


def main():
    app=QApplication(sys.argv)
    configure_app(app)
    studio=Studio()
    area=app.primaryScreen().availableGeometry()
    studio.resize(min(1440,area.width()-50),min(980,area.height()-60))
    studio.show()
    result=app.exec()
    shutdown_gui(app)
    sys.exit(result)


def shutdown_gui(app):
    """Retire native windows before Qt's platform and font caches shut down."""
    import gc
    from shiboken6 import isValid,delete
    from PySide6.QtGui import QPixmapCache
    for widget in app.allWidgets():
        if isValid(widget):
            widget.blockSignals(True)
    for widget in app.topLevelWidgets():
        if isValid(widget):
            for viewport in widget.findChildren(ImageViewport):
                viewport.picture=None
            delete(widget)
    QPixmapCache.clear()
    QFontDatabase.removeAllApplicationFonts()
    gc.collect()


def configure_app(app):
    # Explicit font loading also makes the headless verification match Windows.
    for name in ('msyh.ttc','msyhbd.ttc','segoeui.ttf'):
        path=Path('C:/Windows/Fonts')/name
        if path.exists():
            QFontDatabase.addApplicationFont(str(path))
    app.setApplicationName('Cosfolio')
    app.setFont(QFont('Microsoft YaHei UI',10))
    app.setStyle('Fusion')
    app.setStyleSheet(STYLE)
    icon=ROOT/'resources'/'icon.ico'
    if icon.exists():
        app.setWindowIcon(QIcon(str(icon)))
