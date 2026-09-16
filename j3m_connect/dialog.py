# SPDX-License-Identifier: GPL-3.0-or-later
"""Modeless resource browser with secure connection settings."""
from qgis.PyQt.QtCore import QDateTime, Qt
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateTimeEdit, QDialog,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget,
)
from . import settings
from .adapters import catalog_records, geofence_geojson, indicator_rows, _response_data
from .api import ApiClient
from .layers import add_geojson_layer

SCOPES = ('sessions', 'devices', 'geofences', 'clusters')
TITLES = ('Sessões', 'Coletas por dispositivo', 'Geocercas', 'Clusters')
COLORS = {'blue': '#0284c7', 'green': '#16a34a', 'yellow': '#ca8a04',
          'orange': '#ea580c', 'red': '#dc2626', 'purple': '#7e22ce'}


def label(text=''):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


class J3MDialog(QDialog):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.api = ApiClient(self)
        self._busy = False
        self._loaded = False
        self._scope = 'sessions'
        self._cache = {}
        self.setWindowTitle('J3M Connect')
        self.resize(900, 650)
        layout = QVBoxLayout(self)
        body = QHBoxLayout()
        layout.addLayout(body)
        self.menu = QListWidget()
        self.menu.addItems(list(TITLES) + ['Conexão'])
        self.menu.setMaximumWidth(210)
        body.addWidget(self.menu)
        self.pages = QStackedWidget()
        body.addWidget(self.pages, 1)
        self.browser = QWidget()
        panel = QVBoxLayout(self.browser)
        self.title = label(TITLES[0])
        self.title.setStyleSheet('font-size: 20px; font-weight: bold;')
        panel.addWidget(self.title)
        self.search = QLineEdit()
        self.search.setPlaceholderText('Buscar registros por nome ou UUID…')
        panel.addWidget(self.search)
        self.records = QComboBox()
        panel.addWidget(self.records)
        self.refreshButton = QPushButton('Atualizar registros')
        panel.addWidget(self.refreshButton)
        self.details = label()
        panel.addWidget(self.details)
        self.periodBox = QWidget()
        form = QFormLayout(self.periodBox)
        self.start = QDateTimeEdit(QDateTime.currentDateTime().addDays(-7))
        self.end = QDateTimeEdit(QDateTime.currentDateTime())
        for edit in (self.start, self.end):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat('dd/MM/yyyy HH:mm:ss')
        form.addRow('Início', self.start)
        form.addRow('Fim', self.end)
        self.timezone = label()
        form.addRow('Fuso horário', self.timezone)
        panel.addWidget(self.periodBox)
        self.consultButton = QPushButton('Consultar indicadores')
        panel.addWidget(self.consultButton)
        self.summary = label('Selecione um registro.')
        panel.addWidget(self.summary)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(['Métrica', 'Média', 'Unidade', 'Mínimo', 'Máximo'])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        panel.addWidget(self.table, 1)
        self.addButton = QPushButton('Adicionar coletas ao mapa')
        self.polygonButton = QPushButton('Adicionar limite da geocerca ao mapa')
        panel.addWidget(self.addButton)
        panel.addWidget(self.polygonButton)
        self.pages.addWidget(self.browser)
        self.configPage = QWidget()
        config = QVBoxLayout(self.configPage)
        config.addWidget(label('Conexão com a J3M'))
        config.addWidget(label('Informe as credenciais da sua integração. Elas ficam protegidas no cofre de autenticação do QGIS.'))
        fields = QFormLayout()
        self.clientEdit = QLineEdit()
        self.secretEdit = QLineEdit()
        self.secretEdit.setEchoMode(QLineEdit.EchoMode.Password)
        self.secretEdit.setPlaceholderText('Cole o Secret; vazio mantém o que já está salvo')
        fields.addRow('Client ID', self.clientEdit)
        fields.addRow('Client Secret', self.secretEdit)
        config.addLayout(fields)
        self.showSecret = QCheckBox('Mostrar Secret digitado')
        self.showSecret.toggled.connect(lambda show: self.secretEdit.setEchoMode(
            QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password))
        config.addWidget(self.showSecret)
        self.saveButton = QPushButton('Salvar e conectar')
        self.removeButton = QPushButton('Remover conexão salva')
        config.addWidget(self.saveButton)
        config.addWidget(self.removeButton)
        config.addStretch()
        self.pages.addWidget(self.configPage)
        self.statusLabel = label('Configure a conexão para começar.')
        layout.addWidget(self.statusLabel)
        close = QPushButton('Fechar')
        close.clicked.connect(self.close)
        layout.addWidget(close)
        self.menu.currentRowChanged.connect(self._navigate)
        self.search.textChanged.connect(self._filter)
        self.records.currentIndexChanged.connect(self._selected)
        self.refreshButton.clicked.connect(self._refresh)
        self.consultButton.clicked.connect(self._consult)
        self.addButton.clicked.connect(lambda: self._request('collections'))
        self.polygonButton.clicked.connect(self._polygon)
        self.start.dateTimeChanged.connect(self._period_changed)
        self.end.dateTimeChanged.connect(self._period_changed)
        self.saveButton.clicked.connect(self._save)
        self.removeButton.clicked.connect(self._remove)
        self.api.busyChanged.connect(self._set_busy)
        self.api.failed.connect(self._error)
        self.api.received.connect(self._received)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self.menu.setCurrentRow(0 if settings.preferences()[1] else 4)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            if settings.preferences()[1]:
                try:
                    _, client, _ = settings.credentials()
                    self.clientEdit.setText(client)
                    self._refresh()
                except ValueError as error:
                    self._error(str(error))

    def _navigate(self, index):
        self.api.cancel()
        self.secretEdit.clear()
        self.showSecret.setChecked(False)
        self.pages.setCurrentIndex(1 if index == 4 else 0)
        if index == 4:
            return
        self._scope = SCOPES[index]
        self.title.setText(TITLES[index])
        self.periodBox.setVisible(index != 0)
        self.polygonButton.setVisible(self._scope == 'geofences')
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._filter()
        if self._loaded and self._scope not in self._cache:
            self._refresh()

    def _save(self):
        try:
            settings.save(self.clientEdit.text(), self.secretEdit.text())
            self.secretEdit.clear()
            self._cache.clear()
            self.menu.setCurrentRow(SCOPES.index(self._scope))
        except ValueError as error:
            self._error(str(error))

    def _remove(self):
        try:
            settings.remove()
            self.clientEdit.clear()
            self.secretEdit.clear()
            self._cache.clear()
            self._filter()
            self.statusLabel.setText('Conexão removida. Informe novas credenciais para continuar.')
        except ValueError as error:
            self._error(str(error))

    def _refresh(self):
        self._cache.pop(self._scope, None)
        self._filter()
        self.statusLabel.setText('Carregando registros…')
        self.api.get('catalog', scope=self._scope)

    def _filter(self):
        previous = self.records.currentData()
        needle = self.search.text().casefold().strip()
        self.records.blockSignals(True)
        self.records.clear()
        for record in self._cache.get(self._scope, []):
            if needle in (record['name'] + ' ' + record['uuid']).casefold():
                self.records.addItem(record['name'], record)
        if previous:
            for index in range(self.records.count()):
                if self.records.itemData(index)['uuid'] == previous['uuid']:
                    self.records.setCurrentIndex(index)
                    break
        self.records.blockSignals(False)
        self._selected()

    def _selected(self):
        self.api.cancel()
        self._period_changed()
        record = self.records.currentData()
        self.details.setText('UUID: ' + record['uuid'] if record else 'Nenhum registro disponível.')
        zone = 'UTC' if self._scope == 'geofences' else (record or {}).get('timezone')
        self.timezone.setText(str(zone or 'Não informado pela API'))
        if record and self._scope == 'clusters':
            self.details.setText(self.details.text() + '\nDispositivos: ' + ', '.join(
                str(d.get('name', d.get('uuid', ''))) for d in record.get('devices', []) if isinstance(d, dict)))
        self._set_busy(False)
        if record and self._scope == 'sessions':
            self._consult()

    def _period_changed(self):
        self.table.setRowCount(0)
        self.summary.setText('Consulte os indicadores para o registro e período selecionados.')
        self.statusLabel.setText('Pronto para consultar.')

    def _request(self, kind):
        record = self.records.currentData()
        if not record:
            return
        period = None
        if self._scope != 'sessions':
            if self.end.dateTime() <= self.start.dateTime():
                self._error('A data final deve ser posterior à data inicial.')
                return
            if self._scope in ('devices', 'clusters') and not record.get('timezone'):
                self._error('O recurso não informa seu fuso horário. Atualize o catálogo antes de consultar.')
                return
            period = tuple(edit.dateTime().toString('yyyy-MM-dd HH:mm:ss') for edit in (self.start, self.end))
        self.statusLabel.setText('Consultando ' + {'indicators': 'indicadores', 'table': 'mínimos e máximos', 'collections': 'coletas'}[kind] + '…')
        self.api.get(kind, record['uuid'], scope=self._scope, period=period)

    def _consult(self):
        self._period_changed()
        self._request('indicators')

    def _set_busy(self, busy):
        self._busy = busy
        for widget in (self.records, self.search, self.refreshButton, self.periodBox, self.configPage):
            widget.setEnabled(not busy)
        selected = self.records.currentData() is not None
        for button in (self.consultButton, self.addButton, self.polygonButton):
            button.setEnabled(not busy and selected)

    def _error(self, message):
        self.statusLabel.setText(message)

    def _received(self, kind, payload):
        try:
            if kind == 'catalog':
                self._cache[self._scope] = catalog_records(payload)
                self._filter()
                if not self._busy:
                    self.statusLabel.setText('{} registro(s) disponível(is).'.format(self.records.count()))
            elif kind == 'indicators':
                summary, rows = indicator_rows(payload)
                self.summary.setText(summary)
                self.table.setRowCount(len(rows))
                for row, values in enumerate(rows):
                    for col, value in enumerate(values[:3]):
                        item = QTableWidgetItem(str(value))
                        if col == 1 and values[3] in COLORS:
                            item.setForeground(QColor(COLORS[values[3]]))
                        self.table.setItem(row, col, item)
                self.statusLabel.setText('Indicadores atualizados.')
                if self._scope == 'geofences':
                    self._request('table')
            elif kind == 'table':
                rows = _response_data(payload) or []
                if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                    raise ValueError('Tabela de geocerca inválida.')
                for entry in rows:
                    metric = str(entry.get('metric', '—'))
                    row = next((r for r in range(self.table.rowCount())
                                if self.table.item(r, 0).text() == metric), self.table.rowCount())
                    if row == self.table.rowCount():
                        self.table.insertRow(row)
                        self.table.setItem(row, 0, QTableWidgetItem(metric))
                        self.table.setItem(row, 2, QTableWidgetItem(str(entry.get('unit', ''))))
                    for col, key in ((3, 'min'), (4, 'max')):
                        self.table.setItem(row, col, QTableWidgetItem(str(entry.get(key, '—'))))
                self.statusLabel.setText('Indicadores e mínimos/máximos atualizados.' if rows else 'Sem mínimos/máximos disponíveis no período.')
            elif kind == 'collections':
                self._add_layer(payload)
        except (ValueError, OSError, RecursionError) as error:
            self._error(str(error))

    def _add_layer(self, payload, polygon=False):
        if payload is None:
            self.statusLabel.setText('Nenhuma coleta disponível no período.')
            return
        name = 'J3M — ' + self.records.currentText()
        if not polygon and self._scope != 'sessions':
            name += ' — ' + self.start.text() + ' a ' + self.end.text()
        layer = add_geojson_layer(payload, name)
        if layer is None:
            self.statusLabel.setText('Nenhuma coleta com coordenadas disponível.')
            return
        if polygon:
            from qgis.core import QgsFillSymbol
            color = QColor(self.records.currentData().get('color') or '#16a34a')
            if not color.isValid():
                color = QColor('#16a34a')
            layer.renderer().setSymbol(QgsFillSymbol.createSimple({
                'color': '{},{},{},40'.format(color.red(), color.green(), color.blue()),
                'outline_color': color.name(), 'outline_width': '0.5'}))
            layer.triggerRepaint()
        self.iface.setActiveLayer(layer)
        self.iface.actionMapTips().setChecked(True)
        self.statusLabel.setText('Camada adicionada ao mapa e salva no perfil QGIS.')

    def _polygon(self):
        try:
            self._add_layer(geofence_geojson(self.records.currentData()), polygon=True)
        except (ValueError, OSError, RecursionError) as error:
            self._error(str(error))

    def done(self, result):
        self.api.cancel()
        self.secretEdit.clear()
        super().done(result)

    def closeEvent(self, event):
        self.api.cancel()
        self.secretEdit.clear()
        super().closeEvent(event)
