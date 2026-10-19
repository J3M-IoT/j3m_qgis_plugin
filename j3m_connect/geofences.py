# SPDX-License-Identifier: GPL-3.0-or-later
"""Select catalog geofences and load each one as an independent layer."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from .adapters import catalog_records, geofence_geojson
from .api import ApiClient
from .layers import LayerLoader


class GeofencesPage(QWidget):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.api = ApiClient(self)
        self.layerLoader = LayerLoader(self)
        self._queue = []
        self.loaded = False
        self.busy = False
        layout = QVBoxLayout(self)
        title = QLabel('Geocercas no mapa')
        title.setStyleSheet('font-size: 20px; font-weight: bold;')
        layout.addWidget(title)
        layout.addWidget(QLabel('Marque as geocercas que deseja adicionar. Cada uma será uma camada separada.'))
        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar geocercas por nome ou UUID…')
        layout.addWidget(self.search)
        self.refreshButton = QPushButton('Atualizar geocercas')
        layout.addWidget(self.refreshButton)
        self.records = QListWidget()
        layout.addWidget(self.records, 1)
        actions = QHBoxLayout()
        self.selectButton = QPushButton('Marcar todas as visíveis')
        self.clearButton = QPushButton('Desmarcar todas')
        actions.addWidget(self.selectButton)
        actions.addWidget(self.clearButton)
        layout.addLayout(actions)
        self.selectionLabel = QLabel()
        layout.addWidget(self.selectionLabel)
        self.addButton = QPushButton('Adicionar selecionadas ao QGIS')
        layout.addWidget(self.addButton)
        self.status = QLabel('Atualize a lista para consultar as geocercas.')
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.search.textChanged.connect(self._filter)
        self.records.itemChanged.connect(self._selection_changed)
        self.refreshButton.clicked.connect(self.refresh)
        self.selectButton.clicked.connect(lambda: self._check_all(True))
        self.clearButton.clicked.connect(lambda: self._check_all(False))
        self.addButton.clicked.connect(self._add)
        self.api.received.connect(self._received)
        self.api.failed.connect(self.status.setText)
        self.api.busyChanged.connect(self._set_busy)
        self.layerLoader.failed.connect(self._load_failed)
        self._selection_changed()

    def activate(self):
        if not self.loaded:
            self.refresh()

    def reset(self):
        self.cancel()
        self.loaded = False
        self.records.clear()
        self.search.clear()
        self._selection_changed()
        self.status.setText('Atualize a lista para consultar as geocercas.')

    def cancel(self):
        self._queue = []
        self.api.cancel()
        self.layerLoader.cancel()
        self._set_busy(False)

    def refresh(self):
        self.status.setText('Carregando geocercas…')
        self.api.get('catalog', scope='geofences')

    def _items(self):
        return [self.records.item(index) for index in range(self.records.count())]

    def _received(self, kind, payload):
        if kind != 'catalog':
            return
        try:
            records = catalog_records(payload)
        except ValueError as error:
            self.status.setText(str(error))
            return
        checked = {item.data(Qt.ItemDataRole.UserRole)['uuid'] for item in self._items()
                   if item.checkState() == Qt.CheckState.Checked}
        self.records.blockSignals(True)
        self.records.clear()
        for record in records:
            item = QListWidgetItem(record['name'])
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setToolTip(record['uuid'])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if record['uuid'] in checked else Qt.CheckState.Unchecked)
            self.records.addItem(item)
        self.records.blockSignals(False)
        self.loaded = True
        self._filter()
        self.status.setText('{} geocerca(s) disponível(is).'.format(len(records)))

    def _filter(self):
        needle = self.search.text().strip().casefold()
        for item in self._items():
            record = item.data(Qt.ItemDataRole.UserRole)
            item.setHidden(needle not in (record['name'] + ' ' + record['uuid']).casefold())
        self._selection_changed()

    def _check_all(self, checked):
        self.records.blockSignals(True)
        for item in self._items():
            if not checked or not item.isHidden():
                item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)
        self.records.blockSignals(False)
        self._selection_changed()

    def _selection_changed(self, *_):
        selected = [item for item in self._items() if item.checkState() == Qt.CheckState.Checked]
        hidden = sum(item.isHidden() for item in selected)
        self.selectionLabel.setText('{} selecionada(s), incluindo {} fora do filtro.'.format(len(selected), hidden))
        self.addButton.setEnabled(bool(selected) and not self.busy)

    def _set_busy(self, busy):
        self.busy = busy
        for widget in (self.search, self.records, self.refreshButton, self.selectButton, self.clearButton):
            widget.setEnabled(not busy)
        self._selection_changed()

    def _add(self):
        selected = [item for item in self._items() if item.checkState() == Qt.CheckState.Checked]
        self._queue = [dict(item.data(Qt.ItemDataRole.UserRole)) for item in selected]
        self._added = 0
        self._errors = []
        self._set_busy(True)
        self._next_layer()

    def _load_failed(self, message):
        self._errors.append(message)
        self._next_layer()

    def _next_layer(self):
        if not self._queue:
            self._set_busy(False)
            self.status.setText('{} geocerca(s) adicionada(s).'.format(self._added)+
                ('\nNão foi possível adicionar:\n'+'\n'.join(self._errors) if self._errors else ''))
            return
        record = self._queue.pop(0)
        try:
            payload = geofence_geojson(record)
        except (ValueError, TypeError, RecursionError) as error:
            self._load_failed(record['name']+': '+str(error))
            return
        def finish(layer, digest):
            if layer is not None:
                self._added += 1
                for item in self._items():
                    if item.data(Qt.ItemDataRole.UserRole)['uuid'] == record['uuid']:
                        item.setCheckState(Qt.CheckState.Unchecked)
                self.iface.setActiveLayer(layer)
                self.iface.actionMapTips().setChecked(True)
            self._next_layer()
        self.status.setText('Preparando '+record['name']+'…')
        self.layerLoader.load(payload,'J3M — '+record['name'],finish,geofence=True)
