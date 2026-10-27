"""Window-scoped editing shortcuts; modal editors own their local history."""
from PySide6.QtGui import QShortcut,QKeySequence


def bind_history(widget,undo,redo):
    widget._history_shortcuts=[]
    for key,callback in [('Ctrl+Z',undo),('Ctrl+Y',redo),('Ctrl+Shift+Z',redo)]:
        shortcut=QShortcut(QKeySequence(key),widget)
        shortcut.activated.connect(callback)
        widget._history_shortcuts.append(shortcut)
