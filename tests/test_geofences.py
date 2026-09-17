"""Geofence selection, isolated layers, style, and portable map tips."""
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from qgis.core import QgsApplication, QgsExpression, QgsExpressionContext, QgsProject
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMainWindow
from j3m_connect.geofences import GeofencesPage
from j3m_connect.dialog import J3MDialog
from test_integration import FakeApi


def record(uuid, name):
    return {'uuid': uuid, 'name': name, 'color': '#123456',
            'borderColor': '#abcdef', 'fillColor': '#654321',
            'points': [{'lng': -46, 'lat': -23}, {'lng': -45, 'lat': -23},
                       {'lng': -46, 'lat': -22}]}


class GeofenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance() or QgsApplication([], False)
        cls.app.initQgis()

    def test_separate_navigation_and_requests(self):
        window = QMainWindow()
        iface = Mock()
        iface.mainWindow.return_value = window
        with patch('j3m_connect.dialog.ApiClient', FakeApi), patch('j3m_connect.geofences.ApiClient', FakeApi), patch('j3m_connect.dialog.settings.preferences', return_value=('', '')):
            dialog = J3MDialog(iface)
            dialog._loaded = True
            dialog._select_menu('geofences')
            dialog._cache['geofences'] = [record('dashboard', 'Dashboard')]
            calls = list(dialog.api.calls)
            dialog._select_menu('geofences_map')
            page = dialog.geofencesPage
            self.assertIs(dialog.pages.currentWidget(), page)
            self.assertEqual(page.api.calls, [(('catalog',), {'scope': 'geofences'})])
            page._received('catalog', {'success': True, 'data': [record('map', 'Mapa')]})
            self.assertEqual(dialog.api.calls, calls)
            self.assertEqual(dialog._cache['geofences'][0]['uuid'], 'dashboard')
            dialog._select_menu('geofences')
            self.assertEqual(dialog.records.currentData()['uuid'], 'dashboard')
            dialog.close()

    def test_selection_layers_colors_and_tooltip(self):
        iface = Mock()
        with patch('j3m_connect.geofences.ApiClient', FakeApi):
            page = GeofencesPage(iface)
        records = [record('a', 'Área <Norte> & Sul'), record('b', 'Lago'), record('bad', 'Inválida')]
        records[-1]['points'] = []
        page._received('catalog', {'success': True, 'data': records})
        page.search.setText('Área')
        page._check_all(True)
        page.search.setText('Lago')
        page._check_all(True)
        self.assertIn('2 selecionada(s)', page.selectionLabel.text())
        self.assertIn('1 fora do filtro', page.selectionLabel.text())
        page._received('catalog', {'success': True, 'data': records})
        self.assertEqual(page.records.item(0).checkState(), Qt.CheckState.Checked)
        page.search.clear()
        page._check_all(True)
        before = set(QgsProject.instance().mapLayers())
        with tempfile.TemporaryDirectory() as directory, patch('j3m_connect.layers.QgsApplication.qgisSettingsDirPath', return_value=directory):
            try:
                page._add()
                layers = [layer for key, layer in QgsProject.instance().mapLayers().items() if key not in before]
                self.assertEqual(len(layers), 2)
                self.assertEqual(len({layer.source() for layer in layers}), 2)
                for layer in layers:
                    self.assertEqual(layer.featureCount(), 1)
                    self.assertEqual(layer.crs().authid(), 'EPSG:4326')
                    symbol = layer.renderer().symbol().symbolLayer(0)
                    self.assertEqual(symbol.strokeColor().name(), '#abcdef')
                    self.assertEqual(symbol.strokeColor().alpha(), 255)
                    self.assertEqual(symbol.color().name(), '#654321')
                    self.assertEqual(symbol.color().alpha(), 64)
                    feature = next(layer.getFeatures())
                    context = QgsExpressionContext()
                    context.setFeature(feature)
                    tip = QgsExpression.replaceExpressionText(layer.mapTipTemplate(), context)
                    if feature['uuid'] == 'a':
                        self.assertIn('<strong>Geocerca: </strong>Área &lt;Norte&gt; &amp; Sul', tip)
                        self.assertNotIn('<Norte>', tip)
                self.assertIn('2 geocerca(s) adicionada(s)', page.status.text())
                self.assertIn('Inválida:', page.status.text())
                self.assertEqual(page.records.item(2).checkState(), Qt.CheckState.Checked)
                self.assertEqual(page.records.item(0).checkState(), Qt.CheckState.Unchecked)
                iface.actionMapTips().setChecked.assert_called_with(True)
            finally:
                for key in set(QgsProject.instance().mapLayers()) - before:
                    QgsProject.instance().removeMapLayer(key)
                layers = []
                layer = None
        page.reset()
        self.assertEqual(page.records.count(), 0)
        self.assertFalse(page.addButton.isEnabled())


if __name__ == '__main__':
    unittest.main()
