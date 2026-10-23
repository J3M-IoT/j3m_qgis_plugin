# SPDX-License-Identifier: GPL-3.0-or-later
"""Map-oriented workbench using existing, downloaded J3M observations."""
from .i18n import tr
from .i18n import value_label
import json
from pathlib import Path
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QPushButton,
    QTabWidget, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QCheckBox, QDoubleSpinBox, QFormLayout, QFileDialog, QPlainTextEdit, QSizePolicy, QProgressBar,
)
from qgis.core import QgsProject, QgsVectorLayer, QgsVectorLayerFeatureSource, QgsApplication, QgsTask
from .analysis import summarize, layer_payload, display
from .cartography import style_metric, export_options, export_sidecars, portable_study, report_pdf, copy_original
from .charts import SeriesChart
from .map_tips import LABELS, UNITS


def text(value=''):
    label = QLabel(value)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    label.setSizePolicy(QSizePolicy.Policy.Preferred,QSizePolicy.Policy.Maximum)
    return label


def grid(headers):
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
    table.horizontalHeader().setStretchLastSection(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    return table


def fill(table, rows):
    table.setSortingEnabled(False)
    table.setRowCount(len(rows))
    for row, values in enumerate(rows):
        for col, value in enumerate(values):
            table.setItem(row, col, QTableWidgetItem(str(value) if value is not None else '—'))


class Workbench(QWidget):
    snapshotRefreshRequested = pyqtSignal()

    def __init__(self, iface, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.payload = None
        self.summary = None
        self.fids = []
        self._connected_layer = None
        self._disposed = False
        self._tasks = []
        self._generation = 0
        self._render_jobs = []
        self._analysis_task = None
        layout = QVBoxLayout(self)
        layout.addWidget(text(tr('Camadas do projeto • disponíveis também offline')))
        row = QHBoxLayout()
        self.layers = QComboBox()
        self.layers.setMinimumContentsLength(15)
        self.layers.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        row.addWidget(self.layers, 1)
        refresh = QPushButton(tr('Atualizar lista'))
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        layout.addLayout(row)
        actions = QHBoxLayout()
        adopt = QPushButton(tr('Analisar camada ativa'))
        adopt.clicked.connect(self.adopt_active)
        actions.addWidget(adopt)
        update = QPushButton(tr('Atualizar snapshot'))
        update.clicked.connect(lambda checked=False:self.snapshotRefreshRequested.emit())
        actions.addWidget(update)
        layout.addLayout(actions)
        self.tabs = QTabWidget()
        self.tabs.setUsesScrollButtons(True)
        layout.addWidget(self.tabs)

        visual = QWidget()
        form = QFormLayout(visual)
        self.metric = QComboBox()
        self.metric.setAccessibleName(tr('Métrica do mapa e dos gráficos'))
        form.addRow(tr('Variável'), self.metric)
        self.fixed = QCheckBox(tr('Fixar escala para comparar campanhas'))
        form.addRow(self.fixed)
        limits = QHBoxLayout()
        self.minimum, self.maximum = QDoubleSpinBox(), QDoubleSpinBox()
        for spin in (self.minimum, self.maximum):
            spin.setRange(-1e12, 1e12)
            spin.setDecimals(4)
            limits.addWidget(spin)
        self.minimum.setAccessibleName(tr('Mínimo da escala'))
        self.maximum.setAccessibleName(tr('Máximo da escala'))
        form.addRow(tr('Mínimo / máximo'), limits)
        self.size = QDoubleSpinBox()
        self.size.setRange(.5, 12)
        self.size.setValue(3)
        self.size.setSuffix(' mm')
        form.addRow(tr('Tamanho do ponto'), self.size)
        apply = QPushButton(tr('Aplicar ao mapa'))
        apply.clicked.connect(self.apply_style)
        form.addRow(apply)
        zoom = QPushButton(tr('Aproximar à camada'))
        zoom.clicked.connect(self.zoom)
        form.addRow(zoom)
        self.legend = text(tr('Condição J3M: cor original da API. Escolha uma variável para uma escala numérica.'))
        form.addRow(self.legend)
        form.addRow(text(tr('A camada já está preparada para o Controlador Temporal do QGIS. '
                         'Pontos são observações instantâneas; não são uma superfície interpolada.')))
        self.tabs.addTab(visual, tr('Mapa'))

        temporal = QWidget()
        time_layout = QVBoxLayout(temporal)
        self.chart = SeriesChart()
        self.chart.observationSelected.connect(self.select_observation)
        time_layout.addWidget(self.chart, 1)
        time_layout.addWidget(text(tr('UTC • séries separadas por dispositivo. Quebras acima de 3× o intervalo mediano. '
                                  'Clique no gráfico ou selecione uma linha abaixo para destacar no mapa.')))
        self.observations = grid([tr('Instante UTC'), tr('Dispositivo'), tr('Valor')])
        self.observations.setMaximumHeight(210)
        self.observations.itemSelectionChanged.connect(self._observation_row)
        time_layout.addWidget(self.observations)
        self.tabs.addTab(temporal, tr('Série'))

        stats = QWidget()
        sl = QVBoxLayout(stats)
        self.statistics = grid([tr('Métrica'), tr('Unidade'), tr('n válido'), tr('Mín.'), tr('Média'), tr('Mediana'), tr('Máx.'), tr('Desvio')])
        sl.addWidget(self.statistics)
        self.quality = text()
        sl.addWidget(self.quality)
        sl.addWidget(text(tr('Resumo local de registros baixados. Não é média ponderada por tempo ou sensor. '
                         'Amostras sem GPS excluídas pelo servidor não podem ser auditadas nesta camada.')))
        self.tabs.addTab(stats, tr('Qualidade'))

        distributions = QWidget()
        dl = QVBoxLayout(distributions)
        self.category = QComboBox()
        for caption, key in [(tr('Condição'), 'condition'), (tr('Dia/noite'), 'timePeriod'), (tr('Modo'), 'mode'), (tr('Dispositivo'), 'device')]:
            self.category.addItem(caption, key)
        dl.addWidget(self.category)
        self.distribution = grid([tr('Categoria'), tr('Registros'), tr('% de registros')])
        dl.addWidget(self.distribution)
        dl.addWidget(text(tr('Percentuais por registro; não representam tempo de exposição.')))
        self.category.currentIndexChanged.connect(self._distribution)
        self.tabs.addTab(distributions, tr('Distribuição'))

        comparison = QWidget()
        cl = QVBoxLayout(comparison)
        cl.addWidget(text(tr('A = camada acima. B = camada abaixo. Comparação descritiva, sem pareamento temporal/espacial.')))
        self.other = QComboBox()
        cl.addWidget(self.other)
        compare = QPushButton(tr('Comparar A e B'))
        compare.clicked.connect(self.compare)
        cl.addWidget(compare)
        self.comparison = grid([tr('Métrica / unidade'), 'n A', tr('Média A'), 'n B', tr('Média B'), 'B − A'])
        cl.addWidget(self.comparison)
        self.comparisonInfo = text()
        cl.addWidget(self.comparisonInfo)
        self.tabs.addTab(comparison, tr('Comparar'))

        inspection = QWidget()
        il = QVBoxLayout(inspection)
        il.addWidget(text(tr('Selecione um ponto no QGIS ou no gráfico. Os dados originais permanecem na camada.')))
        self.inspector = QPlainTextEdit()
        self.inspector.setReadOnly(True)
        il.addWidget(self.inspector)
        copy = QPushButton(tr('Copiar informação selecionada'))
        copy.clicked.connect(lambda: self.inspector.selectAll() or self.inspector.copy())
        il.addWidget(copy)
        self.tabs.addTab(inspection, tr('Inspecionar'))

        output = QWidget()
        ol = QVBoxLayout(output)
        self.origin = QPlainTextEdit()
        self.origin.setReadOnly(True)
        self.origin.setMaximumHeight(180)
        ol.addWidget(self.origin)
        for caption, driver in [(tr('Exportar GeoPackage'), 'GPKG'), (tr('Exportar CSV'), 'CSV'), (tr('Exportar GeoJSON'), 'GeoJSON'), (tr('Exportar KML'), 'KML')]:
            button = QPushButton(caption)
            button.clicked.connect(lambda checked=False, d=driver: self.export(d))
            ol.addWidget(button)
        bundle = QPushButton(tr('Salvar estudo portátil\nQGIS + GeoPackage + estilo'))
        bundle.clicked.connect(self.bundle)
        ol.addWidget(bundle)
        pdf = QPushButton(tr('Gerar PDF da camada'))
        pdf.clicked.connect(self.pdf)
        ol.addWidget(pdf)
        self.tabs.addTab(output, tr('Exportar'))
        self.message = text(tr('Adicione coletas para analisar.'))
        layout.addWidget(self.message)
        self.layers.currentIndexChanged.connect(self._load)
        self.metric.currentIndexChanged.connect(self._metric_changed)
        project = QgsProject.instance()
        project.layersAdded.connect(self.refresh)
        project.layersRemoved.connect(self.refresh)
        self.refresh()

    def current_layer(self):
        layer = QgsProject.instance().mapLayer(self.layers.currentData())
        return layer if isinstance(layer, QgsVectorLayer) and layer.isValid() else None

    def adopt_active(self):
        layer = self.iface.activeLayer()
        if not isinstance(layer,QgsVectorLayer) or layer.fields().indexFromName('collectedAt') < 0 or not any(
                field.name().startswith('collects_') for field in layer.fields()):
            self.message.setText(tr('Selecione uma camada J3M com collectedAt e campos collects_ no QGIS.'))
            return
        if not layer.customProperty('j3m/origin',''):
            from .cartography import configure_layer
            configure_layer(layer,{'scope':'local','name':layer.name(),
                'note':tr('Camada preexistente. Consulta, período e hash de download não registrados; não é possível atualizar automaticamente.')},preserve_style=True)
        self.focus_layer(layer)

    def refresh(self, *args):
        current, other = self.layers.currentData(), self.other.currentData()
        available = [layer for layer in QgsProject.instance().mapLayers().values()
                     if isinstance(layer, QgsVectorLayer) and layer.customProperty('j3m/origin', '')]
        for combo, identifier in ((self.layers,current),(self.other,other)):
            combo.blockSignals(True)
            combo.clear()
            for layer in available:
                combo.addItem(layer.name(),layer.id())
            index = combo.findData(identifier)
            if index >= 0:
                combo.setCurrentIndex(index)
            combo.blockSignals(False)
        self._load()

    def focus_layer(self, layer):
        self.refresh()
        self.layers.setCurrentIndex(self.layers.findData(layer.id()))

    def _disconnect_layer(self):
        if self._connected_layer is not None:
            try:
                self._connected_layer.selectionChanged.disconnect(self._inspect)
            except (RuntimeError, TypeError):
                pass
        self._connected_layer = None

    def dispose(self):
        if self._disposed:
            return
        self._disposed = True
        self.cancel_tasks()
        self._disconnect_layer()
        QgsProject.instance().layersAdded.disconnect(self.refresh)
        QgsProject.instance().layersRemoved.disconnect(self.refresh)

    def cancel_tasks(self):
        self._generation += 1
        for task in tuple(self._tasks):
            task.cancel()
        for job in tuple(self._render_jobs):
            job.setProperty('j3mCanceled', True)
            job.cancelWithoutBlocking()

    def _analyze(self, layer, callback):
        # Capture the provider snapshot on the main thread. Workers never access
        # QgsProject, a live layer, or widgets.
        source = QgsVectorLayerFeatureSource(layer)
        context = QgsProject.instance().transformContext()
        generation = self._generation
        def run(task):
            fids = []
            payload = layer_payload(source, context, task.isCanceled, fids)
            if payload is None or task.isCanceled():
                return None
            summary = summarize(payload,task.isCanceled)
            return None if summary is None or task.isCanceled() else (payload,summary,fids)
        def finished(error, result=None):
            if task in self._tasks:
                self._tasks.remove(task)
            if self._analysis_task is task:
                self._analysis_task = None
            if self._disposed or generation != self._generation:
                return
            if error:
                self.message.setText(tr('Falha na análise local: ')+str(error))
            elif result is not None:
                callback(result)
            else:
                self.message.setText(tr('Análise cancelada. Atualize a lista para tentar novamente.'))
        task = QgsTask.fromFunction(tr('J3M: analisar observações'), run, on_finished=finished)
        if self._analysis_task is not None:
            self._analysis_task.cancel()
        self._analysis_task = task
        task.setDependentLayers([layer])
        self._tasks.append(task)
        self.message.setText(tr('Analisando em segundo plano; cancelamento disponível nas tarefas do QGIS.'))
        QgsApplication.taskManager().addTask(task)

    def _load(self, prepared=None):
        self._generation += 1
        self._disconnect_layer()
        layer = self.current_layer()
        self.payload = self.summary = None
        self.chart.selected = set()
        self.metric.blockSignals(True)
        previous = self.metric.currentData()
        self.metric.clear()
        self.metric.addItem(tr('Condição J3M (original)'), '')
        self.inspector.clear()
        self.origin.clear()
        self.quality.clear()
        for t in (self.statistics, self.comparison, self.observations, self.distribution):
            t.setRowCount(0)
        if layer and not isinstance(prepared, tuple) and layer.featureCount() > 1000:
            self.metric.blockSignals(False)
            self.tabs.setEnabled(False)
            self._metric_changed()
            self._analyze(layer, lambda result: self._load(prepared=result))
            return
        if layer:
            try:
                if isinstance(prepared, tuple):
                    self.payload, self.summary, self.fids = prepared
                else:
                    self.fids = []
                    self.payload = layer_payload(layer, fids=self.fids)
                    self.summary = summarize(self.payload)
                self.units = json.loads(layer.customProperty('j3m/units', '{}'))
                for metric in self.summary['stats']:
                    self.metric.addItem(tr(LABELS.get(metric, metric)) + ' ' + self.unit(metric), metric)
                self.origin.setPlainText(str(layer.customProperty('j3m/origin', '{}')))
                origin = json.loads(layer.customProperty('j3m/origin', '{}'))
                self.quality.setText(tr('{count} registros · {invalid_geometry} geometrias não pontuais/inválidas · '
                    '{invalid_time} datas sem fuso/inválidas · {duplicates} IDs repetidos · {missing_ids} sem ID.').format(**self.summary))
                if origin.get('api_total') is not None:
                    self.quality.setText(self.quality.text()+tr('\nTotal consultado nos indicadores da API: ')+str(origin['api_total'])+
                        tr('. As bases podem diferir por GPS, bordas temporais ou atualização da origem.'))
                fill(self.statistics, [[tr(LABELS.get(k,k)),self.unit(k),s['n'],display(s['min']),display(s['mean']),
                    display(s['median']),display(s['max']),display(s['std'])] for k,s in self.summary['stats'].items()])
                layer.selectionChanged.connect(self._inspect)
                self._connected_layer = layer
                self.message.setText(tr('Snapshot local; atualize pela consulta original quando necessário.'))
            except (ValueError, TypeError, RuntimeError) as error:
                self.message.setText(tr('Não foi possível analisar a camada: ')+str(error))
        index = self.metric.findData(previous)
        if index >= 0:
            self.metric.setCurrentIndex(index)
        self.metric.blockSignals(False)
        self.tabs.setEnabled(layer is not None and self.summary is not None)
        self._metric_changed()
        self._distribution()

    def unit(self, metric):
        supplied = (self.summary or {}).get('units', {}).get(metric, set())
        if len(supplied) > 1:
            return tr('Unidades conflitantes')
        return next(iter(supplied)) if supplied else self.units.get(metric, UNITS.get(metric, ''))

    def _metric_changed(self):
        metric = self.metric.currentData()
        points = (self.summary or {}).get('series', {}).get(metric, [])
        self.chart.set_series(points, (tr(LABELS.get(metric,metric or ''))+' '+self.unit(metric)) if metric and self.summary else '',
                              (self.summary or {}).get('plots',{}).get(metric))
        from datetime import datetime, timezone
        self._series_rows = points[:2000]
        fill(self.observations, [[datetime.fromtimestamp(p[0],timezone.utc).strftime('%d/%m/%Y %H:%M:%S'),p[3],display(p[1])]
                                for p in self._series_rows])
        self.observations.setToolTip(tr('Tabela: até 2.000 observações. Exportações e estatísticas incluem todas.'))
        if metric and self.summary and not self.fixed.isChecked():
            s = self.summary['stats'][metric]
            self.minimum.setValue(s['min'] or 0)
            self.maximum.setValue(s['max'] or 0)

    def _distribution(self):
        counts = (self.summary or {}).get('distributions', {}).get(self.category.currentData(), {})
        total = sum(counts.values()) or 1
        field = self.category.currentData()
        fill(self.distribution, [[value_label(field,key),n,display(n*100/total)] for key,n in sorted(counts.items())])
        for row, (key,n) in enumerate(sorted(counts.items())):
            bar = QProgressBar()
            bar.setRange(0,1000)
            bar.setValue(round(n*1000/total))
            bar.setFormat(display(n*100/total)+' %')
            bar.setAccessibleName(value_label(field,key)+': '+str(n)+tr(' registros'))
            self.distribution.setCellWidget(row,2,bar)

    def _observation_row(self):
        row = self.observations.currentRow()
        if 0 <= row < len(self._series_rows):
            self.select_observation(self._series_rows[row][2])

    def select_observation(self, index):
        layer = self.current_layer()
        if layer and 0 <= index < len(self.fids):
            self.iface.setActiveLayer(layer)
            layer.selectByIds([self.fids[index]])
            self.iface.mapCanvas().zoomToSelected(layer)

    def _inspect(self, *args):
        layer = self.current_layer()
        if not layer:
            return
        selected = set(layer.selectedFeatureIds())
        indexes = [i for i,fid in enumerate(self.fids) if fid in selected]
        self.chart.selected = set(indexes)
        self.chart.update()
        fields = [field.name() for field in layer.fields()]
        inspected = [{'fid_qgis':self.fids[i], 'attributes':dict(zip(fields,layer.getFeature(self.fids[i]).attributes())),
                      'geometry_wgs84':self.payload['features'][i]['geometry']} for i in indexes[:20]]
        self.inspector.setPlainText(json.dumps(inspected,ensure_ascii=False,indent=2,default=str))
        if len(indexes)>20:
            self.message.setText(tr('Inspeção limitada aos primeiros 20 pontos selecionados.'))

    def apply_style(self):
        layer = self.current_layer()
        if not layer:
            return
        metric = self.metric.currentData()
        try:
            if metric and self.unit(metric) == tr('Unidades conflitantes'):
                raise ValueError(tr('Não é possível aplicar uma escala comum a unidades conflitantes.'))
            style_metric(layer, metric, self.minimum.value() if self.fixed.isChecked() else None,
                         self.maximum.value() if self.fixed.isChecked() else None,
                         self.unit(metric) if metric else '', self.size.value(),
                         stats=self.summary['stats'].get(metric), categories=self.summary['categories'])
            self.iface.layerTreeView().refreshLayerSymbology(layer.id())
            self.legend.setText(tr('Legenda disponível na árvore de camadas. ')+
                (tr('Classes de intervalo igual; valores fora da escala e ausentes têm símbolos próprios.') if metric else tr('Cores originais da condição J3M.')))
            self.message.setText(tr('Estilo aplicado e salvo com o projeto.'))
        except ValueError as error:
            self.message.setText(str(error))

    def zoom(self):
        layer = self.current_layer()
        if layer:
            self.iface.setActiveLayer(layer)
            self.iface.zoomToActiveLayer()

    def compare(self, other=None):
        a = self.current_layer()
        b = QgsProject.instance().mapLayer(self.other.currentData())
        if not a or not b or a.id() == b.id():
            self.message.setText(tr('Escolha duas camadas diferentes.'))
            return
        try:
            if not isinstance(other, dict):
                if b.featureCount() > 1000:
                    a_id, b_id = a.id(), b.id()
                    def ready(result):
                        if self.layers.currentData() == a_id and self.other.currentData() == b_id:
                            self.compare(result[1])
                    self._analyze(b, ready)
                    return
                other = summarize(layer_payload(b))
            units = json.loads(b.customProperty('j3m/units','{}'))
            rows = []
            for metric, values in self.summary['stats'].items():
                if metric not in other['stats']:
                    continue
                right = other['stats'][metric]
                supplied = other['units'].get(metric, set())
                unit_b = next(iter(supplied)) if len(supplied)==1 else units.get(metric,UNITS.get(metric,''))
                compatible = bool(self.unit(metric)) and self.unit(metric)==unit_b and len(supplied)<=1 and self.unit(metric)!=tr('Unidades conflitantes')
                delta = right['mean']-values['mean'] if compatible and values['n'] and right['n'] else None
                rows.append([metric+' / '+(self.unit(metric) or '?'),values['n'],display(values['mean']),right['n'],
                             display(right['mean']),display(delta) if compatible else tr('Unidades não confirmadas')])
            fill(self.comparison,rows)
            self.comparisonInfo.setText('A: '+str(a.customProperty('j3m/origin',''))+'\nB: '+str(b.customProperty('j3m/origin',''))+
                tr('\nDiferença entre médias dos registros; não é efeito causal ou comparação de amostras pareadas.'))
        except (ValueError, TypeError) as error:
            self.message.setText(str(error))

    def export(self, driver):
        layer = self.current_layer()
        if not layer:
            return
        ext = {'GPKG':'gpkg','CSV':'csv','GeoJSON':'geojson','KML':'kml'}[driver]
        path, _ = QFileDialog.getSaveFileName(self,tr('Exportar camada'),'coletas.'+ext,driver+' (*.'+ext+')')
        if not path:
            return
        if not path.lower().endswith('.'+ext):
            path += '.'+ext
        try:
            self._export(layer,path,driver)
        except (ValueError,OSError) as error:
            self.message.setText(str(error))

    def bundle(self):
        layer = self.current_layer()
        if not layer:
            return
        parent = QFileDialog.getExistingDirectory(self,tr('Pasta para um novo estudo portátil'))
        if not parent:
            return
        from datetime import datetime
        from uuid import uuid4
        directory = Path(parent)/('J3M-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+uuid4().hex[:6])
        try:
            directory.mkdir(parents=True, exist_ok=False)
            self._export(layer,directory/'coletas.gpkg','GPKG',directory)
        except (ValueError,OSError) as error:
            self.message.setText(str(error))

    def _export(self, layer, path, driver, directory=None):
        from qgis.core import QgsVectorFileWriterTask
        task = QgsVectorFileWriterTask(layer,str(path),export_options(layer,path,driver))
        identifier = layer.id()
        def done(*args):
            if task in self._tasks:
                self._tasks.remove(task)
            if self._disposed:
                return
            current = QgsProject.instance().mapLayer(identifier)
            if current is None:
                self.message.setText(tr('Arquivo exportado; camada removida antes de salvar estilo/procedência.'))
                return
            try:
                export_sidecars(current,path)
                if directory:
                    self._finish_bundle(current,directory)
                else:
                    self.message.setText(tr('Exportado com estilo QML e procedência: ')+str(path))
            except (ValueError,OSError,RuntimeError) as error:
                self.message.setText(tr('Exportação incompleta: ')+str(error))
        def failed(code, message):
            if task in self._tasks:
                self._tasks.remove(task)
            if not self._disposed:
                self.message.setText(tr('Exportação cancelada ou incompleta: ')+message)
        task.completed.connect(done)
        task.errorOccurred.connect(failed)
        task.setDependentLayers([layer])
        self._tasks.append(task)
        self.message.setText(tr('Exportando em segundo plano; acompanhe ou cancele nas tarefas do QGIS.'))
        QgsApplication.taskManager().addTask(task)

    def _finish_bundle(self, layer, directory):
        identifier = layer.id()
        source = layer.source().split('|')[0]
        def finished(error, result=None):
            if task in self._tasks:
                self._tasks.remove(task)
            if self._disposed:
                return
            current = QgsProject.instance().mapLayer(identifier)
            if error or not result or task.isCanceled() or current is None:
                self.message.setText(tr('Estudo portátil incompleto ou cancelado.'))
                return
            try:
                path = portable_study(current,directory,exported=True,original_copied=True)
                self.message.setText(tr('Estudo portátil salvo: ')+str(path))
            except (ValueError,OSError,RuntimeError) as caught:
                self.message.setText(tr('Estudo portátil incompleto: ')+str(caught))
        task = QgsTask.fromFunction(tr('J3M: copiar origem do estudo'),copy_original,
                                    source=source,directory=directory,on_finished=finished)
        self._tasks.append(task)
        QgsApplication.taskManager().addTask(task)

    def pdf(self):
        layer = self.current_layer()
        if not layer or not self.summary:
            return
        path, _ = QFileDialog.getSaveFileName(self,tr('Relatório de campanha'),'campanha.pdf','PDF (*.pdf)')
        if not path:
            return
        if not path.lower().endswith('.pdf'):
            path += '.pdf'
        try:
            def done(error=None):
                if job in self._render_jobs:
                    self._render_jobs.remove(job)
                if not self._disposed:
                    self.message.setText(str(error) if error else tr('PDF salvo: ')+path)
            job = report_pdf(layer,path,self.summary,on_finished=done)
            self._render_jobs.append(job)
            self.message.setText(tr('Preparando o mapa do PDF…'))
        except (ValueError,OSError,RuntimeError) as error:
            self.message.setText(str(error))
