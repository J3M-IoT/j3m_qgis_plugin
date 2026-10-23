"""Network failures, worker ownership and cancellation on real Qt event loops."""
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QObject, pyqtSignal, QCoreApplication, QEvent, QThread
from qgis.PyQt.QtNetwork import QNetworkReply
from qgis.core import QgsApplication, QgsProject
from j3m_connect.api import ApiClient, decode_response
from j3m_connect.layers import LayerLoader, _prepare_layer
from qt_helpers import wait_for
from test_workbench import fixture


class Reply(QObject):
    readyRead = pyqtSignal()
    finished = pyqtSignal()
    downloadProgress = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.status = 200
        self.body = b''
        self.network_error = QNetworkReply.NetworkError.NoError

    def attribute(self, key):
        return self.status

    def error(self):
        return self.network_error

    def readAll(self):
        body, self.body = self.body, b''
        return body

    def abort(self):
        self.network_error = QNetworkReply.NetworkError.OperationCanceledError
        self.finished.emit()

    def respond(self, status, body=b'', network_error=None):
        self.status, self.body = status, body
        self.network_error = network_error or QNetworkReply.NetworkError.NoError
        self.readyRead.emit()
        self.finished.emit()


class AsyncTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        language_patch = patch("j3m_connect.i18n._language", "pt-br")
        language_patch.start()
        cls.addClassCleanup(language_patch.stop)
        cls.app = QgsApplication.instance() or QgsApplication([], False)
        cls.app.initQgis()

    def setUp(self):
        self.manager = Mock()
        self.credentials = patch('j3m_connect.api.credentials', return_value=('https://example.test','client','test-secret'))
        self.network = patch('j3m_connect.api.QgsNetworkAccessManager.instance', return_value=self.manager)
        self.credentials.start()
        self.network.start()
        self.api = ApiClient()
        self.results, self.errors, self.busy = [], [], []
        self.api.received.connect(lambda kind,data: self.results.append((kind,data)))
        self.api.failed.connect(self.errors.append)
        self.api.busyChanged.connect(self.busy.append)

    def tearDown(self):
        if not sip.isdeleted(self.api):
            self.api.cancel()
        self.network.stop()
        self.credentials.stop()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def request(self, kind='collections'):
        reply = Reply()
        self.manager.get.return_value = reply
        self.api.get(kind,'uuid')
        return reply

    def test_http_errors_never_expose_remote_body(self):
        for status in (401,403,404,422,429,500,502,503,302):
            with self.subTest(status=status):
                self.errors.clear()
                reply = self.request()
                reply.respond(status,b'{"message":"test-secret PRIVATE REMOTE BODY"}')
                wait_for(lambda: bool(self.errors))
                self.assertFalse(self.results)
                self.assertNotIn('test-secret',self.errors[0])
                self.assertNotIn('PRIVATE',self.errors[0])
                self.assertFalse(self.busy[-1])
                self.assertIsNone(self.api._secret)

    def test_malformed_json_and_reflected_secret(self):
        for body in (b'{',b'\xff',b'{"x":NaN}',b'{"value":"test-secret"}',b'{"test-secret":1}'):
            with self.subTest(body=body):
                self.errors.clear()
                self.request().respond(200,body)
                wait_for(lambda: bool(self.errors))
                self.assertFalse(self.results)
                self.assertNotIn('test-secret',self.errors[0])

    def test_no_data_and_empty_success(self):
        for status, body in ((204,b''),(404,b'{"success":false,"message":"No data found."}')):
            self.results.clear()
            self.request().respond(status,body)
            wait_for(lambda: bool(self.results))
            self.assertEqual(self.results,[('collections',None)])
            self.assertFalse(self.errors)

    def test_timeout_and_network_failure(self):
        for error in (QNetworkReply.NetworkError.ConnectionRefusedError,QNetworkReply.NetworkError.SslHandshakeFailedError):
            self.errors.clear()
            self.request().respond(None,network_error=error)
            wait_for(lambda: bool(self.errors))
            self.assertIn('rede/TLS',self.errors[0])
        self.errors.clear()
        self.request()
        self.api._timeout()
        wait_for(lambda: bool(self.errors))
        self.assertIn('tempo limite',self.errors[0])

    def test_cancel_download_and_repeated_request(self):
        old = self.request()
        self.api.cancel()
        old.readyRead.emit()
        old.finished.emit()
        self.assertFalse(self.results)
        self.assertFalse(self.errors)
        self.request().respond(200,b'{"new":true}')
        wait_for(lambda: bool(self.results))
        self.assertEqual(self.results[0][1],{'new':True})

    def test_cancel_parsing_discards_stale_result(self):
        started, release, ended = threading.Event(), threading.Event(), threading.Event()
        def delayed(task, **kwargs):
            started.set()
            release.wait(10)
            try:
                return decode_response(task,**kwargs)
            finally:
                ended.set()
        try:
            with patch('j3m_connect.api.decode_response',delayed):
                self.request().respond(200,b'{"old":true}')
                wait_for(started.is_set)
                self.api.cancel()
            self.request().respond(200,b'{"new":true}')
            release.set()
            wait_for(lambda: ended.is_set() and bool(self.results))
            self.assertEqual(self.results,[('collections',{'new':True})])
            self.assertFalse(self.errors)
        finally:
            release.set()
            wait_for(ended.is_set)

    def test_layer_preparation_transfers_to_main_thread_and_cleans_cancellation(self):
        with tempfile.TemporaryDirectory() as directory, patch('j3m_connect.layers.QgsApplication.qgisSettingsDirPath',return_value=directory):
            loader = LayerLoader()
            ready, failures = [], []
            loader.failed.connect(failures.append)
            loader.load(fixture(),'Async',lambda layer,digest: ready.append((layer,digest)))
            wait_for(lambda: bool(ready) or bool(failures))
            self.assertFalse(failures)
            layer,digest = ready[0]
            self.assertEqual(layer.thread(),QThread.currentThread())
            import hashlib
            self.assertEqual(digest,hashlib.sha256(json.dumps(fixture(),ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest())
            QgsProject.instance().removeMapLayer(layer.id())
            QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
            started, release, ended = threading.Event(),threading.Event(),threading.Event()
            def delayed(task, **kwargs):
                result = _prepare_layer(task,**kwargs)
                started.set()
                release.wait(10)
                ended.set()
                return result
            baseline = set(Path(directory).rglob('*.geojson'))
            try:
                with patch('j3m_connect.layers._prepare_layer',delayed):
                    loader.load(fixture(),'Cancelled',lambda *args:self.fail('Stale layer published'))
                    wait_for(started.is_set)
                    loader.cancel()
                    loader.deleteLater()
                    QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
                    release.set()
                    wait_for(lambda: ended.is_set() and set(Path(directory).rglob('*.geojson')) == baseline)
                    self.assertFalse(QgsProject.instance().mapLayers())
            finally:
                release.set()
                wait_for(ended.is_set)

    def test_unload_while_layer_is_being_prepared(self):
        from qgis.PyQt.QtWidgets import QMainWindow
        from j3m_connect.j3m_connect import J3MConnect
        from test_integration import FakeApi
        window = QMainWindow()
        iface = Mock()
        iface.mainWindow.return_value = window
        iface.addDockWidget.side_effect = window.addDockWidget
        iface.removeDockWidget.side_effect = window.removeDockWidget
        started, release, ended = threading.Event(),threading.Event(),threading.Event()
        def delayed(task, **kwargs):
            result = _prepare_layer(task,**kwargs)
            started.set()
            release.wait(10)
            ended.set()
            return result
        with tempfile.TemporaryDirectory() as directory, \
                patch('j3m_connect.layers.QgsApplication.qgisSettingsDirPath',return_value=directory), \
                patch('j3m_connect.dialog.ApiClient',FakeApi), \
                patch('j3m_connect.dialog.settings.preferences',return_value=('','')), \
                patch('j3m_connect.layers._prepare_layer',delayed):
            plugin = J3MConnect(iface)
            plugin.initGui()
            plugin.run()
            try:
                plugin.dialog._pending_query=('devices',{'uuid':'sensor-a','name':'Fixture','timezone':'UTC'},['2026-10-19 00:00:00','2026-10-19 23:59:59'])
                plugin.dialog._add_layer(fixture())
                wait_for(started.is_set)
                plugin.unload()
                QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
                release.set()
                wait_for(lambda: ended.is_set() and not list(Path(directory).rglob('*.geojson')))
                self.assertFalse(QgsProject.instance().mapLayers())
                self.assertIsNone(plugin.dialog)
                plugin.initGui()
                plugin.unload()
                self.assertEqual(iface.addToolBarIcon.call_count,2)
                self.assertEqual(iface.removeToolBarIcon.call_count,2)
            finally:
                release.set()
                wait_for(ended.is_set)
                plugin.unload()
                window.close()

    def test_delete_client_while_parsing(self):
        started, release, ended = threading.Event(),threading.Event(),threading.Event()
        def delayed(task, **kwargs):
            started.set()
            release.wait(10)
            ended.set()
            return decode_response(task,**kwargs)
        try:
            with patch('j3m_connect.api.decode_response',delayed):
                self.request().respond(200,b'{"old":true}')
                wait_for(started.is_set)
                self.api.cancel()
                self.api.deleteLater()
                QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)
                release.set()
                wait_for(ended.is_set)
                self.assertFalse(self.results)
                self.assertFalse(self.errors)
        finally:
            release.set()
            wait_for(ended.is_set)
