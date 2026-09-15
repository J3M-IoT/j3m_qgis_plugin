# SPDX-License-Identifier: GPL-3.0-or-later
"""Portable HTML map tips built from the actual OGR fields."""

from html import escape
import re

from qgis.core import QgsExpression

LABELS = {
    "temperatura": "Temperatura", "umidade": "Umidade", "pressao": "Pressão",
    "ponto_orvalho": "Ponto de orvalho", "ruido": "Ruído", "altitude": "Altitude",
    "temperatura_superficial": "Temperatura superficial", "collectedAt": "Coletado em",
    "mode": "Modo", "timePeriod": "Período", "device_battery": "Bateria",
    "geolocation_latitude": "Latitude", "geolocation_longitude": "Longitude",
    "geolocation_velocidade": "Velocidade", "geolocation_status": "Movimento",
    "network_type": "Rede", "network_signal": "Sinal", "network_ssid": "SSID",
    "firmware_version": "Versão", "firmware_type": "Tipo de Firmware",
    "radius_meters": "Raio", "source": "Fonte", "vegetacao": "Vegetação",
    "vegetation": "Vegetação",
    "water": "Água", "water_body": "Corpo d’água", "river": "Rio", "lake": "Lago",
    "forest": "Floresta", "trees": "Árvores", "building": "Edificação",
    "buildings": "Edificações", "road": "Via", "roads": "Vias", "urban": "Área urbana",
    "urban_area": "Área urbana", "park": "Parque", "green_area": "Área verde",
}

TERRITORY_LABELS = {
    "park": "Parque", "parque": "Parque",
    "water": "Água", "agua": "Água", "água": "Água",
    "railway": "Ferrovia", "railroad": "Ferrovia", "rail": "Ferrovia", "ferrovia": "Ferrovia",
    "main_road": "Via principal", "major_road": "Via principal", "highway": "Via principal",
    "road": "Via principal", "via_principal": "Via principal",
    "industrial": "Área industrial", "industrial_area": "Área industrial", "area_industrial": "Área industrial",
    "residential": "Área residencial", "residential_area": "Área residencial", "area_residencial": "Área residencial",
    "commercial": "Área comercial", "commercial_area": "Área comercial", "area_comercial": "Área comercial",
    "forest": "Floresta ou vegetação", "vegetation": "Floresta ou vegetação",
    "forest_or_vegetation": "Floresta ou vegetação", "forest_vegetation": "Floresta ou vegetação",
    "floresta": "Floresta ou vegetação", "vegetacao": "Floresta ou vegetação",
    "vegetação": "Floresta ou vegetação",
}

# Display defaults for known measurements; unknown metrics remain visible.
UNITS = {"temperatura": "°C", "temperatura_superficial": "°C", "ponto_orvalho": "°C",
         "umidade": "%", "pressao": "hPa", "altitude": "m", "ruido": "dB",
         "geolocation_velocidade": "km/h", "device_battery": "%", "network_signal": "%",
         "radius_meters": "m"}


def _number(field):
    value = "trim(to_string({}))".format(_value(field))
    # Do not cast text, booleans, firmware versions or identifiers to numbers.
    if field.startswith("firmware_") or field.endswith(("_id", "_uuid")):
        return _text(field)
    return ("CASE WHEN regexp_match({0}, '^[+-]?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$') "
            "THEN format_number(to_real({0}), 2, 'pt_BR', true) ELSE {1} END").format(value, _text(field))


def _measurement(field, fields, compact=False):
    key = field.removeprefix("collects_")
    base = field[:-6] if field.endswith("_value") else field
    key = key[:-6] if field.endswith("_value") else key
    unit = _literal("m" if field.startswith("territorialContextDistance_") else UNITS.get(key, ""))
    for candidate in (base + "_unit", base + "_unidade"):
        if candidate in fields:
            unit = "CASE WHEN {} THEN {} ELSE {} END".format(_present(candidate), _text(candidate), unit)
    prefix = (_literal('<span class="unit">') if compact else
              "CASE WHEN " + unit + " = '%' THEN '' ELSE ' ' END")
    return (_number(field) + " || CASE WHEN " + unit + " <> '' THEN "
            + prefix
            + " || " + unit + " || " + _literal('</span>' if compact else '') + " ELSE '' END")


def _literal(value):
    return QgsExpression.quotedString(value)


def _value(field):
    return "attribute(@feature, {})".format(_literal(field))


