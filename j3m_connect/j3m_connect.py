# SPDX-License-Identifier: GPL-3.0-or-later
"""QGIS action and dialog lifecycle."""

from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsSettings
from qgis.core import Qgis
try:
    from qgis.PyQt.QtGui import QAction  # Qt 6
except ImportError:
    from qgis.PyQt.QtWidgets import QAction  # Qt 5

from .dialog import J3MDialog


class J3MConnect:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None
        self.inspectAction = None

    def initGui(self):
        if self.action is not None:
            return
        self.action = QAction(
            QIcon(str(Path(__file__).with_name("j3m-logo.jpeg"))),
            "J3M Connect", self.iface.mainWindow(),
        )
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu("&J3M Connect", self.action)
        self.iface.addToolBarIcon(self.action)
        self.inspectAction = QAction('Analisar camada no J3M',self.iface.mainWindow())
        self.inspectAction.triggered.connect(self.inspect_active)
        if hasattr(Qgis,'LayerType'):
            vector = Qgis.LayerType.Vector
        else:
            from qgis.core import QgsMapLayerType
            vector = QgsMapLayerType.VectorLayer
        self.iface.addCustomActionForLayerType(self.inspectAction,'J3M',vector,True)

    def inspect_active(self):
        self.run()
        self.dialog._select_menu('workbench')
        self.dialog.workbench.adopt_active()

    def run(self):
        if self.dialog is None:
            self.dialog = J3MDialog(self.iface)
            self.iface.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.dialog)
            preferences = QgsSettings()
            self.dialog.setFloating(preferences.value('J3MConnect/floating',False,type=bool))
            self.dialog.navigationButton.setChecked(preferences.value('J3MConnect/navigation',True,type=bool))
            geometry = preferences.value('J3MConnect/dockGeometry')
            if geometry and self.dialog.isFloating():
                self.dialog.restoreGeometry(geometry)
        elif not self.dialog.isVisible():
            self.dialog._period_record = None
            self.dialog._selected()
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def unload(self):
        if self.inspectAction is not None:
            self.iface.removeCustomActionForLayerType(self.inspectAction)
            self.inspectAction.deleteLater()
            self.inspectAction = None
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.dispose()
            self.iface.removeDockWidget(self.dialog)
            self.dialog.deleteLater()
            self.dialog = None
        if self.action is not None:
            self.iface.removePluginMenu("&J3M Connect", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.triggered.disconnect(self.run)
            self.action.deleteLater()
            self.action = None
