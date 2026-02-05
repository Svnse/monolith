from PySide6.QtCore import QObject, Signal


class UIBridge(QObject):
    sig_terminal_header = Signal(str, str)