def _present(field):
    value = _value(field)
    return "({0} IS NOT NULL AND lower(trim(to_string({0}))) NOT IN ('', '[]', '{{}}', 'false'))".format(value)


def _is_radius(field):
    return field == "radius_meters" or field.endswith("_radius_meters")


def _radius(fields):
    # Flattened metadata can repeat the radius in both territorial objects.
    # Prefer the top-level value, then the first populated nested value.
    candidates = sorted((field for field in fields if _is_radius(field)),
                        key=lambda field: field != "radius_meters")
    result = "''"
    for field in reversed(candidates):
        value = "trim(to_string({}))".format(_value(field))
        number = ("CASE WHEN regexp_match({0}, '^[+-]?[0-9]+([.][0-9]+)?$') "
                  "THEN format_number(to_real({0}), 0, 'pt_BR', true) ELSE {1} END").format(value, _text(field))
        result = "CASE WHEN {} THEN '<div class=\"radius\">Raio de ' || {} || ' m</div>' ELSE {} END".format(
            _present(field), number, result)
    return result


def _text(field):
    value = "to_string({})".format(_value(field))
    for source, target in (("&", "&amp;"), ("<", "&lt;"), (">", "&gt;"), ('"', "&quot;"), ("'", "&#39;")):
        value = "replace({}, {}, {})".format(value, _literal(source), _literal(target))
    if field == "timePeriod":
        value = "CASE WHEN lower(trim(to_string({0}))) = 'day' THEN 'Dia' WHEN lower(trim(to_string({0}))) = 'night' THEN 'Noite' ELSE {1} END".format(_value(field), value)
    translations = {
        "network_type": {"lte": "4G", "wifi": "Wi-Fi"},
        "device_status": {"online": "Online", "offline": "Offline"},
        "mode": {"online": "Online", "offline": "Offline"},
    }
    for source, label in translations.get(field, {}).items():
        value = "CASE WHEN lower(trim(to_string({}))) = {} THEN {} ELSE {} END".format(
            _value(field), _literal(source), _literal(label), value)
    return value


def _territory_key(field):
    key = field.split("_", 1)[1]
    key = re.sub(r"([a-z])([A-Z])", r"\1_\2", key).lower()
    key = re.sub(r"[\s-]+", "_", key)
    key = key[4:] if key.startswith("has_") else key
    # Unit suffixes describe the value, not the territorial metric's name.
    key = re.sub(r"_(?:distance_)?(?:meters?|metres?|m)$", "", key)
    return TERRITORY_LABELS.get(key, LABELS.get(key, key)).lower()


def _territory_item(key, candidates, fields):
    label = LABELS.get(key, key.replace("_", " "))
    label = escape(label[:1].upper() + label[1:])
    result = "''"
    # Only distance-bearing items belong in this section, never presence flags.
    for field in reversed(candidates):
        if not field.startswith("territorialContextDistance_"):
            continue
        number = "try(to_real({}), NULL)".format(_value(field))
        result = "CASE WHEN {} AND {} >= 0 THEN {} || {} || ' m</div>' ELSE {} END".format(
            _present(field), number, _literal('<div class="row">' + label + ' · '),
            "format_number({}, 2, 'pt_BR', true)".format(number), result)
    return result


def _badge(field, fields):
    content = _measurement(field, fields)
    color = "'version'"
    if field == "timePeriod":
        period = "lower(trim(to_string({})))".format(_value(field))
        return ("CASE WHEN {0} = 'day' THEN '<span class=\"badge day\">☀ Dia</span>' "
                "WHEN {0} = 'night' THEN '<span class=\"badge night\">☾ Noite</span>' "
                "ELSE '<span class=\"badge version\">' || {1} || '</span>' END").format(period, _text(field))
    if field == "device_battery":
        # The API may supply either a number or an already suffixed percentage.
        number = "try(to_real(regexp_replace(trim(to_string({})), '[% ]+$', '')), NULL)".format(_value(field))
        content = "CASE WHEN {0} IS NOT NULL THEN format_number({0}, 2, 'pt_BR', true) || '%' ELSE {1} END".format(number, _text(field))
        color = ("CASE WHEN {0} >= 75 AND {0} <= 100 THEN 'green' "
                 "WHEN {0} >= 50 AND {0} < 75 THEN 'yellow' "
                 "WHEN {0} >= 25 AND {0} < 50 THEN 'orange' "
                 "WHEN {0} >= 0 AND {0} < 25 THEN 'red' ELSE 'version' END").format(number)
    return "'<span class=\"badge ' || " + color + " || '\">' || " + content + " || '</span>'"


