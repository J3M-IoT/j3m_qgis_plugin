# SPDX-License-Identifier: GPL-3.0-or-later
"""QGIS plugin entry point."""


def classFactory(iface):
    from .j3m_connect import J3MConnect

    return J3MConnect(iface)
