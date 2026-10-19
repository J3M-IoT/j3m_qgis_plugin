# SPDX-License-Identifier: GPL-3.0-or-later
"""Asynchronous GET requests using the QGIS network manager."""

import json

from qgis.PyQt.QtCore import QObject, QTimer, QUrl, QUrlQuery, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.core import QgsNetworkAccessManager, QgsApplication, QgsTask
from qgis.PyQt import sip

from .settings import credentials, configured_timeout_seconds, configured_api_url, validate_url


# Versions are independent for each resource and operation.
ENDPOINT_VERSIONS = {
    "sessions": {"catalog": "v1", "indicators": "v1", "collections": "v1", "table": "v1"},
    "devices": {"catalog": "v1", "indicators": "v1", "collections": "v1", "table": "v1"},
    "clusters": {"catalog": "v1", "indicators": "v1", "collections": "v1", "table": "v1"},
    "geofences": {"catalog": "v1", "indicators": "v1", "collections": "v1", "table": "v1"},
}
SESSION_REPORTS = {'range': 'collects/range', 'aggregation': 'aggregation',
                   'changes': 'changes', 'change_detail': 'changes/detail'}


class ApiClient(QObject):
    received = pyqtSignal(str, object)
    failed = pyqtSignal(str)
    busyChanged = pyqtSignal(bool)
    progress = pyqtSignal(int, int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._reply = None
        self._task = None
        self._generation = 0
        self._buffer = bytearray()
        self._failure = ""
        self._secret = None
        self._kind = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._timeout)

    def get(self, kind, session=None, scope="sessions", period=None, params=None):
        self.cancel()
        try:
            self._timeout_seconds = configured_timeout_seconds()
            shared = scope == 'map_links' and kind in ('map_link','link_collections')
            if shared:
                base, client_id, secret = validate_url(configured_api_url()), '', ''
            else:
                base, client_id, secret = credentials()
            if scope not in ("sessions", "devices", "clusters", "geofences", "map_links") or (scope=='map_links' and not shared):
                raise ValueError("Recurso de API desconhecido.")
            report = kind in SESSION_REPORTS
            if report and scope != 'sessions':
                raise ValueError('Relatório complementar disponível somente para sessões.')
            if not report and not shared and kind not in ("sessions", "catalog", "indicators", "collections", "table"):
                raise ValueError("Operação de API desconhecida.")
            operation = "catalog" if kind == "sessions" else kind
            version = 'v1' if report or shared else ENDPOINT_VERSIONS[scope][operation]
            path = "/" + version + "/" + scope
            if kind not in ("sessions", "catalog"):
                if session is None or not str(session) or str(session) in (".", ".."):
                    raise ValueError("Selecione uma sessão válida.")
                segment = bytes(QUrl.toPercentEncoding(str(session))).decode("ascii")
                path += "/" + segment + "/" + kind
                if report:
                    path = '/' + version + '/device-sessions/' + segment + '/' + SESSION_REPORTS[kind]
                if shared:
                    path = '/v1/map-links/' + segment + ('/export' if kind=='link_collections' else '')

            url = QUrl(base + path, QUrl.ParsingMode.StrictMode)

            query = QUrlQuery()
            if not shared and scope != "sessions" and kind not in ("catalog", "sessions"):
                if not period or len(period) != 2 or period[1] <= period[0]:
                    raise ValueError("Informe um período com fim posterior ao início.")
                query.addQueryItem("start_date", period[0])
                query.addQueryItem("end_date", period[1])
            if kind in ("collections", 'link_collections'):
                query.addQueryItem("format", "geojson")
            if kind == 'change_detail':
                if not params or set(params) != {'metric', 'start_date', 'end_date'}:
                    raise ValueError('Informe métrica e intervalo da mudança.')
                for key, value in params.items():
                    query.addQueryItem(key, str(value))
            url.setQuery(query)

            request = QNetworkRequest(url)

            request.setAttribute(
                QNetworkRequest.Attribute.RedirectPolicyAttribute,
                QNetworkRequest.RedirectPolicy.ManualRedirectPolicy,
            )
            request.setAttribute(
                QNetworkRequest.Attribute.CacheLoadControlAttribute,
                QNetworkRequest.CacheLoadControl.AlwaysNetwork,
            )
            request.setAttribute(
                QNetworkRequest.Attribute.CacheSaveControlAttribute,
                False,
            )

            request.setRawHeader(
                b"Accept",
                b"application/geo+json"
                if kind in ("collections", 'link_collections')
                else b"application/json",
            )
            # Complementary session reports have their own public access policy.
            # The UI only offers them for a session from the authorized catalog.
            # Never forward integration credentials to these separate routes.
            if not report and not shared:
                request.setRawHeader(b'X-Client-Id', client_id.encode('utf-8'))
                request.setRawHeader(b'X-Client-Secret', secret.encode('utf-8'))

            self._secret = secret
            self._kind = kind
            self._failure = ""
            self._buffer.clear()

            self._reply = QgsNetworkAccessManager.instance().get(request)
            # QGIS adds an inactivity timer to each reply. Use our configured
            # deadline instead, without changing the global QGIS timeout.
            network_timer = self._reply.findChild(QTimer, "timeoutTimer")
            if network_timer is not None:
                network_timer.stop()
                # QGIS may restart this timer on progress or authentication.
                network_timer.blockSignals(True)
            self._reply.readyRead.connect(self._read)
            self._reply.downloadProgress.connect(self._progress)
            self._reply.finished.connect(self._finished)

            self.busyChanged.emit(True)
            if self._timeout_seconds != -1:
                self._timer.start(self._timeout_seconds * 1000)

        except ValueError as error:
            self.failed.emit(str(error))

    def cancel(self):
        self._generation += 1
        if self._task is not None:
            self._task.cancel()
            self._task = None
        self._timer.stop()

        if self._reply is not None:
            reply, self._reply = self._reply, None
            reply.readyRead.disconnect(self._read)
            reply.finished.disconnect(self._finished)
            reply.downloadProgress.disconnect(self._progress)
            reply.abort()
            reply.deleteLater()

        self._buffer.clear()
        self._secret = None
        self.busyChanged.emit(False)

    def _timeout(self):
        if self._reply is not None:
            self._failure = "A API excedeu o tempo limite de {} segundos.".format(self._timeout_seconds)
            self._reply.abort()

    def _read(self):
        if self._reply is None:
            return

        self._buffer.extend(bytes(self._reply.readAll()))

    def _progress(self, done, total):
        self.progress.emit(min(done, 2147483647), min(total, 2147483647))

    def _finished(self):
        reply = self._reply
        if reply is None:
            return
        self._timer.stop()
        self._read()
        status = reply.attribute(QNetworkRequest.Attribute.HttpStatusCodeAttribute)
        network_error = reply.error() != QNetworkReply.NetworkError.NoError
        reply.readyRead.disconnect(self._read)
        reply.finished.disconnect(self._finished)
        reply.downloadProgress.disconnect(self._progress)
        self._reply = None
        reply.deleteLater()
        # Transfer ownership instead of copying/decoding the whole response in
        # the Qt event handler. Keep busy until parsing and secret checks finish.
        data, self._buffer = self._buffer, bytearray()
        secret, self._secret = self._secret, None
        kind, generation = self._kind, self._generation
        def finished(error, result=None):
            if sip.isdeleted(self) or generation != self._generation:
                return
            self._task = None
            self.busyChanged.emit(False)
            if task.isCanceled():
                self.failed.emit('Processamento da resposta cancelado.')
            elif error:
                self.failed.emit('Não foi possível processar a resposta da API.')
            elif result is not None:
                message, payload = result
                if message:
                    self.failed.emit(message)
                else:
                    self.received.emit(kind, payload)
        task = QgsTask.fromFunction(
            'J3M: processar resposta', decode_response,
            data=data, secret=secret, kind=kind, status=status,
            network_error=network_error, failure=self._failure,
            on_finished=finished)
        self._task = task
        QgsApplication.taskManager().addTask(self._task)


