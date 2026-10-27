from PySide6.QtWidgets import QDialog,QVBoxLayout,QLabel,QFormLayout,QComboBox,QLineEdit,QCheckBox,QDialogButtonBox


class PhotoDeliveryOptions(QDialog):
    def __init__(self,kind,count,title,parent=None):
        super().__init__(parent);self.kind=kind
        self.setWindowTitle('批量导出透明 PNG' if kind=='cutouts' else '生成编号选片联系表')
        self.setMinimumWidth(520);root=QVBoxLayout(self)
        root.addWidget(QLabel(f'本次交付 {count} 张照片，按当前网格顺序排列。'))
        hint=QLabel('将创建新的导出文件夹；取消时保留已经完成的图片。');hint.setObjectName('muted');hint.setWordWrap(True);root.addWidget(hint)
        form=QFormLayout();root.addLayout(form)
        self.long_edge=QComboBox()
        for value,label in [(0,'原图像素'),(3000,'最长边不超过 3000'),(6000,'最长边不超过 6000'),(8000,'最长边不超过 8000')]:self.long_edge.addItem(label,value)
        self.title=QLineEdit(title);self.title.setMaxLength(100)
        self.columns=QComboBox()
        for value in (3,4,5):self.columns.addItem(f'{value} 列 · 每页最多 {value*5} 张',value)
        self.columns.setCurrentIndex(1)
        self.originals=QCheckBox('使用原照片');self.originals.setChecked(True)
        if kind=='cutouts':
            form.addRow('图片大小',self.long_edge)
            note=QLabel('使用照片库当前蒙版，保留透明背景。工程内的调色、投影和排版不带入。\n保留原始像素范围，不额外放大小照片。')
        else:
            form.addRow('联系表标题',self.title);form.addRow('照片布局',self.columns);form.addRow('',self.originals)
            note=QLabel('输出 2400 × 3300 PNG，附带编号与完整照片名清单。\n取消勾选“使用原照片”可制作透明主体的联系表。')
        note.setWordWrap(True);note.setObjectName('muted');root.addWidget(note)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Ok|QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText('选择保存文件夹…')
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        buttons.accepted.connect(self.accept);buttons.rejected.connect(self.reject);root.addWidget(buttons)
