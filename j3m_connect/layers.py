# SPDX-License-Identifier: GPL-3.0-or-later
"""Load direct GeoJSON responses as durable, local OGR vector layers."""
from .i18n import tr

import json
import hashlib
from pathlib import Path
from uuid import uuid4
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt import sip

from qgis.core import (
    Qgis, QgsApplication, QgsFillSymbol, QgsMarkerSymbol, QgsProject, QgsProperty,
    QgsSingleSymbolRenderer, QgsSymbolLayer, QgsVectorLayer, QgsWkbTypes, QgsTask,
)

from .map_tips import configure_map_tip, _text
from .adapters import geofence_geojson


class LayerLoader(QObject):
    """Prepare private layers in a worker, transfer ownership, then publish in Qt."""
    busyChanged = pyqtSignal(bool)
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._task = None
        self._generation = 0

    def cancel(self):
        self._generation += 1
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self.busyChanged.emit(False)

    def load(self, payload, name, callback, *, geofence=False):
        self.cancel()
        generation = self._generation
        directory = Path(QgsApplication.qgisSettingsDirPath()) / 'j3m_connect' / 'layers'
        main_thread = QgsApplication.instance().thread()
        def finished(error, result=None):
            if sip.isdeleted(self) or generation != self._generation:
                discard_prepared(result)
                return
            self._task = None
            self.busyChanged.emit(False)
            if task.isCanceled():
                discard_prepared(result)
                self.failed.emit(tr('Preparação da camada cancelada.'))
                return
            if error:
                # Validation errors are local messages, never remote JSON bodies.
                self.failed.emit(str(error) if isinstance(error, ValueError) else tr('Não foi possível preparar a camada local.'))
                return
            if result is None:
                callback(None, None)
                return
            layer, path, digest = result
            try:
                if geofence:
                    features = payload.get('features') if payload.get('type') == 'FeatureCollection' else [payload]
                    _style_geofence(layer, features[0]['properties'])
                else:
                    _style_points(layer)
                    configure_map_tip(layer)
                QgsProject.instance().addMapLayer(layer)
                callback(layer, digest)
            except (ValueError, TypeError, OSError, RuntimeError, KeyError):
                if not sip.isdeleted(layer):
                    if QgsProject.instance().mapLayer(layer.id()) is not None:
                        QgsProject.instance().removeMapLayer(layer.id())
                    else:
                        sip.delete(layer)
                path.unlink(missing_ok=True)
                self.failed.emit(tr('Não foi possível concluir a camada local.'))
        task = QgsTask.fromFunction(
            tr('J3M: preparar camada'), _prepare_layer, payload=payload, name=name,
            directory=directory, target_thread=main_thread, on_finished=finished)
        self._task = task
        self.busyChanged.emit(True)
        QgsApplication.taskManager().addTask(self._task)


def discard_prepared(result):
    if result is not None:
        layer, path, _ = result
        sip.delete(layer)
        path.unlink(missing_ok=True)


def _prepare_layer(task, payload, name, directory, target_thread=None):
    """No live project, UI, settings, or existing layer is accessed here."""
    if task.isCanceled():
        return None
    if not isinstance(payload, dict):
        raise ValueError(tr('GeoJSON deve ser um objeto Feature ou FeatureCollection.'))
    kind = payload.get('type')
    if kind == 'FeatureCollection':
        features = payload.get('features')
        if not isinstance(features, list):
            raise ValueError(tr('FeatureCollection sem lista de feições válida.'))
    elif kind == 'Feature':
        features = [payload]
    else:
        raise ValueError(tr('GeoJSON deve ser Feature ou FeatureCollection.'))
    categories = {}
    for feature in features:
        if task.isCanceled():
            return None
        if (not isinstance(feature, dict) or feature.get('type') != 'Feature'
                or 'geometry' not in feature or 'properties' not in feature
                or not isinstance(feature['properties'], (dict, type(None)))):
            raise ValueError(tr('GeoJSON contém uma feição inválida.'))
        geometry = feature['geometry']
        if geometry is not None:
            _validate_geometry(geometry)
        props = feature.get('properties') or {}
        condition = props.get('condition') or {}
        # Category keys must stay stable when the interface language changes.
        caption = str(condition.get('name') or 'Sem condição') if isinstance(condition, dict) else 'Sem condição'
        color = str(props.get('markerColor') or '#808080')
        categories[caption+' | '+color] = (caption,color)
    if not features:
        return None
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (uuid4().hex + '.geojson')
    layer = None
    try:
        digest = hashlib.sha256()
        encoder = json.JSONEncoder(ensure_ascii=False, sort_keys=True, allow_nan=False)
        with path.open('wb') as stream:
            for chunk in encoder.iterencode(payload):
                if task.isCanceled():
                    break
                data = chunk.encode('utf-8')
                stream.write(data)
                digest.update(data)
        if task.isCanceled():
            path.unlink(missing_ok=True)
            return None
        layer = QgsVectorLayer(str(path)+'|option:FLATTEN_NESTED_ATTRIBUTES=YES', name, 'ogr')
        if not layer.isValid() or layer.featureCount() != len(features):
            raise ValueError(tr('OGR não conseguiu carregar todas as feições GeoJSON.'))
        layer.setCustomProperty('j3m/categories', json.dumps(categories, ensure_ascii=False))
        if task.isCanceled():
            sip.delete(layer)
            path.unlink(missing_ok=True)
            return None
        if target_thread is not None:
            layer.moveToThread(target_thread)
        return layer, path, digest.hexdigest()
    except Exception:
        if layer is not None and not sip.isdeleted(layer):
            sip.delete(layer)
        if path.exists():
            path.unlink()
        raise


