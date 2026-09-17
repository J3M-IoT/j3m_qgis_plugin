# SPDX-License-Identifier: GPL-3.0-or-later
"""Select catalog geofences and load each one as an independent layer."""
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QPushButton, QVBoxLayout, QWidget,
)

from .adapters import catalog_records
from .api import ApiClient
from .layers import add_geofence_layer


class GeofencesPage(QWidget):
    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.api = ApiClient(self)
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
        self._selection_changed()

    def activate(self):
        if not self.loaded:
            self.refresh()

    def reset(self):
        self.api.cancel()
        self.loaded = False
        self.records.clear()
        self.search.clear()
        self._selection_changed()
        self.status.setText('Atualize a lista para consultar as geocercas.')

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
        self._set_busy(True)
        added, errors = [], []
        try:
            for item in selected:
                record = item.data(Qt.ItemDataRole.UserRole)
                try:
                    layer = add_geofence_layer(record)
                except (ValueError, OSError, RecursionError) as error:
                    errors.append('{}: {}'.format(record['name'], error))
                    continue
                added.append(layer)
                item.setCheckState(Qt.CheckState.Unchecked)
            if added:
                self.iface.setActiveLayer(added[-1])
                self.iface.actionMapTips().setChecked(True)
            message = '{} geocerca(s) adicionada(s) como camadas separadas.'.format(len(added))
            if errors:
                message += '\nNão foi possível adicionar:\n' + '\n'.join(errors)
            self.status.setText(message)
        finally:
            self._set_busy(False)
