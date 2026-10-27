"""The main layout editor in the same Umi visual system as the photo library.

Only widget placement, sizing and decoration live here. The existing Studio
widgets, signals, project state and rendering/export operations are retained.
"""
from __future__ import annotations
from PySide6.QtCore import Qt, QSize, QObject
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QVBoxLayout, QHBoxLayout,
    QSplitter, QPushButton, QToolButton, QMenu, QSizePolicy)
from .library_visual import STYLE as LIBRARY_STYLE, label, icon

STYLE=LIBRARY_STYLE+'''
QWidget#editorRoot, QWidget#editorMain { background: #f0f4f9; }
QFrame#editorChrome { background: white; border: 0; border-bottom: 1px solid #dde6f0; }
QFrame#editorSidebar { background: white; border: 0; border-right: 1px solid #dde6f0; border-radius: 0; }
QFrame#editorInspector { background: white; border: 0; border-left: 1px solid #dde6f0; border-radius: 0; }
QLabel#editorActive { color: #174d8b; background: #e6eef9; padding: 8px 12px; border-radius: 7px; font-size: 12px; }
QLabel#section { color: #233a52; font-size: 13px; font-weight: 500; }
QLabel#muted { color: #687c91; font-size: 11px; }
QPushButton#editorNavigation { border: 0; background: transparent; color: #687c91; font-size: 12px; padding: 8px 11px; }
QPushButton#editorNavigation:hover { background: #e6eef9; color: #174d8b; }
QListWidget#editorPhotos { background: transparent; border: 0; outline: 0; }
QListWidget#editorPhotos::item { background: white; border: 1px solid #dde6f0; border-radius: 8px; margin: 5px 0; padding: 7px; }
QListWidget#editorPhotos::item:selected { background: #f0f5fc; border: 1px solid #174d8b; color: #174d8b; }
QTabWidget#settings::pane { background: white; border: 0; }
QTabWidget#settings QTabBar::tab { background: white; color: #687c91; padding: 10px 7px; font-size: 12px; border: 0; }
QTabWidget#settings QTabBar::tab:selected { color: #174d8b; border-bottom: 2px solid #174d8b; }
QWidget#settingsPage { background: white; }
QStatusBar { color: #687c91; font-size: 11px; background: white; border-top: 1px solid #dde6f0; padding: 4px 14px; }
QStatusBar::item { border: 0; }
QFrame#editorRecovery { background: #e6eef9; border: 0; padding: 6px; }
'''


