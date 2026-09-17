# SPDX-License-Identifier: GPL-3.0-or-later
"""Load direct GeoJSON responses as durable, local OGR vector layers."""

import json
from pathlib import Path
from uuid import uuid4
from qgis.PyQt.QtGui import QColor

from qgis.core import (
    Qgis, QgsApplication, QgsFillSymbol, QgsMarkerSymbol, QgsProject, QgsProperty,
    QgsSingleSymbolRenderer, QgsSymbolLayer, QgsVectorLayer, QgsWkbTypes,
)

from .map_tips import configure_map_tip, _text
from .adapters import geofence_geojson


def add_geojson_layer(payload, name, *, geofence=False):
    """Return the added layer, or None for an empty FeatureCollection."""
    if not isinstance(payload, dict):
        raise ValueError("GeoJSON deve ser um objeto Feature ou FeatureCollection.")
    kind = payload.get("type")
    if kind == "FeatureCollection":
        features = payload.get("features")
        if not isinstance(features, list):
            raise ValueError("FeatureCollection sem lista de feições válida.")
    elif kind == "Feature":
        features = [payload]
    else:
        raise ValueError("GeoJSON deve ser Feature ou FeatureCollection.")
    for feature in features:
        if (not isinstance(feature, dict) or feature.get("type") != "Feature"
                or "geometry" not in feature or "properties" not in feature
                or not isinstance(feature["properties"], (dict, type(None)))):
            raise ValueError("GeoJSON contém uma feição inválida.")
        geometry = feature["geometry"]
        if geometry is not None:
            _validate_geometry(geometry)
    if not features:
        return None
    try:
        serialized = json.dumps(payload, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as error:
        raise ValueError("GeoJSON contém valores inválidos.") from error
    directory = Path(QgsApplication.qgisSettingsDirPath()) / "j3m_connect" / "layers"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / (uuid4().hex + ".geojson")
    try:
        path.write_text(serialized, encoding="utf-8")
        # OGR discovers the union of attributes across all features. Flatten
        # objects for numeric metric columns without imposing a metric schema.
        uri = str(path) + "|option:FLATTEN_NESTED_ATTRIBUTES=YES"
        layer = QgsVectorLayer(uri, name, "ogr")
        if not layer.isValid() or layer.featureCount() != len(features):
            del layer
            raise ValueError("OGR não conseguiu carregar todas as feições GeoJSON.")
        if geofence:
            _style_geofence(layer, features[0]['properties'])
        else:
            _style_points(layer)
            configure_map_tip(layer)
        QgsProject.instance().addMapLayer(layer)
        return layer
    except Exception:
        path.unlink(missing_ok=True)
        raise


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
    layer.setMapTipTemplate('<div style="padding:6px"><strong>Geocerca: </strong>[% ' + _text('name') + ' %]</div>')
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
        raise ValueError("Geometria GeoJSON inválida.")
    kind = geometry.get("type")
    if kind == "GeometryCollection":
        geometries = geometry.get("geometries")
        if not isinstance(geometries, list):
            raise ValueError("GeometryCollection inválida.")
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
        raise ValueError("Tipo de geometria GeoJSON inválido.")
    coordinates = geometry.get("coordinates")
    _validate_coordinates(coordinates, depths[kind])
    lines = (
        [coordinates] if kind == "LineString"
        else coordinates if kind == "MultiLineString"
        else []
    )
    if any(len(line) < 2 for line in lines):
        raise ValueError("LineString deve conter pelo menos duas posições.")
    polygons = (
        [coordinates] if kind == "Polygon"
        else coordinates if kind == "MultiPolygon"
        else []
    )
    for polygon in polygons:
        for ring in polygon:
            if len(ring) < 4 or ring[0] != ring[-1]:
                raise ValueError(
                    "Anel de Polygon deve ser fechado e ter pelo menos quatro posições."
                )


def _validate_coordinates(value, depth):
    if not isinstance(value, list):
        raise ValueError("Coordenadas GeoJSON inválidas.")
    if depth:
        for child in value:
            _validate_coordinates(child, depth - 1)
    elif len(value) < 2 or any(
        isinstance(n, bool) or not isinstance(n, (int, float))
        for n in value
    ):
        raise ValueError("Posição GeoJSON inválida.")
