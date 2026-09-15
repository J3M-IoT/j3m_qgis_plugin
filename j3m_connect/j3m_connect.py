# SPDX-License-Identifier: GPL-3.0-or-later
"""QGIS action and dialog lifecycle."""

from pathlib import Path

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction

from .dialog import J3MDialog


class J3MConnect:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

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

    def run(self):
        if self.dialog is None:
            self.dialog = J3MDialog(self.iface)
        self.dialog.show()
        self.dialog.raise_()
        self.dialog.activateWindow()

    def unload(self):
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None
        if self.action is not None:
            self.iface.removePluginMenu("&J3M Connect", self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action.triggered.disconnect(self.run)
            self.action.deleteLater()
            self.action = None
