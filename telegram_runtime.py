"""Private Telegram control, durable market snapshots and managed Quick Tunnel."""
import asyncio
import atexit
from collections import deque
import contextlib
import hmac
import json
import logging
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import threading
import time

import requests


def atomic_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, separators=(",", ":"))
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


class Tunnel:
    def __init__(self, port):
        self.port = port
        self.process = None
        self.url = None
        self.ready = threading.Event()
        self.lock = threading.Lock()
        self.last_error = ""

    def _read(self, proc):
        try:
            for line in proc.stdout:
                match = re.search(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com\b", line)
                if match and self.process is proc:
                    self.url = match.group(0)
                    self.ready.set()
                if "ERR" in line and self.process is proc:
                    self.last_error = "Cloudflare connection error; check Railway network/logs."
        finally:
            if self.process is proc:
                self.url = None
                self.ready.set()

    def start(self, timeout=50):
        with self.lock:
            if self.process and self.process.poll() is None and self.url:
                return self.url
            self._stop_locked()
            self.ready.clear()
            self.last_error = ""
            binary = os.getenv("CLOUDFLARED_BIN", "cloudflared")
            try:
                self.process = subprocess.Popen(
                    [binary, "tunnel", "--no-autoupdate", "--protocol", "http2",
                     "--url", f"http://127.0.0.1:{self.port}"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, bufsize=1,
                )
            except FileNotFoundError:
                raise RuntimeError("cloudflared not installed; deploy using the supplied Dockerfile.") from None
            threading.Thread(target=self._read, args=(self.process,), daemon=True).start()
            if self.ready.wait(timeout) and self.url and self.process.poll() is None:
                # URL issuance is not an external end-to-end reachability guarantee.
                return self.url
            self._stop_locked()
            raise RuntimeError(self.last_error or "Cloudflare did not issue a URL in time; retry /server.")

    def _stop_locked(self):
        proc, self.process = self.process, None
        self.url = None
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)

    def stop(self):
        with self.lock:
            self._stop_locked()


class Runtime:
    def __init__(self, module):
        self.m = module
        self.data = Path(module.DATA_DIR)
        self.data.mkdir(parents=True, exist_ok=True)
        self.snapshot_lock = threading.RLock()
        self.save_lock = threading.Lock()
        self.owner_lock = threading.Lock()
        self.session_lock = threading.Lock()
        self.events_lock = threading.Lock()
        self.events = deque(maxlen=100)
        self.stop_event = threading.Event()
        self.loop_ready = threading.Event()
        self.loop = None
        self.feed_task = None
        self.clients = []
        self.generation = 0
        self.pending = {}
        self.owner_file = self.data / "telegram_owner.json"
        self.owner = self._read_owner()
        self.pair_code = os.getenv("TELEGRAM_PAIR_CODE", "").strip() or secrets.token_urlsafe(18)
        self.pair_attempts = {}
        self.bot_token = os.getenv("BOT_TOKEN", "").strip()
        self.bot_api = "https://api.telegram.org/bot" + self.bot_token + "/"
        self.http = requests.Session()
        self.tunnel = Tunnel(module.PORT)
        self._patch_market_functions()
        self.restore()
        self.m.BOT_FEED_STATE.update(logged_in=False, status="offline")
        # No automatic login from environment or stale credentials on restart.
        self.m.QUOTEX_SSID_TOKEN = ""
        self.m.QUOTEX_CSRF_TOKEN = ""
        self.m.AUTO_TRADE_LOOP = None

    def _read_owner(self):
        configured = os.getenv("TELEGRAM_OWNER_ID", "").strip()
        if configured:
            return int(configured)
        try:
            return int(json.loads(self.owner_file.read_text())["owner_id"])
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def clean(self, text):
        text = str(text)
        for secret in (self.bot_token, self.m.QUOTEX_SSID_TOKEN, self.m.QUOTEX_CSRF_TOKEN):
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return re.sub(r"bot\d+:[A-Za-z0-9_-]+", "bot[REDACTED]", text)[:4000]

    def event(self, text):
        line = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()) + " | " + self.clean(text)
        with self.events_lock:
            self.events.append(line)
        print(line, flush=True)

    def _patch_market_functions(self):
        for name in ("update_market_data", "update_payout_history"):
            original = getattr(self.m, name)
            def locked(*args, _fn=original, **kwargs):
                with self.snapshot_lock:
                    return _fn(*args, **kwargs)
            setattr(self.m, name, locked)
        build = self.m.build_quotex_client
        def tracked_build():
            client = build()
            self.clients.append(client)
            if len(self.clients) > 32:
                self.clients = self.clients[-32:]
            return client
        self.m.build_quotex_client = tracked_build
        original_launch = self.m._auto_launch
        def launch(*args, **kwargs):
            if self.m.BOT_FEED_STATE.get("status") != "online":
                return False
            return original_launch(*args, **kwargs)
        self.m._auto_launch = launch

    def restore(self):
        path = self.data / "market_snapshot.json"
        if not path.exists():
            return
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
            with self.snapshot_lock:
                self.m.MARKET_DATA.update({k: deque(v, maxlen=self.m.MAX_CANDLES)
                    for k, v in saved.get("market_data", {}).items() if isinstance(v, list)})
                self.m.PAYOUT_HISTORY.update(saved.get("payout_history", {}))
                self.m.ALL_INSTRUMENTS[:] = saved.get("instruments", [])
            self.event("Saved candles and payout history restored (live feed not yet connected).")
        except Exception as exc:
            self.event("Snapshot restore failed: " + type(exc).__name__ + "; original file retained.")
            # Preserve a corrupt snapshot before any future writes.
            path.rename(path.with_name("market_snapshot.corrupt." + str(int(time.time())) + ".json"))

    def save(self):
        with self.save_lock:
            with self.snapshot_lock:
                saved = {"version": 1, "saved_at": time.time(),
                    "market_data": {k: list(v) for k, v in self.m.MARKET_DATA.items()},
                    "payout_history": {k: dict(v) for k, v in self.m.PAYOUT_HISTORY.items()},
                    "instruments": list(self.m.ALL_INSTRUMENTS)}
            atomic_json(self.data / "market_snapshot.json", saved)

    def api(self, method, payload=None, timeout=15):
        try:
            response = self.http.post(self.bot_api + method, json=payload or {}, timeout=timeout)
            data = response.json()
            if not data.get("ok"):
                # Never include the request URL, body, token or credential text in logs.
                self.event("Telegram API " + method + " failed (HTTP " + str(response.status_code) + ").")
                return None
            return data.get("result")
        except (requests.RequestException, ValueError):
            self.event("Telegram API " + method + " temporarily unavailable.")
            return None

    def send(self, chat, text):
        return self.api("sendMessage", {"chat_id": chat, "text": self.clean(text)[:4000],
                                       "disable_web_page_preview": True})

    def erase(self, chat, message_id):
        self.api("deleteMessage", {"chat_id": chat, "message_id": message_id})

    def start(self):
        if not self.bot_token:
            raise RuntimeError("Set the BOT_TOKEN environment variable in your hosting provider before starting.")
        if not self.owner:
            print("SECURE BOT SETUP: In a PRIVATE bot chat send /claim " + self.pair_code,
                  flush=True)
            print("Or set TELEGRAM_OWNER_ID to your numeric Telegram user ID.", flush=True)
        else:
            self.event("Telegram owner configured; use /start in your private bot chat.")
        threading.Thread(target=self._loop_thread, name="quotex-worker", daemon=True).start()
        if not self.loop_ready.wait(10):
            raise RuntimeError("Async worker failed to start")
        threading.Thread(target=self._snapshots, name="snapshot-writer", daemon=True).start()
        threading.Thread(target=self._poll, name="telegram-poll", daemon=True).start()

    def _loop_thread(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        self.loop_ready.set()
        self.loop.run_forever()
        self.loop.close()

    def _snapshots(self):
        while not self.stop_event.wait(30):
            try:
                self.save()
            except Exception as exc:
                self.event("Snapshot write failed: " + type(exc).__name__)

    async def _disconnect(self):
        m = self.m
        m.BOT_FEED_STATE.update(logged_in=False, status="offline")
        m.QUOTEX_SSID_TOKEN = ""
        m.QUOTEX_CSRF_TOKEN = ""
        task, self.feed_task = self.feed_task, None
        if task:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        # Stop pending automatic orders, but already placed broker orders cannot be undone.
        with m.QUOTEX_AUTO_LOCK:
            accounts = list(m.QUOTEX_AUTO_STATE.values())
        for account in accounts:
            account["connected"] = False
            account["settings"]["enabled"] = False
            if account.get("trade"):
                account["trade"]["cancelled"] = True
            client = account.get("client")
            if client:
                self.clients.append(client)
            account["client"] = None
        clients, self.clients = self.clients, []
        async def close_one(client):
            with contextlib.suppress(Exception):
                await asyncio.wait_for(client.close(), timeout=8)
        unique = {id(client): client for client in clients}
        if unique:
            await asyncio.gather(*(close_one(client) for client in unique.values()))
        m.q_instance = None
        m.QUOTEX_SSID_TOKEN = ""
        m.QUOTEX_CSRF_TOKEN = ""
        m.RUNNING_CANDLES.clear()
        # Shared pyquotex connection flags must not leak into the next login.
        from pyquotex import global_value
        global_value.SSID = None
        global_value.check_websocket_if_connect = 0
        global_value.check_websocket_if_error = False
        global_value.check_rejected_connection = 0
        global_value.check_accepted_connection = 0

    async def _login(self, ssid, csrf):
        await self._disconnect()
        self.m.QUOTEX_SSID_TOKEN = ssid
        self.m.QUOTEX_CSRF_TOKEN = csrf
        self.m.BOT_FEED_STATE.update(logged_in=True, status="starting")
        self.feed_task = asyncio.create_task(self.m.background_market_loop())

    def login(self, chat, ssid, csrf):
        with self.session_lock:
            self.generation += 1
            version = self.generation
            future = asyncio.run_coroutine_threadsafe(self._login(ssid, csrf), self.loop)
        self.event("Token/CSRF received; connecting to Quotex. Credentials hidden.")
        self.send(chat, "🔐 Token/CSRF পেয়েছি। Quotex connection যাচাই করছি…")
        threading.Thread(target=self._watch_login, args=(chat, version, future), daemon=True).start()

    def _watch_login(self, chat, version, future):
        try:
            future.result(timeout=25)
            last = None
            deadline = time.monotonic() + 90
            while version == self.generation and not self.stop_event.is_set():
                state = self.m.BOT_FEED_STATE.get("status")
                if state != last:
                    last = state
                    self.event("Quotex login state: " + str(state))
                    if state == "online":
                        self.send(chat, "✅ Quotex login সফল। Live candle collection চলছে।\n/server → public tunnel URL\n/status → অবস্থা\n/logout → logout")
                    elif state == "error":
                        self.send(chat, "❌ Quotex connection/login ব্যর্থ। Fresh Token/CSRF অথবা matching QUOTEX_USER_AGENT লাগতে পারে। /logs দেখুন; নতুন করে দিতে /logout তারপর /start।")
                if time.monotonic() > deadline:
                    if state != "online":
                        self.send(chat, "⏳ ৯০ সেকেন্ডেও login নিশ্চিত হয়নি। /status দেখুন, অথবা /logout করে /start দিয়ে fresh Token/CSRF দিন।")
                    return
                time.sleep(1)
        except Exception as exc:
            if version == self.generation:
                self.event("Login worker failed: " + type(exc).__name__)
                self.send(chat, "❌ Login worker ব্যর্থ/সময় শেষ। /logout করে আবার /start দিন।")

    def logout(self, chat=None):
        with self.session_lock:
            self.generation += 1
            self.pending.clear()
            self.m.BOT_FEED_STATE.update(logged_in=False, status="offline")
            future = asyncio.run_coroutine_threadsafe(self._disconnect(), self.loop)
            future.result(timeout=35)
        self.tunnel.stop()
        self.save()
        self.event("Logged out; credentials cleared, tunnel stopped, saved history retained.")
        if chat:
            self.send(chat, "✅ Logout হয়েছে; Token/CSRF মুছে দেওয়া হয়েছে এবং tunnel বন্ধ। আগের candle/history রাখা আছে।\nআবার login: /start\nইতিমধ্যে broker-এ placed trade logout দিয়ে cancel হয় না।")

    def _server(self, chat, version):
        try:
            # Serialize against logout so a late /server cannot reopen its tunnel.
            with self.session_lock:
                if version != self.generation or self.m.BOT_FEED_STATE.get("status") != "online":
                    return
                url = self.tunnel.start()
                if version != self.generation:
                    self.tunnel.stop()
                    return
            self.event("Cloudflare Quick Tunnel URL issued.")
            self.send(chat, "🌍 Public server URL:\n" + url + "\n\nনতুন tunnel হলে URL বদলাবে। /logout করলে এই tunnel বন্ধ হবে।")
        except Exception as exc:
            self.event("Tunnel failed: " + type(exc).__name__)
            self.send(chat, "❌ " + str(exc))

    def status_text(self):
        with self.snapshot_lock:
            candles = sum(len(v) for v in self.m.MARKET_DATA.values())
            markets = len(self.m.MARKET_DATA)
        url = self.tunnel.url if self.tunnel.process and self.tunnel.process.poll() is None else "বন্ধ"
        return (f"Feed: {self.m.BOT_FEED_STATE.get('status')}\nSaved/current candles: {candles}\n"
                f"Market keys: {markets}\nTunnel: {url}\nData directory: {self.data}\n"
                "History stored ≠ live connection. /logs দিয়ে login log দেখুন।")

    def handle(self, message):
        chat = message.get("chat", {})
        user = message.get("from", {})
        if chat.get("type") != "private" or user.get("is_bot"):
            return
        chat_id, uid = chat.get("id"), user.get("id")
        if not isinstance(uid, int):
            return
        text = (message.get("text") or "").strip()
        command = text.split(maxsplit=1)[0].split("@")[0].lower() if text else ""
        if not self.owner:
            if command == "/claim":
                now = time.monotonic()
                attempts = [t for t in self.pair_attempts.get(uid, []) if now - t < 600]
                if len(attempts) >= 5:
                    return
                attempts.append(now)
                self.pair_attempts[uid] = attempts
                value = text.partition(" ")[2].strip()
                self.erase(chat_id, message["message_id"])
                if not hmac.compare_digest(value, self.pair_code):
                    self.send(chat_id, "Pairing code ভুল। Railway deployment log থেকে code নিন।")
                    return
                with self.owner_lock:
                    if self.owner is None:
                        self.owner = uid
                        atomic_json(self.owner_file, {"owner_id": uid})
                        self.pair_code = ""
                self.event("Private Telegram owner paired.")
                self.send(chat_id, "✅ Owner pairing সম্পন্ন। /start দিন।")
            elif command == "/start":
                self.send(chat_id, "🔒 প্রথমবার setup: Railway logs-এর SECURE BOT SETUP থেকে /claim code পাঠান, অথবা TELEGRAM_OWNER_ID variable দিন।")
            return
        if uid != self.owner:
            # Do not expose status or permit anyone else to control credentials/tunnels.
            return
        if command in ("/start", "/login"):
            if self.m.BOT_FEED_STATE.get("logged_in"):
                self.send(chat_id, "বর্তমান login বদলাতে আগে /logout দিন।\n" + self.status_text())
                return
            self.pending[uid] = {"step": "ssid", "expires": time.monotonic() + 300}
            self.send(chat_id, "🔐 Quotex SSID/Session Token পাঠান। এরপর আলাদাভাবে CSRF চাইব।\nঅথবা এক message-এ JSON: {\"token\":\"...\",\"csrf\":\"...\"}\n৫ মিনিটের মধ্যে দিন। শুধু আপনার নিজের account ব্যবহার করুন।")
        elif command == "/cancel":
            self.pending.pop(uid, None)
            self.send(chat_id, "Login input বাতিল। /start দিয়ে আবার শুরু করুন।")
        elif command == "/logout":
            try:
                self.logout(chat_id)
            except Exception as exc:
                self.tunnel.stop()
                self.event("Logout cleanup incomplete: " + type(exc).__name__)
                self.send(chat_id, "⚠️ Logout cleanup সময় শেষ; tunnel বন্ধ। /status দেখুন; প্রয়োজন হলে Railway restart দিন।")
        elif command == "/server":
            if self.m.BOT_FEED_STATE.get("status") != "online":
                self.send(chat_id, "আগে /start দিয়ে Token/CSRF login সফল করুন।")
                return
            self.send(chat_id, "⏳ Cloudflare tunnel URL তৈরি করছি…")
            threading.Thread(target=self._server, args=(chat_id, self.generation), daemon=True).start()
        elif command == "/status":
            self.send(chat_id, self.status_text())
        elif command == "/logs":
            with self.events_lock:
                text = "\n".join(list(self.events)[-15:]) or "এখনও login log নেই।"
            self.send(chat_id, text)
        elif command == "/help":
            self.send(chat_id, "/start — Token/CSRF login\n/server — trycloudflare URL\n/logout — logout, tunnel stop, history retain\n/status — feed/data status\n/logs — sanitized login logs\n/cancel — cancel credential input")
        elif uid in self.pending:
            pending = self.pending[uid]
            self.erase(chat_id, message["message_id"])
            if time.monotonic() > pending["expires"]:
                self.pending.pop(uid, None)
                self.send(chat_id, "Login input expired। /start দিন।")
                return
            if not text or len(text) > 8192:
                self.send(chat_id, "Token/CSRF text invalid বা অনেক বড়। আবার দিন।")
                return
            if pending["step"] == "ssid":
                if text.startswith("{"):
                    try:
                        data = json.loads(text)
                        ssid = data.get("ssid_token") or data.get("token") or data.get("ssid")
                        csrf = data.get("csrf_token") or data.get("csrf")
                        if not isinstance(ssid, str) or not isinstance(csrf, str) or not ssid.strip() or not csrf.strip():
                            raise ValueError()
                    except (ValueError, TypeError, AttributeError):
                        self.send(chat_id, "JSON-এ non-empty token ও csrf string দিন।")
                        return
                    self.pending.pop(uid, None)
                    self.login(chat_id, ssid.strip(), csrf.strip())
                else:
                    pending.update(step="csrf", ssid=text.strip().strip('\"\''), expires=time.monotonic() + 300)
                    self.send(chat_id, "✅ SSID পেয়েছি। এবার CSRF / XSRF-TOKEN পাঠান।")
            else:
                self.pending.pop(uid, None)
                self.login(chat_id, pending["ssid"], text.strip().strip('\"\''))
        elif command.startswith("/"):
            self.send(chat_id, "Command পাওয়া যায়নি। /help দিন।")

    def _poll(self):
        self.api("deleteWebhook", {"drop_pending_updates": True})
        self.api("setMyCommands", {"commands": [
            {"command": "start", "description": "Token/CSRF login"},
            {"command": "server", "description": "Public Cloudflare URL"},
            {"command": "logout", "description": "Logout; keep history"},
            {"command": "status", "description": "Feed and data status"},
            {"command": "logs", "description": "Safe login logs"},
            {"command": "cancel", "description": "Cancel login input"}]})
        # Discard stale credentials/commands queued while the server was offline.
        old = self.api("getUpdates", {"offset": -1, "timeout": 0})
        offset = old[-1]["update_id"] + 1 if old else 0
        while not self.stop_event.is_set():
            updates = self.api("getUpdates", {"offset": offset, "timeout": 20,
                "allowed_updates": ["message"]}, timeout=30)
            if updates is None:
                self.stop_event.wait(4)
                continue
            for update in updates:
                offset = update["update_id"] + 1
                try:
                    self.handle(update.get("message", {}))
                except Exception as exc:
                    self.event("Telegram command failed: " + type(exc).__name__)
            # Expire buffered credentials even when no new message arrives.
            for uid, item in list(self.pending.items()):
                if time.monotonic() > item["expires"]:
                    self.pending.pop(uid, None)

    def shutdown(self):
        if self.stop_event.is_set():
            return
        self.stop_event.set()
        try:
            if self.loop and self.loop.is_running():
                self.logout()
                async def cancel_remaining():
                    current = asyncio.current_task()
                    tasks = [t for t in asyncio.all_tasks() if t is not current]
                    for task in tasks:
                        task.cancel()
                    if tasks:
                        await asyncio.gather(*tasks, return_exceptions=True)
                asyncio.run_coroutine_threadsafe(cancel_remaining(), self.loop).result(timeout=10)
                self.loop.call_soon_threadsafe(self.loop.stop)
        except Exception:
            self.tunnel.stop()
        with contextlib.suppress(Exception):
            self.save()


def run(module):
    runtime = Runtime(module)
    module.load_signals()
    module.app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
    @module.app.get("/healthz")
    def healthz():
        return {"ok": True, "feed": module.BOT_FEED_STATE.get("status", "offline")}
    @module.app.before_request
    def restrict_shared_credentials():
        # The owner feed credentials must never be inherited by public UI traders.
        if module.request.path == "/quotex-login":
            data = module.request.get_json(silent=True) or {}
            if not data.get("ssid_token"):
                return module.jsonify(success=False, message="Supply your own SSID token"), 400
    runtime.start()
    atexit.register(runtime.shutdown)
    def terminate(signum, frame):
        runtime.shutdown()
        raise SystemExit(0)
    signal.signal(signal.SIGTERM, terminate)
    signal.signal(signal.SIGINT, terminate)
    runtime.event("HTTP server starting; use Telegram /start to login. No console credential prompts.")
    module.app.run(host=module.HOST, port=module.PORT, threaded=True, debug=False, use_reloader=False)
