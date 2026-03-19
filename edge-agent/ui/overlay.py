from __future__ import annotations

from PyQt6 import QtCore, QtGui, QtWidgets


class CaptureBorderOverlay(QtWidgets.QWidget):
    """
    Finestra trasparente e click-through che disegna un bordo rosso attorno
    all'area del monitor selezionato per indicare quale schermo viene catturato.
    """

    def __init__(self, geometry: QtCore.QRect, parent: QtWidgets.QWidget | None = None) -> None:
        super().__init__(parent)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setWindowFlag(QtCore.Qt.WindowType.FramelessWindowHint, True)
        self.setWindowFlag(QtCore.Qt.WindowType.WindowStaysOnTopHint, True)
        self.setWindowFlag(QtCore.Qt.WindowType.Tool, True)
        # Evita taskbar
        self.setWindowFlag(QtCore.Qt.WindowType.BypassWindowManagerHint, True)

        self._geometry = QtCore.QRect(geometry)
        self.setGeometry(self._geometry)

    def set_screen_geometry(self, geometry: QtCore.QRect) -> None:
        self._geometry = QtCore.QRect(geometry)
        self.setGeometry(self._geometry)
        self.update()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:  # noqa: N802
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing, True)
        pen = QtGui.QPen(QtGui.QColor(255, 0, 0))
        pen.setWidth(6)
        painter.setPen(pen)
        # Rettangolo leggermente inset per non essere tagliato dai bordi schermo
        rect = self.rect().adjusted(3, 3, -3, -3)
        painter.drawRect(rect)
        painter.end()
