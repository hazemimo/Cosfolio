"""The selected Umi blue/white demo, rendered with native desktop widgets.

This module only arranges and paints the 0.9 photo-library controls. Storage,
selection, jobs, history, import, comparison and delivery remain in library_ui.
"""
from __future__ import annotations

from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import Qt, QSize, QRect, QRectF, QPointF, QEvent, QObject, QTimer
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QToolButton,
    QVBoxLayout, QHBoxLayout, QGridLayout, QSplitter, QScrollArea, QSizePolicy,
    QStyledItemDelegate, QStyle, QMenu)

BLUE = '#174d8b'
INK = '#233a52'
MUTED = '#687c91'
LINE = '#dde6f0'
STYLE = '''
QDialog#photoLibrary { background: #f0f4f9; }
QWidget#libraryContent, QWidget#libraryMain { background: #f0f4f9; }
QFrame#libraryChrome, QFrame#libraryFooter { background: #ffffff; }
QFrame#libraryChrome { border-bottom: 1px solid #dde6f0; }
QFrame#libraryFooter { border-top: 1px solid #dde6f0; }
QFrame#librarySidebar { background: #ffffff; border: 0; border-right: 1px solid #dde6f0; border-radius: 0; }
QFrame#libraryDetails { background: #ffffff; border: 0; border-left: 1px solid #dde6f0; border-radius: 0; }
QWidget#libraryDetailsBody, QWidget#libraryAdvanced { background: #ffffff; }
QLabel { color: #233a52; }
QLabel#libraryBrand { font-size: 25px; font-weight: 600; letter-spacing: -1px; color: #233a52; }
QLabel#libraryBrandSub { font-size: 12px; letter-spacing: 1px; color: #233a52; }
QLabel#libraryEyebrow { color: #687c91; font-size: 10px; letter-spacing: 2px; }
QLabel#libraryOverline { color: #687c91; font-size: 11px; letter-spacing: 1px; }
QLabel#libraryTitle { color: #233a52; font-size: 19px; font-weight: 500; }
QLabel#libraryHint { color: #687c91; font-size: 11px; }
QLabel#libraryFileName { color: #233a52; font-size: 14px; font-weight: 500; }
QLabel#libraryTag { background: #e6eef9; color: #174d8b; border-radius: 4px; padding: 4px 8px; font-size: 11px; }
QListWidget#albumList, QListView#libraryGrid { background: transparent; border: 0; outline: 0; }
QListWidget#albumList::item, QListWidget#albumList::item:selected,
QListView#libraryGrid::item, QListView#libraryGrid::item:selected { background: transparent; border: 0; padding: 0; margin: 0; }
QListWidget#albumList { font-size: 12px; }
QSplitter::handle { background: #dde6f0; }
QPushButton { background: white; color: #233a52; border: 1px solid #dde6f0; border-radius: 7px; padding: 8px 11px; font-size: 12px; }
QPushButton:hover { border-color: #a9bfd6; background: #f5f8fc; }
QPushButton#primary { background: #174d8b; border-color: #174d8b; color: white; font-weight: 500; }
QPushButton#primary:hover { background: #235e9c; }
QPushButton#primary:disabled { background: #a4bad2; border-color: #a4bad2; color: #f4f7fb; }
QPushButton:disabled { color: #a7b5c4; border-color: #e8edf3; background: #f5f7fa; }
QPushButton#libraryQuiet { background: transparent; border: 0; color: #687c91; padding: 7px 8px; font-size: 11px; text-align: left; }
QPushButton#libraryQuiet:hover { color: #174d8b; background: #e6eef9; }
QToolButton { border: 0; background: transparent; color: #687c91; padding: 5px; border-radius: 5px; font-size: 11px; }
QToolButton:hover { background: #e6eef9; color: #174d8b; }
QToolButton::menu-indicator { image: none; }
QPushButton#libraryHeart { background: transparent; border: 0; padding: 5px; border-radius: 6px; }
QPushButton#libraryHeart:hover { background: #e6eef9; }
QLineEdit, QPlainTextEdit, QComboBox { color: #233a52; border: 1px solid #dde6f0; border-radius: 5px; background: #ffffff; padding: 7px 9px; font-size: 11px; }
QLineEdit#librarySearch { background: #ffffff; padding: 8px 10px; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border-color: #7c9cbe; }
QCheckBox { color: #687c91; font-size: 11px; spacing: 5px; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: transparent; width: 7px; margin: 0; }
QScrollBar::handle:vertical { background: #c4d1df; border-radius: 3px; min-height: 32px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: none; }
'''


