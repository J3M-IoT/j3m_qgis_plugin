"""Run with the QGIS Python interpreter, with QT_QPA_PLATFORM=offscreen."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from qgis.core import (QgsApplication, QgsExpression, QgsExpressionContext,
                       QgsFeature, QgsField, QgsVectorLayer)
from qgis.PyQt.QtCore import QVariant
from j3m_connect.map_tips import configure_map_tip


class MapTipTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QgsApplication([], False)
        cls.app.initQgis()

    def render(self, values):
        layer = QgsVectorLayer('Point', 'test', 'memory')
        layer.dataProvider().addAttributes([
            QgsField(key, QVariant.Bool if isinstance(value, bool) else QVariant.String)
            for key, value in values.items()])
        layer.updateFields()
        feature = QgsFeature(layer.fields())
        feature.setAttributes(list(values.values()))
        configure_map_tip(layer)
        context = QgsExpressionContext()
        context.setFeature(feature)
        context.setFields(layer.fields())
        import re
        def evaluate(match):
            expression = QgsExpression(match.group(1))
            self.assertFalse(expression.hasParserError(), expression.parserErrorString())
            result = expression.evaluate(context)
            self.assertFalse(expression.hasEvalError(), expression.evalErrorString())
            return str(result)
        return re.sub(r'\[% (.*?) %\]', evaluate, layer.mapTipTemplate(), flags=re.S)

    def test_dynamic_values_units_and_escape(self):
        html = self.render({'device_name': '<sensor>', 'condition_name': 'Bom',
                            'collectedAt': '2026-09-04T01:14:23',
                            'condition_hex': '#16865a', 'markerColor': '#ff0000',
                            'collects_temperatura': '0', 'collects_nova_value': '12',
                            'collects_nova_unit': 'ppm', 'collects_vazia': None,
                            'territorialContext_parque': 'Presente',
                            'geolocation_latitude': '-23', 'geolocation_longitude': '-46'})
        self.assertIn('background:#16865a', html)
        self.assertIn('04/09/2026 01:14:23', html)
        self.assertIn('&lt;sensor&gt;', html)
        self.assertIn('0,00<span class="unit">°C</span>', html)
        self.assertIn('12,00<span class="unit">ppm</span>', html)
        self.assertNotIn('Parque', html)
        self.assertNotIn('Vazia', html)
        self.assertIn('<span>Lat: -23</span><span>Lon: -46</span>', html)

    def test_empty_sections_and_unit_override(self):
        html = self.render({'collects_temperatura': '72', 'collects_temperatura_unit': '°F',
                            'territorialContext_parque': None, 'condition_hex': 'invalid',
                            'device_name': 'Sensor'})
        self.assertIn('72,00<span class="unit">°F</span>', html)
        self.assertNotIn('<h4>Contexto territorial</h4>', html)
        self.assertIn('background:#808080', html)

    def test_rounding_operation_and_territory(self):
        html = self.render({'collects_temperatura': '22.356', 'collects_nova': '-0.126',
                            'network_type': 'WIFI', 'network_signal': '80',
                            'device_battery': '100', 'firmware_version': '1.12',
                            'territorialContextDistance_vegetacao': '5', 'radius_meters': '200'})
        self.assertIn('22,36<span class="unit">°C</span>', html)
        self.assertIn('<b>-0,13</b>', html)
        self.assertIn('Wi-Fi · sinal 80,00%', html)
        self.assertIn('100,00%', html)
        self.assertIn('>1.12</span>', html)
        self.assertIn('Floresta ou vegetação · 5,00 m', html)
        self.assertIn('Raio de 200 m', html)
        self.assertNotIn('Outros dados</h4>', html)

    def test_invalid_date_and_unknown_text_are_preserved(self):
        html = self.render({'collectedAt': 'sem data', 'collects_nova': '<indisponível>',
                            'geolocation_latitude': '0', 'geolocation_longitude': None})
        self.assertIn('sem data', html)
        self.assertIn('&lt;indisponível&gt;', html)
        self.assertIn('<span>Lat: 0</span>', html)
        self.assertNotIn('Lon:', html)

    def test_coordinates_keep_precision_at_top(self):
        html = self.render({'geolocation_latitude': '-23.890320123456',
                            'geolocation_longitude': '-46.565139987654',
                            'collectedAt': '2026-09-04T01:14:23',
                            'collects_temperatura': '22.356'})
        self.assertIn('<span>Lat: -23.890320123456</span>', html)
        self.assertIn('<span>Lon: -46.565139987654</span>', html)
        self.assertLess(html.index('<div class="coordinates">'), html.index('<h4>Leituras ambientais'))
        self.assertLess(html.index('<div class="coordinates">'), html.index('<div class="summary">'))
        self.assertNotIn('Coordenadas</span>', html)
        self.assertIn('22,36<span class="unit">', html)
        self.assertNotIn('<div class="coordinates">', self.render({
            'geolocation_latitude': None, 'geolocation_longitude': None}))

    def test_large_collection_keeps_all_metrics_and_period(self):
        values = {'collects_dynamic_' + str(i): str(i) for i in range(60)}
        values.update({'territorialContext_long': 'Territorio' * 100,
                       'timePeriod': 'Último dado da coleta'})
        html = self.render(values)
        self.assertEqual(html.count('<div class="metric">'), 60)
        self.assertNotIn('Territorio' * 100, html)
        self.assertIn('<span>Período</span><b><span class="badge version">Último dado da coleta</span></b>', html)

    def test_sources_false_and_duplicate_radius_are_hidden(self):
        html = self.render({'source': 'hidden-source', 'territorialContext_source': 'hidden-nested',
                            'radius_meters': '200', 'territorialContext_radius_meters': '200.00',
                            'territorialContextDistance_radius_meters': '200',
                            'territorialContext_ausente': False, 'collects_inativa': ' FALSE ',
                            'collects_zero': '0', 'territorialContextDistance_vegetacao': '5'})
        self.assertEqual(html.count('Raio de 200 m'), 1)
        self.assertNotIn('200,00', html)
        for hidden in ('hidden-source', 'hidden-nested', 'Ausente', 'Inativa'):
            self.assertNotIn(hidden, html)
        self.assertIn('<b>0,00</b>', html)
        self.assertIn('Floresta ou vegetação', html)

    def test_empty_sections_and_nested_radius_fallback(self):
        html = self.render({'collects_inativa': False, 'territorialContext_ausente': False,
                            'territorialContext_source': 'hidden'})
        self.assertNotIn('<h4>', html)
        html = self.render({'radius_meters': None, 'territorialContext_radius_meters': '200.00'})
        self.assertEqual(html.count('Raio de 200 m'), 1)

    def test_territorial_flags_translations_and_hidden_fields(self):
        html = self.render({'territorialContext_has_water': True,
                            'territorialContextDistance_water': '12',
                            'territorialContext_has_forest': False,
                            'territorialContext_has_vegetation': True,
                            'use_queue': True, 'has_geolocation': True,
                            'is_working': True, 'device_id': 'secret-id',
                            'condition_id': 'secret-condition', 'geolocation_status': 'parado',
                            'timePeriod': 'night'})
        self.assertIn('Água · 12,00 m', html)
        self.assertNotIn('Vegetação</div>', html)
        self.assertIn('<span>Período</span><b><span class="badge night">☾ Noite</span></b>', html)
        for hidden in ('has_', 'true', 'Floresta', 'secret-id', 'secret-condition', 'parado', 'Use queue'):
            self.assertNotIn(hidden, html)
        self.assertIn('<span>Período</span><b><span class="badge day">☀ Dia</span></b>', self.render({'timePeriod': 'day'}))

    def test_percent_suffix_and_period_in_operation_table(self):
        for value in ('75', '75%', '75%%', '75 % '):
            with self.subTest(value=value):
                html = self.render({'device_battery': value, 'timePeriod': 'night'})
                self.assertIn('<span class="badge green">75,00%</span>', html)
                self.assertNotIn('%%', html)
                self.assertIn('<span>Período</span><b><span class="badge night">☾ Noite</span></b>', html)
                self.assertNotIn('class="footer"', html)

    def test_territory_is_one_translated_distance_per_metric(self):
        html = self.render({'territorialContext_has_water': True,
                            'territorialContext_agua': 'Água',
                            'territorialContextDistance_Water': '12',
                            'territorialContextDistance_water': '12',
                            'territorialContext_has_forest': True,
                            'territorialContextDistance_forest': None})
        self.assertEqual(html.count('Água · 12,00 m'), 1)
        self.assertNotIn('Water', html)
        self.assertNotIn('Floresta', html)
        self.assertNotIn('<div class="row">Água</div>', html)
        empty = self.render({'territorialContext_has_water': True,
                             'territorialContextDistance_water': None})
        self.assertNotIn('<h4>Contexto territorial</h4>', empty)

    def test_territory_labels_match_reference_and_strip_units(self):
        names = {'park_meter': 'Parque', 'water_meter': 'Água', 'railway_meters': 'Ferrovia',
                 'main_road_meter': 'Via principal', 'industrial_meter': 'Área industrial',
                 'residential_meter': 'Área residencial', 'commercial_meter': 'Área comercial',
                 'forest_or_vegetation_meter': 'Floresta ou vegetação'}
        values = {'territorialContextDistance_' + key: '143' for key in names}
        values.update({'territorialContext_has_water': True,
                       'territorialContextDistance_waterMeters': '143'})
        html = self.render(values)
        for label in names.values():
            self.assertEqual(html.count(label + ' · 143,00 m'), 1)
        self.assertNotIn('Water', html)
        self.assertNotIn(' meter', html)

    def test_device_geolocation_hidden_and_coordinates_preserved(self):
        html = self.render({'device_geolocation': 'hidden-location',
                            'geolocation_latitude': '-23.123456', 'timePeriod': ' DAY '})
        self.assertNotIn('hidden-location', html)
        self.assertNotIn('Device geolocation', html)
        self.assertIn('Lat: -23.123456', html)
        self.assertIn('<span class="badge day">☀ Dia</span>', html)

    def test_network_and_status_display_names(self):
        for network, status, network_label, status_label in (
            ('lte', 'online', '4G', 'Online'),
            ('wifi', 'offline', 'Wi-Fi', 'Offline'),
            (' WIFI ', ' ONLINE ', 'Wi-Fi', 'Online'),
            ('ethernet', 'unknown', 'ethernet', 'unknown'),
        ):
            with self.subTest(network=network, status=status):
                html = self.render({'network_type': network, 'device_status': status, 'mode': status})
                self.assertIn('<span>Rede</span><b>' + network_label + '</b>', html)
                self.assertIn('● ' + status_label + '</span>', html)
                self.assertIn('<span>Modo</span><b>' + status_label + '</b>', html)

    def test_battery_badge_boundaries_and_firmware_order(self):
        for value, color in ((100, 'green'), (75, 'green'), (74, 'yellow'), (50, 'yellow'),
                             (49, 'orange'), (25, 'orange'), (24, 'red'), (0, 'red')):
            with self.subTest(value=value):
                html = self.render({'device_battery': str(value), 'firmware_version': 'v1.2',
                                    'firmware_type': 'Mini'})
                self.assertIn('<span class="badge ' + color + '">', html)
                self.assertIn('<span class="badge version">v1.2</span>', html)
                self.assertLess(html.index('Tipo de Firmware</span>'), html.index('Versão</span>'))


if __name__ == '__main__':
    unittest.main()