def _item(field, before, after):
    return "CASE WHEN {} THEN {} || {} || {} ELSE '' END".format(
        _present(field), _literal(before), _text(field), _literal(after),
    )


def _combined_row(label, candidates, fields, separator=" · "):
    available = [field for field in candidates if field in fields]
    if not available:
        return "''"
    pieces = []
    for index, field in enumerate(available):
        prefix = "''"
        if index:
            prefix = "CASE WHEN {} THEN {} ELSE '' END".format(
                " OR ".join(_present(previous) for previous in available[:index]), _literal(separator))
        pieces.append("CASE WHEN {} THEN {} || {} ELSE '' END".format(
            _present(field), prefix, ("'sinal ' || " if field == "network_signal" else "") + _measurement(field, fields)))
    return "CASE WHEN {} THEN {} || {} || '</b></div>' ELSE '' END".format(
        " OR ".join(_present(field) for field in available),
        _literal('<div class="row"><span>' + escape(label) + '</span><b>'), " || ".join(pieces))


def _section(title, fields, cards=False, all_fields=()):
    if not fields:
        return "''"
    order = (["collects_temperatura", "collects_umidade", "collects_pressao",
              "collects_ponto_orvalho", "collects_altitude"] if cards else
             ["device_battery", "firmware_type", "firmware_version", "timePeriod"])
    def rank(entry):
        field = entry[0]
        base = field[:-6] if field.endswith("_value") else field
        return order.index(base) if base in order else len(order)
    fields = sorted(fields, key=rank)
    items = []
    combined = set()
    if title == "Contexto territorial":
        for field, label in fields:
            if _is_radius(field):
                continue
            if field in combined:
                continue
            key = _territory_key(field)
            candidates = [name for name, _ in fields if not _is_radius(name) and _territory_key(name) == key]
            items.append(_territory_item(key, candidates, all_fields))
            combined.update(candidates)
        items.append(_radius(all_fields))
        combined.update(field for field in all_fields if _is_radius(field))
    if title == "Posição e operação":
        for label, candidates, separator in (
            ("Velocidade", ("geolocation_velocidade",), " · "),
            ("Rede", ("network_type", "network_signal"), " · "),
        ):
            items.append(_combined_row(label, candidates, all_fields, separator))
            combined.update(candidates)
    for field, label in fields:
        if field in combined:
            continue
        label = escape(label)
        if cards:
            items.append("CASE WHEN {} THEN {} || {} || {} ELSE '' END".format(
                _present(field), _literal('<div class="metric"><b>'),
                _measurement(field, all_fields, compact=True), _literal('</b><small>' + label + '</small></div>')))
        else:
            items.append("CASE WHEN {} THEN {} || {} || {} ELSE '' END".format(
                _present(field), _literal('<div class="row"><span>' + label + '</span><b>'),
                _badge(field, all_fields) if field in ("device_battery", "firmware_version", "timePeriod") else _measurement(field, all_fields), _literal('</b></div>')))
    return "CASE WHEN {} THEN {} || {} || {} ELSE '' END".format(
        "({}) <> ''".format(" || ".join(items)) if title == "Contexto territorial" else " OR ".join(_present(f) for f, _ in fields),
        _literal('<div class="section ' + ('territory' if title == "Contexto territorial" else 'readings' if cards else 'operation') + '"><h4>' + escape(title) + '</h4><div class="items">'),
        " || ".join(items), _literal('</div></div>'),
    )


