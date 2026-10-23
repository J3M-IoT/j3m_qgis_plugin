# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only summaries of downloaded observations. No server business rules."""
from .i18n import tr
import math
from collections import Counter, defaultdict
from datetime import datetime
from statistics import mean, median, pstdev


def number(value):
    # Never interpret booleans, missing values or numeric strings as measurements.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def timestamp(value):
    try:
        dt = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return dt.timestamp() if dt.tzinfo else None
    except (ValueError, TypeError, OverflowError, OSError):
        return None


def metric_values(properties):
    values = properties.get('collects') or {}
    return {str(k): (v.get('value') if isinstance(v, dict) else v)
            for k, v in values.items()} if isinstance(values, dict) else {}


def series_plot(points):
    """Prepare a bounded display once, outside paintEvent and the Qt thread."""
    if not points:
        return None
    groups = {}
    for point in points:
        groups.setdefault(point[3], []).append(point)
    budget = max(1,4000 // max(1,len(groups)))
    prepared = []
    reduced = len(groups)>4000
    for device, values in list(groups.items())[:4000]:
        values.sort(key=lambda p:(p[0],p[2]))
        gaps = [b[0]-a[0] for a,b in zip(values,values[1:]) if b[0]>a[0]]
        limit = max(1,median(gaps)*3) if gaps else 1
        stride = max(1,(len(values)+budget-1)//budget)
        reduced = reduced or stride>1
        prepared.append((device,values[::stride],limit,stride))
    return {'bounds':(min(p[0] for p in points),max(p[0] for p in points),
                      min(p[1] for p in points),max(p[1] for p in points)),
            'groups':prepared,'reduced':reduced}


def summarize(payload, canceled=None):
    features = payload.get('features', []) if isinstance(payload, dict) else []
    metrics = defaultdict(list)
    units = defaultdict(set)
    series = defaultdict(list)
    distributions = {key: Counter() for key in ('condition', 'timePeriod', 'mode', 'device')}
    ids = Counter()
    device_order = Counter()
    categories = {}
    invalid_geometry = invalid_time = 0
    for index, feature in enumerate(features):
        if canceled is not None and canceled():
            return None
        prop = feature.get('properties') or {}
        condition = prop.get('condition') or {}
        caption = str(condition.get('name') or 'Sem condição') if isinstance(condition, dict) else 'Sem condição'
        color = str(prop.get('markerColor') or '#808080')
        categories[caption+' | '+color] = (caption,color)
        geometry = feature.get('geometry') or {}
        coords = geometry.get('coordinates') or []
        if not (geometry.get('type') == 'Point' and len(coords) >= 2
                and number(coords[0]) and number(coords[1])
                and -180 <= coords[0] <= 180 and -90 <= coords[1] <= 90):
            invalid_geometry += 1
        when = timestamp(prop.get('collectedAt'))
        invalid_time += when is None
        identifier = feature.get('id')
        if identifier is not None:
            ids[str(identifier)] += 1
        device = prop.get('device') or {}
        device_name = str(device.get('name') or device.get('uuid') or tr('Sem dispositivo'))
        device_id = str(device.get('uuid') or device.get('_id') or device.get('id') or device_name)
        ordinal = device_order[device_id]
        device_order[device_id] += 1
        for key in distributions:
            value = prop.get(key)
            if key == 'device':
                value = device_name
            elif isinstance(value, dict):
                value = value.get('name') or value.get('description') or value.get('color')
            distributions[key][str(value if value is not None else tr('Não informado'))] += 1
        for metric, value in metric_values(prop).items():
            metrics[metric]  # Include a metric even if every observation is null.
            raw = (prop.get('collects') or {}).get(metric)
            if isinstance(raw, dict) and (raw.get('unit') or raw.get('unidade')):
                units[metric].add(str(raw.get('unit') or raw.get('unidade')))
            if number(value):
                metrics[metric].append(value)
                if when is not None:
                    series[metric].append((when, value, index, device_id, ordinal))
    stats = {}
    for metric, values in sorted(metrics.items()):
        if canceled is not None and canceled():
            return None
        stats[metric] = {'n': len(values), 'missing': len(features) - len(values),
                         'min': min(values) if values else None, 'max': max(values) if values else None,
                         'mean': mean(values) if values else None, 'median': median(values) if values else None,
                         'std': pstdev(values) if values else None}
        if len(units.get(metric,set()))>1:
            for key in ('min','max','mean','median','std'):
                stats[metric][key] = None
            series[metric] = []
    for points in series.values():
        points.sort(key=lambda row: (row[3], row[0], row[2]))
    return {'count': len(features), 'invalid_geometry': invalid_geometry, 'invalid_time': invalid_time,
            'duplicates': sum(n - 1 for n in ids.values()), 'missing_ids': len(features) - sum(ids.values()),
            'stats': stats, 'units': dict(units), 'series': dict(series), 'distributions': distributions, 'categories':categories,
            'plots':{metric:series_plot(points) for metric,points in series.items()}}


def display(value):
    if value is None:
        return '—'
    if number(value):
        return format(value, '.2f').replace('.', ',')
    return str(value)


def layer_payload(layer, transform_context=None, canceled=None, fids=None):
    """Reconstruct nested observations from OGR fields for offline inspection."""
    features = []
    names = [field.name() for field in layer.fields()]
    from qgis.core import (NULL, Qgis, QgsWkbTypes, QgsCoordinateTransform,
                           QgsCoordinateReferenceSystem, QgsProject, QgsCsException)
    from qgis.PyQt.QtCore import Qt
    point_type = Qgis.GeometryType.Point if hasattr(Qgis,'GeometryType') else QgsWkbTypes.GeometryType.PointGeometry
    target = QgsCoordinateReferenceSystem('EPSG:4326')
    context = transform_context if transform_context is not None else QgsProject.instance().transformContext()
    transform = QgsCoordinateTransform(layer.crs(),target,context) if layer.crs().isValid() and layer.crs()!=target else None
    for feature in layer.getFeatures():
        if canceled is not None and canceled():
            return None
        if fids is not None:
            fids.append(feature.id())
        props = {'collects': {}, 'device': {}, 'condition': {}}
        identifier = None
        for name, value in zip(names, feature.attributes()):
            if value is None or value == NULL:
                value = None
            if name.startswith('collects_'):
                key = name[9:]
                if key.endswith(('_unit', '_unidade', '_value')):
                    base, suffix = key.rsplit('_', 1)
                    if not isinstance(props['collects'].get(base), dict):
                        props['collects'][base] = {}
                    props['collects'][base][suffix] = value
                else:
                    props['collects'][key] = value
            elif name.startswith('device_'):
                props['device'][name[7:]] = value
            elif name.startswith('condition_'):
                props['condition'][name[10:]] = value
            elif name == 'collectedAt':
                props[name] = value.toString(Qt.DateFormat.ISODate) if hasattr(value, 'toString') else value
            elif name in ('mode', 'timePeriod', 'markerColor'):
                props[name] = value
            elif name == 'id':
                identifier = value
        geom = feature.geometry()
        geometry = None
        if layer.crs().isValid() and not geom.isNull() and geom.type() == point_type and not geom.isMultipart():
            try:
                pt = transform.transform(geom.asPoint()) if transform else geom.asPoint()
                geometry = {'type': 'Point', 'coordinates': [pt.x(), pt.y()]}
            except QgsCsException:
                pass
        features.append({'type': 'Feature', 'id': identifier, 'properties': props, 'geometry': geometry})
    return {'type': 'FeatureCollection', 'features': features}
