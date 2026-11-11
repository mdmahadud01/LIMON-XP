"""Optional standalone tunnel helper. Railway already starts the managed bot app."""
import os
import time
from telegram_runtime import Tunnel

def make_server_public():
    tunnel = Tunnel(int(os.getenv("PORT", "5000")))
    try:
        print(tunnel.start(), flush=True)
        while tunnel.process and tunnel.process.poll() is None:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        tunnel.stop()

if __name__ == "__main__":
    make_server_public()
