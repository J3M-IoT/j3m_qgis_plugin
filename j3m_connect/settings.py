# SPDX-License-Identifier: GPL-3.0-or-later
"""Explicit URL configuration and secure QGIS credential storage."""

import json
from pathlib import Path

from qgis.PyQt.QtCore import QUrl
from qgis.core import QgsApplication, QgsAuthMethodConfig, QgsSettings

PREFIX = "J3MConnect/"


def configured_api_url():
    """Read the global configuration shipped with the plugin."""
    try:
        config = json.loads(Path(__file__).with_name("config.json").read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, ValueError):
        return ""
    value = config.get("api_url", "") if isinstance(config, dict) else ""
    return value.strip() if isinstance(value, str) else ""


def validate_url(value):
    url = QUrl(value.strip(), QUrl.StrictMode)
    if (not url.isValid() or not url.host()
            or url.scheme() not in ("https", "http")
            or url.userInfo() or url.hasQuery() or url.hasFragment()):
        raise ValueError("Configuração de conexão do plugin inválida. Contate o responsável pelo plugin.")
    if url.scheme() == "http" and url.host().lower() not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Configuração de conexão do plugin insegura. Contate o responsável pelo plugin.")
    return url.toString(QUrl.FullyEncoded).rstrip("/")


def preferences():
    settings = QgsSettings()
    return (configured_api_url(),
            settings.value(PREFIX + "authcfg", "", type=str))


def _manager():
    manager = QgsApplication.authManager()
    if manager.isDisabled() or not manager.setMasterPassword(True):
        raise ValueError("Desbloqueie o cofre de autenticação do QGIS para continuar.")
    return manager


def _load(authcfg):
    config = QgsAuthMethodConfig()
    if not _manager().loadAuthenticationConfig(authcfg, config, True):
        raise ValueError("Credenciais indisponíveis no cofre QGIS. Salve a configuração novamente.")
    if config.method() != "Basic":
        raise ValueError("Configuração de autenticação incompatível com J3M Connect.")
    return config


def credentials():
    url, authcfg = preferences()
    if not authcfg:
        raise ValueError("Configuração incompleta. Salve Client ID e Client Secret.")
    url = validate_url(url)
    config = _load(authcfg)
    client_id, secret = config.config("username"), config.config("password")
    _validate_credentials(client_id, secret)
    return url, client_id, secret


def _validate_credentials(client_id, secret):
    if not client_id.strip() or not secret.strip():
        raise ValueError("Informe Client ID e Client Secret.")
    if any(ord(char) < 32 or ord(char) == 127 for char in client_id + secret):
        raise ValueError("As credenciais não podem conter caracteres de controle.")


def save(client_id, secret):
    url = validate_url(configured_api_url())
    client_id = client_id.strip()
    _, authcfg = preferences()
    if not secret and authcfg:
        secret = _load(authcfg).config("password")
    _validate_credentials(client_id, secret)
    manager = _manager()
    config = QgsAuthMethodConfig()
    config.setName("J3M Connect")
    config.setMethod("Basic")
    config.setUri(url)
    config.setConfig("username", client_id)
    config.setConfig("password", secret)
    if authcfg:
        config.setId(authcfg)
        success = manager.updateAuthenticationConfig(config)
    else:
        success = manager.storeAuthenticationConfig(config)
    if not success:
        raise ValueError("Não foi possível salvar as credenciais no cofre QGIS.")
    settings = QgsSettings()
    settings.remove(PREFIX + "url")
    settings.setValue(PREFIX + "authcfg", config.id())


def remove():
    _, authcfg = preferences()
    if authcfg and not _manager().removeAuthenticationConfig(authcfg):
        raise ValueError("Não foi possível remover as credenciais do cofre QGIS.")
    QgsSettings().remove(PREFIX.rstrip("/"))