def configure_map_tip(layer):
    """No fixed metric list, custom expression functions or generated attributes."""
    fields = layer.fields().names()
    header = []
    for field, tag in (("condition_name", "b"), ("device_name", "strong"), ("device_type", "small")):
        if field in fields:
            header.append(_item(field, '<' + tag + '>', '</' + tag + '>'))
    color = "'#808080'"
    # The condition controls the header; markerColor still controls the point.
    for field in ("markerColor", "condition_hex"):
        if field in fields:
            value = "trim(to_string({}))".format(_value(field))
            color = "CASE WHEN regexp_match({}, '^#([0-9A-Fa-f]{{6}}|[0-9A-Fa-f]{{3}})$') THEN {} ELSE {} END".format(value, value, color)
    parts = ["{} || {} || {} || {} || {}".format(
        _literal('<div class="header" style="background:'), color, _literal('">'),
        " || ".join(header) if header else "''", _literal('</div>'),
    )] if header else []
    if header:
        visible = [f for f in ("device_name", "device_type", "condition_name") if f in fields]
        parts[0] = "CASE WHEN {} THEN {} ELSE '' END".format(
            " OR ".join(_present(f) for f in visible), parts[0],
        )
    summary = []
    for field in ("device_status", "collectedAt"):
        if field in fields:
            if field == "collectedAt":
                date = "try(to_datetime({}), NULL)".format(_value(field))
                formatted = "CASE WHEN {} IS NOT NULL THEN format_date({}, 'dd/MM/yyyy HH:mm:ss') ELSE {} END".format(date, date, _text(field))
                summary.append("CASE WHEN {} THEN '<span class=\"collectedAt\">' || {} || '</span>' ELSE '' END".format(_present(field), formatted))
            else:
                summary.append(_item(field, '<span class="' + field + '">● ', '</span>'))
    coordinates = [field for field in ("geolocation_latitude", "geolocation_longitude") if field in fields]
    if coordinates:
        values = []
        for field in coordinates:
            # Preserve the source precision; coordinates are location, not a
            # measurement to round to the two-decimal presentation default.
            label = "Lat: " if field == "geolocation_latitude" else "Lon: "
            values.append(_item(field, '<span>' + label, '</span>'))
        parts.append("CASE WHEN {} THEN '<div class=\"coordinates\">' || {} || '</div>' ELSE '' END".format(
            " OR ".join(_present(field) for field in coordinates), " || ".join(values)))
    if summary:
        parts.append("'<div class=\"summary\">' || " + " || ".join(summary) + " || '</div>'")
    groups = {"Leituras ambientais": [], "Posição e operação": [], "Contexto territorial": [], "Outros dados": []}
    excluded = {"device_name", "device_type", "condition_name", "condition_hex", "condition_color",
                "condition_font", "condition_icon", "markerColor", "marker-color", "device_status", "collectedAt",
                "use_queue", "has_geolocation", "is_working", "device_id", "device_geolocation", "condition_id", "condition_uuid", "geolocation_status",
                "geolocation_latitude", "geolocation_longitude"}
    for field in fields:
        if (field in excluded or field == "source" or field.endswith("_source")
                or field.endswith(("_use_queue", "_has_geolocation", "_is_working"))):
            continue
        if field.endswith(("_unit", "_unidade")):
            base = field.rsplit("_", 1)[0]
            if base in fields or base + "_value" in fields:
                continue
        if field.startswith("collects_"):
            group, label = "Leituras ambientais", field[len("collects_"):]
            if label.endswith("_value"):
                label = label[:-6]
        elif field.startswith(("territorialContext_", "territorialContextDistance_")) or _is_radius(field):
            group, label = "Contexto territorial", field.split("_", 1)[1] if not _is_radius(field) else "radius_meters"
        elif field.startswith(("device_", "geolocation_", "network_", "firmware_")) or field in ("collectedAt", "mode", "timePeriod"):
            group, label = "Posição e operação", field
        else:
            group, label = "Outros dados", field
        label = LABELS.get(label, label.replace("_", " "))
        groups[group].append((field, label[:1].upper() + label[1:]))
    for title, entries in groups.items():
        parts.append(_section(title, entries, title == "Leituras ambientais", fields))
    css = """<style>
    body{margin:0;padding:0}
    .card{box-sizing:border-box;width:350px;max-width:100%;height:auto;background:#fafcfd;border:1px solid #d6e4e8;border-radius:10px;overflow:auto;font-family:'Segoe UI',Arial,sans-serif;color:#164761;font-size:14px;line-height:1.25;text-align:left;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere}
    .card .header{display:block;box-sizing:border-box;min-height:54px;padding:10px 12px 8px;color:#fff;overflow:hidden}
    .card .header strong{display:block;font-size:15px;line-height:19px;font-weight:700;word-wrap:break-word}
    .card .header small{display:block;margin-top:1px;font-size:10px;line-height:14px}
    .card .header b{float:right;max-width:40%;margin:3px 0 0 8px;padding:5px 8px;background:rgba(255,255,255,.2);border-radius:15px;font-size:15px;line-height:20px;word-wrap:break-word}
    .card .content{padding:0 12px 4px}
    .card .summary{overflow:hidden;padding:11px 0 0;min-height:20px;font-size:14px;line-height:20px}
    .card .device_status{float:left;max-width:100%;margin-right:10px;word-wrap:break-word}.card .collectedAt{float:left;max-width:100%;word-wrap:break-word}
    .card .coordinates{clear:both;margin-top:3px;font-size:10px;line-height:14px;color:#658898;white-space:normal;word-wrap:break-word;overflow-wrap:anywhere}
    .card .coordinates span{display:inline-block;max-width:100%;margin-right:8px;vertical-align:top}
    .card .section{display:block;margin-top:9px}
    .card h4{font-size:9px;line-height:12px;font-weight:500;letter-spacing:1px;text-transform:uppercase;margin:0 0 4px;color:#39748a}
    .card .readings .items{font-size:0;margin-right:-4px}
    .card .metric{display:inline-block;vertical-align:top;box-sizing:border-box;width:31.9%;width:calc(33.333333% - 4px);min-height:49px;margin:0 4px 4px 0;padding:6px 3px;text-align:center;background:#f2f6f9;border:1px solid #dce7eb;border-radius:7px;word-wrap:break-word}
    .card .metric b{font-size:15px;line-height:19px;font-weight:700}
    .card .metric small{display:block;font-size:9px;line-height:12px;margin-top:1px;font-weight:400}
    .card .unit{font-size:8px;font-weight:400;margin-left:2px;vertical-align:baseline;color:#39748a}
    .card .operation .items{background:#f2f6f9;padding:4px 8px}
    .card .row{display:table;table-layout:fixed;width:100%;box-sizing:border-box;padding:3px 0;border-bottom:1px solid #e5ecf0;font-size:14px;line-height:19px;word-wrap:break-word}
    .card .row:last-child{border-bottom:0}
    .card .row>span{display:table-cell;width:34%;vertical-align:top;color:#658898}
    .card .row>b{display:table-cell;text-align:right;font-weight:500}
    .card .badge{display:inline-block;border-radius:10px;padding:1px 7px;font-size:12px;font-weight:600}
    .card .badge.green{background:#d9f2e3;color:#17683b}
    .card .badge.yellow{background:#fff1b8;color:#765700}
    .card .badge.orange{background:#ffe0bd;color:#934600}
    .card .badge.red{background:#fbdada;color:#a12626}
    .card .badge.version{background:#e1ebf3;color:#315d7a}
    .card .badge.day{background:#fff1b8;color:#765700}
    .card .badge.night{background:#e4e5f6;color:#494375}
    .card .territory{background:#edf7f4;border:1px solid #d4e6e2;border-radius:7px;padding:7px 8px;margin-top:10px}
    .card .territory .row{display:inline-block;width:auto;max-width:100%;background:white;border:1px solid #d4e6e2;border-radius:12px;padding:2px 6px;margin:0 4px 4px 0;font-size:9px;line-height:13px}
    .card .territory .row>span,.card .territory .row>b{display:inline;width:auto;text-align:left;color:#39748a;font-weight:400}
    .card .territory .row>span:after{content:' · ';white-space:pre}
    .card .radius{font-size:9px;line-height:14px;color:#658898;margin-top:1px}
    </style>"""
    template = css + '<div class="card">'
    if header:
        template += '[% ' + parts.pop(0) + ' %]'
    template += '<div class="content">'
    template += ''.join('[% ' + part + ' %]' for part in parts) + '</div></div>'
    # QGIS first measures the HTML, then clamps its web view to the available
    # canvas space with the outer scrollbars disabled. Fit AFTER that resize:
    # retain natural height for short cards and scroll inside long ones.
    # ES5 works in the Qt WebKit shipped with QGIS 3; no external resources.
    template += """<script>
    (function () {
        function fitMapTip() {
            var card = document.querySelector('.card');
            var frame = document.getElementById('QgsWebViewContainer');
            if (!card || !frame) return;
            var width = window.innerWidth || document.documentElement.clientWidth;
            var height = window.innerHeight || document.documentElement.clientHeight;
            if (width <= 12 || height <= 12) return;
            card.style.width = Math.min(350, width - 12) + 'px';
            card.style.maxHeight = (height - 12) + 'px';
        }
        window.addEventListener('resize', fitMapTip, false);
        window.addEventListener('load', function () {
            window.setTimeout(fitMapTip, 0);
        }, false);
    }());
    </script>"""
    layer.setMapTipTemplate(template)
    if hasattr(layer, "setMapTipsEnabled"):
        layer.setMapTipsEnabled(True)