def _invalid_constant(value):
    raise ValueError('Invalid JSON constant')


def _contains_secret(value, secret, canceled):
    if canceled() or not secret:
        return False
    if isinstance(value, dict):
        return any(_contains_secret(k, secret, canceled) or
                   _contains_secret(v, secret, canceled) for k, v in value.items())
    if isinstance(value, list):
        return any(_contains_secret(item, secret, canceled) for item in value)
    return secret in str(value)


def decode_response(task, data, secret, kind, status, network_error, failure):
    """Worker-only parsing. Never return remote error bodies or reflected secrets."""
    if task.isCanceled():
        return None
    if failure:
        return failure, None
    payload = None
    no_data_kind = kind in ('indicators', 'collections', 'link_collections', 'table',
                           'range', 'aggregation', 'changes', 'change_detail')
    if status == 404 and no_data_kind:
        try:
            payload = json.loads(data.decode('utf-8-sig'), parse_constant=_invalid_constant)
        except (ValueError, UnicodeError, RecursionError):
            payload = None
        if (isinstance(payload, dict) and payload.get('success') is False and
                payload.get('message') in ('There is no data for the provided parameters.', 'No data found.')):
            return '', None
    if status in (401, 403):
        return 'Credenciais inválidas ou acesso não autorizado (HTTP 401/403).', None
    if status == 404:
        return 'Recurso ou rota não encontrada, sem dados ou sem acesso (HTTP 404).', None
    if status == 429:
        return 'Limite de requisições excedido (HTTP 429). Aguarde antes de tentar novamente.', None
    if status == 422:
        return 'A API recusou os parâmetros da consulta (HTTP 422).', None
    if status is not None and 300 <= status < 400:
        return 'Redirecionamento recusado. Contate o responsável pela configuração do plugin.', None
    if status is not None and not 200 <= status < 300:
        return 'A API retornou erro HTTP {}.'.format(status), None
    if network_error:
        return 'API indisponível ou falha de rede/TLS. Verifique o acesso e tente novamente.', None
    if status == 204:
        return '', None
    try:
        payload = json.loads(data.decode('utf-8-sig'), parse_constant=_invalid_constant)
        if task.isCanceled():
            return None
        if _contains_secret(payload, secret, task.isCanceled):
            return 'Resposta recusada por conter a credencial de acesso.', None
    except (ValueError, UnicodeError, RecursionError):
        return 'A API retornou uma resposta JSON inválida.', None
    return None if task.isCanceled() else ('', payload)
