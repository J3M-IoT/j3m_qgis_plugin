# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable HTML map tips built from the actual OGR fields."""

from html import escape

from qgis.core import QgsExpression

LABELS = {
    "temperatura": "Temperatura", "umidade": "Umidade", "pressao": "Pressão",
    "ponto_orvalho": "Ponto de orvalho", "ruido": "Ruído", "altitude": "Altitude",
    "temperatura_superficial": "Temperatura superficial", "collectedAt": "Coletado em",
    "mode": "Modo", "timePeriod": "Período", "device_battery": "Bateria",
    "geolocation_latitude": "Latitude", "geolocation_longitude": "Longitude",
    "geolocation_velocidade": "Velocidade", "geolocation_status": "Movimento",
    "network_type": "Rede", "network_signal": "Sinal", "network_ssid": "SSID",
    "firmware_version": "Firmware", "firmware_type": "Tipo de firmware",
    "radius_meters": "Raio (m)", "source": "Fonte",
}


def _literal(value):
    return QgsExpression.quotedString(value)


def _value(field):
    return "attribute(@feature, {})".format(_literal(field))


def _present(field):
    value = _value(field)
    return "({0} IS NOT NULL AND trim(to_string({0})) NOT IN ('', '[]', '{{}}'))".format(value)


def _text(field):
    value = "to_string({})".format(_value(field))
    for source, target in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&#39;")):
        value = "replace({}, {}, {})".format(value, _literal(source), _literal(target))
    return value


def _item(field, before, after):
    return "CASE WHEN {} THEN {} || {} || {} ELSE '' END".format(
        _present(field), _literal(before), _text(field), _literal(after),
    )


def _section(title, fields, cards=False):
    if not fields:
        return "''"
    items = []
    for field, label in fields:
        label = escape(label)
        if cards:
            items.append(_item(field, '<div class="metric"><b>', '</b><small>' + label + '</small></div>'))
        else:
            items.append(_item(field, '<div class="row"><span>' + label + '</span><b>', '</b></div>'))
    return "CASE WHEN {} THEN {} || {} || {} ELSE '' END".format(
        " OR ".join(_present(f) for f, _ in fields),
        _literal('<section><h4>' + escape(title) + '</h4><div class="items">'),
        " || ".join(items), _literal('</div></section>'),
    )


def configure_map_tip(layer):
    """No fixed metric list, custom expression functions or generated attributes."""
    fields = layer.fields().names()
    header = []
    for field, tag in (("device_name", "strong"), ("device_type", "small"), ("condition_name", "b")):
        if field in fields:
            header.append(_item(field, '<' + tag + '>', '</' + tag + '>'))
    color = "'#808080'"
    # The condition controls the header; markerColor still controls the point.
    for field in ("markerColor", "condition_hex"):
        if field in fields:
            value = "trim(to_string({}))".format(_value(field))
            color = "CASE WHEN regexp_match({}, '^#([0-9A-Fa-f]{{6}}|[0-9A-Fa-f]{{3}})$') THEN {} ELSE {} END".format(value, value, color)
    parts = ["{} || {} || {} || {} || {}".format(
        _literal('<header style="background:'), color, _literal('">'),
        " || ".join(header) if header else "''", _literal('</header>'),
    )] if header else []
    if header:
        visible = [f for f in ("device_name", "device_type", "condition_name") if f in fields]
        parts[0] = "CASE WHEN {} THEN {} ELSE '' END".format(
            " OR ".join(_present(f) for f in visible), parts[0],
        )
    groups = {"Leituras ambientais": [], "Posição e operação": [], "Contexto territorial": [], "Outros dados": []}
    excluded = {"device_name", "device_type", "condition_name", "condition_hex", "condition_color",
                "condition_font", "condition_icon", "markerColor", "marker-color"}
    for field in fields:
        if field in excluded:
            continue
        if field.startswith("collects_"):
            group, label = "Leituras ambientais", field[len("collects_"):]
        elif field.startswith(("territorialContext_", "territorialContextDistance_")):
            group, label = "Contexto territorial", field.split("_", 1)[1]
        elif field.startswith(("device_", "geolocation_", "network_", "firmware_")) or field in ("collectedAt", "mode", "timePeriod"):
            group, label = "Posição e operação", field
        else:
            group, label = "Outros dados", field
        label = LABELS.get(label, label.replace("_", " "))
        groups[group].append((field, label[:1].upper() + label[1:]))
    for title, entries in groups.items():
        parts.append(_section(title, entries, title == "Leituras ambientais"))
    css = """<style>
    body{margin:0;font-family:Arial,sans-serif;color:#164761;font-size:12px}
    .card{width:350px;background:#fafcfd;border:1px solid #d6e4e8;border-radius:10px;overflow:hidden}
    header{padding:12px;color:white}header strong{display:block;font-size:16px}
    header small{display:block;margin-top:4px}header b{display:inline-block;margin-top:8px;padding:4px 9px;background:rgba(255,255,255,.2);border-radius:15px}
    .content{padding:0 12px 10px;max-height:440px;overflow:auto}
    section{margin-top:12px}h4{font-size:9px;letter-spacing:1px;text-transform:uppercase;margin:0 0 5px;color:#39748a}
    .metric{display:inline-block;vertical-align:top;box-sizing:border-box;width:31%;margin:0 2% 5px 0;padding:8px 4px;text-align:center;background:#f0f5f8;border:1px solid #dce7eb;border-radius:7px;overflow-wrap:anywhere}
    .metric b{font-size:14px}.metric small{display:block;font-size:10px;margin-top:4px}
    .row{padding:5px 0;border-bottom:1px solid #edf1f3;overflow-wrap:anywhere}
    .row span{display:inline-block;width:44%;vertical-align:top;color:#658898}
    .row b{display:inline-block;width:56%;text-align:right;font-weight:500}
    </style>"""
    template = css + '<div class="card">'
    if header:
        template += '[% ' + parts.pop(0) + ' %]'
    template += '<div class="content">'
    template += ''.join('[% ' + part + ' %]' for part in parts) + '</div></div>'
    layer.setMapTipTemplate(template)
    if hasattr(layer, "setMapTipsEnabled"):
        layer.setMapTipsEnabled(True)
