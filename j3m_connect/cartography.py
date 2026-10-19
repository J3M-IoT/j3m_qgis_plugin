# SPDX-License-Identifier: GPL-3.0-or-later
"""Native QGIS styling, temporal metadata and portable study exports."""
import hashlib
import json
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from qgis.PyQt.QtCore import QSize
from qgis.PyQt.QtGui import QColor, QTextDocument
from qgis.PyQt.QtPrintSupport import QPrinter
from qgis.core import (
    Qgis, QgsExpression, QgsMarkerSymbol, QgsProject, QgsRuleBasedRenderer,
    QgsVectorLayerTemporalProperties, QgsVectorFileWriter, QgsVectorLayer,
    QgsMapSettings, QgsMapRendererParallelJob, QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsWkbTypes,
)
from .map_tips import LABELS, UNITS
from .layers import _style_points

VERSION = '1.2.0'
POINT_TYPE = Qgis.GeometryType.Point if hasattr(Qgis,'GeometryType') else QgsWkbTypes.GeometryType.PointGeometry


def provenance(scope, record, period, payload=None, digest=None):
    from .settings import configured_api_url
    if digest is None:
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False)
        digest = hashlib.sha256(serialized.encode('utf-8')).hexdigest()
    return {'plugin': VERSION, 'api':configured_api_url(),
            'endpoint':'/v1/'+scope+'/'+str(record.get('uuid',''))+'/collections?format=geojson',
            'scope': scope, 'uuid': record.get('uuid'), 'name': record.get('name'),
            'timezone': 'UTC' if scope == 'geofences' else (record.get('timezone') or (record.get('device') or {}).get('timezone')),
            'period': period or [record.get('startDate'), record.get('endDate')],
            'downloaded_at': datetime.now(timezone.utc).isoformat(),
            'sha256': digest,
            'hash_format': 'JSON UTF-8, chaves ordenadas, ensure_ascii=False, separadores padrão Python',
            'note': 'Snapshot; indicadores podem excluir o instante final e incluir coletas sem GPS.'}


def configure_layer(layer, origin, units=None, preserve_style=False):
    layer.setCustomProperty('j3m/origin', json.dumps(origin, ensure_ascii=False))
    layer.setCustomProperty('j3m/units', json.dumps(units or {}, ensure_ascii=False))
    if not preserve_style and not layer.customProperty('j3m/style','') and layer.geometryType()==POINT_TYPE:
        style_metric(layer,'')
    for i, field in enumerate([] if preserve_style else layer.fields()):
        key = field.name().removeprefix('collects_').removesuffix('_value')
        unit = (units or {}).get(key, UNITS.get(key, ''))
        alias = LABELS.get(key, field.name())
        layer.setFieldAlias(i, alias + (' (' + unit + ')' if unit else ''))
    if not preserve_style and layer.fields().indexFromName('collectedAt') >= 0:
        temporal = layer.temporalProperties()
        modes = Qgis.VectorTemporalMode if hasattr(Qgis, 'VectorTemporalMode') else QgsVectorLayerTemporalProperties
        mode = getattr(modes, 'FeatureDateTimeStartAndEndFromExpressions', None)
        if mode is None:
            mode = getattr(modes, 'ModeFeatureDateTimeStartAndEndFromExpressions')
        temporal.setMode(mode)
        temporal.setStartExpression('to_datetime("collectedAt")')
        temporal.setEndExpression('to_datetime("collectedAt")')
        temporal.setIsActive(True)
    root = QgsProject.instance().layerTreeRoot()
    group = root.findGroup('J3M') or root.addGroup('J3M')
    node = root.findLayer(layer.id())
    if node and node.parent() != group:
        copy = node.clone()
        group.addChildNode(copy)
        node.parent().removeChildNode(node)


def metric_field(layer, metric):
    for candidate in ('collects_' + metric, 'collects_' + metric + '_value'):
        if layer.fields().indexFromName(candidate) >= 0:
            return candidate
    raise ValueError('A camada não possui a métrica selecionada.')


