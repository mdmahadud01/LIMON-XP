"""Load the supplied installed-layout archive without invoking pip on it."""
import hashlib
import os
from pathlib import Path, PurePosixPath
import shutil
import sys
import tarfile

ROOT = Path(__file__).resolve().parent
ARCHIVE = ROOT / "pyquotex-1.0.3.tar.gz"
EXPECTED_SHA256 = "719f58f95c78d9fa31693c3c0b813f11b01de82a21b3a5f478d4e88148c036d2"


def prepare_vendor():
    digest = hashlib.sha256(ARCHIVE.read_bytes()).hexdigest()
    if digest != EXPECTED_SHA256:
        raise RuntimeError("Bundled pyquotex checksum mismatch; restore the original archive.")
    # Vercel's deployed source directory is read-only. Extract bundled modules
    # into /tmp there; persistent hosts keep the vendor folder beside the app.
    vendor = (Path("/tmp/hypertrade-vendor") if os.getenv("VERCEL") else ROOT / "vendor")
    marker = vendor / ".hypertrade-patched-v4"
    if not marker.exists() or marker.read_text().strip() != digest:
        vendor.mkdir(exist_ok=True)
        with tarfile.open(ARCHIVE, "r:gz") as archive:
            for member in archive.getmembers():
                path = PurePosixPath(member.name)
                if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                    raise RuntimeError("Unsafe path in bundled archive")
                if not path.parts or path.parts[0] != "pyquotex":
                    continue
                target = vendor.joinpath(*path.parts)
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True)
                elif member.isfile():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.extractfile(member) as src, target.open("wb") as dest:
                        shutil.copyfileobj(src, dest)
        # Session credentials are RAM-only, never written to session.json.
        config = vendor / "pyquotex/config.py"
        source = config.read_text()
        source += '\n\n# HyperTrade override: no session secrets on disk.\ndef load_session(user_agent):\n    return {"cookies": None, "token": None, "user_agent": user_agent}\n\ndef update_session(session_data):\n    return dict(session_data)\n'
        config.write_text(source)
        stable = vendor / "pyquotex/stable_api.py"
        source = stable.read_text()
        source = source.replace('''        if not await self.check_connect():
            logger.debug("Reconnecting on websocket")
            return await self.connect()
''', '''        if not check or not await self.check_connect():
            return False, reason or "WebSocket authentication failed"
        if global_value.check_rejected_connection == 1:
            return False, "Session token rejected or expired"
''')
        source = source.replace('''    @staticmethod
    async def check_connect():
        await asyncio.sleep(2)
        if global_value.check_accepted_connection == 1:
            return True

        return False
''', '''    async def check_connect(self):
        ws = getattr(getattr(self.api, "websocket_client", None), "wss", None)
        sock = getattr(ws, "sock", None)
        return bool(global_value.check_accepted_connection == 1
                    and global_value.check_websocket_if_connect == 1
                    and sock and sock.connected)
''')
        stable.write_text(source)
        api = vendor / "pyquotex/api.py"
        source = api.read_text()
        source = source.replace('''        while True:
            if global_value.check_websocket_if_error:''', '''        connect_deadline = time.monotonic() + 30
        while True:
            if time.monotonic() > connect_deadline:
                return False, "WebSocket connection timed out"
            await asyncio.sleep(0.05)
            if global_value.check_websocket_if_error:''')
        start = source.index('    def send_ssid(self, timeout=10):')
        end = source.index('    async def connect(self, is_demo):', start)
        source = source[:start] + '''    async def send_ssid(self, timeout=15):
        if not global_value.SSID:
            return False
        global_value.check_accepted_connection = 0
        global_value.check_rejected_connection = 0
        self.ssid(global_value.SSID)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if global_value.check_rejected_connection == 1:
                return False
            if global_value.check_accepted_connection == 1:
                return True
            if global_value.check_websocket_if_connect == 0:
                return False
            await asyncio.sleep(0.05)
        return False

''' + source[end:]
        source = source.replace('check_ssid = self.send_ssid()', 'check_ssid = await self.send_ssid()')
        source = source.replace('                self.send_ssid()', '                await self.send_ssid()')
        source = source.replace('''        check_websocket, websocket_reason = await self.start_websocket()''', '''        global_value.check_websocket_if_error = False
        global_value.check_websocket_if_connect = None
        global_value.check_rejected_connection = 0
        global_value.check_accepted_connection = 0
        check_websocket, websocket_reason = await self.start_websocket()''')
        # Bound thread joins so logout cannot hang forever.
        source = source.replace('self.websocket_thread.join()', 'self.websocket_thread.join(timeout=3)')
        source = source.replace('"check_hostname": False,', '"check_hostname": True,')
        source = source.replace('"cert_reqs": ssl.CERT_NONE,', '"cert_reqs": ssl.CERT_REQUIRED,')
        source = source.replace('"reconnect": 5', '"reconnect": 0')
        api.write_text(source)
        ws = vendor / "pyquotex/ws/client.py"
        source = ws.read_text().replace('# cookie=self.api.cookies', 'cookie=self.api.session_data.get("cookies")')
        ws.write_text(source)
        marker.write_text(digest)
    if str(vendor) not in sys.path:
        sys.path.insert(0, str(vendor))
    return vendor


if __name__ == "__main__":
    path = prepare_vendor()
    from pyquotex.stable_api import Quotex
    import numpy
    print("Bundled pyquotex import OK; numpy=" + numpy.__version__)
