"""Three-pane photo management, with lazy thumbnails and local undo."""
from __future__ import annotations
import json
from collections import OrderedDict
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QSize, Signal, QThread, QAbstractListModel, QModelIndex, QMimeData, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import (QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QPlainTextEdit, QComboBox, QSplitter, QListView, QListWidget, QListWidgetItem,
    QAbstractItemView, QFrame, QFileDialog, QMessageBox, QInputDialog, QCheckBox, QSlider, QScrollArea, QMenu)
from .core import DATA, import_asset, make_cutout
from .library import PhotoLibrary, STATUSES, tags_from_text
from .history import bind_history

MIME = 'application/x-cosfolio-library-photos'
LIBRARY_STYLE = '''
QDialog#photoLibrary { background: #edf3f9; }
QFrame#librarySidebar, QFrame#libraryDetails { background: #ffffff; border: 1px solid #dae5f0; border-radius: 12px; }
QLabel#libraryTitle { font-size: 22px; font-weight: 600; color: #173f70; }
QLabel#libraryEyebrow { font-size: 11px; color: #547b9e; letter-spacing: 2px; }
QLabel#libraryHint { font-size: 12px; color: #647b92; }
QListWidget#albumList::item { background: transparent; border: 0; padding: 11px 8px; margin: 2px; border-radius: 7px; }
QListWidget#albumList::item:selected { background: #e6f0fc; color: #173f70; }
QListView#libraryGrid { background: transparent; border: 0; outline: 0; }
QListView#libraryGrid::item { background: #ffffff; border: 1px solid #dbe5f0; border-radius: 9px; padding: 8px; }
QListView#libraryGrid::item:selected { background: #e5f0fd; border: 2px solid #24588e; color: #173f70; }
QPushButton#libraryTab { background: transparent; border: 0; color: #6b8199; padding: 8px 12px; }
QPushButton#libraryTab:checked { background: #e0ecfa; color: #173f70; }
'''


def text(value, name='libraryHint'):
    item = QLabel(value); item.setObjectName(name); item.setWordWrap(name not in ('libraryTitle','libraryEyebrow'))
    return item


def image_files(mime):
    return [u.toLocalFile() for u in mime.urls() if u.isLocalFile()
            and Path(u.toLocalFile()).suffix.lower() in ('.jpg','.jpeg','.png','.webp','.tif','.tiff')
            and Path(u.toLocalFile()).is_file()]


class LibraryJob(QThread):
    progress = Signal(str)
    result = Signal(object)
    failed = Signal(str)

    def __init__(self, function, parent):
        super().__init__(parent); self.function = function

    def run(self):
        try:
            self.result.emit(self.function(self.progress.emit, self.isInterruptionRequested))
        except Exception as exc:
            self.failed.emit(str(exc))


