"""Embedded project cover cards; never extracts source photographs to browse."""
from pathlib import Path
import io
import json
import zipfile
from PIL import Image
from PySide6.QtCore import Qt,QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (QDialog,QVBoxLayout,QHBoxLayout,QLabel,QPushButton,QListWidget,
                              QListWidgetItem,QAbstractItemView,QFileDialog,QDialogButtonBox)


def project_summary(path):
    path=Path(path)
    with zipfile.ZipFile(path) as archive:
        if archive.getinfo('project.json').file_size>2*1024**2:raise ValueError('工程信息过大')
        data=json.loads(archive.read('project.json'))
        if data.get('format')!='cosfolio':raise ValueError('工程格式不正确')
        cover=None
        if 'cover.jpg' in archive.namelist():
            if archive.getinfo('cover.jpg').file_size>4*1024**2:raise ValueError('工程封面过大')
            with Image.open(io.BytesIO(archive.read('cover.jpg'))) as image:
                if image.width*image.height>2_000_000:raise ValueError('工程封面尺寸过大')
                cover=image.convert('RGB');cover.thumbnail((240,250))
        return {'path':str(path),'title':str(data.get('title') or path.stem)[:100],
                'pages':max(1,len(data.get('pages',[]))),'cover':cover}


class ProjectGallery(QDialog):
    def __init__(self,paths=(),folder=None,parent=None):
        super().__init__(parent)
        self.paths=list(paths);self.folder=Path(folder) if folder else None;self.chosen=None
        self.setWindowTitle('工程图库 · 按封面寻找写真')
        self.resize(1020,760)
        root=QVBoxLayout(self)
        root.addWidget(QLabel('保存工程时会自动生成封面；旧工程打开并重新保存后，也会有封面。'))
        bar=QHBoxLayout()
        for title,callback in [('选择工程文件夹',self.choose_folder),('打开工程文件…',self.choose_file)]:
            button=QPushButton(title);button.clicked.connect(callback);bar.addWidget(button)
        bar.addStretch();root.addLayout(bar)
        self.location=QLabel();self.location.setWordWrap(True);root.addWidget(self.location)
        self.gallery=QListWidget()
        self.gallery.setViewMode(QListWidget.ViewMode.IconMode)
        self.gallery.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.gallery.setMovement(QListWidget.Movement.Static)
        self.gallery.setIconSize(QSize(190,220));self.gallery.setGridSize(QSize(232,293))
        self.gallery.setWordWrap(True);self.gallery.setSpacing(7)
        self.gallery.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.gallery.itemDoubleClicked.connect(lambda _:self.accept())
        root.addWidget(self.gallery,1)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Open|QDialogButtonBox.StandardButton.Cancel)
        self.open_btn=buttons.button(QDialogButtonBox.StandardButton.Open);self.open_btn.setText('打开所选工程')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
        self.gallery.currentItemChanged.connect(lambda item,_:self.open_btn.setEnabled(bool(item)))
        self.refresh()

    def refresh(self):
        from .app import pixmap
        self.gallery.clear()
        paths=[Path(p) for p in self.paths if Path(p).is_file()]
        if self.folder and self.folder.is_dir():
            paths+=sorted(self.folder.glob('*.cosfolio'),key=lambda p:p.stat().st_mtime,reverse=True)[:100]
        seen=set();failed=0
        for path in paths:
            identity=str(path.resolve()).casefold()
            if identity in seen:continue
            seen.add(identity)
            try:summary=project_summary(path)
            except (OSError,ValueError,KeyError,zipfile.BadZipFile):failed+=1;continue
            icon=QIcon(pixmap(summary['cover'])) if summary['cover'] is not None else QIcon()
            suffix='\n旧工程 · 保存后生成封面' if summary['cover'] is None else ''
            item=QListWidgetItem(icon,f'{summary["title"]}\n{summary["pages"]} 页 · {path.name}{suffix}')
            item.setData(Qt.ItemDataRole.UserRole,str(path));item.setToolTip(str(path))
            item.setTextAlignment(Qt.AlignmentFlag.AlignCenter);self.gallery.addItem(item)
        self.location.setText((str(self.folder) if self.folder else '最近打开的工程')+
                              (f' · {failed} 个文件暂无法读取' if failed else '')+
                              ('\n这里还没有工程，可选择旧工程所在文件夹。' if not self.gallery.count() else ''))
        self.open_btn.setEnabled(bool(self.gallery.count()))
        if self.gallery.count():self.gallery.setCurrentRow(0)

    def choose_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'选择工程文件夹',str(self.folder or ''))
        if folder:self.folder=Path(folder);self.refresh()

    def choose_file(self):
        path,_=QFileDialog.getOpenFileName(self,'打开工程',str(self.folder or ''),'Cosfolio 工程 (*.cosfolio)')
        if path:self.chosen=path;super().accept()

    def accept(self):
        item=self.gallery.currentItem()
        if item:self.chosen=item.data(Qt.ItemDataRole.UserRole);super().accept()

    def done(self,result):
        for i in range(self.gallery.count()):self.gallery.item(i).setIcon(QIcon())
        super().done(result)