def label(value, name='libraryHint'):
    item = QLabel(value)
    item.setObjectName(name)
    item.setTextFormat(Qt.TextFormat.PlainText)
    item.setWordWrap(True)
    return item


def icon(name, color=MUTED, filled=False):
    canvas = QPixmap(40, 40)
    canvas.fill(Qt.GlobalColor.transparent)
    p = QPainter(canvas)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(2, 2)
    p.setPen(QPen(QColor(color), 1.35, Qt.PenStyle.SolidLine,
                 Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    if name == 'heart':
        path = QPainterPath(QPointF(10, 17))
        path.cubicTo(8, 15, 2, 11, 2, 7)
        path.cubicTo(2, 2, 8, 1, 10, 6)
        path.cubicTo(12, 1, 18, 2, 18, 7)
        path.cubicTo(18, 11, 12, 15, 10, 17)
        if filled: p.setBrush(QColor(color))
        p.drawPath(path)
    elif name == 'photos':
        p.drawRoundedRect(QRectF(4, 2, 14, 14), 2, 2)
        p.drawLine(2, 6, 2, 18); p.drawLine(2, 18, 14, 18)
        p.drawEllipse(QRectF(7, 5, 2.5, 2.5))
        p.drawPolyline([QPointF(6, 13), QPointF(10, 9), QPointF(13, 12), QPointF(16, 9)])
    elif name == 'drive':
        p.drawRoundedRect(QRectF(2, 5, 16, 11), 2, 2)
        p.drawLine(3, 12, 17, 12); p.drawPoint(14, 14); p.drawPoint(16, 14)
    elif name == 'undo' or name == 'redo':
        if name == 'redo': p.translate(20, 0); p.scale(-1, 1)
        p.drawLine(3, 9, 7, 5); p.drawLine(3, 9, 7, 13)
        path = QPainterPath(QPointF(3, 9)); path.cubicTo(17, 4, 20, 17, 10, 17); p.drawPath(path)
    elif name == 'layers':
        for y in (0, 4, 8):
            p.drawPolyline([QPointF(2, 6+y), QPointF(10, 2+y), QPointF(18, 6+y)])
            if y == 0: p.drawPolyline([QPointF(2, 6), QPointF(10, 10), QPointF(18, 6)])
    elif name == 'more':
        for x in (4, 10, 16): p.drawEllipse(QRectF(x-1, 9, 2, 2))
    p.end()
    return QIcon(canvas)


class PreviewCache:
    def __init__(self, dialog):
        self.dialog = dialog
        self.images = OrderedDict()

    def picture(self, row):
        if self.dialog.model.original:
            path = self.dialog.library.root/'files'/(Path(row['source']).stem+'.original.jpg')
        else:
            path = self.dialog.library.root/row['preview']
        key = str(path)
        if key not in self.images:
            # These are the existing 420px thumbnails, never full originals.
            self.images[key] = QPixmap(key)
            if len(self.images) > 120: self.images.popitem(last=False)
        else:
            self.images.move_to_end(key)
        return self.images[key]


def paint_photo(p, rect, picture, checker=True):
    path = QPainterPath(); path.addRoundedRect(QRectF(rect), 5, 5)
    p.save(); p.setClipPath(path)
    p.fillRect(rect, QColor('#e9eef5'))
    if checker:
        for y in range(rect.top(), rect.bottom()+1, 12):
            for x in range(rect.left(), rect.right()+1, 12):
                if ((x-rect.left())//12+(y-rect.top())//12)%2 == 0:
                    p.fillRect(QRect(x, y, 12, 12), QColor('#dfe7ef'))
    if not picture.isNull():
        target = picture.size().scaled(rect.size()-QSize(8, 8), Qt.AspectRatioMode.KeepAspectRatio)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawPixmap(QRect(rect.center().x()-target.width()//2, rect.center().y()-target.height()//2,
                          target.width(), target.height()), picture, picture.rect())
    p.restore()


class PhotoCards(QStyledItemDelegate):
    def __init__(self, dialog, cache):
        super().__init__(dialog.grid); self.dialog = dialog; self.cache = cache

    def sizeHint(self, option, index):
        return self.dialog.grid.gridSize()

    def paint(self, p, option, index):
        row = self.dialog.model.rows[index.row()]
        box = option.rect.adjusted(5, 5, -7, -7)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        p.save(); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(BLUE if selected else LINE), 2 if selected else 1))
        p.setBrush(QColor('#ffffff')); p.drawRoundedRect(QRectF(box), 10, 10)
        photo = QRect(box.left()+7, box.top()+7, box.width()-14, box.height()-57)
        paint_photo(p, photo, self.cache.picture(row), not self.dialog.model.original)
        font = QFont(option.font); font.setPixelSize(11); font.setWeight(QFont.Weight.Medium)
        p.setFont(font); p.setPen(QColor(INK))
        name = ('♡ ' if row['favorite'] else '')+row['name']
        name = p.fontMetrics().elidedText(name, Qt.TextElideMode.ElideRight, box.width()-18)
        p.drawText(QRect(box.left()+9, photo.bottom()+7, box.width()-18, 17), Qt.AlignmentFlag.AlignVCenter, name)
        font.setWeight(QFont.Weight.Normal); p.setFont(font); p.setPen(QColor(MUTED))
        from .library import STATUSES
        p.drawText(QRect(box.left()+9, photo.bottom()+25, box.width()-18, 17), Qt.AlignmentFlag.AlignVCenter, STATUSES[row['status']])
        if option.state & QStyle.StateFlag.State_HasFocus:
            p.setPen(QPen(QColor('#88a7c8'), 1, Qt.PenStyle.DotLine)); p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(QRectF(box.adjusted(3, 3, -3, -3)), 7, 7)
        p.restore()


class AlbumRows(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(130, 78 if index.row() == 4 else 43)

    def paint(self, p, option, index):
        from PySide6.QtGui import QFontMetrics
        box = option.rect.adjusted(1, 2, -2, -2)
        p.save(); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        font = QFont(option.font); font.setPixelSize(12); p.setFont(font)
        if index.row() == 4:
            p.setPen(QColor(LINE)); p.drawLine(box.left()+8, box.top()+4, box.right()-8, box.top()+4)
            p.setPen(QColor(MUTED)); small = QFont(font); small.setPixelSize(11); p.setFont(small)
            p.drawText(box.adjusted(9, 10, 0, 0), Qt.AlignmentFlag.AlignTop, '专辑')
            box.setTop(box.top()+35); p.setFont(font)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        if selected or option.state & QStyle.StateFlag.State_MouseOver:
            p.setPen(Qt.PenStyle.NoPen); p.setBrush(QColor('#e6eef9'))
            p.drawRoundedRect(QRectF(box), 8, 8)
        title, _, count = index.data().rpartition('  ')
        if not title: title, count = index.data(), ''
        title = title.removeprefix('★ ')
        color = BLUE if selected else INK
        content = box.adjusted(10, 0, -10, 0)
        if index.row() < 2:
            icon('photos' if index.row() == 0 else 'heart', color).paint(p, QRect(content.left(), content.center().y()-8, 16, 16))
            content.setLeft(content.left()+23)
        p.setPen(QColor(color))
        p.drawText(content.adjusted(0, 0, -23, 0), Qt.AlignmentFlag.AlignVCenter,
                   QFontMetrics(font).elidedText(title, Qt.TextElideMode.ElideRight, content.width()-23))
        p.setPen(QColor(MUTED)); p.drawText(content, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, count)
        p.restore()


class DetailPreview(QWidget):
    def __init__(self, parent):
        super().__init__(parent); self.picture = QPixmap(); self.original = False
        self.setFixedHeight(142); self.setAccessibleName('当前照片预览')

    def paintEvent(self, event):
        p = QPainter(self); p.setRenderHint(QPainter.RenderHint.Antialiasing)
        paint_photo(p, self.rect(), self.picture, not self.original)
        if self.picture.isNull():
            p.setPen(QColor(MUTED)); p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, '选择照片查看预览')
        p.end()


class LibraryPresentation(QObject):
    def __init__(self, dialog):
        super().__init__(dialog); self.dialog = dialog; self.cache = PreviewCache(dialog)
        self.timer = QTimer(self); self.timer.setSingleShot(True); self.timer.timeout.connect(self.sync_details)
        self.flow_timer = QTimer(self); self.flow_timer.setSingleShot(True); self.flow_timer.timeout.connect(self.reflow)
        self.mount()

    def mount(self):
        d = self.dialog
        buttons = {b.text(): b for b in d.findChildren(QPushButton)}
        self.save = buttons['保存照片信息']
        old_content = d.content
        self.park = QWidget(d); self.park.hide()
        root = d.layout()

        def park_layout(layout):
            while layout.count():
                item = layout.takeAt(0)
                if item.widget(): item.widget().setParent(self.park)
                elif item.layout(): park_layout(item.layout())

        park_layout(root)
        old_content.hide()
        root.setContentsMargins(0, 0, 0, 0); root.setSpacing(0)
        d.setStyleSheet(STYLE)
        d.content = QWidget(d); d.content.setObjectName('libraryContent')
        outer = QVBoxLayout(d.content); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        chrome = QFrame(); chrome.setObjectName('libraryChrome'); chrome.setFixedHeight(91)
        ch = QHBoxLayout(chrome); ch.setContentsMargins(26, 15, 26, 14)
        brand = QVBoxLayout(); brand.setSpacing(3)
        brandrow = QHBoxLayout(); brandrow.setSpacing(12)
        brandrow.addWidget(label('Cosfolio', 'libraryBrand'))
        brandrow.addWidget(label('偶像写真工房', 'libraryBrandSub')); brandrow.addStretch()
        brand.addLayout(brandrow); brand.addWidget(label('PHOTO LIBRARY', 'libraryEyebrow'))
        ch.addLayout(brand); ch.addStretch()
        more = QToolButton(); more.setText('本机照片库'); more.setIcon(icon('drive')); more.setIconSize(QSize(16, 16))
        more.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        more.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(more)
        collect = menu.addAction('收录当前工程照片', d.collect_btn.click); collect.setEnabled(d.collect_btn.isEnabled())
        menu.addAction('恢复照片归档包…', d.restore_btn.click)
        more.setMenu(menu); more.setToolTip('本机照片库 · 收录工程照片 / 恢复归档包'); ch.addWidget(more)
        outer.addWidget(chrome)

        split = QSplitter(Qt.Orientation.Horizontal); split.setHandleWidth(1); split.setChildrenCollapsible(False)
        self.split = split; outer.addWidget(split, 1)
        left = QFrame(); left.setObjectName('librarySidebar'); left.setMinimumWidth(158)
        ll = QVBoxLayout(left); ll.setContentsMargins(12, 24, 12, 18); ll.setSpacing(6)
        ll.addWidget(label('我的照片', 'libraryOverline'))
        d.albums.setItemDelegate(AlbumRows(d.albums)); d.albums.setMouseTracking(True)
        ll.addWidget(d.albums, 1)
        new = buttons['＋ 新建专辑']; new.setObjectName('libraryQuiet'); ll.addWidget(new)
        manage = QToolButton(); manage.setText('专辑管理'); manage.setIcon(icon('more'))
        manage.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        manage.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu = QMenu(manage)
        menu.addAction('重命名专辑', buttons['重命名专辑'].click)
        menu.addAction('移除专辑 · 保留照片', buttons['移除专辑 · 保留照片'].click)
        manage.setMenu(menu); ll.addWidget(manage, 0, Qt.AlignmentFlag.AlignLeft)
        hint = label('照片留在本机\n精修结果随时复用'); hint.setContentsMargins(8, 16, 0, 0); ll.addWidget(hint)
        split.addWidget(left)

        middle = QWidget(); middle.setObjectName('libraryMain'); middle.setMinimumWidth(320)
        ml = QVBoxLayout(middle); ml.setContentsMargins(20, 24, 20, 16); ml.setSpacing(12)
        title = QHBoxLayout(); title.setSpacing(10); wording = QVBoxLayout(); wording.setSpacing(4)
        wording.addWidget(label('YOUR MOMENTS, KEPT.', 'libraryEyebrow'))
        wording.addWidget(label('每一次闪光，都值得留存。', 'libraryTitle'))
        title.addLayout(wording, 1); title.addWidget(buttons['＋ 导入照片']); ml.addLayout(title)
        d.search.setObjectName('librarySearch'); d.search.setClearButtonEnabled(True); ml.addWidget(d.search)
        tools = QHBoxLayout(); tools.setSpacing(7)
        tools.addWidget(d.compare_btn); tools.addWidget(d.delivery_btn); tools.addStretch(); ml.addLayout(tools)
        countrow = QHBoxLayout(); d.album_title.setObjectName('libraryHint'); countrow.addWidget(d.album_title, 1)
        d.original.setText('查看原图'); countrow.addWidget(d.original); ml.addLayout(countrow)
        d.grid.setItemDelegate(PhotoCards(d, self.cache)); d.grid.setSpacing(0)
        d.grid.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        d.grid.setVerticalScrollMode(d.grid.ScrollMode.ScrollPerPixel)
        d.grid.viewport().installEventFilter(self); ml.addWidget(d.grid, 1)
        d.empty.setText('把照片拖到这里\n或点击右上角「导入照片」，开始整理你的写真。')
        ml.addWidget(d.empty, 1)
        bottom = QHBoxLayout(); bottom.addWidget(label('点击照片查看信息 · Ctrl 多选'), 1)
        bottom.addWidget(label('缩略图')); d.size.setMaximumWidth(88); bottom.addWidget(d.size); ml.addLayout(bottom)
        d.size.valueChanged.disconnect(d.resize_grid); d.size.valueChanged.connect(lambda *_: self.flow_timer.start(0))
        split.addWidget(middle)

        right = QFrame(); right.setObjectName('libraryDetails'); right.setMinimumWidth(240)
        rl = QVBoxLayout(right); rl.setContentsMargins(0, 0, 0, 0); rl.setSpacing(0)
        body = QWidget(); body.setObjectName('libraryDetailsBody')
        dl = QVBoxLayout(body); dl.setContentsMargins(18, 24, 18, 12); dl.setSpacing(9)
        detailheading = QHBoxLayout(); detailheading.addWidget(label('照片信息', 'libraryOverline'), 1)
        d.favorite_btn.setObjectName('libraryHeart'); d.favorite_btn.setMinimumWidth(0); d.favorite_btn.setFixedSize(30, 30)
        d.favorite_btn.setIconSize(QSize(18, 18)); detailheading.addWidget(d.favorite_btn); dl.addLayout(detailheading)
        self.preview = DetailPreview(body); dl.addWidget(self.preview)
        self.filename = label('选择一张照片', 'libraryFileName'); self.filename.setContentsMargins(0, 8, 0, 0); dl.addWidget(self.filename)
        d.info.setObjectName('libraryHint'); dl.addWidget(d.info)
        dl.addSpacing(7); dl.addWidget(label('标签', 'libraryOverline'))
        self.tags = QWidget(); self.tag_layout = QGridLayout(self.tags)
        self.tag_layout.setContentsMargins(0, 0, 0, 0); self.tag_layout.setSpacing(5); dl.addWidget(self.tags)
        dl.addSpacing(7); dl.addWidget(label('处理状态', 'libraryHint')); dl.addWidget(d.status)
        self.save.setText('保存照片信息'); self.save.setObjectName('libraryQuiet'); dl.addWidget(self.save)
        history = QHBoxLayout(); history.setSpacing(8)
        stack = QLabel(); stack.setPixmap(icon('layers', BLUE).pixmap(18, 18)); history.addWidget(stack, 0, Qt.AlignmentFlag.AlignTop)
        self.history = label('精修蒙版已保留\n用于新工程时无需重新抠图'); history.addWidget(self.history, 1)
        dl.addLayout(history)
        d.edit_btn.setObjectName('libraryQuiet'); dl.addWidget(d.edit_btn)
        self.expand = QToolButton(); self.expand.setText('编辑信息与蒙版版本'); self.expand.setCheckable(True)
        self.expand.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.expand.setArrowType(Qt.ArrowType.RightArrow); dl.addWidget(self.expand)
        advanced = QWidget(); advanced.setObjectName('libraryAdvanced'); al = QVBoxLayout(advanced)
        al.setContentsMargins(0, 4, 0, 4); al.setSpacing(7)
        for caption, control in (('照片名称', d.name), ('所属专辑', d.album_field), ('标签 · 用逗号分隔', d.tags), ('备注', d.notes), ('蒙版版本', d.version)):
            al.addWidget(label(caption)); al.addWidget(control)
        al.addWidget(buttons['使用此蒙版版本']); al.addWidget(buttons['标记归档 / 恢复'])
        dl.addWidget(advanced); advanced.hide(); dl.addStretch()
        def expand(checked):
            advanced.setVisible(checked)
            self.expand.setArrowType(Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow)
        self.expand.toggled.connect(expand)
        scroll = QScrollArea(); scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff); scroll.setWidget(body)
        rl.addWidget(scroll, 1)
        primary = QVBoxLayout(); primary.setContentsMargins(18, 9, 18, 18); primary.setSpacing(8)
        primary.addWidget(d.add_btn); primary.addWidget(d.archive_btn); rl.addLayout(primary)
        split.addWidget(right); split.setSizes([185, 810, 285]); split.setStretchFactor(1, 1)
        root.addWidget(d.content, 1)

        footer = QFrame(); footer.setObjectName('libraryFooter'); footer.setFixedHeight(46)
        fl = QHBoxLayout(footer); fl.setContentsMargins(22, 5, 22, 5); fl.setSpacing(8)
        d.message.setWordWrap(False); d.message.setMinimumWidth(0)
        d.message.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        fl.addWidget(d.message, 1); fl.addWidget(d.cancel_btn)
        for button, name, hint in ((d.undo_btn, 'undo', '撤销 · Ctrl+Z'), (d.redo_btn, 'redo', '重做 · Ctrl+Y')):
            button.setText(''); button.setIcon(icon(name)); button.setIconSize(QSize(16, 16))
            button.setFixedSize(30, 30); button.setObjectName('libraryQuiet'); button.setToolTip(hint); button.setAccessibleName(hint)
            fl.addWidget(button)
        fl.addSpacing(10)
        offline = label('原图完整保留 · 全程离线'); offline.setWordWrap(False)
        fl.addWidget(offline); root.addWidget(footer)
        # Hidden controls still own their original signal connections, including
        # the commands exposed in menus. Their methods and handlers are untouched.
        d.collect_btn.setParent(self.park); d.restore_btn.setParent(self.park)
        d.selection_title.setParent(self.park)
        # Finish painting the presentation synchronously after the existing
        # detail-field refresh, so the first frame never shows stale labels.
        base_details = d.show_details
        def refresh_detail_presentation():
            base_details()
            self.sync_details()
        d.show_details = refresh_detail_presentation
        d.grid.selectionModel().selectionChanged.connect(self.schedule)
        d.model.modelReset.connect(self.schedule)
        d.original.toggled.connect(self.schedule)
        self.sync_details(); self.reflow()

    def schedule(self, *_):
        self.timer.start(0)

    def sync_details(self):
        d = self.dialog; keys = set(d.selected_keys())
        rows = [r for r in d.model.rows if r['id'] in keys]
        single = len(rows) == 1
        row = rows[0] if single else None
        self.filename.setText(row['name'] if row else (f'已选择 {len(rows)} 张照片' if rows else '选择一张照片'))
        self.preview.picture = self.cache.picture(row) if row else QPixmap()
        self.preview.original = d.model.original; self.preview.update()
        loved = bool(rows) and all(r['favorite'] for r in rows)
        d.favorite_btn.setText(''); d.favorite_btn.setIcon(icon('heart', BLUE if loved else MUTED, loved))
        d.favorite_btn.setEnabled(bool(rows)); d.favorite_btn.setToolTip('取消收藏' if loved else '收藏照片')
        d.favorite_btn.setAccessibleName(d.favorite_btn.toolTip())
        while self.tag_layout.count():
            item = self.tag_layout.takeAt(0)
            if item.widget(): item.widget().deleteLater()
        tags = row['tags'] if row else []
        for i, tag in enumerate(tags[:6]):
            item = label(tag, 'libraryTag'); item.setTextFormat(Qt.TextFormat.PlainText)
            item.setToolTip(tag); self.tag_layout.addWidget(item, i//2, i%2)
        if not tags: self.tag_layout.addWidget(label('尚未添加标签' if not rows or single else '展开下方可批量追加标签'), 0, 0)
        elif len(tags) > 6: self.tag_layout.addWidget(label(f'另有 {len(tags)-6} 个标签 · 展开编辑查看'), 3, 0, 1, 2)
        self.history.setText('精修蒙版已保留\n用于新工程时无需重新抠图' if rows else '原图与精修一起收藏\n选中照片后可查看蒙版版本')

    def eventFilter(self, watched, event):
        if event.type() == QEvent.Type.Resize:
            self.reflow()
        return super().eventFilter(watched, event)

    def reflow(self):
        grid = self.dialog.grid
        # Reserve the scrollbar width even before it appears. Using viewport
        # width here can alternate column counts as the bar appears/disappears.
        available = max(100, grid.width()-16)
        columns = max(1, min(6, available//max(145, int(self.dialog.size.value()*1.35))))
        width = available//columns
        height = int(max(80, width-27)*4/3)+69
        size = QSize(width, height)
        if grid.gridSize() != size:
            grid.setGridSize(size)
            grid.doItemsLayout()
        grid.viewport().update()


def apply_library_visual(dialog):
    dialog.presentation = LibraryPresentation(dialog)
