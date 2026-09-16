"""Integration UI and contract checks using QGIS, without real credentials."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import QMainWindow
from j3m_connect.adapters import catalog_records, indicator_rows, geofence_geojson
from j3m_connect.layers import add_geojson_layer
from j3m_connect.dialog import J3MDialog
from j3m_connect.j3m_connect import J3MConnect
from j3m_connect.api import ApiClient
from qgis.PyQt.QtCore import QUrlQuery


class FakeApi(QObject):
    busyChanged = pyqtSignal(bool)
    failed = pyqtSignal(str)
    received = pyqtSignal(str, object)

    def __init__(self, parent):
        super().__init__(parent)
        self.calls = []

    def cancel(self):
        self.busyChanged.emit(False)

    def get(self, *args, **kwargs):
        self.calls.append((args, kwargs))


class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance() or QgsApplication([], False)
        cls.app.initQgis()

    def test_plugin_action_lifecycle(self):
        window = QMainWindow()
        iface = Mock()
        iface.mainWindow.return_value = window
        plugin = J3MConnect(iface)
        plugin.initGui()
        action = plugin.action
        self.assertIsNotNone(action)
        iface.addToolBarIcon.assert_called_once_with(action)
        plugin.initGui()
        iface.addToolBarIcon.assert_called_once()
        with patch('j3m_connect.dialog.settings.preferences', return_value=('', '')):
            action.trigger()
            self.assertTrue(plugin.dialog.isVisible())
        plugin.unload()
        iface.removeToolBarIcon.assert_called_once_with(action)
        self.assertIsNone(plugin.action)
        self.assertIsNone(plugin.dialog)

    def test_point_style(self):
        from qgis.core import QgsVectorLayer
        from j3m_connect.layers import _style_points
        layer = QgsVectorLayer('Point?crs=EPSG:4326&field=markerColor:string', 'points', 'memory')
        _style_points(layer)
        self.assertEqual(layer.renderer().symbol().size(), 3)

    def test_api_paths_and_period(self):
        manager = Mock()
        with patch('j3m_connect.api.credentials', return_value=('https://example.test/v1', 'client', 'secret')), \
                patch('j3m_connect.api.QgsNetworkAccessManager.instance', return_value=manager):
            api = ApiClient()
            for scope in ('sessions', 'devices', 'clusters', 'geofences'):
                api.get('catalog', scope=scope)
                request = manager.get.call_args.args[0]
                self.assertEqual(request.url().path(), '/v1/' + scope)
                self.assertEqual(bytes(request.rawHeader(b'X-Client-Secret')), b'secret')
                api.get('collections', 'uuid', scope=scope,
                        period=('2026-01-01 00:00:00', '2026-01-02 00:00:00'))
                url = manager.get.call_args.args[0].url()
                self.assertEqual(url.path(), '/v1/' + scope + '/uuid/collections')
                query = QUrlQuery(url)
                self.assertEqual(query.queryItemValue('format'), 'geojson')
                self.assertEqual(query.hasQueryItem('start_date'), scope != 'sessions')
            api.cancel()

    def test_contracts(self):
        record = {'uuid': 'a', 'name': 'Área', 'points': [
            {'lng': -46, 'lat': -23}, {'lng': -45, 'lat': -23}, {'lng': -46, 'lat': -22}]}
        polygon = geofence_geojson(record)
        ring = polygon['geometry']['coordinates'][0]
        self.assertEqual(ring[0], [-46, -23])
        self.assertEqual(ring[-1], ring[0])
        self.assertEqual(catalog_records({'success': True, 'data': [record]})[0]['points'], record['points'])
        for avgs in ([{'name': 'T', 'avg': 0, 'unit': 'C'}], {'T': {'avg': 0, 'unit': 'C'}}):
            _, rows = indicator_rows({'success': True, 'data': {'totalCollects': 3, 'avgs': avgs}})
            self.assertEqual(rows[0][:3], ('T', 0, 'C'))
        with self.assertRaises(ValueError):
            geofence_geojson(dict(record, points=[{'lng': 200, 'lat': 0}]))
        with patch('j3m_connect.layers.QgsApplication.qgisSettingsDirPath',
                   return_value=str(Path(__file__).resolve().parents[1] / 'dist' / 'test-profile')):
            layer = add_geojson_layer(polygon, 'test geofence')
        self.assertTrue(layer.isValid())
        self.assertEqual(layer.crs().authid(), 'EPSG:4326')
        path = layer.source().split('|')[0]
        QgsProject.instance().removeMapLayer(layer.id())
        Path(path).unlink()

    def test_navigation_period_and_tables(self):
        window = QMainWindow()
        iface = Mock()
        iface.mainWindow.return_value = window
        with patch('j3m_connect.dialog.ApiClient', FakeApi), patch('j3m_connect.dialog.settings.preferences', return_value=('', '')):
            dialog = J3MDialog(iface)
            self.assertEqual(dialog.pages.currentIndex(), 1)
            dialog._loaded = True
            for index, scope in enumerate(('sessions', 'devices', 'geofences', 'clusters')):
                dialog.menu.setCurrentRow(index)
                self.assertEqual(dialog.api.calls[-1][1]['scope'], scope)
                dialog._received('catalog', {'success': True, 'data': [
                    {'uuid': scope + '-id', 'name': 'Sensor', 'timezone': 'America/Sao_Paulo'}]})
                dialog._consult()
                args, kwargs = dialog.api.calls[-1]
                self.assertEqual(args, ('indicators', scope + '-id'))
                self.assertEqual(kwargs['period'] is None, scope == 'sessions')
                dialog._received('indicators', {'success': True, 'data': {
                    'totalCollects': 5, 'avgs': [{'name': 'temperatura', 'avg': 22, 'unit': 'C'}]}})
                if scope == 'geofences':
                    self.assertEqual(dialog.timezone.text(), 'UTC')
                    self.assertEqual(dialog.api.calls[-1][0][0], 'table')
                    dialog._received('table', {'success': True, 'data': [
                        {'metric': 'temperatura', 'min': 10, 'max': 30, 'unit': 'C'}]})
                    self.assertEqual(dialog.table.item(0, 3).text(), '10')
                dialog._request('collections')
                self.assertEqual(dialog.api.calls[-1][0][0], 'collections')
            dialog.end.setDateTime(dialog.start.dateTime())
            count = len(dialog.api.calls)
            dialog._request('collections')
            self.assertEqual(len(dialog.api.calls), count)
            dialog.search.setText('missing')
            self.assertEqual(dialog.records.count(), 0)
            self.assertFalse(dialog.addButton.isEnabled())
            dialog.close()


if __name__ == '__main__':
    unittest.main()