def style_metric(layer, metric, minimum=None, maximum=None, unit='', size=3.0, stats=None, categories=None):
    if not metric:
        _style_points(layer)
        if layer.geometryType() == POINT_TYPE:
            layer.renderer().symbol().setSize(size)
            if layer.fields().indexFromName('condition_name')>=0 and layer.fields().indexFromName('markerColor')>=0:
                from qgis.core import NULL
                if categories is None:
                    cached = layer.customProperty('j3m/categories','')
                    categories = json.loads(cached) if cached else {}
                    if not cached:
                        for feature in layer.getFeatures():
                            name=feature['condition_name']
                            name='Sem condição' if name is None or name==NULL else str(name)
                            color=feature['markerColor']
                            color='#808080' if color is None or color==NULL else str(color)
                            categories[name+' | '+color]=(name,color)
                entries=[]
                for key,(name,color) in sorted(categories.items()):
                    symbol=layer.renderer().symbol().clone()
                    candidate=QColor(color)
                    symbol.setColor(candidate if candidate.isValid() else QColor('#808080'))
                    entries.append(QgsRendererCategory(key,symbol,name+' · '+color))
                expression='concat(coalesce("condition_name", \'Sem condição\'), \' | \', coalesce("markerColor", \'#808080\'))'
                layer.setRenderer(QgsCategorizedSymbolRenderer(expression,entries))
        layer.removeCustomProperty('j3m/style')
        layer.triggerRepaint()
        return
    if layer.geometryType() != POINT_TYPE:
        raise ValueError('Escolha uma camada de pontos J3M.')
    field = metric_field(layer, metric)
    index = layer.fields().indexFromName(field)
    from .analysis import number
    if stats is None:
        values = [f[index] for f in layer.getFeatures() if number(f[index])]
        stats = {'n':len(values), 'min':min(values) if values else None, 'max':max(values) if values else None}
    if not stats['n']:
        raise ValueError('Não há valores numéricos válidos nesta métrica.')
    lo = stats['min'] if minimum is None else minimum
    hi = stats['max'] if maximum is None else maximum
    if hi < lo:
        raise ValueError('O máximo deve ser maior ou igual ao mínimo.')
    root = QgsRuleBasedRenderer.Rule(None)
    quoted = QgsExpression.quotedColumnRef(field)
    colors = ['#416e9d', '#7ea3b4', '#c5c68c', '#dca263', '#b85738']

    def rule(expression, caption, color):
        symbol = QgsMarkerSymbol.createSimple({'name': 'circle', 'color': color, 'size': str(size),
                                               'outline_color': '#ffffff', 'outline_width': '0.2'})
        root.appendChild(QgsRuleBasedRenderer.Rule(symbol, 0, 0, expression, caption))
    if hi == lo:
        rule(f'{quoted} = {lo}', f'{lo:g} {unit}', colors[2])
    else:
        for i, color in enumerate(colors):
            a, b = lo+(hi-lo)*i/5, lo+(hi-lo)*(i+1)/5
            rule(f'{quoted} >= {a!r} AND {quoted} {"<=" if i == 4 else "<"} {b!r}',
                 f'{a:.2f} – {b:.2f} {unit}', color)
    rule(f'{quoted} < {lo!r}', f'Abaixo de {lo:g} {unit}', '#263b67')
    rule(f'{quoted} > {hi!r}', f'Acima de {hi:g} {unit}', '#782e35')
    rule(f'{quoted} IS NULL', 'Sem valor', '#999999')
    layer.setRenderer(QgsRuleBasedRenderer(root))
    layer.setCustomProperty('j3m/style', json.dumps({'metric':metric,'min':lo,'max':hi,'unit':unit,'size':size}))
    layer.triggerRepaint()


def export_options(layer, filename, driver):
    source = Path(layer.source().split('|')[0])
    if source.resolve() == Path(filename).resolve():
        raise ValueError('Escolha outro arquivo; a exportação não pode sobrescrever a origem da camada.')
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver
    options.fileEncoding = 'UTF-8'
    options.layerName = 'coletas'
    if driver == 'GPKG':
        # Original GeoJSON id may be a non-integer: reserve a separate GPKG primary key.
        options.layerOptions = ['FID=j3m_gpkg_fid']
    if driver == 'CSV':
        options.layerOptions = ['GEOMETRY=AS_XY', 'CREATE_CSVT=YES']
    return options


def export_sidecars(layer, filename):
    layer.saveNamedStyle(str(Path(filename).with_suffix('.qml')))
    Path(str(filename) + '.origem.json').write_text(str(layer.customProperty('j3m/origin', '{}')), encoding='utf-8')


def export_layer(layer, filename, driver):
    options = export_options(layer, filename, driver)
    result = QgsVectorFileWriter.writeAsVectorFormatV3(layer, str(filename), QgsProject.instance().transformContext(), options)
    error_enum = QgsVectorFileWriter.WriterError if hasattr(QgsVectorFileWriter,'WriterError') else QgsVectorFileWriter
    if result[0] != error_enum.NoError:
        raise ValueError('Falha ao exportar: ' + str(result[1]))
    export_sidecars(layer, filename)


def copy_original(task, source, directory):
    source, directory = Path(source), Path(directory)
    if source.suffix.lower() not in ('.json','.geojson') or not source.is_file():
        return True
    partial = directory/'origem.geojson.part'
    try:
        with source.open('rb') as reader, partial.open('wb') as writer:
            while not task.isCanceled():
                chunk = reader.read(1024*1024)
                if not chunk:
                    break
                writer.write(chunk)
        if task.isCanceled():
            return False
        partial.replace(directory/'origem.geojson')
        return True
    finally:
        partial.unlink(missing_ok=True)


