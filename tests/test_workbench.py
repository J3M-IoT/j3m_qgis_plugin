"""Regression checks for real QGIS layers, portable output and the Qt workbench."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from qgis.core import QgsApplication, QgsProject, QgsVectorLayer, QgsExpression, QgsExpressionContext, QgsExpressionContextUtils
from qgis.PyQt.QtCore import QDateTime, Qt, QUrlQuery, QTimeZone
from qgis.PyQt.QtWidgets import QMainWindow
from j3m_connect.analysis import summarize, layer_payload, timestamp
from j3m_connect.cartography import configure_layer, provenance, style_metric, export_layer, portable_study, report_pdf
from j3m_connect.layers import add_geojson_layer
from j3m_connect.dialog import J3MDialog
from j3m_connect.workbench import Workbench
from j3m_connect.api import ApiClient
from test_integration import FakeApi


def fixture():
    return {'type':'FeatureCollection','features':[
        {'type':'Feature','id':'collect-'+str(i),'geometry':{'type':'Point','coordinates':[-46+i*.001,-23]},
         'properties':{'collectedAt':'2026-10-19T12:0'+str(i)+':00Z',
                       'device':{'uuid':'sensor-a','name':'Praça','battery':85},
                       'collects':{'temperatura':v,'umidade':{'value':70+i,'unit':'%'}},
                       'condition':{'name':'Boa','color':'green','hex':'#16a34a'},'timePeriod':'day','mode':'continuous',
                       'markerColor':'#16a34a'}} for i,v in enumerate([0,20,None,30])]}


class WorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        language_patch = patch("j3m_connect.i18n._language", "pt-br")
        language_patch.start()
        cls.addClassCleanup(language_patch.stop)
        cls.app = QgsApplication.instance() or QgsApplication([],False)
        cls.app.initQgis()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.profile = patch('j3m_connect.layers.QgsApplication.qgisSettingsDirPath',return_value=self.temp.name)
        self.profile.start()
        self.window = QMainWindow()
        self.iface = Mock()
        self.iface.mainWindow.return_value = self.window

    def tearDown(self):
        QgsProject.instance().removeAllMapLayers()
        import gc
        from qgis.PyQt.QtCore import QCoreApplication, QEvent
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
        QgsApplication.processEvents()
        gc.collect()
        self.window.close()
        self.profile.stop()
        self.temp.cleanup()

    def layer(self):
        payload = fixture()
        layer = add_geojson_layer(payload,'Campanha Praça')
        origin = provenance('devices',{'uuid':'sensor-a','name':'Praça','timezone':'America/Sao_Paulo'},
                            ['2026-10-19 09:00:00','2026-10-19 10:00:00'],payload)
        configure_layer(layer,origin,{'temperatura':'°C','umidade':'%'})
        return layer

    def test_null_zero_and_timezone(self):
        report = summarize(fixture())
        values = report['stats']['temperatura']
        self.assertEqual(values['n'],3)
        self.assertEqual(values['min'],0)
        self.assertEqual(values['missing'],1)
        self.assertEqual(report['invalid_time'],0)
        self.assertEqual(timestamp('2026-10-19T09:00:00-03:00'),timestamp('2026-10-19T12:00:00Z'))
        self.assertIsNone(timestamp('2026-10-19 09:00:00'))

    def test_temporal_roundtrip_and_null_legend(self):
        layer = self.layer()
        self.assertTrue(layer.temporalProperties().isActive())
        self.assertEqual(summarize(layer_payload(layer))['stats']['temperatura']['n'],3)
        self.assertEqual(summarize(layer_payload(layer))['stats']['umidade']['mean'],71.5)
        style_metric(layer,'temperatura',10,25,'°C')
        self.assertEqual(len(layer.renderer().rootRule().children()),8)
        context = QgsExpressionContext()
        context.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        for feature in layer.getFeatures():
            context.setFeature(feature)
            matching = [r for r in layer.renderer().rootRule().children() if QgsExpression(r.filterExpression()).evaluate(context)]
            self.assertEqual(len(matching),1)
        self.assertEqual(len(QgsProject.instance().layerTreeRoot().findGroup('J3M').findLayers()),1)
        QgsApplication.processEvents()
        self.assertIsNotNone(QgsProject.instance().mapLayer(layer.id()))

    def test_exports_and_portable_project(self):
        layer = self.layer()
        for driver,ext in [('GPKG','gpkg'),('GeoJSON','geojson'),('CSV','csv'),('KML','kml')]:
            path = self.directory/('result.'+ext)
            export_layer(layer,path,driver)
            self.assertTrue(path.exists())
            self.assertTrue(Path(str(path)+'.origem.json').exists())
        project_path = portable_study(layer,self.directory/'study')
        project = QgsProject()
        self.assertTrue(project.read(str(project_path)))
        saved = list(project.mapLayers().values())[0]
        self.assertTrue(saved.isValid())
        self.assertEqual(saved.featureCount(),4)
        self.assertTrue(saved.customProperty('j3m/origin'))
        self.assertTrue(saved.temporalProperties().isActive())
        self.assertTrue((project_path.parent/'origem.geojson').exists())
        import zipfile
        with zipfile.ZipFile(project_path) as archive:
            xml=archive.read(next(name for name in archive.namelist() if name.endswith('.qgs'))).decode('utf-8')
        self.assertIn('./coletas.gpkg',xml)
        project.clear()
        report_pdf(layer,self.directory/'report.pdf',summarize(fixture()))
        self.assertTrue((self.directory/'report.pdf').read_bytes().startswith(b'%PDF'))

    def test_workbench_selection_and_units(self):
        layer = self.layer()
        panel = Workbench(self.iface)
        try:
            panel.focus_layer(layer)
            self.assertEqual(panel.summary['count'],4)
            self.assertEqual(panel.unit('umidade'),'%')
            panel.metric.setCurrentIndex(panel.metric.findData('temperatura'))
            self.assertEqual(len(panel.chart.points),3)
            panel.select_observation(1)
            self.assertEqual(layer.selectedFeatureCount(),1)
            self.assertIn('collect-1',panel.inspector.toPlainText())
            panel.apply_style()
            self.assertEqual(layer.renderer().type(),'RuleRenderer')
        finally:
            panel.dispose()
            panel.close()

    def test_wall_clock_preserves_instant_and_saved_query(self):
        with patch('j3m_connect.dialog.ApiClient',FakeApi), patch('j3m_connect.dialog.settings.preferences',return_value=('', '')):
            dialog = J3MDialog(self.iface)
            try:
                dialog.start.setDateTime(QDateTime.fromString('2026-10-19T12:00:00Z',Qt.DateFormat.ISODate))
                dialog._set_zone('America/Sao_Paulo')
                self.assertEqual(dialog.start.text(),'19/10/2026 09:00:00')
                self.assertIn('2026-10-19 12:00:00',dialog.utcLabel.text())
                dialog._set_zone('UTC')
                self.assertEqual(dialog.start.text(),'19/10/2026 12:00:00')
            finally:
                dialog.dispose()
                dialog.close()

    def test_default_period_is_today_in_resource_timezone(self):
        with patch('j3m_connect.dialog.ApiClient',FakeApi),patch('j3m_connect.dialog.settings.preferences',return_value=('','')):
            dialog=J3MDialog(self.iface)
            try:
                for scope,zone in [('devices','America/Sao_Paulo'),('clusters','Pacific/Auckland'),('geofences','UTC')]:
                    dialog._select_menu(scope)
                    dialog._received('catalog',{'success':True,'data':[{'uuid':scope,'name':scope,'timezone':zone}]})
                    today=QDateTime.currentDateTimeUtc().toTimeZone(QTimeZone(zone.encode('utf-8'))).date()
                    self.assertEqual(dialog.start.date(),today)
                    self.assertEqual(dialog.end.date(),today)
                    self.assertEqual(dialog.start.time().toString('HH:mm:ss'),'00:00:00')
                    self.assertEqual(dialog.end.time().toString('HH:mm:ss'),'23:59:59')
                    dialog._request('collections')
                    period=dialog.api.calls[-1][1]['period']
                    self.assertTrue(period[0].endswith('00:00:00'))
                    self.assertTrue(period[1].endswith('23:59:59'))
            finally:
                dialog.dispose()
                dialog.close()

    def test_shared_map_routes_use_code_then_uuid_without_secret(self):
        manager=Mock()
        with patch('j3m_connect.api.configured_api_url',return_value='https://example.test'),patch('j3m_connect.api.credentials') as creds,patch('j3m_connect.api.QgsNetworkAccessManager.instance',return_value=manager):
            api=ApiClient()
            try:
                api.get('map_link','public-code',scope='map_links')
                request=manager.get.call_args.args[0]
                self.assertEqual(request.url().path(),'/v1/map-links/public-code')
                self.assertFalse(request.hasRawHeader(b'X-Client-Secret'))
                api.get('link_collections','link-uuid',scope='map_links')
                request=manager.get.call_args.args[0]
                self.assertEqual(request.url().path(),'/v1/map-links/link-uuid/export')
                self.assertEqual(QUrlQuery(request.url()).queryItemValue('format'),'geojson')
                creds.assert_not_called()
            finally:
                api.cancel()

    def test_separate_session_reports_do_not_send_credentials(self):
        manager=Mock()
        with patch('j3m_connect.api.credentials',return_value=('https://example.test','client','secret')),patch('j3m_connect.api.QgsNetworkAccessManager.instance',return_value=manager):
            api=ApiClient()
            try:
                for kind,path in [('range','collects/range'),('aggregation','aggregation'),('changes','changes')]:
                    api.get(kind,'authorized-session',scope='sessions')
                    req=manager.get.call_args.args[0]
                    self.assertEqual(req.url().path(),'/v1/device-sessions/authorized-session/'+path)
                    self.assertFalse(req.hasRawHeader(b'X-Client-Secret'))
                    self.assertFalse(req.hasRawHeader(b'X-Client-Id'))
                api.get('change_detail','authorized-session',scope='sessions',params={
                    'metric':'temperatura','start_date':'2026-10-19 09:00:00','end_date':'2026-10-19 09:10:00'})
                req=manager.get.call_args.args[0]
                self.assertEqual(QUrlQuery(req.url()).queryItemValue('metric'),'temperatura')
            finally:
                api.cancel()

    def test_refresh_keeps_layer_id_and_style(self):
        with patch('j3m_connect.dialog.ApiClient',FakeApi),patch('j3m_connect.dialog.settings.preferences',return_value=('','')):
            dialog=J3MDialog(self.iface)
            try:
                layer=self.layer()
                identifier=layer.id()
                style_metric(layer,'temperatura',0,40,'°C')
                dialog.workbench.focus_layer(layer)
                dialog._cache['devices']=[{'uuid':'sensor-a','name':'Praça','timezone':'America/Sao_Paulo'}]
                dialog._replace()
                data=fixture()
                data['features'][0]['properties']['collects']['temperatura']=5
                dialog._received('collections',data)
                from qt_helpers import wait_for
                wait_for(lambda: dialog.layerLoader._task is None)
                refreshed=QgsProject.instance().mapLayer(identifier)
                self.assertIsNotNone(refreshed)
                self.assertEqual(refreshed.renderer().type(),'RuleRenderer')
                self.assertEqual(summarize(layer_payload(refreshed))['stats']['temperatura']['min'],5)
                self.assertEqual(len(QgsProject.instance().mapLayers()),1)
            finally:
                dialog.dispose()
                dialog.close()

    def test_background_analysis_export_and_pdf(self):
        from time import monotonic
        from qgis.PyQt.QtTest import QTest
        payload = fixture()
        payload['features'] = [dict(payload['features'][i % 4], id='async-'+str(i)) for i in range(1200)]
        layer = add_geojson_layer(payload, 'Campanha extensa')
        configure_layer(layer, {'scope':'local','name':'Campanha extensa'})
        panel = Workbench(self.iface)
        def wait_until(predicate):
            deadline = monotonic()+15
            while not predicate() and monotonic()<deadline:
                QTest.qWait(10)
            self.assertTrue(predicate(),panel.message.text())
        try:
            self.assertIsNone(panel.summary)
            wait_until(lambda: panel.summary is not None)
            self.assertEqual(panel.summary['count'],1200)
            self.assertEqual(len(panel.fids),1200)
            output = self.directory/'async.gpkg'
            panel._export(layer,output,'GPKG')
            wait_until(lambda: not panel._tasks)
            self.assertTrue(Path(str(output)+'.origem.json').exists())
            bundle = self.directory/'async-study'
            bundle.mkdir()
            panel._export(layer,bundle/'coletas.gpkg','GPKG',bundle)
            wait_until(lambda: not panel._tasks)
            self.assertTrue((bundle/'estudo.qgz').exists())
            self.assertTrue((bundle/'origem.geojson').exists())
            pdf = self.directory/'async.pdf'
            with patch('j3m_connect.workbench.QFileDialog.getSaveFileName', return_value=(str(pdf),'PDF')):
                panel.pdf()
            wait_until(lambda: not panel._render_jobs)
            self.assertTrue(pdf.read_bytes().startswith(b'%PDF'))
        finally:
            panel.dispose()
            panel.close()