class PhotoModel(QAbstractListModel):
    def __init__(self, library, parent=None):
        super().__init__(parent); self.library=library; self.rows=[]; self.cache=OrderedDict(); self.original=False

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role):
        if not index.isValid() or not 0<=index.row()<len(self.rows): return None
        row=self.rows[index.row()]
        if role==Qt.ItemDataRole.DisplayRole:
            return ('★ ' if row['favorite'] else '')+row['name']+'\n'+STATUSES[row['status']]
        if role==Qt.ItemDataRole.UserRole: return row['id']
        if role==Qt.ItemDataRole.ToolTipRole:
            return row['name']+'\n'+(' · '.join(row['tags']) or '尚未添加标签')+f"\n{row['width']} × {row['height']} · {row['version_count']} 个蒙版版本"
        if role==Qt.ItemDataRole.DecorationRole:
            key=(row['source'] if self.original else row['preview'],self.original)
            if key not in self.cache:
                if self.original:
                    # Original thumbnails are generated once in a worker, never by decoding full originals on scroll.
                    path=self.library.root/'files'/(Path(row['source']).stem+'.original.jpg')
                else: path=self.library.root/row['preview']
                raw=QPixmap(str(path))
                canvas=QPixmap(180,180);canvas.fill(QColor('#f0f3f7'))
                p=QPainter(canvas)
                if not self.original:
                    for y in range(0,180,12):
                        for x in range(0,180,12):
                            if (x//12+y//12)%2==0:p.fillRect(x,y,12,12,QColor('#e0e8f1'))
                if not raw.isNull():
                    raw=raw.scaled(172,172,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation)
                    p.drawPixmap((180-raw.width())//2,(180-raw.height())//2,raw)
                p.end();self.cache[key]=QIcon(canvas)
                if len(self.cache)>240:self.cache.popitem(last=False)
            return self.cache[key]
        return None

    def reset(self, rows):
        self.beginResetModel();self.rows=rows;self.endResetModel()

    def flags(self,index):
        return super().flags(index)|Qt.ItemFlag.ItemIsDragEnabled

    def mimeTypes(self): return [MIME]

    def mimeData(self,indexes):
        mime=QMimeData();mime.setData(MIME,json.dumps(list(dict.fromkeys(self.rows[i.row()]['id'] for i in indexes))).encode())
        return mime

    def supportedDragActions(self): return Qt.DropAction.CopyAction


class PhotoGrid(QListView):
    filesDropped=Signal(list)

    def __init__(self,parent):
        super().__init__(parent);self.setObjectName('libraryGrid')
        self.setViewMode(QListView.ViewMode.IconMode);self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static);self.setUniformItemSizes(True)
        self.setLayoutMode(QListView.LayoutMode.Batched);self.setBatchSize(60)
        self.setSpacing(7);self.setIconSize(QSize(150,150));self.setGridSize(QSize(174,207))
        self.setWordWrap(False);self.setTextElideMode(Qt.TextElideMode.ElideMiddle)
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DragDrop)
        self.setDropIndicatorShown(False);self.setDragEnabled(True);self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self,event):
        if image_files(event.mimeData()):event.acceptProposedAction()
        else:event.ignore()

    def dragMoveEvent(self,event): self.dragEnterEvent(event)

    def dropEvent(self,event):
        paths=image_files(event.mimeData())
        if paths:self.filesDropped.emit(paths);event.acceptProposedAction()


class AlbumList(QListWidget):
    photosMoved=Signal(list,str)

    def __init__(self,parent):
        super().__init__(parent);self.setObjectName('albumList');self.setAcceptDrops(True)
        self.setDragDropMode(QAbstractItemView.DragDropMode.DropOnly);self.viewport().setAcceptDrops(True)

    def dragEnterEvent(self,event):
        if event.mimeData().hasFormat(MIME):event.acceptProposedAction()
        else:event.ignore()

    def dragMoveEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if event.mimeData().hasFormat(MIME) and item and item.data(Qt.ItemDataRole.UserRole) not in ('all','favorite','archived'):
            event.acceptProposedAction()
        else:event.ignore()

    def dropEvent(self,event):
        item=self.itemAt(event.position().toPoint())
        if not item:return
        album=item.data(Qt.ItemDataRole.UserRole)
        if album in ('all','favorite','archived'):return
        try:keys=json.loads(bytes(event.mimeData().data(MIME)))
        except (ValueError,TypeError):return
        self.photosMoved.emit(keys,album);event.acceptProposedAction()


