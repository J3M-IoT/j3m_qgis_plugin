# SPDX-License-Identifier: GPL-3.0-or-later
"""Small modeless dialog for configuring and querying J3M."""

from pathlib import Path

from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QDialog, QPushButton

from . import settings
from .adapters import indicator_text, session_choices
from .api import ApiClient
from .layers import add_geojson_layer

FORM_CLASS, _ = uic.loadUiType(str(Path(__file__).with_name("dialog.ui")))


class J3MDialog(QDialog, FORM_CLASS):
    def __init__(self, iface):
        super().__init__(iface.mainWindow())
        self.setupUi(self)
        self.iface = iface
        self.api = ApiClient(self)
        self._busy = False
        self._dirty = False
        self._loaded = False
        for button in self.findChildren(QPushButton):
            button.setAutoDefault(False)
        self.saveButton.clicked.connect(self._save)
        self.removeButton.clicked.connect(self._remove)
        self.refreshButton.clicked.connect(self._refresh)
        self.sessionCombo.currentIndexChanged.connect(self._session_changed)
        self.addButton.clicked.connect(self._add)
        self.closeButton.clicked.connect(self.close)
        self.api.busyChanged.connect(self._set_busy)
        self.api.failed.connect(self._error)
        self.api.received.connect(self._received)
        for edit in (self.clientEdit, self.secretEdit):
            edit.textEdited.connect(self._edited)

    def showEvent(self, event):
        super().showEvent(event)
        if not self._loaded:
            self._loaded = True
            if settings.preferences()[1]:
                try:
                    _, client_id, _ = settings.credentials()
                    self.clientEdit.setText(client_id)
                    self.statusLabel.setText("Configuração carregada. Atualize as sessões.")
                except ValueError as error:
                    self._error(str(error))

    def _edited(self):
        self._dirty = True
        self._clear_sessions()
        self.statusLabel.setText("Configuração alterada. Salve antes de consultar a API.")

    def _clear_sessions(self):
        self.sessionCombo.blockSignals(True)
        self.sessionCombo.clear()
        self.sessionCombo.blockSignals(False)
        self.indicatorsEdit.clear()
        self.addButton.setEnabled(False)

    def _save(self):
        try:
            settings.save(self.clientEdit.text(), self.secretEdit.text())
            self.secretEdit.clear()
            self._dirty = False
            self._clear_sessions()
            self.statusLabel.setText("Configuração salva no QGIS. Atualize as sessões.")
        except ValueError as error:
            self._error(str(error))

    def _remove(self):
        try:
            settings.remove()
            self.clientEdit.clear()
            self.secretEdit.clear()
            self._dirty = False
            self._clear_sessions()
            self.statusLabel.setText("Configuração e credenciais removidas.")
        except ValueError as error:
            self._error(str(error))

    def _refresh(self):
        if self._dirty:
            self._error("Salve a configuração alterada antes de consultar a API.")
            return
        self._clear_sessions()
        self.statusLabel.setText("Consultando sessões…")
        self.api.get("sessions")

    def _session_changed(self):
        self.indicatorsEdit.clear()
        session = self.sessionCombo.currentData()
        self.addButton.setEnabled(session is not None and not self._busy)
        if session is not None:
            self.statusLabel.setText("Consultando indicadores…")
            self.api.get("indicators", session)

    def _add(self):
        session = self.sessionCombo.currentData()
        if session is not None:
            self.statusLabel.setText("Consultando GeoJSON…")
            self.api.get("collections", session)

    def _set_busy(self, busy):
        self._busy = busy
        self.configGroup.setEnabled(not busy)
        self.refreshButton.setEnabled(not busy)
        self.sessionCombo.setEnabled(not busy)
        self.addButton.setEnabled(not busy and self.sessionCombo.currentData() is not None)

    def _error(self, message):
        self.statusLabel.setText(message)

    def _received(self, kind, payload):
        try:
            if kind == "sessions":
                choices = session_choices(payload)
                self.sessionCombo.blockSignals(True)
                self.sessionCombo.clear()
                for identifier, label in choices:
                    self.sessionCombo.addItem(label, identifier)
                self.sessionCombo.setCurrentIndex(-1)
                self.sessionCombo.blockSignals(False)
                if choices:
                    self.sessionCombo.setCurrentIndex(0)
                else:
                    self.statusLabel.setText("Nenhuma sessão disponível.")
            elif kind == "indicators":
                self.indicatorsEdit.setPlainText(indicator_text(payload))
                self.statusLabel.setText("Consulta de indicadores concluída.")
            elif kind == "collections":
                if payload is None:
                    self.statusLabel.setText("Nenhuma coleta disponível.")
                    return
                layer = add_geojson_layer(payload, "J3M — " + self.sessionCombo.currentText())
                if layer is None:
                    self.statusLabel.setText("Nenhuma coleta disponível.")
                else:
                    self.iface.setActiveLayer(layer)
                    self.iface.actionMapTips().setChecked(True)
                    self.statusLabel.setText("Camada adicionada ao mapa e salva no perfil QGIS.")
        except ValueError as error:
            self._error(str(error))
        except OSError:
            self._error("Não foi possível salvar o GeoJSON no perfil QGIS.")
        except RecursionError:
            self._error("A resposta possui aninhamento excessivo.")

    def done(self, result):
        self.api.cancel()
        self.secretEdit.clear()
        super().done(result)

    def closeEvent(self, event):
        self.api.cancel()
        self.secretEdit.clear()
        super().closeEvent(event)
