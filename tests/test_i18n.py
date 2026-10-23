"""Language selection, localized API contracts and real Qt panel lifecycle."""
import ast
import json
import string
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from qgis.core import QgsApplication, QgsSettings, QgsProject, Qgis
from qgis.PyQt.QtCore import QLocale, QT_VERSION_STR
from qgis.PyQt.QtWidgets import QMainWindow
from qgis.PyQt.QtGui import QImage

from j3m_connect import i18n
from j3m_connect.api import ApiClient, decode_response
from j3m_connect.j3m_connect import J3MConnect
from j3m_connect.dialog import J3MDialog
from j3m_connect.settings import configured_timeout_seconds
from test_async import Reply
from test_integration import FakeApi
import test_map_tips
from test_workbench import fixture
from j3m_connect.layers import add_geojson_layer
from j3m_connect.cartography import configure_layer, style_metric
from j3m_connect.analysis import summarize
from j3m_connect.cartography import _write_report, portable_study
from qt_helpers import wait_for


class TranslationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication.instance() or QgsApplication([], False)
        cls.app.initQgis()
        print('\nTranslation runtime:', Qgis.QGIS_VERSION, 'Qt', QT_VERSION_STR)

    def setUp(self):
        self.settings = QgsSettings()
        keys = (i18n.LANGUAGE_KEY, 'locale/overrideFlag', 'locale/userLocale')
        previous = [(key, self.settings.contains(key), self.settings.value(key)) for key in keys]
        old_language = i18n.language()
        old_locale = QLocale()

        def restore():
            for key, exists, value in previous:
                if exists:
                    self.settings.setValue(key, value)
                else:
                    self.settings.remove(key)
            i18n._language = old_language
            QLocale.setDefault(old_locale)
        self.addCleanup(restore)

    def test_normalization_and_unsupported_locale(self):
        for source, expected in (
                ('pt_BR', 'pt-br'), ('EN_us', 'en-us'), ('es_ES', 'es-es'),
                ('pt', 'pt-br'), ('es', 'es-es'), ('en', 'en-us'),
                ('fr_FR', 'en-us'), ('de', 'en-us'), ('pt_PT', 'en-us'),
                ('es_MX', 'en-us'), ('', 'en-us')):
            with self.subTest(source=source):
                self.assertEqual(i18n.resolve_language(source), expected)

    def test_qgis_ui_override_and_system_fallback(self):
        # A real QGIS window's active translation takes precedence over OS locale.
        with patch.object(i18n.QgsApplication, 'instance', return_value=Mock(translation=lambda: 'es')):
            self.assertEqual(i18n.qgis_language(), 'es-es')
        with patch.object(i18n.QgsApplication, 'instance', return_value=None):
            self.settings.setValue('locale/overrideFlag', True)
            for locale, expected in [('pt_BR', 'pt-br'), ('es_ES', 'es-es'), ('fr_FR', 'en-us')]:
                self.settings.setValue('locale/userLocale', locale)
                self.assertEqual(i18n.qgis_language(), expected)
            self.settings.setValue('locale/overrideFlag', False)
            QLocale.setDefault(QLocale('es_ES'))
            self.assertEqual(i18n.qgis_language(), 'es-es')

    def test_persisted_selection_and_return_to_qgis(self):
        with patch.object(i18n, 'qgis_language', return_value='pt-br'):
            i18n.set_language('es-es')
            i18n.initialize()
            self.assertEqual(i18n.language(), 'es-es')
            self.assertEqual(i18n.tr('Conexão'), 'Conexión')
            i18n.set_language('')
            self.assertEqual(i18n.language(), 'pt-br')
            self.assertEqual(i18n.tr('Conexão'), 'Conexão')
        with self.assertRaises(ValueError):
            i18n.set_language('fr-fr')

    def test_catalog_coverage_and_format_fields(self):
        english, spanish = i18n._catalogs['en-us'], i18n._catalogs['es-es']
        self.assertEqual(english.keys(), spanish.keys())
        formatter = string.Formatter()
        fields = lambda text: sorted((name, spec, conversion) for _, name, spec, conversion in formatter.parse(text) if name is not None)
        for source in english:
            for catalog in (english, spanish):
                self.assertTrue(catalog[source])
                self.assertEqual(fields(source), fields(catalog[source]), source)
        plugin = Path(__file__).resolve().parents[1] / 'j3m_connect'
        for path in plugin.glob('*.py'):
            for node in ast.walk(ast.parse(path.read_text(encoding='utf-8'))):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                        and node.func.id == 'tr' and node.args and isinstance(node.args[0], ast.Constant)):
                    self.assertIn(node.args[0].value, english, str(path) + ':' + str(node.lineno))
        with patch.object(i18n, '_language', 'es-es'), patch.dict(i18n._catalogs, {'es-es': {}}):
            self.assertEqual(i18n.tr('Conexão'), 'Connection')

    def test_all_request_types_use_selected_language(self):
        manager = Mock()
        api = ApiClient()
        self.addCleanup(api.cancel)
        with patch('j3m_connect.api.credentials', return_value=('https://example.test', 'client', 'secret')), \
                patch('j3m_connect.api.QgsNetworkAccessManager.instance', return_value=manager):
            for locale in i18n.LANGUAGES:
                i18n.set_language(locale)
                for kind, scope, period in (
                        ('catalog', 'devices', None), ('indicators', 'devices', ('2026-01-01', '2026-01-02')),
                        ('collections', 'sessions', None), ('range', 'sessions', None),
                        ('map_link', 'map_links', None), ('link_collections', 'map_links', None)):
                    with self.subTest(locale=locale, kind=kind):
                        manager.get.return_value = Reply()
                        api.get(kind, 'uuid', scope=scope, period=period)
                        request = manager.get.call_args.args[0]
                        self.assertEqual(bytes(request.rawHeader(b'X-Locale')).decode(), locale)
                        self.assertEqual(bytes(request.rawHeader(b'Accept-Language')).decode(), locale)
                        authenticated = kind not in ('range', 'map_link', 'link_collections')
                        self.assertEqual(request.hasRawHeader(b'X-Client-Secret'), authenticated)
                        self.assertEqual(api._timer.interval(), 60000)

    def test_timeout_default_and_shipped_value(self):
        self.assertEqual(configured_timeout_seconds(), 60)
        with patch('j3m_connect.settings._configuration', return_value={}):
            self.assertEqual(configured_timeout_seconds(), 60)

    def test_localized_empty_responses_and_errors(self):
        task = Mock(isCanceled=lambda: False)
        for locale, message in (
                ('pt-br', 'Não há dados para os parâmetros informados.'),
                ('en-us', 'There is no data for the provided parameters.'),
                ('es-es', 'No hay datos para los parámetros informados.')):
            i18n.set_language(locale)
            body = json.dumps({'success': False, 'message': message}).encode()
            for kind in ('indicators', 'collections', 'table', 'range', 'aggregation', 'changes', 'change_detail', 'link_collections'):
                self.assertEqual(decode_response(task, body, 'secret', kind, 404, True, ''), ('', None))
            error, data = decode_response(task, b'{"message":"secret"}', 'secret', 'collections', 401, True, '')
            self.assertEqual(error, i18n.tr('Credenciais inválidas ou acesso não autorizado (HTTP 401/403).'))
            self.assertNotIn('secret', error)
            self.assertIsNone(data)

    def test_metric_rows_merge_by_identifier_after_translation(self):
        window = QMainWindow()
        iface = Mock()
        iface.mainWindow.return_value = window
        self.addCleanup(window.close)
        with patch('j3m_connect.dialog.ApiClient', FakeApi), \
                patch('j3m_connect.dialog.settings.preferences', return_value=('', '')):
            for locale in i18n.LANGUAGES:
                i18n.set_language(locale)
                dialog = J3MDialog(iface)
                try:
                    dialog._select_menu('geofences')
                    dialog._received('catalog', {'success': True, 'data': [{'uuid': 'geo', 'name': 'Original name'}]})
                    dialog._received('indicators', {'success': True, 'data': {
                        'totalCollects': 1, 'avgs': [{'name': 'umidade', 'avg': 0, 'unit': '%'}]}})
                    dialog._received('table', {'success': True, 'data': [
                        {'metric': 'umidade', 'min': 0, 'max': 50, 'unit': '%'}]})
                    self.assertEqual(dialog.table.rowCount(), 1)
                    self.assertEqual(dialog.table.item(0, 0).text(), i18n.tr('Umidade'))
                    self.assertEqual(dialog.table.item(0, 3).text(), '0')
                    self.assertEqual(dialog.records.currentText(), 'Original name')
                    self.assertEqual(dialog.locale().name().lower().replace('_', '-'), locale)
                    dialog.workbench.summary = {'distributions': {'timePeriod': {'day': 1, 'night': 2}}}
                    dialog.workbench.category.setCurrentIndex(dialog.workbench.category.findData('timePeriod'))
                    self.assertEqual(dialog.workbench.distribution.item(0, 0).text(), i18n.tr('Dia'))
                    self.assertEqual(dialog.workbench.summary['distributions']['timePeriod'], {'day': 1, 'night': 2})
                    dialog._report('changes', {'success': True, 'data': {'changes': [
                        {'metric': 'umidade', 'direction': 'drop', 'delta': -1}]}})
                    self.assertEqual(dialog.reportTable.item(0, 1).text(), i18n.tr('Queda'))
                    self.assertEqual(i18n.value_label('direction', 'new-server-value'), 'new-server-value')
                finally:
                    dialog.dispose()
                    dialog.deleteLater()

    def test_translated_map_tips_aliases_and_null_condition_renderer(self):
        render = test_map_tips.MapTipTests().render
        for locale, title, day, humidity in (
                ('pt-br', 'Leituras ambientais', 'Dia', 'Umidade'),
                ('en-us', 'Environmental readings', 'Day', 'Humidity'),
                ('es-es', 'Lecturas ambientales', 'Día', 'Humedad')):
            i18n.set_language(locale)
            html = render({'collects_umidade': '60.1', 'timePeriod': 'day', 'radius_meters': '100',
                           'territorialContextDistance_park': '12.5'})
            self.assertIn(title, html)
            self.assertIn(day, html)
            self.assertIn(humidity, html)
            payload = fixture()
            payload['features'][0]['properties']['condition'] = None
            layer = add_geojson_layer(payload, 'Unchanged user name')
            try:
                configure_layer(layer, {'scope': 'local'})
                self.assertIn(humidity, layer.attributeAlias(layer.fields().indexFromName('collects_umidade_value')))
                self.assertEqual(layer.name(), 'Unchanged user name')
                self.assertIn('Sem condição', layer.renderer().classAttribute())
                self.assertIn(i18n.tr('Sem condição'), [category.label().split(' · ')[0] for category in layer.renderer().categories()])
                cached_keys = [category.value() for category in layer.renderer().categories()]
                # Restyling a cached snapshot in another language must not alter
                # category identifiers or make null-condition points disappear.
                i18n.set_language('en-us' if locale != 'en-us' else 'es-es')
                style_metric(layer, '')
                self.assertEqual(cached_keys, [category.value() for category in layer.renderer().categories()])
                self.assertIn(i18n.tr('Sem condição'), [category.label().split(' · ')[0] for category in layer.renderer().categories()])
            finally:
                QgsProject.instance().removeMapLayer(layer.id())

    def test_apply_language_rebuilds_panel_and_preserves_layers(self):
        window = QMainWindow()
        iface = Mock()
        iface.mainWindow.return_value = window
        iface.addDockWidget.side_effect = window.addDockWidget
        iface.removeDockWidget.side_effect = window.removeDockWidget
        plugin = J3MConnect(iface)
        i18n.set_language('pt-br')
        plugin.initGui()
        self.addCleanup(window.close)
        self.addCleanup(plugin.unload)
        with patch('j3m_connect.dialog.ApiClient', FakeApi), \
                patch('j3m_connect.geofences.ApiClient', FakeApi), \
                patch('j3m_connect.dialog.settings.preferences', return_value=('', '')):
            plugin.run()
            layer = add_geojson_layer(fixture(), 'Keep this layer')
            layer_id = layer.id()
            self.addCleanup(lambda: QgsProject.instance().removeMapLayer(layer_id))
            for locale, save, action in (
                    ('en-us', 'Save and connect', 'Analyze layer in J3M'),
                    ('es-es', 'Guardar y conectar', 'Analizar capa en J3M'),
                    ('pt-br', 'Salvar e conectar', 'Analisar camada no J3M')):
                old = plugin.dialog
                old._select_menu('connection')
                self.assertIs(old.pages.currentWidget(), old.configPage)
                self.assertFalse(old.configPage.isAncestorOf(old.languageCombo))
                old._select_menu('language')
                self.assertIs(old.pages.currentWidget(), old.languagePage)
                self.assertTrue(old.languagePage.isAncestorOf(old.languageCombo))
                self.assertFalse(old.languagePage.isAncestorOf(old.clientEdit))
                self.assertIs(old.menuItems['language'].parent(), old.menuItems['connection'].parent())
                old.languageCombo.setCurrentIndex(old.languageCombo.findData(locale))
                old.applyLanguageButton.click()
                wait_for(lambda: plugin.dialog is not old)
                self.assertEqual(plugin.dialog.saveButton.text(), save)
                self.assertEqual(plugin.inspectAction.text(), action)
                self.assertEqual(plugin.dialog.menuItems['connection'].text(0), i18n.tr('Conexão'))
                self.assertEqual(plugin.dialog.menuItems['language'].text(0), i18n.tr('Idioma'))
                self.assertIs(plugin.dialog.pages.currentWidget(), plugin.dialog.languagePage)
                self.assertEqual(plugin.dialog.workbench.tabs.tabText(1), i18n.tr('Série'))
                self.assertIsNotNone(QgsProject.instance().mapLayer(layer_id))
            iface.addToolBarIcon.assert_called_once()

    def test_export_text_uses_selected_language(self):
        for locale in i18n.LANGUAGES:
            i18n.set_language(locale)
            payload = fixture()
            layer = add_geojson_layer(payload, 'Keep original <name>')
            try:
                configure_layer(layer, {'scope': 'local'})
                with tempfile.TemporaryDirectory() as directory:
                    root = Path(directory)
                    portable_study(layer, root / 'study')
                    readme = (root / 'study' / 'LEIA-ME.txt').read_text(encoding='utf-8')
                    self.assertIn({'pt-br': 'Abra', 'en-us': 'Open', 'es-es': 'Abra'}[locale] + ' estudo.qgz', readme)
                    job = Mock()
                    job.renderedImage.return_value = QImage(2, 2, QImage.Format.Format_RGB32)
                    document = Mock()
                    with patch('j3m_connect.cartography.QTextDocument', return_value=document):
                        _write_report(layer, str(root / 'report.pdf'), summarize(payload), job, directory)
                    html = document.setHtml.call_args.args[0]
                    self.assertIn(i18n.tr('Relatório de campanha'), html)
                    self.assertIn(i18n.tr('Observações baixadas'), html)
                    self.assertIn(i18n.tr('Umidade'), html)
                    self.assertIn('Keep original &lt;name&gt;', html)
            finally:
                QgsProject.instance().removeMapLayer(layer.id())

    def test_unload_cancels_pending_panel_rebuild(self):
        window = QMainWindow()
        iface = Mock()
        iface.mainWindow.return_value = window
        iface.addDockWidget.side_effect = window.addDockWidget
        iface.removeDockWidget.side_effect = window.removeDockWidget
        plugin = J3MConnect(iface)
        plugin.initGui()
        self.addCleanup(window.close)
        self.addCleanup(plugin.unload)
        with patch('j3m_connect.dialog.settings.preferences', return_value=('', '')):
            plugin.run()
            plugin.dialog.languageChanged.emit()
            plugin.unload()
            QgsApplication.processEvents()
            self.assertIsNone(plugin.dialog)
            self.assertIsNone(plugin.action)
            iface.addDockWidget.assert_called_once()