class EditorPresentation(QObject):
    def __init__(self, studio):
        super().__init__(studio);self.studio=studio
        self.mount()

    def mount(self):
        s=self.studio;root=s.centralWidget();root.setObjectName('editorRoot')
        layout=root.layout();self.park=QWidget(root);self.park.hide()
        sidebar=s.photos.parentWidget();sidebar_layout=sidebar.layout()
        visible_banner=not s.recovery_banner.isHidden()
        visible_progress=not s.progress.isHidden();visible_cancel=not s.cancel_batch_btn.isHidden()

        def park_layout(old):
            while old.count():
                item=old.takeAt(0)
                if item.widget():item.widget().setParent(self.park)
                elif item.layout():park_layout(item.layout())

        park_layout(layout);park_layout(sidebar_layout)
        layout.setContentsMargins(0,0,0,0);layout.setSpacing(0)
        s.setStyleSheet(STYLE)
        chrome=QFrame();chrome.setObjectName('editorChrome');chrome.setFixedHeight(91)
        ch=QHBoxLayout(chrome);ch.setContentsMargins(26,15,26,14);ch.setSpacing(9)
        brand=QVBoxLayout();brand.setSpacing(3);brandrow=QHBoxLayout();brandrow.setSpacing(12)
        brandrow.addWidget(label('Cosfolio','libraryBrand'))
        brandrow.addWidget(label('偶像写真工房','libraryBrandSub'));brandrow.addStretch()
        brand.addLayout(brandrow);brand.addWidget(label('PHOTO STUDIO','libraryEyebrow'))
        brand_widget=QWidget();brand_widget.setLayout(brand);brand_widget.setFixedWidth(245)
        ch.addWidget(brand_widget);ch.addSpacing(18)
        active=label('排版创作','editorActive');active.setWordWrap(False);active.setFixedHeight(34);ch.addWidget(active)
        s.library_btn.setText('照片库');s.library_btn.setObjectName('editorNavigation')
        s.library_btn.setIcon(icon('photos'));s.library_btn.setIconSize(QSize(16,16))
        s.library_btn.setFixedHeight(34)
        s.library_btn.setToolTip('打开照片库 · 专辑、选片与精修素材');ch.addWidget(s.library_btn)
        ch.addStretch()
        for b in (s.new_btn,s.open_btn,s.save_btn,s.batch_btn,s.export_btn):ch.addWidget(b)
        layout.addWidget(chrome)
        s.recovery_banner.setObjectName('editorRecovery');layout.addWidget(s.recovery_banner)
        s.recovery_banner.setVisible(visible_banner)

        split=QSplitter(Qt.Orientation.Horizontal);split.setHandleWidth(1);split.setChildrenCollapsible(False)
        self.split=split
        sidebar.setObjectName('editorSidebar');sidebar.setMinimumWidth(180);sidebar.setMaximumWidth(330)
        ll=sidebar_layout;ll.setContentsMargins(16,24,16,18);ll.setSpacing(12)
        sideheading=QHBoxLayout();sideheading.addWidget(label('工程照片','libraryOverline'),1)
        s.count_label.setObjectName('libraryHint');sideheading.addWidget(s.count_label);ll.addLayout(sideheading)
        ll.addWidget(s.import_btn)
        hint=label('从文件夹拖入照片\n拖到画框中，安排你的构图。');hint.setContentsMargins(0,0,0,4);ll.addWidget(hint)
        s.photos.setObjectName('editorPhotos');s.photos.setIconSize(QSize(70,90))
        ll.addWidget(s.photos,1)
        ll.addWidget(label('照片留在本机\n精修结果可在照片库复用'))
        split.addWidget(sidebar);sidebar.show()

        middle=QWidget();middle.setObjectName('editorMain');middle.setMinimumWidth(380)
        ml=QVBoxLayout(middle);ml.setContentsMargins(20,24,20,14);ml.setSpacing(10)
        intro=QHBoxLayout();wording=QVBoxLayout();wording.setSpacing(4)
        wording.addWidget(label('YOUR OWN PHOTO BOOK.','libraryEyebrow'))
        wording.addWidget(label('把喜欢，排成一册。','libraryTitle'));intro.addLayout(wording,1)
        local=QToolButton();local.setIcon(icon('drive'));local.setText('本机创作')
        local.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon);local.setEnabled(False)
        intro.addWidget(local);ml.addLayout(intro)
        pages=QHBoxLayout();pages.setSpacing(7)
        pages.addWidget(label('写真页'))
        s.page_selector.setMinimumWidth(120);s.page_selector.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed)
        pages.addWidget(s.page_selector,1);pages.addWidget(s.page_buttons[0])
        self.page_menu_button=QToolButton();self.page_menu_button.setText('页面操作');self.page_menu_button.setIcon(icon('more'))
        self.page_menu_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.page_menu_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(self.page_menu_button);actions=[]
        for button in s.page_buttons[1:]:
            actions.append((menu.addAction(button.text(),button.click),button))
        menu.addSeparator();actions.append((menu.addAction('导出整本写真…',s.book_btn.click),s.book_btn))
        menu.aboutToShow.connect(lambda:[action.setEnabled(button.isEnabled()) for action,button in actions])
        self.page_menu_button.setMenu(menu);pages.addWidget(self.page_menu_button);ml.addLayout(pages)
        previewbar=QHBoxLayout();s.preview_label.setObjectName('libraryHint');previewbar.addWidget(s.preview_label,1)
        previewbar.addWidget(s.guides)
        for b,name,hint in ((s.undo_btn,'undo','撤销 · Ctrl+Z'),(s.redo_btn,'redo','重做 · Ctrl+Y')):
            b.setText('');b.setIcon(icon(name));b.setIconSize(QSize(16,16));b.setFixedSize(29,29)
            b.setObjectName('libraryQuiet');b.setToolTip(hint);b.setAccessibleName(hint);previewbar.addWidget(b)
        ml.addLayout(previewbar)
        s.canvas.workspace_color='#f0f4f9';s.canvas.setMinimumSize(300,300);ml.addWidget(s.canvas,1)
        caption=label('拖动调整人物 · 滚轮缩放 · 方向键微调')
        caption.setAlignment(Qt.AlignmentFlag.AlignCenter);ml.addWidget(caption)
        split.addWidget(middle)

        right=QFrame();right.setObjectName('editorInspector');right.setMinimumWidth(250);right.setMaximumWidth(380)
        rl=QVBoxLayout(right);rl.setContentsMargins(16,24,16,16);rl.setSpacing(8)
        rl.addWidget(label('页面设置','libraryOverline'));rl.addWidget(s.settings_tabs,1)
        s.settings_tabs.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Expanding)
        for page_layout in s.settings_layouts:
            page_layout.setContentsMargins(2,14,2,10);page_layout.setSpacing(10)
        s.template_picture.setFixedHeight(195)
        for b in (s.template_picker,s.create_template_btn,s.reference_button):
            b.setSizePolicy(QSizePolicy.Policy.Ignored,QSizePolicy.Policy.Fixed);b.setMinimumWidth(0)
        for i in range(s.settings_tabs.count()):
            s.settings_tabs.widget(i).setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        split.addWidget(right);split.setSizes([218,935,285]);split.setStretchFactor(1,1)
        layout.addWidget(split,1)
        layout.addWidget(s.progress);s.progress.setVisible(visible_progress)
        layout.addWidget(s.cancel_batch_btn);s.cancel_batch_btn.setVisible(visible_cancel)
        s.statusBar().setSizeGripEnabled(False)


def apply_editor_visual(studio):
    studio.editor_presentation=EditorPresentation(studio)