def add_geojson_layer(payload, name, *, geofence=False):
    """Synchronous helper for scripts/tests; UI workflows use LayerLoader."""
    class Immediate:
        def isCanceled(self):
            return False
    directory = Path(QgsApplication.qgisSettingsDirPath()) / 'j3m_connect' / 'layers'
    result = _prepare_layer(Immediate(),payload,name,directory)
    if result is None:
        return None
    layer, _, _ = result
    if geofence:
        features = payload.get('features') if payload.get('type') == 'FeatureCollection' else [payload]
        _style_geofence(layer,features[0]['properties'])
    else:
        _style_points(layer)
        configure_map_tip(layer)
    QgsProject.instance().addMapLayer(layer)
    return layer


def add_geofence_layer(record):
    return add_geojson_layer(geofence_geojson(record), 'J3M — ' + record['name'], geofence=True)


def _style_geofence(layer, record):
    def color(value, fallback):
        result = QColor(value) if isinstance(value, str) else QColor()
        return result if result.isValid() else QColor(fallback)

    base = color(record.get('color'), '#16a34a')
    border = color(record.get('borderColor') or record.get('strokeColor'), base)
    fill = color(record.get('fillColor') or record.get('backgroundColor'), base)
    symbol = QgsFillSymbol.createSimple({
        'color': '{},{},{},64'.format(fill.red(), fill.green(), fill.blue()),
        'outline_color': border.name(), 'outline_style': 'solid', 'outline_width': '0.5',
    })
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    layer.setDisplayExpression('"name"')
    layer.setMapTipTemplate('<div style="padding:6px"><strong>' + tr('Geocerca: ') + '</strong>[% ' + _text('name') + ' %]</div>')
    if hasattr(layer, 'setMapTipsEnabled'):
        layer.setMapTipsEnabled(True)


def _style_points(layer):
    """Use only the backend markerColor hex; missing/invalid values stay gray."""
    point_type = Qgis.GeometryType.Point if hasattr(Qgis, 'GeometryType') else QgsWkbTypes.GeometryType.PointGeometry
    if layer.geometryType() != point_type:
        return
    symbol = QgsMarkerSymbol.createSimple({
        "name": "circle", "size": "3", "color": "#808080",
        "outline_color": "#ffffff", "outline_width": "0.2",
    })
    if layer.fields().indexFromName("markerColor") >= 0:
        expression = (
            "CASE WHEN regexp_match(trim(to_string(\"markerColor\")), "
            "'^#([0-9A-Fa-f]{6}|[0-9A-Fa-f]{3})$') "
            "THEN trim(to_string(\"markerColor\")) ELSE '#808080' END"
        )
        fill_property = (QgsSymbolLayer.Property.FillColor
                         if hasattr(QgsSymbolLayer.Property, 'FillColor')
                         else QgsSymbolLayer.Property.PropertyFillColor)
        symbol.symbolLayer(0).setDataDefinedProperty(
            fill_property,
            QgsProperty.fromExpression(expression),
        )
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def _validate_geometry(geometry):
    if not isinstance(geometry, dict):
        raise ValueError(tr("Geometria GeoJSON inválida."))
    kind = geometry.get("type")
    if kind == "GeometryCollection":
        geometries = geometry.get("geometries")
        if not isinstance(geometries, list):
            raise ValueError(tr("GeometryCollection inválida."))
        for child in geometries:
            _validate_geometry(child)
        return
    depths = {
        "Point": 0,
        "MultiPoint": 1,
        "LineString": 1,
        "MultiLineString": 2,
        "Polygon": 2,
        "MultiPolygon": 3,
    }
    if kind not in depths:
        raise ValueError(tr("Tipo de geometria GeoJSON inválido."))
    coordinates = geometry.get("coordinates")
    _validate_coordinates(coordinates, depths[kind])
    lines = (
        [coordinates] if kind == "LineString"
        else coordinates if kind == "MultiLineString"
        else []
    )
    if any(len(line) < 2 for line in lines):
        raise ValueError(tr("LineString deve conter pelo menos duas posições."))
    polygons = (
        [coordinates] if kind == "Polygon"
        else coordinates if kind == "MultiPolygon"
        else []
    )
    for polygon in polygons:
        for ring in polygon:
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError(
                    tr("Anel de Polygon deve ser fechado e ter pelo menos quatro posições.")
                )


def _validate_coordinates(value, depth):
    if not isinstance(value, list):
        raise ValueError(tr("Coordenadas GeoJSON inválidas."))
    if depth:
        for child in value:
            _validate_coordinates(child, depth - 1)
    elif len(value) < 2 or any(
        isinstance(n, bool) or not isinstance(n, (int, float))
        for n in value
    ):
        raise ValueError(tr("Posição GeoJSON inválida."))