def portable_study(layer, directory, exported=False, original_copied=False):
    directory = Path(directory)
    if not exported:
        directory.mkdir(parents=True, exist_ok=False)
    path = directory / 'coletas.gpkg'
    if not exported:
        export_layer(layer, path, 'GPKG')
    copy = QgsVectorLayer(str(path) + '|layername=coletas', layer.name(), 'ogr')
    if not copy.isValid():
        raise ValueError('Não foi possível reabrir o GeoPackage exportado.')
    copy.loadNamedStyle(str(path.with_suffix('.qml')))
    for key in ('j3m/origin', 'j3m/units', 'j3m/style'):
        copy.setCustomProperty(key, layer.customProperty(key, ''))
    project = QgsProject()
    project.setCrs(layer.crs())
    project.addMapLayer(copy)
    project.setFileName(str(directory / 'estudo.qgz'))
    if hasattr(project,'setFilePathStorage'):
        project.setFilePathStorage(Qgis.FilePathType.Relative)
    if not project.write():
        raise ValueError('Não foi possível salvar o projeto portátil.')
    source = Path(layer.source().split('|')[0])
    if not original_copied and source.suffix.lower() in ('.json','.geojson') and source.is_file():
        import shutil
        shutil.copyfile(source, directory/'origem.geojson')
    (directory/'LEIA-ME.txt').write_text('Snapshot J3M. Abra estudo.qgz no QGIS.\n'
        'O pacote contém a camada selecionada, estilo e procedência; não contém credenciais.\n'
        'Consulte coletas.gpkg.origem.json para período, fuso e data do download.\n', encoding='utf-8')
    return directory / 'estudo.qgz'


def report_pdf(layer, filename, summary, on_finished=None):
    """Render asynchronously for UI callers; synchronous form is for scripts/tests."""
    import tempfile
    directory = tempfile.TemporaryDirectory(prefix='j3m-report-')
    settings = QgsMapSettings()
    settings.setLayers([layer])
    settings.setDestinationCrs(layer.crs())
    extent = layer.extent()
    if extent.isEmpty():
        extent.grow(.001)
    extent.scale(1.12)
    settings.setExtent(extent)
    settings.setOutputSize(QSize(1200, 650))
    settings.setBackgroundColor(QColor('white'))
    job = QgsMapRendererParallelJob(settings)
    def finish():
        error = None
        try:
            if job.property('j3mCanceled'):
                raise ValueError('PDF cancelado.')
            if job.errors():
                raise ValueError('Falha ao renderizar o mapa do PDF.')
            _write_report(layer, filename, summary, job, directory.name)
        except (ValueError, OSError, RuntimeError) as caught:
            error = caught
        finally:
            directory.cleanup()
        if on_finished is not None:
            try:
                on_finished(error)
            finally:
                job.deleteLater()
        elif error is not None:
            raise error
    if on_finished is not None:
        job.finished.connect(finish)
        job.start()
    else:
        job.start()
        job.waitForFinished()
        finish()
    return job


def _write_report(layer, filename, summary, job, directory):
    from .analysis import display
    origin = str(layer.customProperty('j3m/origin', '{}'))
    image = Path(directory)/'map.png'
    job.renderedImage().save(str(image))
    units = json.loads(layer.customProperty('j3m/units','{}'))
    for metric, supplied in summary.get('units',{}).items():
        if len(supplied)==1:
            units[metric]=next(iter(supplied))
        elif len(supplied)>1:
            units[metric]='Unidades conflitantes'
    rows = ''.join('<tr>' + ''.join('<td>'+escape(display(v))+'</td>' for v in
        (key, units.get(key,UNITS.get(key,'')), value['n'],value['min'],value['mean'],value['median'],value['max']))+'</tr>'
        for key,value in summary['stats'].items())
    legend = '<table>'+''.join('<tr><td bgcolor="'+item.symbol().color().name()+'">&nbsp;&nbsp;&nbsp;</td><td>'+
        escape(item.label() or 'Condição original J3M')+'</td></tr>' for item in layer.renderer().legendSymbolItems())+'</table>'
    document = QTextDocument()
    document.setHtml('<style>body{font-family:sans-serif;color:#203b48}td,th{padding:5px}h1{color:#087f8c}</style>'
        '<h1>J3M • Relatório de campanha</h1><h2>'+escape(layer.name())+'</h2>'
        '<img width="660" src="'+image.as_uri()+'"/><p>'+legend+'</p>'
        '<p>Mapa: somente a camada selecionada. Coordenadas: '+escape(layer.crs().authid())+'.</p>'
        '<h2>Observações baixadas</h2><table border="1" cellspacing="0"><tr><th>Métrica</th><th>Unidade</th><th>n</th>'
        '<th>Mín.</th><th>Média</th><th>Mediana</th><th>Máx.</th></tr>'+rows+'</table>'
        '<p>Estatísticas por registro georreferenciado; não representam duração de exposição. '
        'Nenhuma classificação científica nova foi aplicada.</p><h2>Procedência</h2><p>'+
        escape(origin).replace(',', ',<br/>')+'</p>')
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(filename))
    document.print_(printer) if hasattr(document, 'print_') else document.print(printer)
