"""Generate browser fixtures without starting Qt WebKit (QGIS Python)."""
from html import escape
from pathlib import Path
from test_map_tips import MapTipTests

MapTipTests.setUpClass()
test = MapTipTests()
sample = {
    'device_name': 'Dispositivo Mini', 'device_type': 'Estação Meteorológica 1',
    'condition_name': 'Bom(a)', 'condition_hex': '#168659', 'device_status': 'Online',
    'collectedAt': '2026-09-04T01:14:23', 'collects_temperatura': '22.3',
    'collects_umidade': '41.6', 'collects_pressao': '930', 'collects_ponto_orvalho': '8.7',
    'collects_altitude': '717.1', 'geolocation_status': 'em_transito',
    'geolocation_velocidade': '97.4', 'geolocation_latitude': '-23.890320',
    'geolocation_longitude': '-46.565139', 'network_type': 'WIFI', 'network_signal': '80',
    'device_battery': '100', 'firmware_type': 'Mini', 'firmware_version': 'v1.1.2',
    'territorialContext_has_water': True, 'territorialContextDistance_water': '12',
    'territorialContextDistance_vegetacao': '5', 'radius_meters': '200',
    'timePeriod': 'night',
}
long = dict(sample)
long.update({'collects_metrica_dinamica_' + str(i): str(i + 0.123) for i in range(30)})
long['territorialContext_nome_extenso'] = 'Territorio' * 35
long['device_name'] = 'Dispositivo' * 20
long['network_ssid'] = 'Rede' * 50

def frame(data, width, height):
    # Same outer wrapper and 5px inner margin as QgsMapTip::htmlText.
    html = ('<!doctype html><html><head><meta charset="utf-8"><style>'
            'body{margin:0}#QgsWebViewContainer{display:inline-block;border:1px solid #aaa}'
            '#QgsWebViewContainerInner{margin:5px}</style></head><body>'
            '<div id="QgsWebViewContainer"><div id="QgsWebViewContainerInner">'
            + test.render(data) + '</div></div></body></html>')
    return '<iframe width="{}" height="{}" srcdoc="{}"></iframe>'.format(width, height, escape(html, quote=True))

output = Path(__file__).resolve().parents[1] / 'dist'
output.mkdir(exist_ok=True)
html = '''<!doctype html><meta charset="utf-8"><style>
body{background:#dde5e5;font-family:Arial}iframe{border:0;vertical-align:top;margin:10px}
#results{position:absolute;left:700px;top:10px;width:280px;font-size:11px;white-space:pre-wrap}
</style>''' + frame(sample, 362, 510) + frame(long, 280, 320) + '''
<pre id="results">Waiting</pre><script>
window.addEventListener('load', function () { setTimeout(function () {
    var results = [];
    document.querySelectorAll('iframe').forEach(function (frame, index) {
        var card = frame.contentDocument.querySelector('.card');
        var lastSection = card.querySelector('.content').lastElementChild;
        card.scrollTop = card.scrollHeight;
        var box = card.getBoundingClientRect(), end = lastSection.getBoundingClientRect();
        results.push({fixture:index, width:card.clientWidth, height:card.clientHeight,
            contentHeight:card.scrollHeight,
            noHorizontalCut:card.scrollWidth <= card.clientWidth,
            fitsViewport:box.bottom <= frame.clientHeight && box.right <= frame.clientWidth,
            lastSectionReachable:end.bottom <= box.bottom,
            metrics:card.querySelectorAll('.metric').length});
        card.scrollTop = 0;
    });
    document.getElementById('results').textContent = JSON.stringify(results, null, 2);
}, 100); });
</script>'''
(output / 'tooltip-validation.html').write_text(html, encoding='utf-8')
print(output / 'tooltip-validation.html')
