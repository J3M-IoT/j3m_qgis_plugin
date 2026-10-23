# SPDX-License-Identifier: GPL-3.0-or-later
"""Modeless resource browser with secure connection settings."""
from .i18n import tr
from .i18n import LANGUAGES, LANGUAGE_KEY, set_language, value_label, language
import json
from qgis.PyQt.QtCore import QDateTime, Qt, QTimeZone, QTimer, QTime, QLocale, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QDateTimeEdit, QDialog, QDockWidget,
    QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QTreeWidget, QTreeWidgetItem,
    QPushButton, QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout,
    QWidget, QTabWidget, QScrollArea, QSplitter, QProgressBar, QPlainTextEdit,
    QInputDialog, QListWidget, QListWidgetItem, QDialogButtonBox, QGridLayout,
)
from qgis.core import QgsProject, QgsSettings, QgsMapLayerStyle
from . import settings
from .adapters import catalog_records, geofence_geojson, indicator_rows, _response_data
from .api import ApiClient
from .layers import LayerLoader
from .geofences import GeofencesPage
from .workbench import Workbench, grid, fill
from .cartography import configure_layer, provenance, VERSION
from .shared_maps import SharedMapsPage
from .map_tips import LABELS

TITLES = {'devices': 'Dispositivos — Coletas e indicadores',
          'sessions': 'Sessões — Coletas e indicadores',
          'clusters': 'Clusters — Coletas e indicadores',
          'geofences': 'Geocercas — Dashboard'}
MENU = (
    ('Dispositivos', (('Coletas e indicadores', 'devices'),)),
    ('Sessões', (('Coletas e indicadores', 'sessions'),)),
    ('Clusters', (('Coletas e indicadores', 'clusters'),)),
    ('Geocercas', (('Dashboard', 'geofences'), ('Geocercas no mapa', 'geofences_map'))),
    ('Análise', (('Camadas e estudos', 'workbench'),)),
    ('Compartilhados', (('Mapas por código', 'shared_maps'),)),
    ('Configurações', (('Conexão', 'connection'), ('Idioma', 'language'))),
)
COLORS = {'blue': '#0284c7', 'green': '#16a34a', 'yellow': '#ca8a04',
          'orange': '#ea580c', 'red': '#dc2626', 'purple': '#7e22ce'}


def label(text=''):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    return widget


