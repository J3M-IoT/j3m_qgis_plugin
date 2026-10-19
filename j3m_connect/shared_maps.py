# SPDX-License-Identifier: GPL-3.0-or-later
"""Read an existing public map link by code; never forward integration secrets."""
from urllib.parse import urlencode
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtWidgets import QWidget,QVBoxLayout,QLineEdit,QPushButton
from qgis.core import QgsProject,QgsRasterLayer
from .api import ApiClient
from .adapters import _response_data
from .layers import LayerLoader
from .cartography import configure_layer,provenance
from .workbench import text


class SharedMapsPage(QWidget):
    def __init__(self,iface,workbench,parent=None):
        super().__init__(parent)
        self.iface,self.workbench=iface,workbench
        self.api=ApiClient(self)
        self.layerLoader=LayerLoader(self)
        self.record=None
        layout=QVBoxLayout(self)
        layout.addWidget(text('Mapas compartilhados J3M'))
        layout.addWidget(text('Informe o código de um mapa compartilhado já existente. '
            'A consulta usa a public_api configurada e não envia credenciais de integração.'))
        self.code=QLineEdit()
        self.code.setPlaceholderText('Código do mapa (não cole uma URL)')
        layout.addWidget(self.code)
        self.loadButton=QPushButton('Consultar mapa compartilhado')
        self.loadButton.clicked.connect(self.load)
        layout.addWidget(self.loadButton)
        self.details=text()
        layout.addWidget(self.details)
        self.addButton=QPushButton('Adicionar coletas compartilhadas')
        self.addButton.clicked.connect(lambda:self.api.get('link_collections',self.record['uuid'],scope='map_links'))
        layout.addWidget(self.addButton)
        self.baseButton=QPushButton('Adicionar mapa de fundo cadastrado')
        self.baseButton.clicked.connect(self.basemap)
        layout.addWidget(self.baseButton)
        cancel=QPushButton('Cancelar')
        cancel.clicked.connect(self.cancel)
        layout.addWidget(cancel)
        self.status=text('A disponibilidade e o período são definidos pelo compartilhamento J3M.')
        layout.addWidget(self.status)
        layout.addStretch()
        self.api.received.connect(self.received)
        self.api.failed.connect(self.status.setText)
        self.api.busyChanged.connect(self.busy)
        self.layerLoader.busyChanged.connect(self.busy)
        self.layerLoader.failed.connect(self.status.setText)
        self.code.textChanged.connect(self.reset)
        self.busy(False)

    def reset(self):
        self.cancel()
        self.record=None
        self.details.clear()
        self.busy(False)

    def cancel(self):
        self.api.cancel()
        self.layerLoader.cancel()

    def busy(self,value):
        self.code.setEnabled(not value)
        self.loadButton.setEnabled(not value)
        self.addButton.setEnabled(not value and bool(self.record))
        self.baseButton.setEnabled(not value and bool((self.record or {}).get('map')))

    def load(self):
        code=self.code.text().strip()
        if not code or any(ch in code for ch in '/\\?#') or code in ('.','..'):
            self.status.setText('Informe somente o código do mapa compartilhado.')
            return
        self.record=None
        self.api.get('map_link',code,scope='map_links')

    def received(self,kind,payload):
        try:
            if kind=='map_link':
                record=_response_data(payload)
                if not isinstance(record,dict) or not record.get('uuid'):
                    raise ValueError('O mapa compartilhado não informa UUID.')
                self.record=record
                self.details.setText(str(record.get('name','Mapa'))+'\n'+str(record.get('rangeStart','—'))+' a '+
                    str(record.get('rangeEnd','—'))+'\nFuso: '+str(record.get('timezone','—'))+'\n'+
                    'Dispositivos: '+', '.join(str(d.get('name','')) for d in record.get('devices',[])))
                self.status.setText('Mapa compartilhado disponível. Atualização manual.')
            elif kind=='link_collections' and self.record:
                if payload is None:
                    self.status.setText('Não há coletas georreferenciadas disponíveis.')
                    return
                record=self.record
                def finish(layer, digest):
                    if layer is None:
                        self.status.setText('Não há coletas georreferenciadas disponíveis.')
                        return
                    origin=provenance('map_links',record,[record.get('rangeStart'),record.get('rangeEnd')],digest=digest)
                    origin['endpoint']='/v1/map-links/'+record['uuid']+'/export?format=geojson'
                    origin['access']='Compartilhamento público, separado da integração'
                    configure_layer(layer,origin)
                    self.iface.setActiveLayer(layer)
                    self.iface.actionMapTips().setChecked(True)
                    self.workbench.focus_layer(layer)
                    self.status.setText('Camada compartilhada adicionada; disponível em Análise.')
                self.status.setText('Preparando a camada compartilhada…')
                self.layerLoader.load(payload,'J3M • Compartilhado — '+str(record.get('name','Mapa')),finish)
        except (ValueError,TypeError,OSError) as error:
            self.status.setText(str(error))
        finally:
            self.busy(self.layerLoader._task is not None)

    def basemap(self):
        record=(self.record or {}).get('map') or {}
        raw=str(record.get('url',''))
        subdomains=str(record.get('subdomains') or '').split(',')
        if '{s}' in raw and subdomains[0]:
            raw=raw.replace('{s}',subdomains[0].strip()[0])
        url=QUrl(raw)
        if not url.isValid() or url.scheme()!='https' or not url.host() or url.userInfo():
            self.status.setText('O fundo cadastrado precisa de URL HTTPS válida e sem credenciais.')
            return
        if not all(token in raw for token in ('{x}','{y}','{z}')):
            self.status.setText('Este fundo não informa um modelo XYZ compatível ({z}/{x}/{y}).')
            return
        layer=QgsRasterLayer(urlencode({'type':'xyz','url':raw}),str(record.get('name','J3M • Fundo')),'wms')
        if not layer.isValid():
            self.status.setText('Não foi possível carregar o fundo cadastrado.')
            return
        QgsProject.instance().addMapLayer(layer)
        root=QgsProject.instance().layerTreeRoot()
        node=root.findLayer(layer.id())
        root.addChildNode(node.clone())
        root.removeChildNode(node)
        self.status.setText('Mapa de fundo adicionado com a fonte cadastrada no J3M.')
