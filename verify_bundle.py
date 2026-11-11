"""Offline tests only. No real Telegram, Cloudflare, Quotex login or trades."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from vendor_bootstrap import prepare_vendor
prepare_vendor()
from telegram_runtime import Runtime, Tunnel, atomic_json


class FakeQuotex:
    created = []
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.closed = False
        self.api = types.SimpleNamespace(websocket_client=types.SimpleNamespace(
            wss=types.SimpleNamespace(on_message=None)))
        self.created.append(self)
    def set_token_csrf(self, *args, **kwargs):
        pass
    async def connect(self):
        return True, "offline mocked authentication"
    async def check_connect(self):
        return not self.closed
    async def close(self):
        self.closed = True
    async def change_account(self, mode):
        self.mode = mode


class BundleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = patch.dict(os.environ, {"DATA_DIR": self.tmp.name,
            "BOT_TOKEN": "123456:OFFLINE_TEST_TOKEN", "TELEGRAM_OWNER_ID": "101"})
        self.env.start()
        name = "hypertrade_offline_" + str(id(self))
        spec = importlib.util.spec_from_file_location(name, ROOT / "HyperTrade_TokenCSRF.py")
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)
        self.rt = Runtime(self.m)
        self.sent = []
        self.erased = []
        self.rt.send = lambda chat, text: self.sent.append((chat, text))
        self.rt.erase = lambda chat, msg: self.erased.append((chat, msg))
        self.m.load_signals()

    def tearDown(self):
        self.rt.shutdown()
        self.env.stop()
        self.tmp.cleanup()

    def message(self, text, uid=101, kind="private"):
        self.rt.handle({"chat": {"id": uid, "type": kind},
                        "from": {"id": uid}, "message_id": 12, "text": text})

    def start_loop(self):
        threading.Thread(target=self.rt._loop_thread, daemon=True).start()
        self.assertTrue(self.rt.loop_ready.wait(3))

    def wait_for(self, fn, timeout=4):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if fn():
                return
            time.sleep(0.025)
        self.fail("Timed out waiting for mocked worker")

    def candle(self):
        return {"time": "2026-11-07 12:00:00", "open": 1, "close": 2,
                "high": 3, "low": 0.5, "pair": "EURUSD", "payout": 85}

    def test_01_import_and_original_ui(self):
        self.assertGreater(len(self.m.UI_HTML), 100000)
        self.assertEqual(self.m.app.test_client().get('/').status_code, 200)
        self.assertFalse(self.m.BOT_FEED_STATE['logged_in'])

    def test_02_explicit_numpy_and_token_constructor(self):
        import numpy
        from pyquotex.stable_api import Quotex
        q = Quotex(ssid_token="OFFLINE_SSID", csrf_token="OFFLINE_CSRF")
        self.assertTrue(q.manual_token)
        self.assertEqual(q.session_data['token'], "OFFLINE_SSID")
        self.assertFalse((ROOT / 'session.json').exists())
        self.assertTrue(numpy.__version__)

    def test_03_owner_only(self):
        self.message('/start', uid=102)
        self.message('/start', kind='group')
        self.assertEqual(self.sent, [])
        self.assertEqual(self.rt.pending, {})
        self.message('/start')
        self.assertEqual(self.rt.pending[101]['step'], 'ssid')

    def test_04_separate_token_csrf_input(self):
        captured = []
        self.rt.login = lambda *args: captured.append(args)
        self.message('/start')
        self.message('OFFLINE_SSID')
        self.assertEqual(self.rt.pending[101]['step'], 'csrf')
        self.message('OFFLINE_CSRF')
        self.assertEqual(captured, [(101, 'OFFLINE_SSID', 'OFFLINE_CSRF')])
        self.assertNotIn(101, self.rt.pending)
        self.assertEqual(len(self.erased), 2)

    def test_05_json_token_csrf_input(self):
        captured = []
        self.rt.login = lambda *args: captured.append(args)
        self.message('/start')
        self.message('{"token":"OFFLINE_SSID","csrf":"OFFLINE_CSRF"}')
        self.assertEqual(captured[0], (101, 'OFFLINE_SSID', 'OFFLINE_CSRF'))

    def test_06_expired_input_and_cancel(self):
        self.message('/start')
        self.rt.pending[101]['expires'] = 0
        self.message('OFFLINE_SSID')
        self.assertNotIn(101, self.rt.pending)
        self.message('/start')
        self.message('/cancel')
        self.assertNotIn(101, self.rt.pending)

    def test_07_snapshot_roundtrip_and_no_credentials(self):
        self.m.update_market_data('EURUSD_1m', self.candle())
        self.m.PAYOUT_HISTORY['EURUSD_1m'] = {'2026-11-07 12:00:00': 85}
        self.m.QUOTEX_SSID_TOKEN = 'SECRET_SSID_ABC'
        self.m.QUOTEX_CSRF_TOKEN = 'SECRET_CSRF_DEF'
        self.rt.save()
        raw = (Path(self.tmp.name) / 'market_snapshot.json').read_text()
        self.assertNotIn('SECRET_', raw)
        self.m.MARKET_DATA.clear()
        self.m.PAYOUT_HISTORY.clear()
        self.rt.restore()
        self.assertEqual(self.m.MARKET_DATA['EURUSD_1m'][0]['close'], 2)
        self.assertEqual(self.m.PAYOUT_HISTORY['EURUSD_1m']['2026-11-07 12:00:00'], 85)

    def test_08_saved_candles_public_api(self):
        self.m.update_market_data('EURUSD_1m', self.candle())
        response = self.m.app.test_client().get('/?Pair=EURUSD&Time=1m&Candle=5')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['count'], 1)

    def test_09_signal_and_user_persistence(self):
        self.m.register_signal('EURUSD', '2026-11-07 12:00:00', 'BUY')
        self.assertTrue((Path(self.tmp.name) / 'signals_data.json').exists())
        self.m.save_users({'test@example.invalid': {'uid': 'offline-test'}})
        self.assertEqual(self.m.load_users()['test@example.invalid']['uid'], 'offline-test')

    def test_10_public_login_cannot_inherit_owner_token(self):
        self.m.QUOTEX_SSID_TOKEN = 'OWNER_SECRET'
        result = self.m.app.test_client().post('/quotex-login', json={})
        self.assertEqual(result.status_code, 400)
        self.assertNotIn('OWNER_SECRET', result.get_data(as_text=True))

    def test_11_credential_redaction(self):
        self.m.QUOTEX_SSID_TOKEN = 'SECRET_SSID'
        self.m.QUOTEX_CSRF_TOKEN = 'SECRET_CSRF'
        cleaned = self.rt.clean('SECRET_SSID SECRET_CSRF 123456:OFFLINE_TEST_TOKEN')
        self.assertNotIn('SECRET_', cleaned)
        self.assertNotIn('OFFLINE_TEST_TOKEN', cleaned)

    def test_12_pairing_is_not_first_user_takeover(self):
        self.rt.owner = None
        self.rt.pair_code = 'OFFLINE_PAIR_SECRET'
        self.message('/start', uid=202)
        self.assertIsNone(self.rt.owner)
        self.message('/claim WRONG', uid=202)
        self.assertIsNone(self.rt.owner)
        self.message('/claim OFFLINE_PAIR_SECRET', uid=101)
        self.assertEqual(self.rt.owner, 101)
        self.assertEqual(json.loads(self.rt.owner_file.read_text())['owner_id'], 101)

    def test_13_server_requires_successful_login(self):
        self.message('/server')
        self.assertIn('আগে /start', self.sent[-1][1])
        self.assertIsNone(self.rt.tunnel.process)

    def test_14_mocked_login_logout_relogin_keeps_candles(self):
        self.m.Quotex = FakeQuotex
        self.m.detect_markets = lambda q: [{'pair': 'EURUSD'}]
        async def fetch(q, pair, period):
            return [{'time': time.time()-60, 'open': 1, 'close': 2, 'high': 3, 'low': 0.5}]
        self.m.safe_fetch = fetch
        self.start_loop()
        self.rt.login(101, 'OFFLINE_SSID', 'OFFLINE_CSRF')
        self.wait_for(lambda: self.m.BOT_FEED_STATE.get('status') == 'online')
        self.wait_for(lambda: bool(self.m.MARKET_DATA))
        self.rt.logout()
        self.assertFalse(self.m.BOT_FEED_STATE['logged_in'])
        self.assertEqual(self.m.QUOTEX_SSID_TOKEN, '')
        self.assertEqual(self.m.QUOTEX_CSRF_TOKEN, '')
        self.assertTrue(self.m.MARKET_DATA)
        self.assertTrue((Path(self.tmp.name) / 'market_snapshot.json').exists())
        self.rt.login(101, 'OFFLINE_NEW_SSID', 'OFFLINE_NEW_CSRF')
        self.wait_for(lambda: self.m.BOT_FEED_STATE.get('status') == 'online')
        self.rt.logout()
        self.assertTrue(self.m.MARKET_DATA)

    def test_15_tunnel_missing_binary_is_explicit(self):
        with patch('telegram_runtime.subprocess.Popen', side_effect=FileNotFoundError):
            with self.assertRaisesRegex(RuntimeError, 'cloudflared not installed'):
                Tunnel(5000).start(timeout=0.1)

    def test_16_atomic_json_has_no_partial_temp(self):
        path = Path(self.tmp.name) / 'atomic.json'
        atomic_json(path, {'ok': True})
        self.assertEqual(json.loads(path.read_text()), {'ok': True})
        self.assertFalse(path.with_name('atomic.json.tmp').exists())

    def test_17_library_connection_checks_live_socket(self):
        from pyquotex.stable_api import Quotex
        from pyquotex import global_value
        q = Quotex(ssid_token='OFFLINE')
        global_value.check_accepted_connection = 1
        global_value.check_websocket_if_connect = 1
        q.api = types.SimpleNamespace(websocket_client=types.SimpleNamespace(
            wss=types.SimpleNamespace(sock=types.SimpleNamespace(connected=True))))
        self.assertTrue(asyncio.run(q.check_connect()))
        q.api.websocket_client.wss.sock.connected = False
        self.assertFalse(asyncio.run(q.check_connect()))

    def test_18_login_failure_does_not_report_online(self):
        class Rejected(FakeQuotex):
            async def connect(self):
                return False, 'Offline test rejected token'
        self.m.Quotex = Rejected
        self.start_loop()
        self.rt.login(101, 'OFFLINE_BAD_TOKEN', 'OFFLINE_CSRF')
        self.wait_for(lambda: self.m.BOT_FEED_STATE.get('status') == 'error')
        self.assertNotEqual(self.m.BOT_FEED_STATE['status'], 'online')
        self.rt.logout()

    def test_19_tunnel_url_reuse_and_stop_with_mock_process(self):
        class FakeProcess:
            def __init__(self):
                self.exited = threading.Event()
                self.stdout = self.lines()
            def lines(self):
                yield 'INFO https://offline-unit-test.trycloudflare.com ready\n'
                self.exited.wait(3)
            def poll(self):
                return 0 if self.exited.is_set() else None
            def terminate(self):
                self.exited.set()
            def kill(self):
                self.exited.set()
            def wait(self, timeout=None):
                self.exited.wait(timeout)
                return 0
        proc = FakeProcess()
        tunnel = Tunnel(5000)
        with patch('telegram_runtime.subprocess.Popen', return_value=proc) as popen:
            url = tunnel.start(timeout=1)
            self.assertEqual(url, 'https://offline-unit-test.trycloudflare.com')
            self.assertEqual(tunnel.start(timeout=1), url)
            self.assertEqual(popen.call_count, 1)
            tunnel.stop()
            self.assertIsNone(tunnel.url)
            self.assertTrue(proc.exited.is_set())

    def test_20_async_ssid_rejection_does_not_authorize(self):
        from pyquotex.api import QuotexAPI
        from pyquotex import global_value
        class RejectionHarness:
            def ssid(self, value):
                global_value.check_rejected_connection = 1
        global_value.SSID = 'OFFLINE_BAD'
        global_value.check_websocket_if_connect = 1
        result = asyncio.run(QuotexAPI.send_ssid(RejectionHarness(), timeout=0.1))
        self.assertFalse(result)
        self.assertEqual(global_value.check_accepted_connection, 0)

    def test_21_library_resets_closed_flag_before_connecting(self):
        from pyquotex.api import QuotexAPI
        from pyquotex import global_value
        testcase = self
        class ConnectHarness:
            manual_token = True
            async def start_websocket(self):
                testcase.assertIsNone(global_value.check_websocket_if_connect)
                global_value.check_websocket_if_connect = 1
                return True, 'mock websocket opened'
            async def send_ssid(self):
                global_value.check_accepted_connection = 1
                return True
        global_value.check_websocket_if_connect = 0
        result = asyncio.run(QuotexAPI.connect(ConnectHarness(), 1))
        self.assertTrue(result[0])


if __name__ == '__main__':
    unittest.main(verbosity=2)