class J3MDialog(QDockWidget):
    languageChanged = pyqtSignal()

    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.setLocale(QLocale(language().replace('-', '_')))
        self.iface = iface
        self.api = ApiClient(self)
        self.layerLoader = LayerLoader(self)
        self._busy = False
        self._loaded = False
        self._scope = 'devices'
        self._cache = {}
        self._metric_units = {}
        self._indicator_counts = {}
        self._zone = 'UTC'
        self._period_record = None
        self._pending_query = None
        self._batch = []
        self._replace_id = None
        self._deferred_query = None
        self.setObjectName('J3MConnectDock')
        self.setWindowTitle('J3M Connect • '+VERSION)
        self.resize(760, 800)
        container = QWidget()
        self.setWidget(container)
        layout = QVBoxLayout(container)
        header = QHBoxLayout()
        brand = label('J3M Connect · '+VERSION)
        brand_font = brand.font()
        brand_font.setBold(True)
        brand_font.setPointSize(max(brand_font.pointSize(), 10) + 1)
        brand.setFont(brand_font)
        brand.setContentsMargins(6,6,6,6)
        header.addWidget(brand, 1)
        self.navigationButton = QPushButton(tr('Menu'))
        self.navigationButton.setCheckable(True)
        self.navigationButton.setChecked(True)
        header.addWidget(self.navigationButton)
        floatButton = QPushButton(tr('Flutuar'))
        floatButton.clicked.connect(lambda: self.setFloating(not self.isFloating()))
        self.topLevelChanged.connect(lambda floating: floatButton.setText(tr('Acoplar') if floating else tr('Flutuar')))
        header.addWidget(floatButton)
        layout.addLayout(header)
        body = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(body, 1)
        self.menu = QTreeWidget()
        self.menu.setHeaderHidden(True)
        self.menu.setIndentation(16)
        self.menu.setMinimumWidth(130)
        self.menu.setMaximumWidth(220)
        self.navigationButton.toggled.connect(self.menu.setVisible)
        self.menu.setAccessibleName(tr('Navegação J3M'))
        self.menuItems = {}
        for title, entries in MENU:
            group = QTreeWidgetItem(self.menu, [tr(title)])
            group.setFlags(group.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            font = group.font(0)
            font.setBold(True)
            group.setFont(0, font)
            for caption, route in entries:
                item = QTreeWidgetItem(group, [tr(caption)])
                item.setData(0, Qt.ItemDataRole.UserRole, route)
                self.menuItems[route] = item
            group.setExpanded(False)
        body.addWidget(self.menu)
        self.pages = QStackedWidget()
        body.addWidget(self.pages)
        body.setStretchFactor(1, 1)
        self.browser = QWidget()
        panel = QVBoxLayout(self.browser)
        self.title = label(tr(TITLES[self._scope]))
        self.title.setStyleSheet('font-size: 20px; font-weight: bold;')
        panel.addWidget(self.title)
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr('Buscar registros por nome ou UUID…'))
        panel.addWidget(self.search)
        self.records = QComboBox()
        panel.addWidget(self.records)
        self.refreshButton = QPushButton(tr('Atualizar registros'))
        panel.addWidget(self.refreshButton)
        saved = QHBoxLayout()
        self.savedQueries = QComboBox()
        self.savedQueries.setAccessibleName(tr('Consultas salvas no projeto'))
        saved.addWidget(self.savedQueries, 1)
        for caption, handler in [(tr('Salvar consulta'),self._save_query),(tr('Abrir'),self._load_query),(tr('Excluir'),self._remove_query)]:
            button = QPushButton(caption)
            button.clicked.connect(handler)
            saved.addWidget(button)
        panel.addLayout(saved)
        self.details = label()
        panel.addWidget(self.details)
        self.periodBox = QWidget()
        form = QFormLayout(self.periodBox)
        # Editors hold a neutral wall clock. Conversion is explicit using _zone.
        today = QDateTime.currentDateTimeUtc().date()
        self.start = QDateTimeEdit(QDateTime(today,QTime(0,0,0),Qt.TimeSpec.UTC))
        self.end = QDateTimeEdit(QDateTime(today,QTime(23,59,59),Qt.TimeSpec.UTC))
        for edit in (self.start, self.end):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat('dd/MM/yyyy HH:mm:ss')
        form.addRow(tr('Início'), self.start)
        form.addRow(tr('Fim'), self.end)
        self.timezone = label()
        form.addRow(tr('Fuso horário'), self.timezone)
        self.utcLabel = label()
        form.addRow(tr('Equivalente UTC'), self.utcLabel)
        quick = QHBoxLayout()
        for caption, preset in [(tr('Hoje'),'today'),(tr('Ontem'),'yesterday'),(tr('7 dias'),'week'),(tr('24 horas'),'day')]:
            button = QPushButton(caption)
            button.clicked.connect(lambda checked=False, value=preset: self._quick_period(value))
            quick.addWidget(button)
        form.addRow(quick)
        panel.addWidget(self.periodBox)
        self.consultButton = QPushButton(tr('Consultar indicadores'))
        panel.addWidget(self.consultButton)
        self.summary = label(tr('Selecione um registro.'))
        self.summary.setStyleSheet('font-size: 14px; font-weight: 600; padding: 10px; border: 1px solid palette(mid); border-radius: 6px;')
        panel.addWidget(self.summary)
        self.cards = QGridLayout()
        panel.addLayout(self.cards)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr('Métrica'), tr('Média'), tr('Unidade'), tr('Mínimo'), tr('Máximo')])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.resultTabs = QTabWidget()
        self.resultTabs.setUsesScrollButtons(True)
        self.resultTabs.addTab(self.table, tr('Indicadores da API'))
        self.sessionPage = QWidget()
        sessionLayout = QVBoxLayout(self.sessionPage)
        sessionLayout.addWidget(label(tr('Relatórios públicos complementares da sessão selecionada. '
            'Essas rotas têm acesso próprio e não recebem o Secret da integração.')))
        reportButtons = QHBoxLayout()
        self.reportButtons = []
        for caption, kind in [(tr('Extremos'),'range'),(tr('Condições'),'aggregation'),(tr('Mudanças'),'changes')]:
            button = QPushButton(caption)
            button.clicked.connect(lambda checked=False, report=kind: self._request(report))
            self.reportButtons.append(button)
            reportButtons.addWidget(button)
        sessionLayout.addLayout(reportButtons)
        self.reportTable = grid([tr('Métrica'), tr('Mínimo'), tr('Máximo')])
        self.reportTable.itemDoubleClicked.connect(self._change_detail)
        sessionLayout.addWidget(self.reportTable)
        self.reportText = QPlainTextEdit()
        self.reportText.setReadOnly(True)
        self.reportText.setMaximumHeight(140)
        sessionLayout.addWidget(self.reportText)
        self.resultTabs.addTab(self.sessionPage, tr('Relatórios da sessão'))
        panel.addWidget(self.resultTabs, 1)
        panel.addWidget(label(tr('O total do mapa pode diferir dos indicadores: a exportação exige coordenadas '
            'e as rotas atuais não usam a mesma inclusão do instante final.')))
        self.addButton = QPushButton(tr('Adicionar coletas ao mapa'))
        self.polygonButton = QPushButton(tr('Adicionar limite da geocerca ao mapa'))
        panel.addWidget(self.addButton)
        panel.addWidget(self.polygonButton)
        self.batchButton = QPushButton(tr('Adicionar vários registros…'))
        self.batchButton.clicked.connect(self._choose_batch)
        panel.addWidget(self.batchButton)
        self.replaceButton = QPushButton(tr('Atualizar snapshot da camada selecionada'))
        self.replaceButton.clicked.connect(self._replace)
        panel.addWidget(self.replaceButton)
        panel.removeWidget(self.addButton)
        panel.insertWidget(panel.indexOf(self.consultButton)+1,self.addButton)
        self.pages.addWidget(self.browser)
        self.configPage = QWidget()
        config = QVBoxLayout(self.configPage)
        languageForm = QFormLayout()
        self.languageCombo = QComboBox()
        self.languageCombo.setAccessibleName(tr('Idioma'))
        for caption, code in [(tr('Automático (QGIS)'), ''),
                              ('Português (Brasil)', LANGUAGES[0]),
                              ('English (United States)', LANGUAGES[1]),
                              ('Español (España)', LANGUAGES[2])]:
            self.languageCombo.addItem(caption, code)
        self.languageCombo.setCurrentIndex(max(0, self.languageCombo.findData(
            QgsSettings().value(LANGUAGE_KEY, '', type=str))))
        languageForm.addRow(tr('Idioma'), self.languageCombo)
        self.languagePage = QWidget()
        languageLayout = QVBoxLayout(self.languagePage)
        languageLayout.addWidget(label(tr('Idioma')))
        languageLayout.addLayout(languageForm)
        self.applyLanguageButton = QPushButton(tr('Aplicar idioma'))
        self.applyLanguageButton.clicked.connect(self._change_language)
        languageLayout.addWidget(self.applyLanguageButton)
        languageLayout.addStretch()
        config.addWidget(label(tr('Conexão com a J3M')))
        config.addWidget(label(tr('Informe as credenciais da sua integração. Elas ficam protegidas no cofre de autenticação do QGIS.')))
        fields = QFormLayout()
        self.clientEdit = QLineEdit()
        self.secretEdit = QLineEdit()
        self.secretEdit.setEchoMode(QLineEdit.EchoMode.Password)
        self.secretEdit.setPlaceholderText(tr('Cole o Secret; vazio mantém o que já está salvo'))
        fields.addRow('Client ID', self.clientEdit)
        fields.addRow('Client Secret', self.secretEdit)
        config.addLayout(fields)
        self.showSecret = QCheckBox(tr('Mostrar Secret digitado'))
        self.showSecret.toggled.connect(lambda show: self.secretEdit.setEchoMode(
            QLineEdit.EchoMode.Normal if show else QLineEdit.EchoMode.Password))
        config.addWidget(self.showSecret)
        self.saveButton = QPushButton(tr('Salvar e conectar'))
        self.removeButton = QPushButton(tr('Remover conexão salva'))
        config.addWidget(self.saveButton)
        config.addWidget(self.removeButton)
        config.addStretch()
        self.pages.addWidget(self.configPage)
        self.geofencesPage = GeofencesPage(iface, self)
        self.pages.addWidget(self.geofencesPage)
        self.workbench = Workbench(iface, self)
        self.workbench.snapshotRefreshRequested.connect(self._replace)
        self.pages.addWidget(self.workbench)
        self.sharedMapsPage = SharedMapsPage(iface,self.workbench,self)
        self.pages.addWidget(self.sharedMapsPage)
        self.pages.addWidget(self.languagePage)
        self.pages.removeWidget(self.browser)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.browser)
        self.pages.insertWidget(0, scroll)
        self.statusLabel = label(tr('Configure a conexão para começar.'))
        layout.addWidget(self.statusLabel)
        progressRow = QHBoxLayout()
        self.progressBar = QProgressBar()
        self.progressBar.setVisible(False)
        progressRow.addWidget(self.progressBar, 1)
        self.cancelButton = QPushButton(tr('Cancelar'))
        self.cancelButton.clicked.connect(self._cancel)
        self.cancelButton.setVisible(False)
        progressRow.addWidget(self.cancelButton)
        layout.addLayout(progressRow)
        close = QPushButton(tr('Fechar'))
        close.clicked.connect(self.close)
        layout.addWidget(close)
        self.menu.currentItemChanged.connect(self._navigate)
        self.menu.itemClicked.connect(self._toggle_group)
        self.menu.setExpandsOnDoubleClick(False)
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
        self.layerLoader.busyChanged.connect(self._set_busy)
        self.layerLoader.failed.connect(self._error)
        self.api.busyChanged.connect(self._set_busy)
        self.api.failed.connect(self._error)
        self.api.received.connect(self._received)
        if hasattr(self.api, 'progress'):
            self.api.progress.connect(self._progress)
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        for combo in self.findChildren(QComboBox):
            combo.setMinimumContentsLength(10)
            combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._select_menu('devices' if settings.preferences()[1] else 'connection')
        self.menu.expandAll()
        self._reload_queries()
        QgsProject.instance().readProject.connect(self._project_changed)
        QgsProject.instance().cleared.connect(self._project_changed)

    def showEvent(self, event):
        super().showEvent(event)
        if self.pages.currentWidget() is self.geofencesPage:
            self._loaded = True
            self.geofencesPage.activate()
            return
        if not self._loaded:
            self._loaded = True
            if settings.preferences()[1]:
                try:
                    _, client, _ = settings.credentials()
                    self.clientEdit.setText(client)
                    self._refresh()
                except ValueError as error:
                    self._error(str(error))

    def _select_menu(self, route):
        item = self.menuItems[route]
        self.menu.setCurrentItem(item)

    def _toggle_group(self, item, column):
        if item.childCount():
            item.setExpanded(not item.isExpanded())

    def _navigate(self, item, previous=None):
        route = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if route is None:
            return
        self.layerLoader.cancel()
        self.api.cancel()
        self._batch = []
        self._replace_id = None
        self._deferred_query = None
        self.geofencesPage.cancel()
        self.sharedMapsPage.cancel()
        self.secretEdit.clear()
        self.showSecret.setChecked(False)
        self.pages.setCurrentIndex(1 if route == 'connection' else 2 if route == 'geofences_map' else 3 if route == 'workbench' else 4 if route=='shared_maps' else 5 if route == 'language' else 0)
        self.statusLabel.setVisible(route not in ('geofences_map', 'workbench','shared_maps', 'language'))
        if route=='shared_maps':
            return
        if route == 'workbench':
            self.workbench.refresh()
            return
        if route in ('connection', 'language'):
            return
        if route == 'geofences_map':
            if self._loaded:
                self.geofencesPage.activate()
            return
        self._scope = route
        self.title.setText(tr(TITLES[route]))
        self.periodBox.setVisible(route != 'sessions')
        self.polygonButton.setVisible(self._scope == 'geofences')
        self.resultTabs.setTabEnabled(1, self._scope == 'sessions')
        if self._scope != 'sessions':
            self.resultTabs.setCurrentIndex(0)
        self.search.blockSignals(True)
        self.search.clear()
        self.search.blockSignals(False)
        self._filter()
        if self._loaded and self._scope not in self._cache:
            self._refresh()

    def _change_language(self):
        self._cancel()
        self.geofencesPage.cancel()
        self.sharedMapsPage.cancel()
        self.workbench.cancel_tasks()
        set_language(self.languageCombo.currentData())
        self.statusLabel.setText(tr('Idioma alterado. Feche e abra o painel para aplicar à interface.'))
        self.languageChanged.emit()

    def _save(self):
        try:
            settings.save(self.clientEdit.text(), self.secretEdit.text())
            self.secretEdit.clear()
            self._cache.clear()
            self._metric_units.clear()
            self.geofencesPage.reset()
            self._select_menu(self._scope)
        except ValueError as error:
            self._error(str(error))

    def _remove(self):
        try:
            settings.remove()
            self.clientEdit.clear()
            self.secretEdit.clear()
            self._cache.clear()
            self._metric_units.clear()
            self.geofencesPage.reset()
            self._filter()
            self.statusLabel.setText(tr('Conexão removida. Informe novas credenciais para continuar.'))
        except ValueError as error:
            self._error(str(error))

    def _refresh(self):
        self._cache.pop(self._scope, None)
        self._filter()
        self.statusLabel.setText(tr('Carregando registros…'))
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
        self.layerLoader.cancel()
        self.api.cancel()
        self._period_changed()
        record = self.records.currentData()
        self.details.setText('UUID: ' + record['uuid'] if record else tr('Nenhum registro disponível.'))
        zone = 'UTC' if self._scope == 'geofences' else ((record or {}).get('timezone') or ((record or {}).get('device') or {}).get('timezone'))
        self.timezone.setText(str(zone or tr('Não informado pela API')))
        if zone:
            self._set_zone(zone)
        context = (self._scope,record['uuid']) if record else None
        if context != self._period_record:
            self._period_record = context
            if record and self._scope != 'sessions':
                self._quick_period('today')
        if record:
            device = record.get('device') or record
            details = ['UUID: '+record['uuid']]
            for key, caption in [('type',tr('Tipo')),('mode',tr('Modo')),('battery',tr('Bateria (%)')),
                                 ('lastCollect',tr('Última coleta')),('status',tr('Status')),('validator',tr('Validador'))]:
                if device.get(key) is not None:
                    details.append(caption+': '+value_label(key, device[key]))
            if self._scope == 'sessions':
                details.extend([tr('Período: ')+str(record.get('startDate','—'))+tr(' a ')+str(record.get('endDate','—')),
                                tr('Observação: ')+str(record.get('obs') or '—'),
                                tr('Sessão ao vivo: ')+(tr('Sim (atualização manual)') if record.get('isLive') else tr('Não'))])
            if record.get('description'):
                details.append(str(record['description']))
            self.details.setText('\n'.join(details))
        if record and self._scope == 'clusters':
            self.details.setText(self.details.text() + tr('\nDispositivos: ') + ', '.join(
                str(d.get('name', d.get('uuid', ''))) for d in record.get('devices', []) if isinstance(d, dict)))
        self._set_busy(False)
        if record and self._scope == 'sessions':
            self._consult()

    def _period_changed(self):
        if hasattr(self, 'cards'):
            while self.cards.count():
                item = self.cards.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        self.table.setRowCount(0)
        self.summary.setText(tr('Consulte os indicadores para o registro e período selecionados.'))
        self.statusLabel.setText(tr('Pronto para consultar.'))
        if hasattr(self, 'reportTable'):
            self.reportTable.setRowCount(0)
            self.reportText.clear()
            self._changes = []
        if hasattr(self, 'utcLabel'):
            zone = QTimeZone(self._zone.encode('utf-8'))
            times = [QDateTime(edit.date(), edit.time(), zone).toUTC().toString('yyyy-MM-dd HH:mm:ss') for edit in (self.start,self.end)]
            self.utcLabel.setText(' → '.join(times)+' UTC')

    def _request(self, kind):
        record = self.records.currentData()
        if not record:
            return
        period = None
        if self._scope != 'sessions':
            if self.end.dateTime() <= self.start.dateTime():
                self._error(tr('A data final deve ser posterior à data inicial.'))
                return
            if self._scope in ('devices', 'clusters') and not record.get('timezone'):
                self._error(tr('O recurso não informa seu fuso horário. Atualize o catálogo antes de consultar.'))
                return
            if not QTimeZone(self._zone.encode('utf-8')).isValid() or (
                    self._scope in ('devices','clusters') and not QTimeZone(str(record.get('timezone','')).encode('utf-8')).isValid()):
                self._error(tr('O recurso informa um fuso inválido. Atualize o catálogo.'))
                return
            period = tuple(edit.dateTime().toString('yyyy-MM-dd HH:mm:ss') for edit in (self.start, self.end))
        if kind in ('range','aggregation','changes') and (self._scope != 'sessions' or
                not any(r['uuid']==record['uuid'] for r in self._cache.get('sessions',[]))):
            self._error(tr('Escolha uma sessão do catálogo autorizado.'))
            return
        self._pending_query = (self._scope, dict(record), period)
        self.statusLabel.setText(tr('Consultando ') + {'indicators': tr('indicadores'), 'table': tr('mínimos e máximos'), 'collections': tr('coletas'),
            'range':tr('extremos da sessão'),'aggregation':tr('condições da sessão'),'changes':tr('mudanças da sessão')}[kind] + '…')
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
        for button in self.reportButtons:
            button.setEnabled(not busy and selected and self._scope == 'sessions')
        self.batchButton.setEnabled(not busy and bool(self._cache.get(self._scope)))
        self.replaceButton.setEnabled(not busy)
        self.savedQueries.setEnabled(not busy)
        self.progressBar.setVisible(busy)
        self.progressBar.setRange(0, 0)
        self.cancelButton.setVisible(busy)

    def _error(self, message):
        self._batch = []
        self._replace_id = None
        self.statusLabel.setText(message)
        self.workbench.message.setText(message)

    def _received(self, kind, payload):
        try:
            if kind == 'catalog':
                self._cache[self._scope] = catalog_records(payload)
                self._filter()
                query = getattr(self, '_deferred_query', None)
                if query and query.get('scope') == self._scope:
                    self._deferred_query = None
                    if not self._apply_query(query):
                        self.statusLabel.setText(tr('A consulta salva não está disponível no catálogo autorizado.'))
                if not self._busy:
                    self.statusLabel.setText(tr('{} registro(s) disponível(is).').format(self.records.count()))
            elif kind == 'indicators':
                summary, rows = indicator_rows(payload)
                self.summary.setText(summary)
                condition = (_response_data(payload) or {}).get('condition') or {}
                self.summary.setToolTip(str(condition.get('description','')) if isinstance(condition,dict) else '')
                self.table.setRowCount(len(rows))
                record = self.records.currentData()
                if record:
                    self._metric_units[(self._scope,record['uuid'])] = {v[0]:v[2] for v in rows}
                if self._pending_query:
                    scope, source, period = self._pending_query
                    self._indicator_counts[(scope, source['uuid'], tuple(period or []))] = (_response_data(payload) or {}).get('totalCollects')
                from .analysis import display
                for index, values in enumerate(rows[:4]):
                    card = label(tr(LABELS.get(values[0],str(values[0])))+'\n'+display(values[1])+' '+str(values[2]))
                    card.setStyleSheet('font-size: 13px; font-weight: 600; padding: 10px; border: 1px solid palette(mid); '
                                      'border-left: 4px solid '+COLORS.get(values[3],'#808080')+'; border-radius: 5px;')
                    card.setAccessibleName(tr(LABELS.get(values[0], str(values[0])))+tr(' média ')+display(values[1]))
                    self.cards.addWidget(card,index//2,index%2)
                for row, values in enumerate(rows):
                    for col, value in enumerate(values[:3]):
                        item = QTableWidgetItem(tr(LABELS.get(str(value), str(value))) if col == 0 else str(value))
                        if col == 0:
                            item.setData(Qt.ItemDataRole.UserRole, str(value))
                        if col == 1 and values[3] in COLORS:
                            item.setForeground(QColor(COLORS[values[3]]))
                        self.table.setItem(row, col, item)
                self.statusLabel.setText(tr('Indicadores atualizados.'))
                if self._scope == 'geofences':
                    self._request('table')
            elif kind == 'table':
                rows = _response_data(payload) or []
                if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                    raise ValueError(tr('Tabela de geocerca inválida.'))
                for entry in rows:
                    metric = str(entry.get('metric', '—'))
                    row = next((r for r in range(self.table.rowCount())
                                if self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) == metric), self.table.rowCount())
                    if row == self.table.rowCount():
                        self.table.insertRow(row)
                        item = QTableWidgetItem(tr(LABELS.get(metric, metric)))
                        item.setData(Qt.ItemDataRole.UserRole, metric)
                        self.table.setItem(row, 0, item)
                        self.table.setItem(row, 2, QTableWidgetItem(str(entry.get('unit', ''))))
                    for col, key in ((3, 'min'), (4, 'max')):
                        self.table.setItem(row, col, QTableWidgetItem(str(entry.get(key, '—'))))
                self.statusLabel.setText(tr('Indicadores e mínimos/máximos atualizados.') if rows else tr('Sem mínimos/máximos disponíveis no período.'))
            elif kind == 'collections':
                self._add_layer(payload)
            elif kind in ('range','aggregation','changes','change_detail'):
                self._report(kind, payload)
        except (ValueError, OSError, RecursionError, TypeError, KeyError) as error:
            self._error(str(error))

    def _add_layer(self, payload, polygon=False):
        if payload is None:
            self._replace_id = None
            self.statusLabel.setText(tr('Nenhuma coleta disponível no período.'))
            if self._batch:
                QTimer.singleShot(0, self._next_batch)
            return
        scope, record, period = self._pending_query or (self._scope, self.records.currentData(), None)
        name = 'J3M — ' + record.get('name', self.records.currentText())
        if not polygon:
            dates = period or [record.get('startDate'), record.get('endDate')]
            name += ' — ' + tr(' a ').join(str(value or '—') for value in dates)
        def finish(layer, digest):
            if layer is None:
                self._replace_id = None
                self.statusLabel.setText(tr('Nenhuma coleta com coordenadas disponível.'))
                if self._batch:
                    QTimer.singleShot(0, self._next_batch)
                return
            if polygon:
                from qgis.core import QgsFillSymbol
                color = QColor(self.records.currentData().get('color') or '#16a34a')
                if not color.isValid():
                    color = QColor('#16a34a')
                layer.renderer().setSymbol(QgsFillSymbol.createSimple({
                    'color': '{},{},{},64'.format(color.red(), color.green(), color.blue()),
                    'outline_color': color.name(), 'outline_width': '0.5'}))
                layer.triggerRepaint()
            else:
                units = {entry['metric']: entry.get('unit','') for entry in
                    (record.get('metrics') or (record.get('device') or {}).get('metrics') or [])
                    if isinstance(entry,dict) and entry.get('metric')}
                units.update(self._metric_units.get((scope,record['uuid']),{}))
                origin = provenance(scope,record,period,digest=digest)
                origin['api_total'] = self._indicator_counts.get((scope,record['uuid'],tuple(period or [])))
                configure_layer(layer,origin,units)
                if self._replace_id:
                    previous = QgsProject.instance().mapLayer(self._replace_id)
                    self._replace_id = None
                    if previous and not previous.isEditable():
                        style = QgsMapLayerStyle()
                        style.readFromLayer(previous)
                        previous.setDataSource(layer.source(),previous.name(),'ogr')
                        previous.setCustomProperty('j3m/categories',layer.customProperty('j3m/categories',''))
                        style.writeToLayer(previous)
                        configure_layer(previous,origin,units,preserve_style=True)
                        QgsProject.instance().removeMapLayer(layer.id())
                        layer = previous
                self.workbench.focus_layer(layer)
            self.iface.setActiveLayer(layer)
            self.iface.actionMapTips().setChecked(True)
            self.statusLabel.setText(tr('Camada adicionada ao mapa e salva no perfil QGIS.'))
            if self._batch:
                QTimer.singleShot(0, self._next_batch)
        self.statusLabel.setText(tr('Preparando a camada em segundo plano…'))
        self.layerLoader.load(payload,name,finish,geofence=polygon)

    def _polygon(self):
        try:
            self._pending_query = (self._scope, self.records.currentData(), None)
            self._add_layer(geofence_geojson(self.records.currentData()), polygon=True)
        except (ValueError, OSError, RecursionError) as error:
            self._error(str(error))

    def closeEvent(self, event):
        self._cancel()
        self.workbench.cancel_tasks()
        self.geofencesPage.cancel()
        self.sharedMapsPage.cancel()
        self.secretEdit.clear()
        QgsSettings().setValue('J3MConnect/dockGeometry',self.saveGeometry())
        QgsSettings().setValue('J3MConnect/floating',self.isFloating())
        QgsSettings().setValue('J3MConnect/navigation',self.navigationButton.isChecked())
        super().closeEvent(event)

    def dispose(self):
        self._cancel()
        self.geofencesPage.cancel()
        self.sharedMapsPage.cancel()
        self.workbench.dispose()
        QgsProject.instance().readProject.disconnect(self._project_changed)
        QgsProject.instance().cleared.disconnect(self._project_changed)

    def _cancel(self):
        self._batch = []
        self._replace_id = None
        self.layerLoader.cancel()
        self.api.cancel()
        self.statusLabel.setText(tr('Operação cancelada. As camadas concluídas foram preservadas.'))

    def _progress(self, done, total):
        if total > 0:
            self.progressBar.setRange(0,100)
            self.progressBar.setValue(int(done*100/total))
        self.statusLabel.setText(tr('Recebendo {:.1f} MB…').format(done/1024/1024))

    def _set_zone(self, name):
        zone, old = QTimeZone(str(name).encode('utf-8')), QTimeZone(self._zone.encode('utf-8'))
        if not zone.isValid():
            self.timezone.setText(str(name)+tr(' (fuso inválido)'))
            return
        if name != self._zone:
            for edit in (self.start,self.end):
                instant = QDateTime(edit.date(),edit.time(),old).toTimeZone(zone)
                edit.blockSignals(True)
                edit.setDateTime(QDateTime(instant.date(),instant.time(),Qt.TimeSpec.UTC))
                edit.blockSignals(False)
        self._zone = name
        self._period_changed()

    def _quick_period(self, preset):
        zone = QTimeZone(self._zone.encode('utf-8'))
        now = QDateTime.currentDateTimeUtc().toTimeZone(zone)
        from qgis.PyQt.QtCore import QTime
        if preset in ('today','yesterday'):
            date = now.date().addDays(-1 if preset=='yesterday' else 0)
            start = QDateTime(date,QTime(0,0),zone)
            end = QDateTime(date,QTime(23,59,59),zone)
        else:
            start, end = now.addDays(-7 if preset=='week' else -1), now
        self.start.setDateTime(QDateTime(start.date(),start.time(),Qt.TimeSpec.UTC))
        self.end.setDateTime(QDateTime(end.date(),end.time(),Qt.TimeSpec.UTC))

    def _project_changed(self, *args):
        self._cancel()
        self._reload_queries()
        self.workbench.refresh()

    def _queries(self):
        raw = QgsProject.instance().readEntry('J3MConnect','queries','[]')[0]
        try:
            result = json.loads(raw)
            return result if isinstance(result,list) else []
        except ValueError:
            return []

    def _reload_queries(self):
        self.savedQueries.clear()
        for query in self._queries():
            if isinstance(query,dict) and query.get('name'):
                self.savedQueries.addItem(str(query['name']),query)

    def _save_query(self):
        record = self.records.currentData()
        if not record or self._busy:
            return
        prompt = QInputDialog(self)
        prompt.setWindowTitle(tr('Salvar consulta'))
        prompt.setLabelText(tr('Nome'))
        prompt.setTextValue(record['name'])
        prompt.setOkButtonText(tr('Salvar consulta'))
        prompt.setCancelButtonText(tr('Cancelar'))
        ok = prompt.exec() == QDialog.DialogCode.Accepted
        name = prompt.textValue()
        prompt.deleteLater()
        if not ok or not name.strip():
            return
        queries = [q for q in self._queries() if q.get('name')!=name.strip()]
        queries.append({'name':name.strip(),'scope':self._scope,'uuid':record['uuid'],
                        'start':self.start.dateTime().toString('yyyy-MM-dd HH:mm:ss'),
                        'end':self.end.dateTime().toString('yyyy-MM-dd HH:mm:ss'),'timezone':self._zone})
        QgsProject.instance().writeEntry('J3MConnect','queries',json.dumps(queries,ensure_ascii=False))
        self._reload_queries()
        self.statusLabel.setText(tr('Consulta guardada no projeto. Salve o projeto QGIS para persistir.'))

    def _remove_query(self):
        current = self.savedQueries.currentData()
        if current:
            QgsProject.instance().writeEntry('J3MConnect','queries',json.dumps([q for q in self._queries() if q!=current],ensure_ascii=False))
            self._reload_queries()

    def _load_query(self):
        query = self.savedQueries.currentData()
        if not query or self._busy or query.get('scope') not in TITLES:
            return
        self._select_menu(query['scope'])
        self.layerLoader.cancel()
        self.api.cancel()
        if not self._apply_query(query):
            self._deferred_query = query
            self._refresh()

    def _apply_query(self, query):
        for index in range(self.records.count()):
            if self.records.itemData(index)['uuid']==query.get('uuid'):
                self.records.setCurrentIndex(index)
                for edit,key in ((self.start,'start'),(self.end,'end')):
                    dt = QDateTime.fromString(str(query.get(key,'')),'yyyy-MM-dd HH:mm:ss')
                    if dt.isValid():
                        source = QTimeZone(str(query.get('timezone','UTC')).encode('utf-8'))
                        target = QTimeZone(self._zone.encode('utf-8'))
                        if not source.isValid() or not target.isValid():
                            return False
                        dt = QDateTime(dt.date(),dt.time(),source).toTimeZone(target)
                        edit.setDateTime(QDateTime(dt.date(),dt.time(),Qt.TimeSpec.UTC))
                return True
        return False

    def _choose_batch(self):
        dialog = QDialog(self)
        dialog.setWindowTitle(tr('Adicionar registros do catálogo autorizado'))
        layout = QVBoxLayout(dialog)
        layout.addWidget(label(tr('Dispositivos, clusters e geocercas usam o período digitado no fuso de cada recurso. '
                              'Sessões usam seu próprio intervalo. Cada consulta cria uma camada.')))
        records = QListWidget()
        for record in self._cache.get(self._scope,[]):
            item = QListWidgetItem(record['name'])
            item.setData(Qt.ItemDataRole.UserRole, record)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            records.addItem(item)
        layout.addWidget(records)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr('Adicionar coletas ao mapa'))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr('Cancelar'))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        execute = getattr(dialog,'exec',None) or dialog.exec_
        if execute() == QDialog.DialogCode.Accepted:
            self._batch = [records.item(i).data(Qt.ItemDataRole.UserRole) for i in range(records.count())
                           if records.item(i).checkState()==Qt.CheckState.Checked]
            self._next_batch()

    def _next_batch(self):
        if not self._batch:
            return
        record = self._batch.pop(0)
        if self._scope in ('devices','clusters') and not QTimeZone(str(record.get('timezone','')).encode('utf-8')).isValid():
            self._error(tr('O registro ')+record['name']+tr(' não possui fuso válido. Lote interrompido.'))
            return
        if self._scope != 'sessions' and self.end.dateTime()<=self.start.dateTime():
            self._error(tr('Informe fim posterior ao início.'))
            return
        period = None if self._scope=='sessions' else tuple(edit.dateTime().toString('yyyy-MM-dd HH:mm:ss') for edit in (self.start,self.end))
        self._pending_query = (self._scope,dict(record),period)
        self.statusLabel.setText(tr('Carregando ')+record['name']+'; '+str(len(self._batch))+tr(' restantes.'))
        self.api.get('collections',record['uuid'],scope=self._scope,period=period)

    def _replace(self):
        layer = self.workbench.current_layer()
        if not layer or self._busy:
            self._error(tr('Escolha uma camada em Análise → Camadas e estudos.'))
            return
        if layer.isEditable():
            self._error(tr('Encerre a edição da camada antes de atualizar o snapshot.'))
            return
        try:
            origin = json.loads(layer.customProperty('j3m/origin','{}'))
            scope = origin['scope']
            if scope not in TITLES or not origin.get('uuid'):
                raise ValueError(tr('Esta camada não possui consulta de integração registrada. Recarregue pela origem correspondente.'))
            record = next((r for r in self._cache.get(scope,[]) if r['uuid']==origin['uuid']),None)
            if not record:
                raise ValueError(tr('Atualize o catálogo original antes de atualizar esta camada.'))
            self._replace_id = layer.id()
            period = None if scope=='sessions' else origin['period']
            self._pending_query = (scope,record,period)
            self.workbench.message.setText(tr('Atualizando o snapshot pela consulta original…'))
            self.api.get('collections',record['uuid'],scope=scope,period=period)
        except (ValueError,KeyError,TypeError) as error:
            self._error(str(error))

    def _report(self, kind, payload):
        data = _response_data(payload)
        self.resultTabs.setCurrentIndex(1)
        self._changes = []
        if data is None:
            self.reportTable.setRowCount(0)
            self.reportText.setPlainText(tr('Nenhum dado disponível neste relatório.'))
            return
        if kind in ('range','aggregation') and (not isinstance(data,list) or any(not isinstance(v,dict) for v in data)):
            raise ValueError(tr('Formato de relatório inválido: esperada uma lista.'))
        if kind in ('changes','change_detail') and not isinstance(data,dict):
            raise ValueError(tr('Formato de relatório inválido: esperado um objeto.'))
        if kind == 'range':
            headers = [tr('Métrica'),tr('Mínimo'),tr('Máximo'),tr('Instante mínimo'),tr('Instante máximo')]
            rows = [[tr(LABELS.get(str(v.get('metric','—')), str(v.get('metric','—'))))] +
                    [v.get(k,'—') for k in ('min','max','minDate','maxDate')] for v in data]
        elif kind == 'aggregation':
            headers = [tr('Condição'),tr('Registros')]
            rows = [[v.get('id',v.get('_id','—')),v.get('count','—')] for v in data]
        elif kind == 'changes':
            headers = [tr('Métrica'),tr('Direção'),tr('Antes'),tr('Depois'),tr('Delta'),tr('Início UTC'),tr('Fim UTC')]
            self._changes = data.get('changes',[])
            rows = [[tr(LABELS.get(str(v.get('metric','—')), str(v.get('metric','—')))),
                     value_label('direction', v.get('direction','—'))] +
                    [v.get(k,'—') for k in ('before','after','delta','startedAt','endedAt')] for v in self._changes]
        else:
            headers = [tr('Instante UTC'),tr('Valor')]
            rows = [[v.get('timestamp'),v.get('value')] for v in data.get('series',[])]
        self.reportTable.setColumnCount(len(headers))
        self.reportTable.setHorizontalHeaderLabels(headers)
        fill(self.reportTable,rows)
        self.reportText.setPlainText((tr('Duplo clique em uma mudança para consultar o detalhe.\n') if kind=='changes' else '')+
            json.dumps(data if kind=='change_detail' else {'relatorio':kind,'linhas':len(rows)},ensure_ascii=False,indent=2))
        self.statusLabel.setText(tr('Relatório complementar recebido.'))

    def _change_detail(self, item):
        if self._busy or not 0<=item.row()<len(getattr(self,'_changes',[])):
            return
        change = self._changes[item.row()]
        record = self.records.currentData()
        zone = QTimeZone(((record.get('device') or {}).get('timezone') or self._zone).encode('utf-8'))
        params = {'metric':change['metric']}
        for key,source in (('start_date','startedAt'),('end_date','endedAt')):
            dt = QDateTime.fromString(change[source],Qt.DateFormat.ISODate).toTimeZone(zone)
            if not dt.isValid():
                self._error(tr('O evento possui um instante inválido.'))
                return
            params[key] = dt.toString('yyyy-MM-dd HH:mm:ss')
        self.api.get('change_detail',record['uuid'],scope='sessions',params=params)
