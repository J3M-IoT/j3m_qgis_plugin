# SPDX-License-Identifier: GPL-3.0-or-later
"""Presentation adapters for the integration API; no business rules."""

import json
import math


def _response_data(payload):
    if payload is None:
        return None
    if not isinstance(payload, dict) or payload.get("success") is not True or "data" not in payload:
        raise ValueError("Resposta inválida: esperado um objeto com success=true e data.")
    return payload["data"]


def session_choices(payload):
    """Use the session UUID for requests and its name for presentation."""
    sessions = _response_data(payload)
    if sessions is None:
        return []
    if not isinstance(sessions, list):
        raise ValueError("Resposta inválida: data deve conter uma lista de sessões.")
    choices = []
    seen = set()
    for item in sessions:
        if not isinstance(item, dict) or not isinstance(item.get("uuid"), str) or not item["uuid"].strip():
            raise ValueError("A resposta contém uma sessão sem UUID válido.")
        identifier = item["uuid"].strip()
        if identifier in (".", "..") or any(ord(char) < 32 for char in identifier):
            raise ValueError("A resposta contém um identificador de sessão inválido.")
        if identifier in seen:
            raise ValueError("A resposta contém identificadores de sessão duplicados.")
        seen.add(identifier)
        label = item.get("name")
        choices.append((identifier, label.strip() if isinstance(label, str) and label.strip() else identifier))
    return choices


def indicator_text(payload):
    """Display all returned indicator fields, including unknown/optional ones."""
    payload = _response_data(payload)
    if payload is None or payload == {} or payload == []:
        return "Nenhum indicador disponível."
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def catalog_records(payload):
    choices = session_choices(payload)
    records = _response_data(payload) or []
    return [dict(record, uuid=identifier, name=label)
            for record, (identifier, label) in zip(records, choices)]


def indicator_rows(payload):
    data = _response_data(payload)
    if not data:
        return "Nenhum indicador disponível.", []
    if not isinstance(data, dict):
        raise ValueError("Formato de indicadores inválido.")
    condition = data.get("condition") or {}
    summary = "Total de coletas: {}".format(data.get("totalCollects", "—"))
    if isinstance(condition, dict) and condition.get("description"):
        summary += " · " + str(condition["description"])
    avgs = data.get("avgs") or []
    if isinstance(avgs, dict):
        avgs = [dict(value, name=value.get("name", key))
                for key, value in avgs.items() if isinstance(value, dict)]
    if not isinstance(avgs, list) or any(not isinstance(v, dict) for v in avgs):
        raise ValueError("Formato de médias inválido.")
    return summary, [(v.get("name", "—"), v.get("avg", "—"),
                      v.get("unit", ""), v.get("color", "")) for v in avgs]


def geofence_geojson(record):
    ring = []
    for point in record.get("points") or []:
        if not isinstance(point, dict):
            raise ValueError("Ponto de geocerca inválido.")
        lon, lat = point.get("lng"), point.get("lat")
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not math.isfinite(v) for v in (lon, lat)):
            raise ValueError("Coordenadas da geocerca inválidas.")
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            raise ValueError("Coordenadas da geocerca fora dos limites.")
        ring.append([lon, lat])
    if len(set(map(tuple, ring))) < 3:
        raise ValueError("A geocerca precisa de pelo menos três pontos distintos.")
    if ring[-1] != ring[0]:
        ring.append(ring[0])
    return {"type": "Feature", "geometry": {"type": "Polygon", "coordinates": [ring]},
            "properties": {key: record.get(key) for key in ("uuid", "name", "color")}}
