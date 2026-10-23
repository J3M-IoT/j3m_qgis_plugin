# SPDX-License-Identifier: GPL-3.0-or-later
"""Small native Qt plot: no QtCharts, WebEngine or external dependency."""
from .i18n import tr
from datetime import datetime, timezone
from .analysis import series_plot
from qgis.PyQt.QtCore import Qt, QPointF, QRectF, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPen, QPalette
from qgis.PyQt.QtWidgets import QWidget


class SeriesChart(QWidget):
    observationSelected = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.points = []
        self.positions = []
        self.selected = set()
        self.caption = ''
        self.plot = None
        self.setMinimumHeight(210)
        self.setAccessibleName(tr('Série temporal UTC; clique para selecionar uma coleta no mapa'))
        self.setToolTip(tr('Cada cor é uma série de dispositivo. Clique em um ponto para selecionar a coleta. Datas em UTC.'))

    def set_series(self, points, caption, prepared=None):
        self.points = points
        self.caption = caption
        self.plot = prepared if prepared is not None else series_plot(points)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        painter.fillRect(self.rect(), palette.brush(QPalette.ColorRole.Base))
        painter.setPen(palette.color(QPalette.ColorRole.Text))
        painter.drawText(QRectF(10, 5, self.width()-20, 30), Qt.AlignmentFlag.AlignLeft, self.caption or tr('Carregue coletas e escolha uma métrica.'))
        self.positions = []
        if not self.plot:
            return
        x0, x1, y0, y1 = self.plot['bounds']
        left, top, width, height = 63, 64, max(30, self.width()-83), max(30, self.height()-107)
        painter.drawRect(QRectF(left, top, width, height))
        painter.drawText(5, top+10, format(y1, '.2f'))
        painter.drawText(5, top+height, format(y0, '.2f'))
        painter.drawText(left, top+height+22, datetime.fromtimestamp(x0, timezone.utc).strftime('%d/%m %H:%M'))
        painter.drawText(max(left, self.width()-115), top+height+22, datetime.fromtimestamp(x1, timezone.utc).strftime('%d/%m %H:%M'))
        groups = self.plot['groups']
        colors = ['#1683ac', '#d98418', '#9b59b6', '#208574', '#bf4961']
        for group_index, (device, shown, limit, stride) in enumerate(groups):
            if group_index < 4:
                slot = max(40,(self.width()-20)//min(4,len(groups)))
                painter.setPen(QColor(colors[group_index % len(colors)]))
                caption = painter.fontMetrics().elidedText(device,Qt.TextElideMode.ElideRight,slot-12)
                painter.drawText(10+group_index*slot,46,caption)
            painter.setPen(QPen(QColor(colors[group_index % len(colors)]), 1.5))
            previous = None
            for point in shown:
                x = left+(point[0]-x0)/(x1-x0 or 1)*width
                y = top+height-(point[1]-y0)/(y1-y0 or 1)*height
                pos = QPointF(x, y)
                # Downsampled plots use isolated points to avoid bridging missing intervals.
                if previous and stride == 1 and point[0]-previous[0] <= limit and point[4]==previous[2]+1:
                    painter.drawLine(previous[1], pos)
                painter.drawEllipse(pos, 2.3, 2.3)
                if point[2] in self.selected:
                    painter.save()
                    painter.setPen(QPen(palette.color(QPalette.ColorRole.Highlight),3))
                    painter.drawEllipse(pos,6,6)
                    painter.restore()
                self.positions.append((x, y, point[2]))
                previous = (point[0], pos, point[4])
        if self.plot['reduced']:
            painter.drawText(left, top+15, tr('Visualização reduzida; estatísticas usam todas as coletas.'))

    def mousePressEvent(self, event):
        pos = event.position() if hasattr(event, 'position') else event.localPos()
        if self.positions:
            x,y,index = min(self.positions, key=lambda p: (p[0]-pos.x())**2+(p[1]-pos.y())**2)
            if (x-pos.x())**2+(y-pos.y())**2 < 225:
                self.observationSelected.emit(index)
        super().mousePressEvent(event)
