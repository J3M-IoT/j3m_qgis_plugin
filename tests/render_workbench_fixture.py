"""Render actual native Qt layouts with local fixtures and no network/credentials."""
import sys
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from qgis.core import QgsApplication,QgsProject
from qgis.PyQt.QtCore import Qt,QCoreApplication,QEvent
from qgis.PyQt.QtGui import QPalette,QColor,QFontDatabase,QFont
from qgis.PyQt.QtWidgets import QMainWindow,QLabel
from test_integration import FakeApi
from test_workbench import fixture
from j3m_connect.dialog import J3MDialog

app=QgsApplication([],False)
app.initQgis()
if Path('C:/Windows/Fonts/arial.ttf').exists():
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/arial.ttf')
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/arialbd.ttf')
    app.setFont(QFont('Arial',10))
window=QMainWindow()
window.resize(1320,950)
canvas=QLabel('Área do mapa QGIS')
canvas.setAlignment(Qt.AlignmentFlag.AlignCenter)
window.setCentralWidget(canvas)
iface=Mock()
iface.mainWindow.return_value=window
output=Path(os.environ.get('J3M_PREVIEW_DIRECTORY',str(Path(__file__).resolve().parents[1]/'dist')))
output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as directory, patch('j3m_connect.layers.QgsApplication.qgisSettingsDirPath',return_value=directory),patch('j3m_connect.dialog.ApiClient',FakeApi),patch('j3m_connect.geofences.ApiClient',FakeApi),patch('j3m_connect.dialog.settings.preferences',return_value=('','')):
    dialog=J3MDialog(iface)
    dialog._loaded=True
    window.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea,dialog)
    window.show()
    dialog._select_menu('devices')
    record={'uuid':'device-a','name':'Praça central • Campanha de outubro','timezone':'America/Sao_Paulo',
            'battery':85,'status':'enabled','mode':'continuous','lastCollect':'2026-10-19T12:03:00Z',
            'metrics':[{'metric':'temperatura','unit':'°C'},{'metric':'umidade','unit':'%'}]}
    dialog._received('catalog',{'success':True,'data':[record]})
    dialog._received('indicators',{'success':True,'data':{'totalCollects':4,'condition':{'description':'Boa','color':'green'},
        'avgs':[{'name':'temperatura','avg':16.67,'unit':'°C','color':'green'},{'name':'umidade','avg':71.5,'unit':'%','color':'blue'}]}})
    dialog._pending_query=('devices',record,['2026-10-19 09:00:00','2026-10-19 10:00:00'])
    dialog._add_layer(fixture())
    from qt_helpers import wait_for
    wait_for(lambda: dialog.layerLoader._task is None)
    for name,route,tab in [('consulta','devices',0),('analise','workbench',1),('exportar','workbench',6)]:
        if route=='workbench':
            dialog._select_menu(route)
            dialog.workbench.metric.setCurrentIndex(dialog.workbench.metric.findData('temperatura'))
            dialog.workbench.tabs.setCurrentIndex(tab)
        dialog.setFloating(True)
        dialog.resize(1080,900)
        app.processEvents()
        print(name,'layers',len(QgsProject.instance().mapLayers()),'metric',dialog.workbench.metric.currentText(),'size',dialog.size().width(),dialog.size().height())
        dialog.grab().save(str(output/('v1.2.0-'+name+'.png')))
    palette=app.palette()
    dark=QPalette(palette)
    for role,color in [('Window','#202832'),('WindowText','#edf2f7'),('Base','#18202b'),('AlternateBase','#293544'),
                       ('Text','#edf2f7'),('Button','#293544'),('ButtonText','#edf2f7'),('Highlight','#237b98'),('HighlightedText','#ffffff')]:
        dark.setColor(getattr(QPalette.ColorRole,role),QColor(color))
    app.setPalette(dark)
    dialog.workbench.tabs.setCurrentIndex(0)
    dialog.navigationButton.setChecked(False)
    dialog.resize(540,800)
    app.processEvents()
    dialog.grab().save(str(output/'v1.2.0-compacto-escuro.png'))
    dialog.dispose()
    dialog.close()
    QgsProject.instance().removeAllMapLayers()
    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
    app.processEvents()
window.close()
print('Previews:',output)
