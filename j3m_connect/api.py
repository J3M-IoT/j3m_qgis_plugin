# SPDX-License-Identifier: GPL-3.0-or-later
"""Asynchronous GET requests using the QGIS network manager."""

import json

from qgis.PyQt.QtCore import QObject, QTimer, QUrl, QUrlQuery, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import QgsNetworkAccessManager

from .settings import credentials

MAX_BYTES = 20 * 1024 * 1024


class ApiClient(QObject):
    received = pyqtSignal(str, object)
    failed = pyqtSignal(str)
    busyChanged = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reply = None
        self._buffer = bytearray()
        self._failure = ""
        self._secret = ""
        self._kind = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)

    def get(self, kind, session=None):
        self.cancel()
        try:
            base, client_id, secret = credentials()
            if kind not in ("sessions", "indicators", "collections"):
                raise ValueError("Operação de API desconhecida.")
            path = "/sessions"
            if kind != "sessions":
                if session is None or not str(session) or str(session) in (".", ".."):
                    raise ValueError("Selecione uma sessão válida.")
                segment = bytes(QUrl.toPercentEncoding(str(session))).decode("ascii")
                path += "/" + segment + "/" + kind
            url = QUrl(base + path, QUrl.StrictMode)
            if kind == "collections":
                query = QUrlQuery()
                query.addQueryItem("format", "geojson")
                url.setQuery(query)
            request = QNetworkRequest(url)
            request.setAttribute(QNetworkRequest.RedirectPolicyAttribute, QNetworkRequest.ManualRedirectPolicy)
            request.setAttribute(QNetworkRequest.CacheLoadControlAttribute, QNetworkRequest.AlwaysNetwork)
            request.setAttribute(QNetworkRequest.CacheSaveControlAttribute, False)
            request.setRawHeader(b"Accept", b"application/geo+json" if kind == "collections" else b"application/json")
            request.setRawHeader(b"X-Client-Id", client_id.encode("utf-8"))
            request.setRawHeader(b"X-Client-Secret", secret.encode("utf-8"))
            self._secret = secret
            self._kind = kind
            self._failure = ""
            self._buffer.clear()
            self._reply = QgsNetworkAccessManager.instance().get(request)
            self._reply.readyRead.connect(self._read)
            self._reply.finished.connect(self._finished)
            self.busyChanged.emit(True)
            self._timer.start(30000)
        except ValueError as error:
            self.failed.emit(str(error))

    def cancel(self):
        self._timer.stop()
        if self._reply is not None:
            reply, self._reply = self._reply, None
            reply.readyRead.disconnect(self._read)
            reply.finished.disconnect(self._finished)
            reply.abort()
            reply.deleteLater()
        self._buffer.clear()
        self._secret = ""
        self.busyChanged.emit(False)

    def _timeout(self):
        if self._reply is not None:
            self._failure = "A API excedeu o tempo limite de 30 segundos."
            self._reply.abort()

    def _read(self):
        if self._reply is None:
            return
        self._buffer.extend(bytes(self._reply.readAll()))
        if len(self._buffer) > MAX_BYTES:
            self._failure = "A resposta excede o limite de 20 MiB desta versão."
            self._buffer.clear()
            self._reply.abort()

    def _finished(self):
        reply = self._reply
        if reply is None:
            return
        self._timer.stop()
        self._read()
        status = reply.attribute(QNetworkRequest.HttpStatusCodeAttribute)
        no_data = status == 404 and self._is_no_data()
        message = self._failure
        if not message:
            if status in (401, 403):
                message = "Credenciais inválidas ou acesso não autorizado (HTTP 401/403)."
            elif status == 404 and not no_data:
                message = "Sessão ou rota não encontrada ou sem acesso (HTTP 404)."
            elif status == 429:
                message = "Limite de requisições excedido (HTTP 429). Aguarde antes de tentar novamente."
            elif status == 422:
                message = "A API recusou os parâmetros da consulta (HTTP 422)."
            elif status is not None and 300 <= status < 400:
                message = "Redirecionamento recusado. Configure a URL final da API."
            elif status is not None and not 200 <= status < 300 and not no_data:
                message = "A API retornou erro HTTP {}.".format(status)
            elif reply.error() != QNetworkReply.NoError and not no_data:
                message = "API indisponível ou falha de rede/TLS. Verifique o acesso e tente novamente."
        payload = None
        if not message and status != 204 and not no_data:
            try:
                payload = json.loads(self._buffer.decode("utf-8-sig"), parse_constant=self._invalid_constant)
                # Refuse reflected credentials before they can reach UI or disk.
                if self._contains_secret(payload):
                    message = "Resposta recusada por conter a credencial de acesso."
                    payload = None
            except (ValueError, UnicodeError, RecursionError):
                message = "A API retornou uma resposta JSON inválida."
        kind = self._kind
        self._reply = None
        reply.deleteLater()
        self._buffer.clear()
        self._secret = ""
        self.busyChanged.emit(False)
        if message:
            self.failed.emit(message)
        else:
            self.received.emit(kind, payload)

    @staticmethod
    def _invalid_constant(value):
        raise ValueError("Invalid JSON constant")

    def _is_no_data(self):
        """Recognize only the documented no-data error; never display its body."""
        if (self._kind not in ("indicators", "collections") or self._reply is None
                or self._reply.attribute(QNetworkRequest.HttpStatusCodeAttribute) != 404):
            return False
        try:
            payload = json.loads(self._buffer.decode("utf-8-sig"))
        except (ValueError, UnicodeError, RecursionError):
            return False
        return (isinstance(payload, dict) and payload.get("success") is False
                and payload.get("message") == "There is no data for the provided parameters.")

    def _contains_secret(self, value):
        if isinstance(value, str):
            return bool(self._secret and self._secret in value)
        if isinstance(value, dict):
            return any(self._contains_secret(k) or self._contains_secret(v) for k, v in value.items())
        if isinstance(value, list):
            return any(self._contains_secret(item) for item in value)
        return bool(self._secret and self._secret in str(value))