class PhotoLibraryDialog(QDialog):
    def __init__(self, segmenter, project_assets, parent=None, library=None):
        super().__init__(parent);self.setObjectName('photoLibrary');self.setWindowTitle('Cosfolio · 照片库')
        self.library=library or PhotoLibrary();self.segmenter=segmenter;self.project_assets=list(project_assets)
        self.added_assets=[];self.busy=False;self.worker=None;self.undo_stack=[];self.redo_stack=[];self.filter_key='all'
        self.resize(1280,840);self.setMinimumSize(940,650);self.setStyleSheet(LIBRARY_STYLE)
        root=QVBoxLayout(self);root.setContentsMargins(24,20,24,16);root.setSpacing(16)
        self.content=QWidget();content=QVBoxLayout(self.content);content.setContentsMargins(0,0,0,0);content.setSpacing(16)
        heading=QHBoxLayout();brand=QVBoxLayout();brand.addWidget(text('COSFOLIO / PHOTO LIBRARY','libraryEyebrow'))
        brand.addWidget(text('每一次精修，都值得留存','libraryTitle'));heading.addLayout(brand);heading.addStretch()
        self.collect_btn=QPushButton('收录当前工程照片');self.collect_btn.setEnabled(bool(project_assets));self.collect_btn.clicked.connect(self.collect_project)
        heading.addWidget(self.collect_btn);button=QPushButton('＋ 导入照片');button.setObjectName('primary');button.clicked.connect(self.import_dialog);heading.addWidget(button)
        content.addLayout(heading)
        split=QSplitter(Qt.Orientation.Horizontal);split.setChildrenCollapsible(False);content.addWidget(split,1)
        left=QFrame();left.setObjectName('librarySidebar');left.setMinimumWidth(180);ll=QVBoxLayout(left);ll.setContentsMargins(12,16,12,12)
        ll.addWidget(text('我的专辑','section'));self.albums=AlbumList(self);ll.addWidget(self.albums,1)
        self.albums.currentItemChanged.connect(lambda *_:self.album_changed());self.albums.photosMoved.connect(self.move_to_album)
        b=QPushButton('＋ 新建专辑');b.clicked.connect(self.new_album);ll.addWidget(b)
        b=QPushButton('重命名专辑');b.clicked.connect(self.rename_album);ll.addWidget(b)
        b=QPushButton('移除专辑 · 保留照片');b.clicked.connect(self.remove_album);ll.addWidget(b)
        ll.addWidget(text('把照片拖到专辑即可整理'));split.addWidget(left)
        middle=QWidget();ml=QVBoxLayout(middle);ml.setContentsMargins(14,0,14,0);ml.setSpacing(10)
        self.search=QLineEdit();self.search.setPlaceholderText('搜索照片名称、标签或备注');self.search.textChanged.connect(self.schedule_filter);ml.addWidget(self.search)
        tools=QHBoxLayout();self.compare_btn=QPushButton('双图对比选片');self.compare_btn.clicked.connect(self.compare_photos);tools.addWidget(self.compare_btn)
        self.delivery_btn=QPushButton('交付照片…');menu=QMenu(self.delivery_btn)
        menu.addAction('批量导出透明 PNG…',lambda:self.deliver_photos('cutouts'))
        menu.addAction('生成编号选片联系表…',lambda:self.deliver_photos('contact'))
        self.delivery_btn.setMenu(menu);self.delivery_btn.setToolTip('优先导出选中照片；没有选择时导出当前专辑或筛选结果')
        tools.addWidget(self.delivery_btn);tools.addStretch();ml.addLayout(tools)
        row=QHBoxLayout();self.album_title=text('全部照片','section');row.addWidget(self.album_title,1)
        self.original=QCheckBox('原图缩略图');self.original.toggled.connect(self.change_thumbnails);row.addWidget(self.original)
        ml.addLayout(row);self.model=PhotoModel(self.library,self);self.grid=PhotoGrid(self);self.grid.setModel(self.model);ml.addWidget(self.grid,1)
        self.grid.filesDropped.connect(self.import_paths);self.grid.selectionModel().selectionChanged.connect(lambda *_:self.show_details())
        self.grid.doubleClicked.connect(lambda _:self.edit_mask())
        self.empty=text('照片库还是空的\n拖入照片，或收录已经精修过的工程照片。');self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter);ml.addWidget(self.empty)
        actions=QHBoxLayout();self.favorite_btn=QPushButton('☆ 收藏');self.favorite_btn.setMinimumWidth(124);self.favorite_btn.clicked.connect(self.toggle_favorite);actions.addWidget(self.favorite_btn)
        b=QPushButton('标记归档 / 恢复');b.clicked.connect(self.toggle_archived);actions.addWidget(b)
        actions.addStretch();self.size=QSlider(Qt.Orientation.Horizontal);self.size.setRange(120,220);self.size.setValue(150);self.size.setMaximumWidth(100)
        self.size.setToolTip('调整照片缩略图大小');self.size.valueChanged.connect(self.resize_grid);actions.addWidget(self.size);ml.addLayout(actions);split.addWidget(middle)
        right=QFrame();right.setObjectName('libraryDetails');right.setMinimumWidth(235);rl=QVBoxLayout(right);rl.setContentsMargins(16,16,16,16);rl.setSpacing(9)
        rl.addWidget(text('照片信息','section'));self.selection_title=text('选择照片查看信息');rl.addWidget(self.selection_title)
        self.name=QLineEdit();self.name.setPlaceholderText('照片名称');rl.addWidget(self.name)
        self.info=text('');rl.addWidget(self.info)
        rl.addWidget(text('所属专辑'));self.album_field=QComboBox();rl.addWidget(self.album_field)
        rl.addWidget(text('标签 · 用逗号分隔'));self.tags=QLineEdit();self.tags.setPlaceholderText('海未，万圣节，笑笑');rl.addWidget(self.tags)
        rl.addWidget(text('处理状态'));self.status=QComboBox()
        self.status.addItem('保持各自状态',None)
        for key,value in STATUSES.items():self.status.addItem(value,key)
        rl.addWidget(self.status);rl.addWidget(text('备注'));self.notes=QPlainTextEdit();self.notes.setMaximumHeight(90);rl.addWidget(self.notes)
        b=QPushButton('保存照片信息');b.clicked.connect(self.save_details);rl.addWidget(b)
        rl.addWidget(text('蒙版版本'));self.version=QComboBox();rl.addWidget(self.version)
        b=QPushButton('使用此蒙版版本');b.clicked.connect(self.use_version);rl.addWidget(b)
        self.edit_btn=QPushButton('精修抠图…');self.edit_btn.clicked.connect(self.edit_mask);rl.addWidget(self.edit_btn)
        rl.addWidget(text('原图与自动抠图基准保留。\n精修不会改变已完成的工程。'));rl.addStretch()
        details_scroll=QScrollArea();details_scroll.setWidgetResizable(True);details_scroll.setMinimumWidth(255)
        details_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff);details_scroll.setWidget(right)
        split.addWidget(details_scroll);split.setSizes([205,735,280])
        root.addWidget(self.content,1)
        footer=QHBoxLayout();self.message=text('照片和精修结果只保存在本机');footer.addWidget(self.message,1)
        self.cancel_btn=QPushButton('取消处理');self.cancel_btn.clicked.connect(self.cancel_job);self.cancel_btn.hide();footer.addWidget(self.cancel_btn)
        self.undo_btn=QPushButton('撤销');self.undo_btn.clicked.connect(self.undo);footer.addWidget(self.undo_btn)
        self.redo_btn=QPushButton('重做');self.redo_btn.clicked.connect(self.redo);footer.addWidget(self.redo_btn)
        self.archive_btn=QPushButton('导出归档包…');self.archive_btn.clicked.connect(self.export_archive);footer.addWidget(self.archive_btn)
        self.restore_btn=QPushButton('恢复归档包…');self.restore_btn.clicked.connect(self.import_archive);footer.addWidget(self.restore_btn)
        self.add_btn=QPushButton('加入当前工程');self.add_btn.setObjectName('primary');self.add_btn.clicked.connect(self.add_to_project);footer.addWidget(self.add_btn)
        root.addLayout(footer);bind_history(self,self.undo,self.redo)
        self.search_timer=QTimer(self);self.search_timer.setSingleShot(True);self.search_timer.setInterval(160);self.search_timer.timeout.connect(self.refresh_grid)
        self.refresh()

        # Presentation only: reuse the existing controls, signals and actions.
        from .library_visual import apply_library_visual
        apply_library_visual(self)

    def selected_keys(self):
        return [i.data(Qt.ItemDataRole.UserRole) for i in sorted(self.grid.selectionModel().selectedIndexes(),key=lambda i:i.row())]

    def remember(self):
        self.undo_stack.append(self.library.snapshot());self.undo_stack=self.undo_stack[-30:];self.redo_stack.clear()

    def undo(self):
        if self.busy or not self.undo_stack:return
        self.redo_stack.append(self.library.snapshot());self.library.restore_snapshot(self.undo_stack.pop());self.refresh();self.message.setText('已撤销照片库修改；素材文件保留供重做')

    def redo(self):
        if self.busy or not self.redo_stack:return
        self.undo_stack.append(self.library.snapshot());self.library.restore_snapshot(self.redo_stack.pop());self.refresh();self.message.setText('已重做照片库修改')

    def refresh(self):
        albums=self.library.albums();self.all_rows=self.library.rows();self.albums.blockSignals(True);self.albums.clear()
        entries=[('全部照片','all',len(self.all_rows)),('★ 我的收藏','favorite',sum(r['favorite'] for r in self.all_rows)),
                 ('未分类','',sum(not r['album'] for r in self.all_rows)),('已归档','archived',sum(r['status']=='archived' for r in self.all_rows))]
        entries.extend((a['name'],a['id'],a['count']) for a in albums)
        self.album_field.clear();self.album_field.addItem('保持各自专辑',None);self.album_field.addItem('未分类','')
        for a in albums:self.album_field.addItem(a['name'],a['id'])
        for title,key,count in entries:
            item=QListWidgetItem(f'{title}  {count}');item.setData(Qt.ItemDataRole.UserRole,key);self.albums.addItem(item)
            if key==self.filter_key:self.albums.setCurrentItem(item)
        if self.albums.currentItem() is None:self.filter_key='all';self.albums.setCurrentRow(0)
        self.albums.blockSignals(False);self.refresh_grid()

    def album_changed(self):
        item=self.albums.currentItem()
        if item:self.filter_key=item.data(Qt.ItemDataRole.UserRole);self.refresh_grid()

    def schedule_filter(self):self.search_timer.start()

    def refresh_grid(self):
        selected=set(self.selected_keys());query=self.search.text().strip().casefold();key=self.filter_key
        rows=[r for r in self.all_rows if (key=='all' or (key=='favorite' and r['favorite']) or
              (key=='archived' and r['status']=='archived') or r['album']==key)
              and (not query or query in (r['name']+' '+','.join(r['tags'])+' '+r['notes']).casefold())]
        self.model.reset(rows)
        from PySide6.QtCore import QItemSelectionModel
        for index,row in enumerate(rows):
            if row['id'] in selected:self.grid.selectionModel().select(self.model.index(index),QItemSelectionModel.SelectionFlag.Select)
        self.empty.setVisible(not rows);self.grid.setVisible(bool(rows))
        item=self.albums.currentItem();title=item.text().rsplit('  ',1)[0] if item else '全部照片'
        self.album_title.setText(f'{title} · {len(rows)} 张');self.show_details()
        self.undo_btn.setEnabled(bool(self.undo_stack));self.redo_btn.setEnabled(bool(self.redo_stack))

    def show_details(self):
        keys=self.selected_keys();single=len(keys)==1;self.add_btn.setEnabled(bool(keys));self.edit_btn.setEnabled(single)
        self.compare_btn.setEnabled(len(keys)==2);self.delivery_btn.setEnabled(bool(self.model.rows))
        self.compare_btn.setToolTip('按住 Ctrl 选择两张照片，再同步放大比较表情与对焦')
        self.name.setEnabled(single);self.notes.setEnabled(single);self.version.setEnabled(single);self.version.clear()
        self.selection_title.setText(f'已选择 {len(keys)} 张' if keys else '选择照片查看信息')
        if not keys:
            self.name.clear();self.tags.clear();self.notes.clear();self.info.setText('');return
        row=next(r for r in self.model.rows if r['id']==keys[0]);self.name.setText(row['name'] if single else '批量编辑：标签将追加，名称与备注保留')
        self.tags.setText(', '.join(row['tags']) if single else '');self.notes.setPlainText(row['notes'] if single else '')
        self.album_field.setCurrentIndex(max(0,self.album_field.findData(row['album'])) if single else 0)
        self.status.setCurrentIndex(self.status.findData(row['status']) if single else 0)
        self.info.setText(f"{row['width']} × {row['height']} 像素\n{row['version_count']} 个蒙版版本 · 原照片完整保留" if single else '标签会追加；未指定的专辑与状态保持各自设置')
        if single:
            for i,v in enumerate(self.library.versions(row['id'])):
                title=datetime.fromtimestamp(v['created']).strftime('%m-%d %H:%M:%S')
                self.version.addItem(('当前 · ' if v['id']==row['current_version'] else '')+title+f' / {row["version_count"]-i}',v['id'])
                if v['id']==row['current_version']:self.version.setCurrentIndex(i)
        favorite=all(r['favorite'] for r in self.model.rows if r['id'] in keys);self.favorite_btn.setText('★ 取消收藏' if favorite else '☆ 收藏')

    def change(self, function):
        if self.busy:return
        before=self.library.snapshot()
        try:
            function()
            if self.library.snapshot()!=before:self.undo_stack.append(before);self.undo_stack=self.undo_stack[-30:];self.redo_stack.clear()
            self.refresh()
        except Exception as exc:
            self.library.restore_snapshot(before);self.refresh();QMessageBox.warning(self,'照片库',str(exc))

    def new_album(self):
        name,ok=QInputDialog.getText(self,'新建专辑','专辑名称，例如：笑笑 · 海未 · 万圣节')
        if ok and name.strip():
            def action():self.filter_key=self.library.create_album(name)
            self.change(action)

    def rename_album(self):
        album=next((a for a in self.library.albums() if a['id']==self.filter_key),None)
        if not album:self.message.setText('先在左侧选择自己创建的专辑');return
        name,ok=QInputDialog.getText(self,'重命名专辑','专辑名称',text=album['name'])
        if ok:self.change(lambda:self.library.rename_album(album['id'],name))

    def move_to_album(self,keys,album):self.change(lambda:self.library.update(keys,album=album))

    def remove_album(self):
        if not any(a['id']==self.filter_key for a in self.library.albums()):
            self.message.setText('先选择自己创建的专辑');return
        key=self.filter_key
        def remove():self.library.remove_album(key);self.filter_key=''
        self.change(remove);self.message.setText('专辑已移除，照片已回到未分类；Ctrl+Z 可恢复专辑')

    def save_details(self):
        keys=self.selected_keys()
        if not keys:return
        tags=tags_from_text(self.tags.text());album=self.album_field.currentData();status=self.status.currentData()
        if len(keys)==1:
            changes=dict(name=self.name.text(),tags=tags,notes=self.notes.toPlainText())
            if album is not None:changes['album']=album
            if status is not None:changes['status']=status
            self.change(lambda:self.library.update(keys,**changes))
        else:
            def update():
                with self.library.connect() as db:
                    for key in keys:
                        row=db.execute('SELECT tags FROM photos WHERE id=?',(key,)).fetchone()
                        merged=list(dict.fromkeys(json.loads(row['tags'])+tags))[:40]
                        changes={'tags':json.dumps(merged,ensure_ascii=False)}
                        if album is not None:changes['album']=album
                        if status is not None:changes['status']=status
                        db.execute('UPDATE photos SET '+','.join(f'{k}=?' for k in changes)+' WHERE id=?',[*changes.values(),key])
            self.change(update)
        self.message.setText('照片信息已保存 · Ctrl+Z 可撤销')

    def toggle_favorite(self):
        keys=self.selected_keys()
        if keys:self.change(lambda:self.library.update(keys,favorite=not all(r['favorite'] for r in self.model.rows if r['id'] in keys)))

    def toggle_archived(self):
        keys=self.selected_keys()
        if keys:self.change(lambda:self.library.update(keys,status='ready' if all(r['status']=='archived' for r in self.model.rows if r['id'] in keys) else 'archived'))
        self.message.setText('归档状态已更新；导出归档包可另存到其他硬盘，原文件不会自动删除')

    def use_version(self):
        keys=self.selected_keys();version=self.version.currentData()
        if len(keys)==1 and version:self.change(lambda:self.library.update(keys,current_version=version))

    def current_album(self):return self.filter_key if self.filter_key not in ('all','favorite','archived') else ''

    def start_job(self,function,done,undo=True):
        if self.busy:return
        before=self.library.snapshot() if undo else None
        self.busy=True;self.content.setEnabled(False)
        for b in (self.undo_btn,self.redo_btn,self.archive_btn,self.restore_btn,self.add_btn):b.setEnabled(False)
        self.cancel_btn.show();self.cancel_btn.setEnabled(True)
        worker=LibraryJob(function,self);self.worker=worker
        worker.progress.connect(self.message.setText);worker.result.connect(done)
        worker.failed.connect(lambda error:self.message.setText(error))
        def finish():
            if before is not None and self.library.snapshot()!=before:
                self.undo_stack.append(before);self.undo_stack=self.undo_stack[-30:];self.redo_stack.clear()
            self.busy=False;self.content.setEnabled(True);self.cancel_btn.hide()
            self.archive_btn.setEnabled(True);self.restore_btn.setEnabled(True);self.refresh()
            worker.deleteLater();self.worker=None
        worker.finished.connect(finish);worker.start()

    def cancel_job(self):
        if self.worker:self.worker.requestInterruption();self.cancel_btn.setEnabled(False);self.message.setText('正在结束当前处理…')

    def collect_project(self):
        assets=list(self.project_assets);album=self.current_album()
        def run(progress,cancel):
            count=0
            for i,asset in enumerate(assets):
                if cancel():break
                progress(f'收录工程照片 {i+1}/{len(assets)}');self.library.capture(asset,album);count+=1
            return count
        self.start_job(run,lambda count:self.message.setText(f'已收录 {count} 张工程照片，沿用现有精修结果'))

    def import_dialog(self):
        paths,_=QFileDialog.getOpenFileNames(self,'导入照片','','照片 (*.jpg *.jpeg *.png *.webp *.tif *.tiff)')
        if paths:self.import_paths(paths)

    def import_paths(self,paths):
        if self.busy:return
        album=self.current_album()
        def run(progress,cancel):
            count=reused=0;errors=[]
            for i,path in enumerate(paths):
                if cancel():break
                progress(f'导入照片 {i+1}/{len(paths)} · {Path(path).name}')
                try:
                    existing=self.library.find_source(path)
                    if existing:
                        if album:self.library.update([existing['id']],album=album)
                        reused+=1
                    else:self.library.capture(import_asset(path,self.segmenter),album)
                    count+=1
                except Exception as exc:errors.append(Path(path).name+'：'+str(exc))
            return count,reused,errors
        def done(result):
            count,reused,errors=result;self.message.setText(f'已导入 {count} 张，{reused} 张复用已有抠图'+('；'+errors[0] if errors else ''))
        self.start_job(run,done)

    def edit_mask(self):
        keys=self.selected_keys()
        if self.busy or len(keys)!=1:return
        from .app import MaskDialog
        try:
            row=self.library.get(keys[0])
            from .core import Asset
            asset=Asset(row['id'],row['name'],str(self.library.root/row['source']),
                        str(self.library.root/row['mask']),str(self.library.root/row['initial_mask']),
                        row['seconds'],row['width'],row['height'])
            dialog=MaskDialog(asset,self)
            try:
                if dialog.exec()==QDialog.DialogCode.Accepted:
                    import tempfile
                    with tempfile.TemporaryDirectory(dir=self.library.root) as folder:
                        target=Path(folder)/'refined.png';dialog.canvas.mask.save(target);asset.mask=str(target)
                        self.change(lambda:self.library.capture(asset))
                    self.message.setText('精修已保存为新蒙版版本；已有工程保持原来的效果')
            finally:dialog.deleteLater()
        except Exception as exc:QMessageBox.warning(self,'精修抠图',str(exc))

    def resize_grid(self,value):
        self.grid.setIconSize(QSize(value,value));self.grid.setGridSize(QSize(value+24,value+57))

    def change_thumbnails(self,original):
        if not original:
            self.model.original=False;self.refresh_grid();return
        rows=list(self.all_rows)
        def run(progress,cancel):
            from .core import oriented_image
            for i,row in enumerate(rows):
                if cancel():return False
                target=self.library.root/'files'/(Path(row['source']).stem+'.original.jpg')
                if not target.exists():
                    progress(f'生成原图缩略图 {i+1}/{len(rows)}');oriented_image(self.library.root/row['source'],420).save(target,quality=85)
            return True
        def done(ok):
            self.model.original=ok;self.original.blockSignals(True);self.original.setChecked(ok);self.original.blockSignals(False)
        self.start_job(run,done,undo=False)

    def add_to_project(self):
        keys=self.selected_keys()
        if not keys:return
        if len(self.project_assets)+len(keys)>100:
            QMessageBox.information(self,'工程照片数量','当前工程最多支持 100 张照片，请减少选择。');return
        def run(progress,cancel):
            result=[]
            for i,key in enumerate(keys):
                if cancel():return []
                progress(f'加入当前工程 {i+1}/{len(keys)}');result.append(self.library.materialize(key))
            return result
        def done(result):
            self.added_assets=result
            if result:QTimer.singleShot(0,self.accept_when_ready)
        self.start_job(run,done,undo=False)

    def accept_when_ready(self):
        if self.busy:QTimer.singleShot(10,self.accept_when_ready)
        else:self.accept()

    def export_archive(self):
        keys=self.selected_keys() or [r['id'] for r in self.model.rows]
        if not keys:self.message.setText('当前专辑没有可归档的照片');return
        path,_=QFileDialog.getSaveFileName(self,'导出照片归档包',str(DATA/'exports'/'照片专辑.cosphotos'),'Cosfolio 照片归档 (*.cosphotos)')
        if not path:return
        if not path.lower().endswith('.cosphotos'):path+='.cosphotos'
        self.start_job(lambda p,c:self.library.export_archive(keys,path,p,c),
                       lambda n:self.message.setText(f'已归档 {n} 张照片并通过校验；原图、所有蒙版版本和标签已打包。原文件保留。'),undo=False)

    def compare_photos(self):
        if self.busy:return
        keys=self.selected_keys()
        if len(keys)!=2:self.message.setText('按住 Ctrl 选择两张照片，再打开双图对比');return
        from .compare import CompareDialog
        try:dialog=CompareDialog(self.library,keys,self)
        except Exception as exc:QMessageBox.warning(self,'无法打开照片对比',str(exc));return
        dialog.favoriteRequested.connect(lambda key:self.change(lambda:self.library.update([key],favorite=not self.library.get(key)['favorite'])))
        try:
            dialog.exec()
            if dialog.chosen:
                from PySide6.QtCore import QItemSelectionModel
                for index,row in enumerate(self.model.rows):
                    if row['id']==dialog.chosen:
                        self.grid.selectionModel().select(self.model.index(index),QItemSelectionModel.SelectionFlag.ClearAndSelect)
                        break
        finally:dialog.deleteLater()

    def deliver_photos(self,kind):
        if self.busy:return
        keys=self.selected_keys() or [row['id'] for row in self.model.rows]
        if not keys:self.message.setText('当前没有可交付的照片');return
        from .delivery_ui import PhotoDeliveryOptions
        from .library_export import export_cutouts,export_contact_sheets
        title=self.albums.currentItem().text().rsplit('  ',1)[0] if self.albums.currentItem() else '选片联系表'
        dialog=PhotoDeliveryOptions(kind,len(keys),title,self)
        try:
            if dialog.exec()!=QDialog.DialogCode.Accepted:return
            edge=dialog.long_edge.currentData();columns=dialog.columns.currentData()
            title=dialog.title.text();originals=dialog.originals.isChecked()
        finally:dialog.deleteLater()
        folder=QFileDialog.getExistingDirectory(self,'选择照片交付文件夹',str(DATA/'exports'))
        if not folder:return
        def work(progress,cancel):
            if kind=='cutouts':return export_cutouts(self.library,keys,folder,edge,progress,cancel)
            return export_contact_sheets(self.library,keys,folder,title,columns,originals,progress,cancel)
        def done(report):
            count=len(report['files']);unit='张主体' if kind=='cutouts' else '页联系表'
            message=('已停止后续导出，保留 ' if report['cancelled'] else '已导出 ')+f'{count} {unit}'
            if report['errors']:message+=f' · {len(report["errors"])} 张照片读取或导出失败，详见导出清单'
            self.message.setText(message+' · '+report['folder'])
        self.start_job(work,done,undo=False)

    def import_archive(self):
        path,_=QFileDialog.getOpenFileName(self,'恢复照片归档包','','Cosfolio 照片归档 (*.cosphotos)')
        if path:self.start_job(lambda p,c:self.library.import_archive(path,p,c),
                              lambda n:self.message.setText(f'已恢复 {n} 张归档照片；已有照片与标签不会被覆盖'))

    def reject(self):
        if self.busy:self.message.setText('请先结束当前处理，再关闭照片库');return
        super().reject()

    def closeEvent(self,event):
        if self.busy:event.ignore();self.message.setText('请先结束当前处理，再关闭照片库')
        else:super().closeEvent(event)
