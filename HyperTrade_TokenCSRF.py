import asyncio
import threading
import queue
import json
import time
import os
import smtplib
from collections import deque
from datetime import datetime, timezone, timedelta
import pytz
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from flask import Flask, request, jsonify, send_file, Response, stream_with_context
from flask_cors import CORS
from flask_sock import Sock
from pathlib import Path
from vendor_bootstrap import prepare_vendor
prepare_vendor()
from pyquotex.stable_api import Quotex

# Runtime data belongs to a mounted Railway volume, not the deployment image.
# Vercel functions have a read-only application bundle; /tmp is the writable area.
# It is ephemeral, so use a persistent volume on Railway/Render for long-running use.
_default_data_dir = "/tmp/hypertrade-data" if os.getenv("VERCEL") else str(Path(__file__).resolve().parent / "data")
DATA_DIR = Path(os.getenv("DATA_DIR") or os.getenv("RAILWAY_VOLUME_MOUNT_PATH") or _default_data_dir).resolve()
DATA_DIR.mkdir(parents=True, exist_ok=True)


import re
import traceback
from io import BytesIO
import urllib.request

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None


# ==========================================
# 🔐 APP PASSWORD (server-side, secure)
# ==========================================


# ==========================================
# EMBEDDED WEB UI (index.html) - served directly from this file
# ==========================================
UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover" />
    <title>HyperTrade — RAVITH AI PRO</title>

    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/lucide@latest"></script>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet" />

    <style>
        :root {
            --bg: #cfe7f4;
            --text: #0a2540;
            --muted: #4a6b82;
            --primary: #0ea5a4;
            --red: #ef4444;
            --glass-alpha: 0.30;
            --glass-border-alpha: 0.7;
            --glass-bg-rgb: 255, 255, 255;
            --glass-border-rgb: 255, 255, 255;
            --speed-multiplier: 1;
            --anim-speed: 1;
            --glass-blur: 44px;
            --glass-opacity: 0.30;
            --indicator-glow: 0.08;
            --ui-scale: 1;
            --anim-smooth: cubic-bezier(0.22, 1, 0.36, 1);
            --anim-spring: cubic-bezier(0.34, 1.45, 0.64, 1);
            --font-base: 12px;
            --watermark-text: "𝐑𝐀𝐕𝐈𝐓𝐇 𝐒𝐒";
            --dashboard-name: "RAVITH PRO";
        }

        * {
            box-sizing: border-box;
            -webkit-tap-highlight-color: transparent;
            font-family: 'JetBrains Mono', monospace;
            margin: 0;
            padding: 0;
        }

        html { font-size: var(--font-base); }

        body {
            background:
                radial-gradient(circle at 12% 15%, rgba(140, 210, 245, 0.55), transparent 42%),
                radial-gradient(circle at 88% 10%, rgba(180, 230, 255, 0.45), transparent 42%),
                radial-gradient(circle at 50% 90%, rgba(170, 225, 250, 0.40), transparent 48%),
                radial-gradient(circle at 5% 85%, rgba(150, 215, 245, 0.35), transparent 40%),
                linear-gradient(165deg, #bfe0ef 0%, #d0e9f6 25%, #c7e4f2 50%, #d6ecf7 75%, #cce6f3 100%);
            color: var(--text);
            overflow-x: hidden;
            min-height: 100vh;
            transition: background 0.4s ease, color 0.4s ease;
            font-size: 1rem;
            padding-top: 48px;
            padding-bottom: 70px;
            background-attachment: fixed;
        }

        body.dark-mode {
            --bg: #061019;
            --text: #e6f2f8;
            --muted: #8bb1c9;
            --glass-alpha: 0.16;
            --glass-border-alpha: 0.28;
            --glass-bg-rgb: 60, 120, 160;
            --glass-border-rgb: 150, 210, 245;
            background:
                radial-gradient(circle at 12% 15%, rgba(30, 100, 140, 0.45), transparent 42%),
                radial-gradient(circle at 88% 10%, rgba(50, 130, 180, 0.35), transparent 42%),
                radial-gradient(circle at 50% 90%, rgba(20, 90, 140, 0.40), transparent 48%),
                radial-gradient(circle at 5% 85%, rgba(15, 70, 110, 0.35), transparent 40%),
                linear-gradient(165deg, #050c14 0%, #081722 25%, #061019 50%, #081825 75%, #050e17 100%);
            background-attachment: fixed;
        }

        .ambient {
            position: fixed;
            inset: 0;
            z-index: -2;
            pointer-events: none;
            background:
                radial-gradient(circle at 12% 18%, rgba(120, 210, 250, 0.25), transparent 42%),
                radial-gradient(circle at 88% 12%, rgba(160, 220, 255, 0.22), transparent 42%),
                radial-gradient(circle at 50% 88%, rgba(190, 230, 250, 0.18), transparent 45%);
        }
        body.dark-mode .ambient {
            background:
                radial-gradient(circle at 12% 18%, rgba(40, 130, 180, 0.20), transparent 42%),
                radial-gradient(circle at 88% 12%, rgba(60, 150, 200, 0.16), transparent 42%),
                radial-gradient(circle at 50% 88%, rgba(30, 110, 160, 0.18), transparent 45%);
        }

        #app-wrapper {
            min-height: 100vh;
            transition: filter calc(0.4s * var(--speed-multiplier)) var(--anim-smooth),
                transform calc(0.4s * var(--speed-multiplier)) var(--anim-smooth);
        }
        #app-wrapper.blur-active {
            filter: blur(8px) brightness(0.9);
            transform: scale(0.97);
            pointer-events: none;
        }

        main {
            position: relative;
            max-width: 850px;
            margin: 0 auto;
            padding: 16px 16px 20px;
            min-height: 100vh;
            overflow: hidden;
        }

        .view-container {
            position: absolute;
            top: 0;
            left: 16px;
            right: 16px;
            opacity: 0;
            pointer-events: none;
            transform: translateX(36px);
            transition: transform calc(0.5s * var(--anim-speed)) var(--anim-smooth),
                opacity calc(0.45s * var(--anim-speed)) var(--anim-smooth);
            will-change: transform, opacity;
        }
        .view-container.active {
            opacity: 1;
            pointer-events: auto;
            transform: translateX(0);
            position: relative;
            top: 0;
            left: 0;
            right: 0;
        }
        .view-container.exit-left { transform: translateX(-36px); opacity: 0; }
        .view-container.exit-right { transform: translateX(36px); opacity: 0; }

        .hyper-group {
            position: relative;
            background: linear-gradient(135deg,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.95)) 0%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.32)) 45%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.55)) 100%);
            border: 1px solid rgba(var(--glass-border-rgb), var(--glass-border-alpha));
            border-radius: 20px;
            overflow: hidden;
            margin-bottom: 14px;
            backdrop-filter: blur(var(--glass-blur)) saturate(200%);
            -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(200%);
            box-shadow:
                inset 0 1.5px 0 rgba(255, 255, 255, 0.85),
                inset 0 -1px 0 rgba(255, 255, 255, 0.20),
                inset 0 0 32px rgba(200, 235, 255, 0.10),
                0 8px 32px rgba(90, 150, 200, 0.10);
            transition: background 0.3s ease, border 0.3s ease;
        }
        .hyper-group::before {
            content: '';
            position: absolute;
            top: 0; left: 0; right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.95) 20%, rgba(255,255,255,0.95) 80%, transparent);
            pointer-events: none;
            z-index: 2;
        }
        body.dark-mode .hyper-group {
            background: linear-gradient(135deg,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 1.0)) 0%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.32)) 45%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.60)) 100%);
            border-color: rgba(var(--glass-border-rgb), var(--glass-border-alpha));
            box-shadow:
                inset 0 1.5px 0 rgba(180, 225, 255, 0.22),
                inset 0 -1px 0 rgba(100, 160, 210, 0.10),
                inset 0 0 32px rgba(60, 140, 200, 0.10),
                0 8px 32px rgba(0, 0, 0, 0.30);
        }

        .hyper-item {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 12px 16px;
            cursor: pointer;
            transition: background 0.2s ease;
            position: relative;
        }
        .hyper-item:not(:last-child)::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 16px;
            right: 16px;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(var(--glass-border-rgb), calc(var(--glass-border-alpha) * 0.6)) 20%, rgba(var(--glass-border-rgb), calc(var(--glass-border-alpha) * 0.6)) 80%, transparent);
        }
        .hyper-item:active { background: rgba(255, 255, 255, 0.15); }

        .item-left { display: flex; align-items: center; gap: 10px; }
        .item-icon {
            width: 28px; height: 28px;
            border-radius: 8px;
            background: rgba(14, 165, 164, 0.15);
            color: var(--primary);
            display: grid;
            place-items: center;
            font-size: 0.9rem;
        }
        .item-title { font-size: 0.8rem; font-weight: 600; color: var(--text); }
        .item-subtitle { font-size: 0.65rem; color: var(--muted); margin-top: 2px; }
        .item-right { display: flex; align-items: center; gap: 6px; }
        .item-value { font-size: 0.75rem; color: var(--muted); font-weight: 500; }
        .item-arrow { color: rgba(10, 37, 64, 0.35); }
        body.dark-mode .item-arrow { color: rgba(255, 255, 255, 0.35); }

        .toggle {
            width: 38px; height: 22px;
            border-radius: 11px;
            background: rgba(15, 23, 42, 0.22);
            position: relative;
            cursor: pointer;
            transition: background 0.3s ease;
            flex-shrink: 0;
        }
        .toggle::after {
            content: '';
            position: absolute;
            top: 2px; left: 2px;
            width: 18px; height: 18px;
            border-radius: 50%;
            background: white;
            transition: transform calc(0.3s * var(--speed-multiplier)) var(--anim-spring);
            box-shadow: 0 2px 5px rgba(0, 0, 0, 0.2);
        }
        .toggle.active { background: var(--primary); }
        .toggle.active::after { transform: translateX(16px); }

        .signal-panel { text-align: center; padding: 20px 14px; }

        .chart-panel {
            position: relative;
            border-radius: 18px;
            overflow: hidden;
            background: linear-gradient(140deg, rgba(0, 18, 36, 0.85), rgba(5, 10, 20, 0.92));
            border: 1px solid rgba(120, 210, 245, 0.30);
            box-shadow:
                inset 0 1px 0 rgba(180, 225, 255, 0.20),
                0 8px 32px rgba(90, 150, 200, 0.15);
            margin: 0 auto 12px;
            aspect-ratio: 16 / 9;
            width: 100%;
        }
        #chart { display: block; width: 100%; height: 100%; background: #050508; image-rendering: auto; }
        .chart-status {
            position: absolute;
            top: 8px; right: 10px;
            display: flex; align-items: center; gap: 5px;
            padding: 3px 8px;
            border-radius: 10px;
            background: rgba(0, 242, 254, 0.18);
            border: 1px solid rgba(0, 242, 254, 0.45);
            color: #00F2FE;
            font-size: 0.55rem;
            letter-spacing: 1px;
            font-weight: 700;
            z-index: 3;
            backdrop-filter: blur(6px);
        }
        .chart-status .dot {
            width: 6px; height: 6px;
            border-radius: 50%;
            background: #00F2FE;
            box-shadow: 0 0 6px #00F2FE;
            animation: pulse 1.5s infinite;
        }
        .chart-status.err { background: rgba(239, 68, 68, 0.15); border-color: rgba(239, 68, 68, 0.5); color: #ff6688; }
        .chart-status.err .dot { background: #ff3366; box-shadow: 0 0 6px #ff3366; }
        .chart-status.warn { background: rgba(255, 204, 0, 0.15); border-color: rgba(255, 204, 0, 0.5); color: #FFCC00; }
        .chart-status.warn .dot { background: #FFCC00; box-shadow: 0 0 6px #FFCC00; }

        .signal-card {
            margin: 0 auto 14px;
            padding: 14px 12px;
            border-radius: 16px;
            background: linear-gradient(135deg,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.85)) 0%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.30)) 100%);
            border: 1px solid rgba(var(--glass-border-rgb), var(--glass-border-alpha));
            backdrop-filter: blur(var(--glass-blur)) saturate(180%);
            -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(180%);
            box-shadow:
                inset 0 1.5px 0 rgba(255, 255, 255, 0.85),
                inset 0 -1px 0 rgba(255, 255, 255, 0.15),
                0 8px 32px rgba(90, 150, 200, 0.10);
            text-align: left;
            font-size: 0.72rem;
            line-height: 1.65;
            white-space: pre;
            overflow-x: auto;
            color: var(--text);
            display: none;
            font-family: 'JetBrains Mono', monospace;
        }
        .signal-card.show { display: block; animation: cardIn calc(0.4s * var(--speed-multiplier)) var(--anim-spring); }
        @keyframes cardIn {
            from { opacity: 0; transform: translateY(10px) scale(0.97); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }

        .result-card {
            margin: 0 auto 14px;
            padding: 14px 12px;
            border-radius: 16px;
            background: linear-gradient(135deg,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.85)) 0%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.30)) 100%);
            border: 1px solid rgba(var(--glass-border-rgb), var(--glass-border-alpha));
            backdrop-filter: blur(var(--glass-blur)) saturate(180%);
            -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(180%);
            box-shadow:
                inset 0 1.5px 0 rgba(255, 255, 255, 0.85),
                0 8px 32px rgba(90, 150, 200, 0.10);
            text-align: left;
            font-size: 0.72rem;
            line-height: 1.65;
            white-space: pre;
            overflow-x: auto;
            color: var(--text);
            display: none;
            font-family: 'JetBrains Mono', monospace;
        }
        .result-card.show { display: block; animation: cardIn calc(0.4s * var(--speed-multiplier)) var(--anim-spring); }
        .result-card.win { border-color: rgba(34, 197, 94, 0.55); background: linear-gradient(135deg, rgba(34, 197, 94, 0.15), rgba(34, 197, 94, 0.05)); }
        .result-card.loss { border-color: rgba(239, 68, 68, 0.55); background: linear-gradient(135deg, rgba(239, 68, 68, 0.15), rgba(239, 68, 68, 0.05)); }

        .action-row { display: flex; gap: 8px; width: 100%; flex-wrap: wrap; }
        .action-row .btn-primary { flex: 1; min-width: 120px; }
        .action-row .btn-secondary { flex: 1; min-width: 100px; }
        .action-row .btn-partial {
            flex: 1;
            min-width: 120px;
            background: linear-gradient(135deg, #8b5cf6, #6d28d9);
            color: white;
            border: none;
            padding: 12px;
            border-radius: 14px;
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            box-shadow: 0 4px 12px rgba(139, 92, 246, 0.25);
            letter-spacing: 0.5px;
        }
        .action-row .btn-partial:active { transform: scale(0.96); }

        .stats-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; margin-bottom: 16px; }
        .stat-card {
            background: linear-gradient(135deg,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.90)) 0%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.30)) 100%);
            border: 1px solid rgba(var(--glass-border-rgb), var(--glass-border-alpha));
            border-radius: 16px;
            padding: 10px 4px;
            text-align: center;
            backdrop-filter: blur(var(--glass-blur)) saturate(180%);
            -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(180%);
            box-shadow:
                inset 0 1.5px 0 rgba(255, 255, 255, 0.85),
                inset 0 -1px 0 rgba(255, 255, 255, 0.15),
                0 8px 32px rgba(90, 150, 200, 0.10);
        }
        .stat-card strong { display: block; font-size: 1rem; font-weight: 700; color: var(--text); margin-top: 4px; }
        .stat-card span { font-size: 0.55rem; color: var(--muted); letter-spacing: 1px; text-transform: uppercase; }

        .section-label {
            margin: 18px 4px 8px;
            font-size: 0.65rem;
            letter-spacing: 2px;
            color: var(--muted);
            text-transform: uppercase;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .two-col { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
        .two-col .hyper-group { margin-bottom: 0; }
        .two-col .hyper-item { padding: 10px 12px; }
        .two-col .hyper-item:not(:last-child)::after { display: none; }
        .two-col .item-value {
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.55) 0%, rgba(255, 255, 255, 0.22) 100%);
            border: 1px solid rgba(255, 255, 255, 0.75);
            padding: 4px 8px;
            border-radius: 12px;
            font-size: 0.65rem;
            font-weight: 600;
            color: var(--text);
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            max-width: 90px;
            text-align: center;
            backdrop-filter: blur(16px);
            -webkit-backdrop-filter: blur(16px);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.9), 0 2px 8px rgba(90, 150, 200, 0.10);
        }
        body.dark-mode .two-col .item-value {
            background: linear-gradient(135deg, rgba(80, 140, 200, 0.30) 0%, rgba(60, 120, 180, 0.15) 100%);
            border: 1px solid rgba(150, 210, 245, 0.35);
            color: #e6f2f8;
        }

        .overlay {
            position: fixed;
            inset: 0;
            background: rgba(10, 30, 50, 0.35);
            z-index: 1000;
            opacity: 0;
            pointer-events: none;
            transition: opacity calc(0.3s * var(--speed-multiplier)) ease;
            backdrop-filter: blur(4px);
            -webkit-backdrop-filter: blur(4px);
        }
        .overlay.show { opacity: 1; pointer-events: auto; }

        .hyper-dialog {
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%) scale(0.96);
            width: 85%;
            max-width: 340px;
            background: linear-gradient(135deg,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 1.0)) 0%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.40)) 100%);
            backdrop-filter: blur(var(--glass-blur)) saturate(200%);
            -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(200%);
            border: 1px solid rgba(var(--glass-border-rgb), calc(var(--glass-border-alpha) + 0.1));
            border-radius: 22px;
            z-index: 1001;
            opacity: 0;
            pointer-events: none;
            transition: all calc(0.35s * var(--anim-speed)) var(--anim-smooth);
            overflow: hidden;
            box-shadow:
                inset 0 2px 0 rgba(255, 255, 255, 0.95),
                inset 0 -1px 0 rgba(255, 255, 255, 0.20),
                0 20px 60px rgba(60, 120, 180, 0.25);
        }
        .hyper-dialog.show { opacity: 1; pointer-events: auto; }
        .hyper-dialog.anim-scale { transform: translate(-50%, -50%) scale(0.85); }
        .hyper-dialog.anim-scale.show { transform: translate(-50%, -50%) scale(1); }
        .hyper-dialog.anim-fade { transform: translate(-50%, -50%); }
        .hyper-dialog.anim-fade.show { opacity: 1; }
        .hyper-dialog.anim-slide-up { transform: translate(-50%, 100%); }
        .hyper-dialog.anim-slide-up.show { transform: translate(-50%, -50%); }
        .hyper-dialog.anim-flip { transform: translate(-50%, -50%) rotateX(-90deg); }
        .hyper-dialog.anim-flip.show { transform: translate(-50%, -50%) rotateX(0); }
        .hyper-dialog.anim-bounce { transform: translate(-50%, -50%) scale(0.5); }
        .hyper-dialog.anim-bounce.show { transform: translate(-50%, -50%) scale(1); }

        .dialog-title {
            text-align: center;
            padding: 14px 14px 6px;
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--muted);
            letter-spacing: 1px;
        }
        .dialog-list { padding: 6px; max-height: 55vh; overflow-y: auto; -webkit-overflow-scrolling: touch; }
        .dialog-item {
            display: flex; justify-content: space-between; align-items: center;
            padding: 10px 12px; border-radius: 10px; cursor: pointer;
            transition: 0.2s ease;
        }
        .dialog-item:active { background: rgba(255, 255, 255, 0.15); transform: scale(0.98); }
        .dialog-item .check-icon { color: var(--primary); opacity: 0; transform: scale(0.5); transition: 0.3s var(--anim-spring); }
        .dialog-item.selected { background: rgba(14, 165, 164, 0.18); }
        .dialog-item.selected .check-icon { opacity: 1; transform: scale(1); }
        .dialog-item span { font-size: 0.7rem; font-weight: 500; }
        .dialog-item .check-box {
            width: 18px; height: 18px; border-radius: 4px;
            border: 2px solid var(--muted);
            display: grid; place-items: center;
            transition: 0.2s ease; flex-shrink: 0;
        }
        .dialog-item .check-box.checked { background: var(--primary); border-color: var(--primary); }
        .dialog-item .check-box.checked::after { content: '✓'; color: white; font-size: 0.6rem; font-weight: bold; }

        .header {
            position: fixed;
            top: 0; left: 0; right: 0;
            height: 48px;
            z-index: 50;
            background: linear-gradient(180deg,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 1.05)) 0%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.30)) 100%);
            backdrop-filter: blur(var(--glass-blur)) saturate(200%);
            -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(200%);
            border-bottom: 1px solid rgba(var(--glass-border-rgb), var(--glass-border-alpha));
            box-shadow:
                inset 0 1.5px 0 rgba(255, 255, 255, 0.90),
                0 4px 24px rgba(90, 150, 200, 0.12);
            transition: background 0.3s ease, border 0.3s ease;
            display: flex;
            align-items: center;
        }
        body.dark-mode .header {
            background: linear-gradient(180deg,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 1.15)) 0%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.30)) 100%);
            border-bottom-color: rgba(var(--glass-border-rgb), calc(var(--glass-border-alpha) * 0.7));
            box-shadow:
                inset 0 1.5px 0 rgba(180, 225, 255, 0.20),
                0 4px 24px rgba(0, 0, 0, 0.30);
        }
        .header-inner {
            max-width: 850px;
            margin: 0 auto;
            width: 100%;
            height: 100%;
            padding: 0 12px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .brand-logo {
            width: 24px; height: 24px;
            border-radius: 6px;
            background: linear-gradient(135deg, #22c55e, #16a34a);
            display: grid; place-items: center; color: white;
            box-shadow: 0 2px 8px rgba(34, 197, 94, 0.35);
            flex-shrink: 0;
        }
        .header-title {
            font-size: 0.9rem;
            font-weight: 700;
            letter-spacing: 0.5px;
            color: var(--text);
            white-space: nowrap;
        }
        .header-title span { color: var(--primary); }
        .live-badge {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 4px 8px;
            background: rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.6));
            border: 1px solid rgba(var(--glass-border-rgb), calc(var(--glass-border-alpha) * 0.8));
            border-radius: 12px;
            font-size: 0.55rem;
            font-weight: 600;
            color: var(--muted);
            flex-shrink: 0;
            backdrop-filter: blur(12px);
        }
        .pulse-dot {
            width: 5px; height: 5px;
            border-radius: 50%;
            background: #22c55e;
            animation: pulse 1.5s infinite;
        }
        @keyframes pulse {
            0% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.4); }
            70% { box-shadow: 0 0 0 6px rgba(34, 197, 94, 0); }
            100% { box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }
        }

        .status-badge {
            display: flex;
            align-items: center;
            gap: 4px;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 0.55rem;
            font-weight: 700;
            flex-shrink: 0;
            backdrop-filter: blur(12px);
        }
        .status-badge.unlocked {
            background: rgba(34, 197, 94, 0.15);
            border: 1px solid rgba(34, 197, 94, 0.45);
            color: #22c55e;
        }

        .bottom-nav {
            position: fixed;
            bottom: 14px;
            left: 50%;
            transform: translateX(-50%);
            width: min(calc(100% - 28px), 400px);
            height: 56px;
            background: linear-gradient(135deg,
                rgba(255, 255, 255, 0.32) 0%,
                rgba(255, 255, 255, 0.10) 50%,
                rgba(255, 255, 255, 0.22) 100%);
            backdrop-filter: blur(var(--glass-blur)) saturate(220%);
            -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(220%);
            border: 1px solid rgba(255, 255, 255, 0.60);
            border-radius: 26px;
            display: flex;
            justify-content: space-around;
            align-items: center;
            padding: 0 4px;
            z-index: 50;
            box-shadow:
                inset 0 1.5px 0 rgba(255, 255, 255, 0.95),
                inset 0 -1px 0 rgba(255, 255, 255, 0.35),
                inset 0 0 40px rgba(200, 235, 255, 0.15),
                0 10px 40px rgba(90, 150, 200, 0.18);
            overflow: visible;
            transition: background 0.3s ease, border-color 0.3s ease;
        }
        body.dark-mode .bottom-nav {
            background: linear-gradient(135deg,
                rgba(90, 160, 220, 0.18) 0%,
                rgba(50, 110, 170, 0.06) 50%,
                rgba(90, 160, 220, 0.14) 100%);
            border-color: rgba(150, 210, 245, 0.35);
            box-shadow:
                inset 0 1.5px 0 rgba(180, 225, 255, 0.25),
                inset 0 -1px 0 rgba(100, 160, 210, 0.10),
                0 10px 40px rgba(0, 0, 0, 0.40);
        }
        .nav-btn {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            gap: 2px;
            height: 100%;
            color: var(--muted);
            position: relative;
            z-index: 2;
            transition: color calc(0.35s * var(--anim-speed)) ease,
                        transform calc(0.4s * var(--anim-speed)) var(--anim-spring);
            border: none;
            background: transparent;
            cursor: pointer;
            border-radius: 18px;
            -webkit-tap-highlight-color: transparent;
        }
        .nav-btn.active { color: var(--primary); }
        .nav-btn.active i { transform: scale(1.18) translateY(-1px); filter: none; }
        .nav-btn.magnify { transform: scale(1.18) translateY(-3px); color: var(--primary); z-index: 4; }
        .nav-btn.magnify i { transform: scale(1.12); filter: none; }
        .nav-btn.magnify span {
            font-weight: 700;
            font-size: 0.58rem;
            background: rgba(255, 255, 255, 0.60);
            backdrop-filter: blur(8px);
            padding: 2px 6px;
            border-radius: 8px;
            box-shadow: 0 2px 8px rgba(90, 150, 200, 0.15);
            margin-top: 1px;
        }
        body.dark-mode .nav-btn.magnify span { background: rgba(30, 80, 130, 0.7); color: #e6f2f8; }
        .nav-btn i { width: 17px; height: 17px; transition: transform calc(0.4s * var(--anim-speed)) var(--anim-spring), filter 0.3s ease; }
        .nav-btn span { font-size: 0.55rem; font-weight: 600; letter-spacing: 0.2px; transition: all calc(0.3s * var(--anim-speed)) ease; }
        .nav-indicator {
            position: absolute;
            top: 50%; left: 0;
            height: 42px;
            width: calc((100% - 8px) / 4);
            border-radius: 16px;
            z-index: 1;
            pointer-events: auto;
            cursor: grab;
            touch-action: none;
            opacity: 0;
            transform: translateY(-50%) translateX(0);
            transition: transform calc(0.45s * var(--anim-speed)) var(--anim-spring),
                        width calc(0.45s * var(--anim-speed)) var(--anim-spring),
                        height calc(0.3s * var(--anim-speed)) ease,
                        background calc(0.3s * var(--anim-speed)) ease,
                        opacity 0.3s ease;
            background: linear-gradient(135deg,
                rgba(255, 255, 255, 0.55) 0%,
                rgba(255, 255, 255, 0.22) 50%,
                rgba(255, 255, 255, 0.42) 100%);
            border: 1px solid rgba(255, 255, 255, 0.85);
            box-shadow:
                inset 0 1px 0 rgba(255, 255, 255, 0.98),
                inset 0 -1px 0 rgba(255, 255, 255, 0.40),
                inset 0 0 20px rgba(200, 235, 255, 0.30),
                0 2px 12px rgba(90, 150, 200, 0.18);
            backdrop-filter: blur(18px) saturate(180%);
            -webkit-backdrop-filter: blur(18px) saturate(180%);
            overflow: hidden;
        }
        .nav-indicator.ready { opacity: 1; }
        .nav-indicator.dragging {
            height: 46px;
            border-radius: 18px;
            cursor: grabbing;
            z-index: 5;
            background: linear-gradient(135deg,
                rgba(255, 255, 255, 0.70) 0%,
                rgba(255, 255, 255, 0.35) 50%,
                rgba(255, 255, 255, 0.55) 100%);
        }
        .nav-indicator::before {
            content: '';
            position: absolute;
            top: 1px; left: 15%;
            width: 70%; height: 40%;
            background: radial-gradient(ellipse at top, rgba(255,255,255,0.85) 0%, transparent 70%);
            border-radius: 50%;
            filter: blur(2px);
            pointer-events: none;
        }
        .nav-indicator::after { display: none; }
        body.dark-mode .nav-indicator {
            background: linear-gradient(135deg,
                rgba(120, 200, 240, 0.28) 0%,
                rgba(60, 140, 200, 0.12) 50%,
                rgba(120, 200, 240, 0.22) 100%);
            border-color: rgba(180, 225, 255, 0.45);
            box-shadow:
                inset 0 1px 0 rgba(200, 235, 255, 0.35),
                inset 0 0 20px rgba(60, 140, 200, 0.15),
                0 2px 12px rgba(0, 0, 0, 0.35);
        }
        body.dark-mode .nav-indicator.dragging {
            background: linear-gradient(135deg,
                rgba(140, 210, 250, 0.40) 0%,
                rgba(70, 150, 210, 0.18) 50%,
                rgba(140, 210, 250, 0.32) 100%);
        }

        .btn-primary {
            width: 100%;
            padding: 12px;
            border-radius: 14px;
            background: linear-gradient(135deg, #22c55e, #16a34a);
            color: white;
            font-size: 0.8rem;
            font-weight: 600;
            border: none;
            cursor: pointer;
            transition: transform 0.2s ease, opacity 0.2s ease;
            box-shadow: 0 4px 14px rgba(34, 197, 94, 0.35);
            letter-spacing: 1px;
        }
        .btn-primary:active { transform: scale(0.97); }
        .btn-primary.waiting { background: linear-gradient(135deg, #f59e0b, #d97706); box-shadow: 0 4px 14px rgba(245, 158, 11, 0.35); cursor: default; }
        .btn-primary.mtg { background: linear-gradient(135deg, #8b5cf6, #6d28d9); box-shadow: 0 4px 14px rgba(139, 92, 246, 0.35); cursor: default; }
        .btn-primary.analyzing { background: linear-gradient(135deg, #06b6d4, #0891b2); box-shadow: 0 4px 14px rgba(6, 182, 212, 0.35); cursor: default; }
        .btn-primary.scanning { background: linear-gradient(135deg, #f472b6, #ec4899); box-shadow: 0 4px 14px rgba(244, 114, 182, 0.35); cursor: default; }
        .btn-primary.auto-active { background: linear-gradient(135deg, #a78bfa, #7c3aed); box-shadow: 0 4px 14px rgba(167, 139, 250, 0.35); }

        .btn-secondary {
            padding: 12px 14px;
            border-radius: 14px;
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.20) 0%, rgba(239, 68, 68, 0.10) 100%);
            color: #ef4444;
            border: 1px solid rgba(239, 68, 68, 0.40);
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            transition: 0.2s ease;
            letter-spacing: 0.5px;
            white-space: nowrap;
            backdrop-filter: blur(10px);
        }
        .btn-secondary:active { transform: scale(0.96); background: linear-gradient(135deg, rgba(239, 68, 68, 0.30), rgba(239, 68, 68, 0.15)); }

        .profile-avatar {
            width: 68px; height: 68px;
            margin: 0 auto 10px;
            border-radius: 50%;
            background: linear-gradient(135deg, rgba(14, 165, 164, 0.25), rgba(14, 165, 164, 0.10));
            border: 2px solid rgba(14, 165, 164, 0.35);
            display: flex; align-items: center; justify-content: center;
            color: var(--primary);
            backdrop-filter: blur(10px);
            box-shadow:
                inset 0 2px 0 rgba(255, 255, 255, 0.6),
                0 4px 16px rgba(14, 165, 164, 0.20);
        }

        .btn-logout {
            margin: 16px auto;
            display: block;
            padding: 12px 30px;
            border-radius: 14px;
            background: linear-gradient(135deg, rgba(239, 68, 68, 0.18), rgba(239, 68, 68, 0.08));
            color: #ef4444;
            border: 1px solid rgba(239, 68, 68, 0.40);
            font-size: 0.75rem;
            font-weight: 600;
            cursor: pointer;
            transition: 0.2s ease;
            letter-spacing: 0.5px;
            backdrop-filter: blur(10px);
        }
        .btn-logout:active { transform: scale(0.96); background: linear-gradient(135deg, rgba(239, 68, 68, 0.30), rgba(239, 68, 68, 0.15)); }

        input[type="range"] {
            -webkit-appearance: none;
            width: 100%; height: 4px;
            background: rgba(10, 37, 64, 0.25);
            border-radius: 2px;
            outline: none;
            cursor: pointer;
        }
        input[type="range"]::-webkit-slider-thumb {
            -webkit-appearance: none;
            width: 16px; height: 16px;
            border-radius: 50%;
            background: var(--primary);
            cursor: pointer;
            box-shadow: 0 2px 8px rgba(14, 165, 164, 0.35);
        }
        body.dark-mode input[type="range"] { background: rgba(255, 255, 255, 0.22); }
        .slider-group { display: flex; align-items: center; gap: 6px; flex: 1; min-width: 0; }
        .slider-group span { min-width: 36px; text-align: center; font-size: 0.65rem; color: var(--muted); }

        .telegram-input {
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.55), rgba(255, 255, 255, 0.22));
            border: 1px solid rgba(255, 255, 255, 0.70);
            border-radius: 10px;
            padding: 6px 10px;
            font-size: 0.7rem;
            font-family: 'JetBrains Mono', monospace;
            color: var(--text);
            width: 100%;
            max-width: 220px;
            outline: none;
            transition: border 0.2s ease;
            backdrop-filter: blur(12px);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
        }
        .telegram-input:focus { border-color: var(--primary); }
        body.dark-mode .telegram-input {
            background: linear-gradient(135deg, rgba(80, 140, 200, 0.22), rgba(60, 120, 180, 0.10));
            border-color: rgba(150, 210, 245, 0.35);
            color: #e6f2f8;
        }

        .tg-status { font-size: 0.6rem; color: var(--muted); text-align: center; padding: 4px 0; min-height: 18px; }
        .tg-status.success { color: #22c55e; }
        .tg-status.error { color: #ef4444; }
        .tg-status.sending { color: #06b6d4; }

        .auto-status-bar {
            margin: 0 auto 14px;
            padding: 10px 14px;
            border-radius: 14px;
            background: linear-gradient(135deg, rgba(124, 58, 237, 0.15), rgba(124, 58, 237, 0.05));
            border: 1px solid rgba(124, 58, 237, 0.35);
            font-size: 0.65rem;
            color: var(--muted);
            text-align: center;
            display: none;
            line-height: 1.6;
            backdrop-filter: blur(14px);
        }
        .auto-status-bar.show { display: block; animation: cardIn 0.3s var(--anim-spring); }
        .auto-status-bar .scanning-text { color: #a78bfa; font-weight: 600; }
        .auto-status-bar .signal-found { color: #22c55e; font-weight: 700; }
        .auto-status-bar .no-signal { color: #f59e0b; font-weight: 600; }

        ::-webkit-scrollbar { width: 0px; background: transparent; }

        .watermark-preview {
            font-size: 1.2rem;
            padding: 8px 12px;
            border-radius: 8px;
            background: rgba(10, 37, 64, 0.08);
            text-align: center;
            font-family: 'JetBrains Mono', monospace;
            letter-spacing: 1px;
            color: var(--muted);
        }
        body.dark-mode .watermark-preview { background: rgba(255, 255, 255, 0.08); }

        /* ===== LOCK / PASSWORD OVERLAY ===== */
        .auth-overlay {
            position: fixed;
            inset: 0;
            z-index: 2000;
            background: linear-gradient(165deg,
                rgba(200, 235, 250, 0.80) 0%,
                rgba(220, 245, 255, 0.75) 100%);
            backdrop-filter: blur(44px) saturate(180%);
            -webkit-backdrop-filter: blur(44px) saturate(180%);
            display: flex;
            align-items: center;
            justify-content: center;
            transition: opacity 0.4s ease, visibility 0.4s ease;
            opacity: 0;
            visibility: hidden;
        }
        .auth-overlay.visible { opacity: 1; visibility: visible; }
        .auth-box {
            background: linear-gradient(135deg,
                rgba(255, 255, 255, 0.60) 0%,
                rgba(255, 255, 255, 0.25) 100%);
            border: 1px solid rgba(255, 255, 255, 0.90);
            border-radius: 24px;
            padding: 30px 24px;
            max-width: 400px;
            width: 90%;
            box-shadow:
                inset 0 2px 0 rgba(255, 255, 255, 0.95),
                inset 0 -1px 0 rgba(255, 255, 255, 0.20),
                0 20px 60px rgba(60, 120, 180, 0.20);
            backdrop-filter: blur(44px) saturate(200%);
            -webkit-backdrop-filter: blur(44px) saturate(200%);
            max-height: 90vh;
            overflow-y: auto;
        }
        .auth-box .logo {
            text-align: center;
            font-size: 1.8rem;
            font-weight: 700;
            color: var(--primary);
            margin-bottom: 16px;
        }
        .auth-box .logo span { color: var(--text); }
        .auth-form { display: flex; flex-direction: column; gap: 14px; }
        .auth-form label { font-size: 0.7rem; font-weight: 600; color: var(--muted); letter-spacing: 0.5px; }
        .auth-form input {
            padding: 12px 14px;
            border-radius: 12px;
            border: 1px solid rgba(255, 255, 255, 0.70);
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.55), rgba(255, 255, 255, 0.25));
            font-size: 0.85rem;
            color: var(--text);
            outline: none;
            transition: border 0.2s ease;
            font-family: 'JetBrains Mono', monospace;
            backdrop-filter: blur(12px);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
            letter-spacing: 2px;
            text-align: center;
        }
        .auth-form input:focus { border-color: var(--primary); }
        .auth-form .btn-auth {
            padding: 13px;
            border-radius: 12px;
            border: none;
            font-weight: 700;
            font-size: 0.85rem;
            cursor: pointer;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            background: linear-gradient(135deg, #22c55e, #16a34a);
            color: white;
            box-shadow: 0 4px 14px rgba(34, 197, 94, 0.35);
            letter-spacing: 1px;
        }
        .auth-form .btn-auth:active { transform: scale(0.96); }
        .auth-form .btn-auth:disabled { opacity: 0.6; cursor: not-allowed; transform: none; }
        .auth-form .auth-error { color: #ef4444; font-size: 0.7rem; text-align: center; min-height: 18px; font-weight: 600; }
        .auth-footer { text-align: center; margin-top: 18px; font-size: 0.6rem; color: var(--muted); }
        body.dark-mode .auth-overlay {
            background: linear-gradient(165deg,
                rgba(5, 15, 25, 0.88) 0%,
                rgba(10, 25, 40, 0.85) 100%);
        }
        body.dark-mode .auth-box {
            background: linear-gradient(135deg,
                rgba(70, 130, 180, 0.30) 0%,
                rgba(40, 90, 140, 0.15) 100%);
            border-color: rgba(150, 210, 245, 0.40);
            box-shadow:
                inset 0 2px 0 rgba(180, 225, 255, 0.25),
                0 20px 60px rgba(0, 0, 0, 0.55);
        }
        body.dark-mode .auth-form input {
            background: linear-gradient(135deg, rgba(80, 140, 200, 0.25), rgba(60, 120, 180, 0.12));
            border-color: rgba(150, 210, 245, 0.40);
            color: #e6f2f8;
        }

        .toast {
            position: fixed;
            bottom: 80px;
            left: 50%;
            transform: translateX(-50%);
            padding: 8px 18px;
            border-radius: 12px;
            background: linear-gradient(135deg, rgba(34, 197, 94, 0.95), rgba(22, 163, 74, 0.95));
            color: white;
            font-size: 0.7rem;
            font-weight: 600;
            z-index: 3000;
            opacity: 0;
            transition: opacity 0.3s ease;
            pointer-events: none;
            backdrop-filter: blur(12px);
            box-shadow: 0 4px 16px rgba(34, 197, 94, 0.35);
        }
        .toast.show { opacity: 1; }

        .chart-panel .chart-status { opacity: 1; }
        .chart-panel .chart-status .dot { opacity: 1; }

        .fc-hero { text-align: center; padding: 14px 6px 6px; }
        .fc-hero h3 {
            font-size: 1.02rem;
            font-weight: 800;
            background: linear-gradient(90deg, #0ea5a4, #00f2fe);
            -webkit-background-clip: text;
            background-clip: text;
            color: transparent;
            margin-bottom: 4px;
        }
        .fc-hero p { font-size: 0.58rem; color: var(--muted); }
        .fc-card {
            border-radius: 18px;
            padding: 14px 12px;
            margin-top: 12px;
            background: linear-gradient(135deg,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.85)) 0%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.30)) 100%);
            border: 1px solid rgba(var(--glass-border-rgb), var(--glass-border-alpha));
            backdrop-filter: blur(var(--glass-blur)) saturate(180%);
            -webkit-backdrop-filter: blur(var(--glass-blur)) saturate(180%);
            box-shadow:
                inset 0 1.5px 0 rgba(255, 255, 255, 0.85),
                0 8px 32px rgba(90, 150, 200, 0.10);
        }
        .fc-sec {
            font-size: 0.56rem;
            font-weight: 800;
            letter-spacing: 0.14em;
            color: var(--muted);
            text-transform: uppercase;
            margin: 12px 0 6px;
        }
        .fc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 7px; }
        .fc-chip {
            display: flex;
            flex-direction: column;
            gap: 3px;
            padding: 8px 10px;
            border-radius: 13px;
            cursor: pointer;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.35), rgba(255, 255, 255, 0.12));
            border: 1px solid rgba(255, 255, 255, 0.55);
            backdrop-filter: blur(14px);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
        }
        .fc-chip:active { transform: scale(0.96); }
        .fc-chip-l { font-size: 0.52rem; font-weight: 700; color: var(--muted); }
        .fc-chip-v { font-size: 0.66rem; font-weight: 700; color: #00b8d4; display: flex; align-items: center; justify-content: space-between; gap: 4px; }
        body.dark-mode .fc-chip { background: linear-gradient(135deg, rgba(80, 140, 200, 0.22), rgba(60, 120, 180, 0.10)); border-color: rgba(150, 210, 245, 0.35); }
        .fc-textarea {
            width: 100%;
            min-height: 118px;
            border-radius: 13px;
            padding: 10px 12px;
            resize: vertical;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.50), rgba(255, 255, 255, 0.20));
            border: 1px solid rgba(255, 255, 255, 0.70);
            color: var(--text);
            font-family: 'JetBrains Mono', monospace;
            font-size: 0.7rem;
            outline: none;
            box-sizing: border-box;
            backdrop-filter: blur(12px);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
        }
        .fc-textarea:focus { border-color: rgba(0, 242, 254, 0.65); }
        body.dark-mode .fc-textarea { background: linear-gradient(135deg, rgba(80, 140, 200, 0.20), rgba(60, 120, 180, 0.08)); border-color: rgba(150, 210, 245, 0.35); color: #e6f2f8; }
        .fc-run-btn {
            width: 100%;
            margin-top: 12px;
            padding: 11px 0;
            border: none;
            border-radius: 14px;
            cursor: pointer;
            background: linear-gradient(135deg, #22c55e, #16a34a);
            color: #fff;
            font-weight: 700;
            font-size: 0.75rem;
            letter-spacing: 1px;
            font-family: 'JetBrains Mono', monospace;
            box-shadow: 0 4px 14px rgba(34, 197, 94, 0.30);
        }
        .fc-run-btn:disabled { opacity: 0.55; cursor: wait; }
        .fc-run-btn:active { transform: scale(0.98); }
        .fc-result-card {
            margin-top: 12px;
            border-radius: 16px;
            padding: 12px;
            white-space: pre-wrap;
            background: linear-gradient(135deg,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.85)) 0%,
                rgba(var(--glass-bg-rgb), calc(var(--glass-opacity) * 0.30)) 100%);
            border: 1px solid rgba(var(--glass-border-rgb), var(--glass-border-alpha));
            font-size: 0.68rem;
            line-height: 1.55;
            color: var(--text);
            font-family: 'JetBrains Mono', monospace;
            display: none;
            backdrop-filter: blur(24px);
            box-shadow: inset 0 1.5px 0 rgba(255, 255, 255, 0.85);
        }
        .fc-result-card.show { display: block; }
        .fc-chip-stat {
            flex: 1;
            text-align: center;
            padding: 8px 4px;
            border-radius: 12px;
            background: linear-gradient(135deg, rgba(255, 255, 255, 0.35), rgba(255, 255, 255, 0.12));
            border: 1px solid rgba(255, 255, 255, 0.55);
            backdrop-filter: blur(12px);
            box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85);
        }
        body.dark-mode .fc-chip-stat { background: linear-gradient(135deg, rgba(80, 140, 200, 0.22), rgba(60, 120, 180, 0.10)); border-color: rgba(150, 210, 245, 0.35); }
        .fc-chip-stat strong { display: block; font-size: 0.85rem; font-weight: 800; }
        .fc-chip-stat span { font-size: 0.5rem; font-weight: 700; color: var(--muted); text-transform: uppercase; }
        .fc-status { margin-top: 10px; text-align: center; font-size: 0.6rem; font-weight: 700; min-height: 14px; color: var(--muted); }

    </style>
</head>
<body>

    <div class="ambient"></div>
    <div class="toast" id="toast"></div>


    <!-- MAIN APP -->
    <header class="header">
        <div class="header-inner">
            <div style="display:flex;align-items:center;gap:8px;">
                <div class="brand-logo"><i data-lucide="activity" class="w-4 h-4"></i></div>
                <div class="header-title">Hyper<span>Trade</span></div>
            </div>
            <div style="display:flex;align-items:center;gap:6px;">
                <div class="status-badge unlocked" id="lockStatusBadge">
                    <i data-lucide="shield-check" class="w-3 h-3"></i>
                    <span>UNLOCKED</span>
                </div>
                <div class="live-badge"><span class="pulse-dot"></span> LIVE</div>
            </div>
        </div>
    </header>

    <div class="overlay" id="overlay" onclick="closeDialog()"></div>
    <div class="hyper-dialog" id="selectionDialog">
        <div class="dialog-title" id="dialogTitle">Select Option</div>
        <div class="dialog-list" id="dialogList"></div>
    </div>

    <div id="app-wrapper">
        <main>
            <!-- HOME / ENGINE VIEW -->
            <div id="view-0" class="view-container active">
                <div class="hyper-group signal-panel">
                    <div class="chart-panel" id="chartPanel">
                        <div class="chart-status" id="chartStatus">
                            <span class="dot"></span>
                            <span id="chartStatusText">LIVE</span>
                        </div>
                        <canvas id="chart"></canvas>
                    </div>

                    <div class="auto-status-bar" id="autoStatusBar">
                        <span id="autoStatusText">SCANNING MARKETS...</span>
                    </div>

                    <pre class="signal-card" id="signalCard"></pre>
                    <pre class="result-card" id="resultCard"></pre>
                    <div class="tg-status" id="tgStatus"></div>

                    <div class="action-row">
                        <button class="btn-primary" id="actionBtn" onclick="onActionClick()">GENERATE SIGNAL</button>
                        <button class="btn-secondary" onclick="resetResult()">RESET</button>
                        <button class="btn-partial" onclick="sendPartialResult()">PARTIAL RESULT</button>
                    </div>
                </div>

                <div class="stats-grid">
                    <div class="stat-card"><span>Wins</span><strong id="statWin">0</strong></div>
                    <div class="stat-card"><span>Losses</span><strong id="statLoss">0</strong></div>
                    <div class="stat-card"><span>Win Rate</span><strong id="statRate">--%</strong></div>
                </div>

                <div class="section-label">⚡ Market Configuration</div>

                <div class="two-col">
                    <div class="hyper-group">
                        <div class="hyper-item" onclick="openDialog('market')">
                            <div class="item-left">
                                <div class="item-icon"><i data-lucide="candlestick-chart" class="w-4 h-4"></i></div>
                                <div><div class="item-title">Market</div></div>
                            </div>
                            <div class="item-right">
                                <span class="item-value" id="val-market">USDBDT-OTC</span>
                                <i data-lucide="chevron-right" class="w-3 h-3 item-arrow"></i>
                            </div>
                        </div>
                    </div>
                    <div class="hyper-group">
                        <div class="hyper-item" onclick="openDialog('timeframe')">
                            <div class="item-left">
                                <div class="item-icon"><i data-lucide="clock" class="w-4 h-4"></i></div>
                                <div><div class="item-title">Time</div></div>
                            </div>
                            <div class="item-right">
                                <span class="item-value" id="val-timeframe">1 Minute</span>
                                <i data-lucide="chevron-right" class="w-3 h-3 item-arrow"></i>
                            </div>
                        </div>
                    </div>
                </div>

                <div class="section-label">🧠 Strategy & Mode</div>

                <div class="hyper-group">
                    <div class="hyper-item" onclick="openDialog('signalMode')">
                        <div class="item-left">
                            <div class="item-icon" style="background:rgba(124,58,237,0.15);color:#7c3aed;">
                                <i data-lucide="radio" class="w-4 h-4"></i>
                            </div>
                            <div>
                                <div class="item-title">Signal Mode</div>
                                <div class="item-subtitle">Manual or Auto</div>
                            </div>
                        </div>
                        <div class="item-right">
                            <span class="item-value" id="val-signalMode">Manual</span>
                            <i data-lucide="chevron-right" class="w-3 h-3 item-arrow"></i>
                        </div>
                    </div>
                    <div class="hyper-item" onclick="openDialog('strategy')">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="brain-circuit" class="w-4 h-4"></i></div>
                            <div>
                                <div class="item-title">Strategy</div>
                                <div class="item-subtitle">Signal engine</div>
                            </div>
                        </div>
                        <div class="item-right">
                            <span class="item-value" id="val-strategy">AI Smart Signal</span>
                            <i data-lucide="chevron-right" class="w-3 h-3 item-arrow"></i>
                        </div>
                    </div>
                    <div class="hyper-item" onclick="openDialog('chartType')">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="bar-chart-3" class="w-4 h-4"></i></div>
                            <div>
                                <div class="item-title">Chart</div>
                                <div class="item-subtitle">Visualisation</div>
                            </div>
                        </div>
                        <div class="item-right">
                            <span class="item-value" id="val-chartType">Candlestick</span>
                            <i data-lucide="chevron-right" class="w-3 h-3 item-arrow"></i>
                        </div>
                    </div>
                    <div class="hyper-item" onclick="openDialog('chartStyle')">
                        <div class="item-left">
                            <div class="item-icon" style="background:rgba(0,242,254,0.15);color:#00F2FE;">
                                <i data-lucide="palette" class="w-4 h-4"></i>
                            </div>
                            <div>
                                <div class="item-title">Chart Style</div>
                                <div class="item-subtitle">26 photo designs</div>
                            </div>
                        </div>
                        <div class="item-right">
                            <span class="item-value" id="val-chartStyle">Style 1 - Classic</span>
                            <i data-lucide="chevron-right" class="w-3 h-3 item-arrow"></i>
                        </div>
                    </div>
                    <div class="hyper-item" id="autoMarketsItem" onclick="openDialog('autoMarkets')" style="display:none;">
                        <div class="item-left">
                            <div class="item-icon" style="background:rgba(236,72,153,0.15);color:#ec4899;">
                                <i data-lucide="globe" class="w-4 h-4"></i>
                            </div>
                            <div>
                                <div class="item-title">Auto Markets</div>
                                <div class="item-subtitle">Select markets to scan</div>
                            </div>
                        </div>
                        <div class="item-right">
                            <span class="item-value" id="val-autoMarkets">All</span>
                            <i data-lucide="chevron-right" class="w-3 h-3 item-arrow"></i>
                        </div>
                    </div>
                    <div class="hyper-item" onclick="toggleSwitch(this)">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="bell" class="w-4 h-4"></i></div>
                            <div>
                                <div class="item-title">Sound Alerts</div>
                                <div class="item-subtitle">Notify on signal</div>
                            </div>
                        </div>
                        <div class="item-right"><div class="toggle active" data-toggle-key="soundAlerts"></div></div>
                    </div>
                    <div class="hyper-item" onclick="toggleSwitch(this)">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="smartphone" class="w-4 h-4"></i></div>
                            <div>
                                <div class="item-title">Vibration</div>
                                <div class="item-subtitle">Haptic</div>
                            </div>
                        </div>
                        <div class="item-right"><div class="toggle active" data-toggle-key="vibration"></div></div>
                    </div>
                </div>
            </div>

            <!-- SETTINGS VIEW -->
            <div id="view-1" class="view-container">
                <div class="section-label">📡 Telegram Bot</div>
                <div class="hyper-group">
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon" style="background:rgba(0,136,204,0.15);color:#0088cc;">
                                <i data-lucide="bot" class="w-4 h-4"></i>
                            </div>
                            <div><div class="item-title">Bot Token</div><div class="item-subtitle">From @BotFather</div></div>
                        </div>
                        <div class="item-right" style="flex:1;max-width:220px;">
                            <input type="text" class="telegram-input" id="botTokenInput" value="" placeholder="123456:ABC-DEF..." style="max-width:220px;">
                        </div>
                    </div>
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon" style="background:rgba(0,136,204,0.15);color:#0088cc;">
                                <i data-lucide="hash" class="w-4 h-4"></i>
                            </div>
                            <div><div class="item-title">Chat ID</div><div class="item-subtitle">Your chat/group ID</div></div>
                        </div>
                        <div class="item-right" style="flex:1;max-width:220px;">
                            <input type="text" class="telegram-input" id="chatIdInput" value="" placeholder="-100123456789" style="max-width:220px;">
                        </div>
                    </div>
                    <div class="hyper-item" onclick="toggleSwitch(this)" id="autoTelegramItem">
                        <div class="item-left">
                            <div class="item-icon" style="background:rgba(0,136,204,0.15);color:#0088cc;">
                                <i data-lucide="send" class="w-4 h-4"></i>
                            </div>
                            <div><div class="item-title">Auto Send</div><div class="item-subtitle">Signal & Result to Telegram</div></div>
                        </div>
                        <div class="item-right"><div class="toggle active" id="autoTelegramToggle" data-toggle-key="autoTelegram"></div></div>
                    </div>
                </div>

                <div class="section-label">⚙️ Preferences</div>
                <div class="hyper-group">
                    <div class="hyper-item" onclick="openDialog('martingale')">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="trending-up" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Martingale</div><div class="item-subtitle">MTG Config</div></div>
                        </div>
                        <div class="item-right">
                            <span class="item-value" id="val-martingale">No MTG</span>
                            <i data-lucide="chevron-right" class="w-3 h-3 item-arrow"></i>
                        </div>
                    </div>
                    <div class="hyper-item" onclick="toggleDarkMode(this)">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="moon" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Dark Mode</div><div class="item-subtitle">Theme switch</div></div>
                        </div>
                        <div class="item-right"><div class="toggle" id="darkModeToggle" data-toggle-key="darkMode"></div></div>
                    </div>
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="at-sign" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Telegram</div><div class="item-subtitle">Username for result card</div></div>
                        </div>
                        <div class="item-right">
                            <input type="text" class="telegram-input" id="telegramInput" value="@Mahabub_iX" placeholder="@username">
                        </div>
                    </div>
                    <div class="hyper-item" onclick="openDialog('dialogAnim')">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="sparkles" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Dialog Animation</div><div class="item-subtitle">Popup effect</div></div>
                        </div>
                        <div class="item-right">
                            <span class="item-value" id="val-dialogAnim">Scale</span>
                            <i data-lucide="chevron-right" class="w-3 h-3 item-arrow"></i>
                        </div>
                    </div>
                </div>

                <div class="section-label">🎨 Appearance</div>
                <div class="hyper-group">
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="crown" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Signal Name</div><div class="item-subtitle">Signal & result format header</div></div>
                        </div>
                        <div class="item-right" style="flex:1;max-width:160px;">
                            <input type="text" class="telegram-input" id="signalNameInput" value="RAVITH AI PRO" style="max-width:160px;text-align:center;font-weight:700;">
                        </div>
                    </div>
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="type" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Dashboard Name</div><div class="item-subtitle">Shown on chart</div></div>
                        </div>
                        <div class="item-right" style="flex:1;max-width:160px;">
                            <input type="text" class="telegram-input" id="dashboardNameInput" value="RAVITH PRO" style="max-width:160px;text-align:center;font-weight:700;">
                        </div>
                    </div>
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="image" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Watermark Text</div><div class="item-subtitle">Custom chart watermark</div></div>
                        </div>
                        <div class="item-right" style="flex:1;max-width:160px;">
                            <input type="text" class="telegram-input" id="watermarkInput" value="𝐑𝐀𝐕𝐈𝐓𝐇 𝐒𝐒" style="max-width:160px;text-align:center;">
                        </div>
                    </div>
                    <div class="hyper-item" style="cursor:default;">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="eye" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Preview</div><div class="item-subtitle">Watermark preview</div></div>
                        </div>
                        <div class="item-right">
                            <span class="watermark-preview" id="watermarkPreview">𝐑𝐀𝐕𝐈𝐓𝐇 𝐒𝐒</span>
                        </div>
                    </div>
                </div>

                <div class="section-label">🎚️ Glass & Animation Controls</div>
                <div class="hyper-group">
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon" style="background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;"><i data-lucide="gauge" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Animation Speed</div><div class="item-subtitle">Page & indicator speed</div></div>
                        </div>
                        <div class="slider-group">
                            <span id="speedVal">1.0x</span>
                            <input type="range" min="0.4" max="2.5" step="0.1" value="1" id="speedSlider" oninput="updateAnimSpeed(this.value)">
                        </div>
                    </div>
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon" style="background:linear-gradient(135deg,#4facfe,#00f2fe);color:#fff;"><i data-lucide="droplets" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Glass Blur</div><div class="item-subtitle">Backdrop blur strength</div></div>
                        </div>
                        <div class="slider-group">
                            <span id="blurVal">44px</span>
                            <input type="range" min="20" max="60" step="1" value="44" id="blurSlider" oninput="updateGlassBlur(this.value)">
                        </div>
                    </div>
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon" style="background:linear-gradient(135deg,#a18cd1,#fbc2eb);color:#fff;"><i data-lucide="blend" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Glass Opacity</div><div class="item-subtitle">Surface transparency</div></div>
                        </div>
                        <div class="slider-group">
                            <span id="glassVal">30%</span>
                            <input type="range" min="0.10" max="0.70" step="0.05" value="0.30" id="glassSlider" oninput="updateGlassOpacity(this.value)">
                        </div>
                    </div>
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon" style="background:linear-gradient(135deg,#22c55e,#16a34a);color:#fff;"><i data-lucide="sparkles" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Indicator Glow</div><div class="item-subtitle">Nav pill shadow</div></div>
                        </div>
                        <div class="slider-group">
                            <span id="glowVal">8%</span>
                            <input type="range" min="0.02" max="0.25" step="0.02" value="0.08" id="glowSlider" oninput="updateIndicatorGlow(this.value)">
                        </div>
                    </div>
                    <div class="hyper-item">
                        <div class="item-left">
                            <div class="item-icon"><i data-lucide="type" class="w-4 h-4"></i></div>
                            <div><div class="item-title">Font Size</div><div class="item-subtitle">UI text scaling</div></div>
                        </div>
                        <div class="slider-group">
                            <span id="fontVal">12px</span>
                            <input type="range" min="11" max="18" step="1" value="12" id="fontSlider" oninput="updateFontSize(this.value)">
                        </div>
                    </div>
                </div>

                <div class="hyper-group">
                    <div class="hyper-item" onclick="resetAll()">
                        <div class="item-left">
                            <div class="item-icon" style="background:rgba(239,68,68,0.15);color:#ef4444;">
                                <i data-lucide="refresh-cw" class="w-4 h-4"></i>
                            </div>
                            <div>
                                <div class="item-title" style="color:#ef4444;">Reset Settings</div>
                                <div class="item-subtitle">Restore defaults</div>
                            </div>
                        </div>
                        <div class="item-right"><i data-lucide="chevron-right" class="w-4 h-4 item-arrow"></i></div>
                    </div>
                </div>
            </div>

            <!-- FUTURE CHECKER VIEW -->
            <div id="view-3" class="view-container">
                <div class="fc-hero">
                    <h3>⚡ FUTURE CHECKER</h3>
                    <p>Paste signals → verify WIN / LOSS against live candles</p>
                </div>
                <div class="fc-card">
                    <div class="fc-sec">📡 Check Options</div>
                    <div class="fc-grid">
                        <div class="fc-chip" onclick="openDialog('fcDay')">
                            <span class="fc-chip-l">📅 Day</span>
                            <span class="fc-chip-v"><span id="val-fcDay">Today</span><i data-lucide="chevron-right" class="w-3 h-3"></i></span>
                        </div>
                        <div class="fc-chip" onclick="openDialog('fcMtg')">
                            <span class="fc-chip-l">🎯 MTG Level</span>
                            <span class="fc-chip-v"><span id="val-fcMtg">No MTG</span><i data-lucide="chevron-right" class="w-3 h-3"></i></span>
                        </div>
                        <div class="fc-chip" onclick="openDialog('fcPayout')">
                            <span class="fc-chip-l">💰 Min Payout</span>
                            <span class="fc-chip-v"><span id="val-fcPayout">All Payout</span><i data-lucide="chevron-right" class="w-3 h-3"></i></span>
                        </div>
                        <div class="fc-chip" onclick="fcLoadSample()">
                            <span class="fc-chip-l">📝 Sample</span>
                            <span class="fc-chip-v"><span>Insert Demo</span><i data-lucide="clipboard-paste" class="w-3 h-3"></i></span>
                        </div>
                    </div>
                </div>
                <div class="fc-card">
                    <div class="fc-sec">⚡ Paste Signals (PAIR — TIME — DIRECTION)</div>
                    <textarea id="fcSignalInput" class="fc-textarea" placeholder="Example:&#10;USDBDT OTC 14:30 CALL&#10;EURUSD OTC 14:35 PUT&#10;GBPJPY OTC 14:40 CALL"></textarea>
                    <div id="fcStatus" class="fc-status"></div>
                    <button class="fc-run-btn" id="fcCheckBtn" onclick="runFutureCheck()">🚀 CHECK SIGNALS</button>
                </div>
                <div class="fc-card" id="fcSummaryBox" style="display:none;">
                    <div class="fc-sec">📊 Summary</div>
                    <div style="display:flex;gap:6px;">
                        <div class="fc-chip-stat"><strong style="color:#22c55e;" id="fcSumWin">0</strong><span>Win</span></div>
                        <div class="fc-chip-stat"><strong style="color:#ef4444;" id="fcSumLoss">0</strong><span>Loss</span></div>
                        <div class="fc-chip-stat"><strong style="color:#f59e0b;" id="fcSumTie">0</strong><span>Tie</span></div>
                        <div class="fc-chip-stat"><strong style="color:#94a3b8;" id="fcSumPend">0</strong><span>Pend</span></div>
                        <div class="fc-chip-stat"><strong style="color:#00f2fe;" id="fcSumAcc">0%</strong><span>Acc</span></div>
                    </div>
                </div>
                <pre class="fc-result-card" id="fcResultCard"></pre>
                <div class="fc-card" id="fcCopyBox" style="display:none;text-align:center;">
                    <button class="fc-run-btn" style="margin-top:0;background:linear-gradient(135deg,#00f2fe,#4facfe);" onclick="fcCopyResult()">📋 COPY RESULT</button>
                </div>
            </div>

            <!-- PROFILE VIEW (simplified - Local Session) -->
            <div id="view-2" class="view-container">
                <div class="hyper-group" style="padding:26px 16px;text-align:center;">
                    <div class="profile-avatar"><i data-lucide="shield-check" class="w-7 h-7"></i></div>
                    <h2 style="font-size:1.15rem;font-weight:700;color:var(--text);">Device Unlocked</h2>
                    <p style="font-size:0.62rem;color:var(--muted);margin-top:4px;">Local session • no account needed</p>

                    <div class="stats-grid" style="margin-top:20px;">
                        <div class="stat-card"><span>Signals</span><strong id="profSignals">0</strong></div>
                        <div class="stat-card"><span>Win Rate</span><strong id="profRate">--%</strong></div>
                        <div class="stat-card"><span>Session</span><strong>LIVE</strong></div>
                    </div>

                    <div class="hyper-group" style="margin-top:20px;text-align:left;">
                        <div class="hyper-item" style="cursor:default;">
                            <div class="item-left">
                                <div class="item-icon"><i data-lucide="database" class="w-4 h-4"></i></div>
                                <div>
                                    <div class="item-title">Storage</div>
                                    <div class="item-subtitle">All data saved locally in browser</div>
                                </div>
                            </div>
                            <div class="item-right"><span class="item-value">Local</span></div>
                        </div>
                        <div class="hyper-item" style="cursor:default;">
                            <div class="item-left">
                                <div class="item-icon"><i data-lucide="lock" class="w-4 h-4"></i></div>
                                <div>
                                    <div class="item-title">Access</div>
                                    <div class="item-subtitle">Password protected session</div>
                                </div>
                            </div>
                            <div class="item-right"><span class="item-value" style="color:#22c55e;">● UNLOCKED</span></div>
                        </div>
                        <div class="hyper-item" style="cursor:default;">
                            <div class="item-left">
                                <div class="item-icon"><i data-lucide="wifi" class="w-4 h-4"></i></div>
                                <div>
                                    <div class="item-title">Feed Status</div>
                                    <div class="item-subtitle">Live market connection</div>
                                </div>
                            </div>
                            <div class="item-right"><span class="item-value" style="color:#22c55e;">● LIVE</span></div>
                        </div>
                    </div>

                    <button class="btn-logout" onclick="lockApp()">🔒 Lock App</button>
                </div>
            </div>
        </main>
    </div>

    <nav class="bottom-nav">
        <div class="nav-indicator" id="navIndicator"></div>
        <button class="nav-btn active" onclick="switchView(0)">
            <i data-lucide="cpu"></i><span>Engine</span>
        </button>
        <button class="nav-btn" onclick="switchView(1)">
            <i data-lucide="settings-2"></i><span>Settings</span>
        </button>
        <button class="nav-btn" onclick="switchView(3)">
            <i data-lucide="sparkles"></i><span>Future</span>
        </button>
        <button class="nav-btn" onclick="switchView(2)">
            <i data-lucide="user"></i><span>Profile</span>
        </button>
    </nav>

    <script>
        /* ============================================================
           HYPERTRADE — ICE / WATER GLASS THEME + PASSWORD LOCK
           Password: verified on server, unlock persists in localStorage
           All user data → browser localStorage only
           ============================================================ */

        const API_BASE = (function () {
            try {
                if (window.location && window.location.origin && window.location.origin !== 'null')
                    return window.location.origin;
            } catch (e) {}
            try {
                if (window.parent && window.parent.location && window.parent.location.origin)
                    return window.parent.location.origin;
            } catch (e) {}
            return '';
        })();

        const ALL_MARKETS = [
            'ATOUSD-OTC', 'AUDCAD-OTC', 'AUDCHF-OTC', 'AUDJPY-OTC', 'AUDNZD-OTC',
            'AUDUSD-OTC', 'AVAUSD-OTC', 'AXSUSD-OTC', 'BCHUSD-OTC', 'BNBUSD-OTC',
            'BRLUSD-OTC', 'BTCUSD-OTC', 'CADCHF-OTC', 'CADJPY-OTC', 'CHFJPY-OTC',
            'DASUSD-OTC', 'DOTUSD-OTC', 'ETCUSD-OTC', 'ETHUSD-OTC', 'EURAUD-OTC',
            'EURCAD-OTC', 'EURCHF-OTC', 'EURGBP-OTC', 'EURJPY-OTC', 'EURNZD-OTC',
            'EURUSD-OTC', 'GBPAUD-OTC', 'GBPCAD-OTC', 'GBPCHF-OTC', 'GBPJPY-OTC',
            'GBPNZD-OTC', 'GBPUSD-OTC', 'LINUSD-OTC', 'LTCUSD-OTC', 'NZDCAD-OTC',
            'NZDCHF-OTC', 'NZDJPY-OTC', 'NZDUSD-OTC', 'SOLUSD-OTC', 'TONUSD-OTC',
            'TRUUSD-OTC', 'UKBrent-OTC', 'USCrude-OTC', 'USDARS-OTC', 'USDBDT-OTC',
            'USDCAD-OTC', 'USDCHF-OTC', 'USDCOP-OTC', 'USDDZD-OTC', 'USDEGP-OTC',
            'USDIDR-OTC', 'USDINR-OTC', 'USDJPY-OTC', 'USDMXN-OTC', 'USDNGN-OTC',
            'USDPHP-OTC', 'USDPKR-OTC', 'USDZAR-OTC', 'XAGUSD-OTC', 'XAUUSD-OTC',
            'XRPUSD-OTC', 'ZECUSD-OTC'
        ];

        let selectedAutoMarkets = [...ALL_MARKETS];
        let settingsLoaded = false;

        // ======================== SESSION STATUS ========================
        function isUnlocked() { return true; }
        function setUnlocked(v) {}
        function setAuthVisibility(visible) {}
        async function handlePasswordLogin() { initEngine(); }

        function lockApp() {
            try { flushSettingsNow(); } catch (e) {}
            try {
                stopResultPolling();
                stopAutoMode();
                stopLiveTicks();
            } catch (e) {}
            setUnlocked(false);
            setTimeout(() => location.reload(), 200);
        }

        function showToast(msg, duration = 2000) {
            const t = document.getElementById('toast');
            t.innerText = msg;
            t.classList.add('show');
            setTimeout(() => t.classList.remove('show'), duration);
        }

        // ======================== SETTINGS (LOCAL STORAGE ONLY) ========================
        function getSettingsKey() {
            return 'hypertrade_settings';
        }

        function collectSettings() {
            return {
                market: document.getElementById('val-market').innerText,
                timeframe: document.getElementById('val-timeframe').innerText,
                strategy: document.getElementById('val-strategy').innerText,
                chartType: document.getElementById('val-chartType').innerText,
                chartStyle: (document.getElementById('val-chartStyle') || {innerText:'Style 1 - Classic'}).innerText,
                martingale: document.getElementById('val-martingale').innerText,
                dialogAnim: document.getElementById('val-dialogAnim').innerText,
                signalMode: document.getElementById('val-signalMode').innerText,
                telegram: document.getElementById('telegramInput').value,
                botToken: document.getElementById('botTokenInput').value,
                chatId: document.getElementById('chatIdInput').value,
                darkMode: document.getElementById('darkModeToggle').classList.contains('active'),
                autoTelegram: document.getElementById('autoTelegramToggle').classList.contains('active'),
                soundAlerts: !!(document.querySelector('[data-toggle-key="soundAlerts"]') || {}).classList?.contains('active'),
                vibration: !!(document.querySelector('[data-toggle-key="vibration"]') || {}).classList?.contains('active'),
                speed: document.getElementById('speedSlider').value,
                glass: document.getElementById('glassSlider').value,
                fontSize: document.getElementById('fontSlider').value,
                dashboardName: document.getElementById('dashboardNameInput').value,
                watermarkText: document.getElementById('watermarkInput').value,
                signalName: document.getElementById('signalNameInput').value,
                autoMarkets: selectedAutoMarkets,
                stats: engine.stats,
                tradeHistory: tradeHistory
            };
        }

        function saveSettings() {
            if (!settingsLoaded) return;
            try {
                const settings = collectSettings();
                localStorage.setItem(getSettingsKey(), JSON.stringify(settings));
            } catch (e) {}
        }

        function flushSettingsNow() {
            if (!settingsLoaded) return;
            try {
                const settings = collectSettings();
                localStorage.setItem(getSettingsKey(), JSON.stringify(settings));
            } catch (e) {}
        }

        function applySettings(s) {
            if (!s) return;
            if (s.market) document.getElementById('val-market').innerText = s.market;
            if (s.timeframe) document.getElementById('val-timeframe').innerText = s.timeframe;
            if (s.strategy) document.getElementById('val-strategy').innerText = s.strategy;
            if (s.chartType) document.getElementById('val-chartType').innerText = s.chartType;
            if (s.chartStyle && document.getElementById('val-chartStyle')) document.getElementById('val-chartStyle').innerText = s.chartStyle;
            if (s.martingale) document.getElementById('val-martingale').innerText = s.martingale;
            if (s.dialogAnim) {
                document.getElementById('val-dialogAnim').innerText = s.dialogAnim;
                dialogAnimStyle = s.dialogAnim;
            }
            if (s.signalMode) {
                document.getElementById('val-signalMode').innerText = s.signalMode;
                onSignalModeChanged(s.signalMode, true);
            }
            if (typeof s.telegram === 'string') document.getElementById('telegramInput').value = s.telegram;
            if (typeof s.botToken === 'string') document.getElementById('botTokenInput').value = s.botToken;
            if (typeof s.chatId === 'string') document.getElementById('chatIdInput').value = s.chatId;
            if (s.darkMode) {
                document.getElementById('darkModeToggle').classList.add('active');
                document.body.classList.add('dark-mode');
            } else {
                document.getElementById('darkModeToggle').classList.remove('active');
                document.body.classList.remove('dark-mode');
            }
            if (s.autoTelegram) document.getElementById('autoTelegramToggle').classList.add('active');
            else document.getElementById('autoTelegramToggle').classList.remove('active');

            const soundToggle = document.querySelector('[data-toggle-key="soundAlerts"]');
            const vibToggle = document.querySelector('[data-toggle-key="vibration"]');
            if (soundToggle) soundToggle.classList.toggle('active', s.soundAlerts !== false);
            if (vibToggle) vibToggle.classList.toggle('active', s.vibration !== false);

            if (s.speed) {
                document.getElementById('speedSlider').value = s.speed;
                document.documentElement.style.setProperty('--speed-multiplier', parseFloat(s.speed));
                document.getElementById('speedVal').innerText = parseFloat(s.speed).toFixed(1) + 'x';
            }
            if (s.glass) {
                document.getElementById('glassSlider').value = s.glass;
                document.documentElement.style.setProperty('--glass-alpha', parseFloat(s.glass));
                document.documentElement.style.setProperty('--glass-opacity', parseFloat(s.glass));
                document.getElementById('glassVal').innerText = Math.round(parseFloat(s.glass) * 100) + '%';
            }
            if (s.fontSize) {
                document.getElementById('fontSlider').value = s.fontSize;
                document.documentElement.style.fontSize = s.fontSize + 'px';
                document.getElementById('fontVal').innerText = s.fontSize + 'px';
            }
            if (s.dashboardName) {
                document.getElementById('dashboardNameInput').value = s.dashboardName;
                document.documentElement.style.setProperty('--dashboard-name', '"' + s.dashboardName + '"');
            }
            if (s.watermarkText) {
                document.getElementById('watermarkInput').value = s.watermarkText;
                document.getElementById('watermarkPreview').innerText = s.watermarkText;
                document.documentElement.style.setProperty('--watermark-text', '"' + s.watermarkText + '"');
            }
            if (s.signalName) document.getElementById('signalNameInput').value = s.signalName;
            if (Array.isArray(s.autoMarkets) && s.autoMarkets.length) selectedAutoMarkets = s.autoMarkets.slice();
            if (s.stats && typeof s.stats === 'object') {
                engine.stats.wins = Number(s.stats.wins) || 0;
                engine.stats.losses = Number(s.stats.losses) || 0;
                engine.stats.streakW = Number(s.stats.streakW) || 0;
                engine.stats.streakL = Number(s.stats.streakL) || 0;
            }
            if (Array.isArray(s.tradeHistory)) tradeHistory = s.tradeHistory.slice();

            updateStatsUI();
            const count = selectedAutoMarkets.length;
            document.getElementById('val-autoMarkets').innerText = count === ALL_MARKETS.length ? 'All' : count + ' pairs';
        }

        async function loadSettings() {
            const raw = localStorage.getItem(getSettingsKey());
            if (raw) {
                try { applySettings(JSON.parse(raw)); } catch (e) {}
            }
            settingsLoaded = true;
        }

        // ======================== NAV ========================
        let currentView = 0;
        const navOrder = [0, 1, 3, 2];
        let navIndicatorEl = null;
        let navBtns = null;
        let bottomNavEl = null;

        function updateNavIndicator(animate) {
            if (!navIndicatorEl || !bottomNavEl) return;
            const activeBtn = document.querySelector('.nav-btn.active');
            if (!activeBtn) return;
            const navRect = bottomNavEl.getBoundingClientRect();
            const btnRect = activeBtn.getBoundingClientRect();
            const x = btnRect.left - navRect.left;
            const w = btnRect.width;
            if (animate === false) navIndicatorEl.style.transition = 'none';
            navIndicatorEl.style.width = w + 'px';
            navIndicatorEl.style.transform = 'translateY(-50%) translateX(' + x + 'px)';
            if (animate === false) {
                void navIndicatorEl.offsetHeight;
                navIndicatorEl.style.transition = '';
            }
            navIndicatorEl.classList.add('ready');
        }

        function switchView(index) {
            if (index === currentView) return;
            document.querySelectorAll('.nav-btn').forEach((btn, i) => {
                btn.classList.toggle('active', navOrder[i] === index);
                btn.classList.remove('magnify');
            });
            updateNavIndicator(true);
            const oldViewEl = document.getElementById('view-' + currentView);
            const newViewEl = document.getElementById('view-' + index);
            if (!newViewEl) return;
            const slideLeft = index > currentView;
            if (oldViewEl) {
                oldViewEl.className = 'view-container active';
                void oldViewEl.offsetWidth;
                oldViewEl.classList.add(slideLeft ? 'exit-left' : 'exit-right');
                oldViewEl.classList.remove('active');
            }
            newViewEl.className = 'view-container';
            newViewEl.style.transform = slideLeft ? 'translateX(36px)' : 'translateX(-36px)';
            newViewEl.style.opacity = '0';
            void newViewEl.offsetWidth;
            newViewEl.classList.add('active');
            newViewEl.style.transform = '';
            newViewEl.style.opacity = '';
            currentView = index;
            if (index === 0) setTimeout(chartResize, 50);
            try { if (window.lucide) lucide.createIcons(); } catch(e){}
        }

        function setupNavDrag() {
            navIndicatorEl = document.getElementById('navIndicator');
            bottomNavEl = document.querySelector('.bottom-nav');
            navBtns = document.querySelectorAll('.nav-btn');
            if (!navIndicatorEl || !bottomNavEl) return;

            let dragging = false, startX = 0, startLeft = 0, currentX = 0;

            function getCenters() {
                const navRect = bottomNavEl.getBoundingClientRect();
                return Array.from(navBtns).map(item => {
                    const r = item.getBoundingClientRect();
                    return { el: item, center: r.left + r.width/2 - navRect.left, left: r.left - navRect.left, width: r.width };
                });
            }

            function onStart(clientX) {
                dragging = true;
                startX = clientX;
                const m = navIndicatorEl.style.transform.match(/translateX\(([\-\d.]+)px\)/);
                startLeft = m ? parseFloat(m[1]) : 0;
                currentX = startLeft;
                navIndicatorEl.classList.add('dragging');
                navIndicatorEl.style.transition = 'none';
                if (navigator.vibrate) try { navigator.vibrate(8); } catch(e){}
            }

            function onMove(clientX) {
                if (!dragging) return;
                currentX = startLeft + (clientX - startX);
                const navW = bottomNavEl.getBoundingClientRect().width;
                const indW = parseFloat(navIndicatorEl.style.width) || 70;
                currentX = Math.max(0, Math.min(navW - indW, currentX));
                navIndicatorEl.style.transform = 'translateY(-50%) translateX(' + currentX + 'px)';
                const centers = getCenters();
                const indCenter = currentX + indW / 2;
                let closest = null, minDist = Infinity;
                centers.forEach(c => {
                    const d = Math.abs(c.center - indCenter);
                    if (d < minDist) { minDist = d; closest = c; }
                });
                navBtns.forEach(b => b.classList.remove('magnify'));
                if (closest && minDist < 42) closest.el.classList.add('magnify');
            }

            function onEnd() {
                if (!dragging) return;
                dragging = false;
                navIndicatorEl.classList.remove('dragging');
                navIndicatorEl.style.transition = '';
                const centers = getCenters();
                const indW = parseFloat(navIndicatorEl.style.width) || 70;
                const indCenter = currentX + indW / 2;
                let closest = centers[0], minDist = Infinity;
                centers.forEach(c => {
                    const d = Math.abs(c.center - indCenter);
                    if (d < minDist) { minDist = d; closest = c; }
                });
                navBtns.forEach(b => b.classList.remove('magnify'));
                if (closest && closest.el) closest.el.click();
                if (navigator.vibrate) try { navigator.vibrate(12); } catch(e){}
            }

            navIndicatorEl.addEventListener('mousedown', e => { e.preventDefault(); onStart(e.clientX); });
            navIndicatorEl.addEventListener('touchstart', e => { onStart(e.touches[0].clientX); }, { passive: true });
            window.addEventListener('mousemove', e => onMove(e.clientX));
            window.addEventListener('touchmove', e => { if (dragging) onMove(e.touches[0].clientX); }, { passive: true });
            window.addEventListener('mouseup', onEnd);
            window.addEventListener('touchend', onEnd);
            window.addEventListener('resize', () => updateNavIndicator(false));
            setTimeout(() => updateNavIndicator(false), 180);
        }

        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', setupNavDrag);
        } else {
            setTimeout(setupNavDrag, 50);
        }

        // ======================== OPTIONS / DIALOGS ========================
        const optionsData = {
            market: { title: 'Select Market Pair', items: ALL_MARKETS },
            timeframe: { title: 'Select Timeframe', items: ['30 Seconds', '1 Minute', '2 Minutes', '5 Minutes', '15 Minutes'] },
            strategy: { title: 'Select Strategy', items: [
                    'AI Smart Signal', 'Support/Resistance Touch', 'EMA Trend Cross', 'RSI Reversal',
                    'Bollinger Bands', 'MACD Momentum', 'Stochastic Reversal', 'Trend Pullback', 'Breakout Spike'
                ] },
            chartType: { title: 'Select Chart Type', items: ['Candlestick', 'Line', 'Area', 'Heikin Ashi'] },
            chartStyle: { title: 'Chart Style (26 Designs)', items: [
                    'Style 1 - Classic', 'Style 2 - Terminal', 'Style 3 - Futuristic', 'Style 4 - Pro Finance',
                    'Style 5 - Neon Pulse', 'Style 6 - Deep Ocean', 'Style 7 - Sunset Drive', 'Style 8 - Royal Violet',
                    'Style 9 - Cyber Grid', 'Style 10 - Galaxy Starfield', 'Style 11 - Matrix Rain', 'Style 12 - Aurora Borealis',
                    'Style 13 - Golden Bull', 'Style 14 - Ice Crystal', 'Style 15 - Retro Wave', 'Style 16 - Holo 3D Depth',
                    'Style 17 - Quantum Flux', 'Style 18 - Stealth Ops', 'Style 19 - Plasma Storm', 'Style 20 - Limon Kombiner Pro',
                    'Style 21 - Aurora Quantum', 'Style 22 - Cyber Matrix', 'Style 23 - Orbital Glass', 'Style 24 - Dark Phoenix',
                    'Style 25 - Nexus Ultra', 'Style 26 - Quantum Glass Infinity'
                ] },
            martingale: { title: 'Martingale Steps', items: ['No MTG', 'MTG1', 'MTG2', 'MTG3'] },
            dialogAnim: { title: 'Dialog Animation', items: ['Scale', 'Fade', 'Slide Up', 'Flip', 'Bounce'] },
            signalMode: { title: 'Signal Mode', items: ['Manual', 'Auto'] },
            fcDay: { title: 'Select Day', items: ['Today', 'Yesterday'] },
            fcMtg: { title: 'MTG Level', items: ['No MTG', 'MTG1', 'MTG2', 'MTG3'] },
            fcPayout: { title: 'Min Payout Filter', items: ['All Payout', '80%+', '85%+', '90%+', '92%+'] }
        };

        let activeDialogType = '';
        let dialogAnimStyle = 'Scale';

        function openDialog(type) {
            if (type === 'autoMarkets') { openAutoMarketsDialog(); return; }
            activeDialogType = type;
            const data = optionsData[type];
            const currentValue = document.getElementById(`val-${type}`).innerText;
            document.getElementById('dialogTitle').innerText = data.title;
            const listHtml = data.items.map(item => {
                const isSelected = item === currentValue;
                return `<div class="dialog-item ${isSelected ? 'selected' : ''}" onclick="selectItem('${item}', event)">
                    <span>${item}</span>
                    <i data-lucide="check" class="w-4 h-4 check-icon"></i>
                </div>`;
            }).join('');
            document.getElementById('dialogList').innerHTML = listHtml;
            lucide.createIcons();
            showDialogAnim();
        }

        function openAutoMarketsDialog() {
            activeDialogType = 'autoMarkets';
            document.getElementById('dialogTitle').innerText = 'Select Auto Markets';
            const listHtml = ALL_MARKETS.map(item => {
                const checked = selectedAutoMarkets.includes(item);
                return `<div class="dialog-item" onclick="toggleAutoMarket('${item}', this)">
                    <span>${item}</span>
                    <div class="check-box ${checked ? 'checked' : ''}"></div>
                </div>`;
            }).join('') +
                `<div class="dialog-item" style="justify-content:center;margin-top:6px;">
                <button onclick="closeDialog()" style="padding:8px 24px;border-radius:10px;background:var(--primary);color:white;border:none;font-weight:600;font-size:0.7rem;cursor:pointer;">DONE</button>
            </div>`;
            document.getElementById('dialogList').innerHTML = listHtml;
            showDialogAnim();
        }

        function toggleAutoMarket(market, el) {
            const box = el.querySelector('.check-box');
            const idx = selectedAutoMarkets.indexOf(market);
            if (idx >= 0) { selectedAutoMarkets.splice(idx, 1); box.classList.remove('checked'); }
            else { selectedAutoMarkets.push(market); box.classList.add('checked'); }
            const count = selectedAutoMarkets.length;
            document.getElementById('val-autoMarkets').innerText = count === ALL_MARKETS.length ? 'All' : count + ' pairs';
            saveSettings();
        }

        function showDialogAnim() {
            const dialog = document.getElementById('selectionDialog');
            dialog.classList.remove('anim-scale', 'anim-fade', 'anim-slide-up', 'anim-flip', 'anim-bounce');
            switch (dialogAnimStyle) {
                case 'Fade': dialog.classList.add('anim-fade'); break;
                case 'Slide Up': dialog.classList.add('anim-slide-up'); break;
                case 'Flip': dialog.classList.add('anim-flip'); break;
                case 'Bounce': dialog.classList.add('anim-bounce'); break;
                default: dialog.classList.add('anim-scale');
            }
            document.getElementById('overlay').classList.add('show');
            dialog.classList.add('show');
            document.getElementById('app-wrapper').classList.add('blur-active');
        }

        function closeDialog() {
            document.getElementById('overlay').classList.remove('show');
            document.getElementById('selectionDialog').classList.remove('show');
            document.getElementById('app-wrapper').classList.remove('blur-active');
        }

        function selectItem(value, ev) {
            ev.stopPropagation();
            const prev = document.getElementById(`val-${activeDialogType}`).innerText;
            document.getElementById(`val-${activeDialogType}`).innerText = value;
            if (activeDialogType === 'dialogAnim') dialogAnimStyle = value;
            const items = document.querySelectorAll('.dialog-item');
            items.forEach(el => el.classList.remove('selected'));
            ev.currentTarget.classList.add('selected');
            if (activeDialogType === 'market' && prev !== value) onMarketChanged(value);
            if (activeDialogType === 'timeframe' && prev !== value) onTimeframeChanged(value);
            if (activeDialogType === 'signalMode') onSignalModeChanged(value);
            if (activeDialogType === 'chartStyle' || activeDialogType === 'chartType') setTimeout(function(){ chartResize(); requestDraw(); }, 80);
            if (activeDialogType === 'chartType' && prev !== value) setTimeout(chartResize, 100);
            setTimeout(closeDialog, 250);
            saveSettings();
        }

        function onSignalModeChanged(mode, silent) {
            const autoMarketsItem = document.getElementById('autoMarketsItem');
            if (mode === 'Auto') { autoMarketsItem.style.display = 'flex'; }
            else { autoMarketsItem.style.display = 'none'; if (!silent) stopAutoMode(); }
            lucide.createIcons();
            if (!silent) saveSettings();
        }

        function toggleSwitch(element) {
            const toggle = element.querySelector('.toggle');
            if (toggle) toggle.classList.toggle('active');
            saveSettings();
        }

        function updateAnimSpeed(v) {
            document.documentElement.style.setProperty('--anim-speed', v);
            document.documentElement.style.setProperty('--speed-multiplier', v);
            const el = document.getElementById('speedVal');
            if (el) el.textContent = parseFloat(v).toFixed(1) + 'x';
            try { localStorage.setItem('ht_anim_speed', v); } catch(e){}
        }
        function updateGlassBlur(v) {
            document.documentElement.style.setProperty('--glass-blur', v + 'px');
            const el = document.getElementById('blurVal');
            if (el) el.textContent = v + 'px';
            try { localStorage.setItem('ht_glass_blur', v); } catch(e){}
        }
        function updateGlassOpacity(v) {
            document.documentElement.style.setProperty('--glass-opacity', v);
            document.documentElement.style.setProperty('--glass-alpha', v);
            const el = document.getElementById('glassVal');
            if (el) el.textContent = Math.round(parseFloat(v) * 100) + '%';
            try { localStorage.setItem('ht_glass_opacity', v); } catch(e){}
        }
        function updateIndicatorGlow(v) {
            document.documentElement.style.setProperty('--indicator-glow', v);
            const el = document.getElementById('glowVal');
            if (el) el.textContent = Math.round(parseFloat(v) * 100) + '%';
            try { localStorage.setItem('ht_indicator_glow', v); } catch(e){}
        }
        function updateFontSize(v) {
            document.documentElement.style.setProperty('--font-base', v + 'px');
            const el = document.getElementById('fontVal');
            if (el) el.textContent = v + 'px';
            try { localStorage.setItem('ht_font_size', v); } catch(e){}
        }
        (function restoreGlassSettings() {
            try {
                const s = localStorage.getItem('ht_anim_speed');
                const b = localStorage.getItem('ht_glass_blur');
                const o = localStorage.getItem('ht_glass_opacity');
                const g = localStorage.getItem('ht_indicator_glow');
                const f = localStorage.getItem('ht_font_size');
                if (s) { const sl = document.getElementById('speedSlider'); if (sl) { sl.value = s; updateAnimSpeed(s); } }
                if (b) { const sl = document.getElementById('blurSlider'); if (sl) { sl.value = b; updateGlassBlur(b); } }
                if (o) { const sl = document.getElementById('glassSlider'); if (sl) { sl.value = o; updateGlassOpacity(o); } }
                if (g) { const sl = document.getElementById('glowSlider'); if (sl) { sl.value = g; updateIndicatorGlow(g); } }
                if (f) { const sl = document.getElementById('fontSlider'); if (sl) { sl.value = f; updateFontSize(f); } }
            } catch(e){}
        })();

        function toggleDarkMode(element) {
            const toggle = element.querySelector('.toggle');
            toggle.classList.toggle('active');
            document.body.classList.toggle('dark-mode', toggle.classList.contains('active'));
            saveSettings();
        }

        document.getElementById('speedSlider').addEventListener('input', function(e) {
            const val = parseFloat(e.target.value);
            document.documentElement.style.setProperty('--speed-multiplier', val);
            document.getElementById('speedVal').innerText = val.toFixed(1) + 'x';
            saveSettings();
        });
        document.getElementById('glassSlider').addEventListener('input', function(e) {
            const val = parseFloat(e.target.value);
            document.documentElement.style.setProperty('--glass-opacity', val);
            document.documentElement.style.setProperty('--glass-alpha', val);
            document.getElementById('glassVal').innerText = Math.round(val * 100) + '%';
            saveSettings();
        });
        document.getElementById('fontSlider').addEventListener('input', function(e) {
            const val = e.target.value + 'px';
            document.documentElement.style.fontSize = val;
            document.getElementById('fontVal').innerText = val;
            saveSettings();
        });

        document.getElementById('signalNameInput').addEventListener('input', function() { saveSettings(); });
        document.getElementById('dashboardNameInput').addEventListener('input', function() {
            document.documentElement.style.setProperty('--dashboard-name', '"' + this.value + '"');
            saveSettings();
        });
        document.getElementById('watermarkInput').addEventListener('input', function() {
            document.getElementById('watermarkPreview').innerText = this.value;
            document.documentElement.style.setProperty('--watermark-text', '"' + this.value + '"');
            requestDraw();
            saveSettings();
        });
        document.querySelectorAll('.telegram-input').forEach(el => {
            el.addEventListener('change', saveSettings);
            el.addEventListener('input', saveSettings);
        });

        function resetAll() {
            document.getElementById('val-market').innerText = 'USDBDT-OTC';
            document.getElementById('val-timeframe').innerText = '1 Minute';
            document.getElementById('val-strategy').innerText = 'AI Smart Signal';
            document.getElementById('val-chartType').innerText = 'Candlestick';
            document.getElementById('val-martingale').innerText = 'No MTG';
            document.getElementById('val-dialogAnim').innerText = 'Scale';
            document.getElementById('val-signalMode').innerText = 'Manual';
            document.getElementById('telegramInput').value = '@Mahabub_iX';
            document.getElementById('botTokenInput').value = '';
            document.getElementById('chatIdInput').value = '';
            dialogAnimStyle = 'Scale';
            selectedAutoMarkets = [...ALL_MARKETS];
            document.getElementById('val-autoMarkets').innerText = 'All';
            document.getElementById('autoMarketsItem').style.display = 'none';
            document.getElementById('signalNameInput').value = 'RAVITH AI PRO';
            document.getElementById('dashboardNameInput').value = 'RAVITH PRO';
            document.documentElement.style.setProperty('--dashboard-name', '"RAVITH PRO"');
            document.getElementById('watermarkInput').value = '𝐑𝐀𝐕𝐈𝐓𝐇 𝐒𝐒';
            document.getElementById('watermarkPreview').innerText = '𝐑𝐀𝐕𝐈𝐓𝐇 𝐒𝐒';
            document.documentElement.style.setProperty('--watermark-text', '"𝐑𝐀𝐕𝐈𝐓𝐇 𝐒𝐒"');
            const soundToggle = document.querySelector('[data-toggle-key="soundAlerts"]');
            const vibToggle = document.querySelector('[data-toggle-key="vibration"]');
            if (soundToggle) soundToggle.classList.add('active');
            if (vibToggle) vibToggle.classList.add('active');
            document.getElementById('darkModeToggle').classList.remove('active');
            document.body.classList.remove('dark-mode');
            document.getElementById('autoTelegramToggle').classList.add('active');
            document.getElementById('speedSlider').value = 2;
            document.documentElement.style.setProperty('--speed-multiplier', 2);
            document.getElementById('speedVal').innerText = '2.0x';
            document.getElementById('glassSlider').value = 0.8;
            document.documentElement.style.setProperty('--glass-opacity', 0.8);
            document.documentElement.style.setProperty('--glass-alpha', 0.8);
            document.getElementById('glassVal').innerText = '80%';
            document.getElementById('fontSlider').value = 12;
            document.documentElement.style.fontSize = '12px';
            document.getElementById('fontVal').innerText = '12px';
            resetResult();
            onMarketChanged('USDBDT-OTC');
            saveSettings();
        }

        // ======================== CHART ENGINE ========================
        const canvas = document.getElementById("chart");
        const ctx = canvas.getContext("2d", { alpha: false, desynchronized: true });
        const W = 600, H = 337.5;

        let candles = [], allCandles = [], liveCandle = null;
        let currentPair = "USDBDT-OTC";
        let currentApiPair = "USDBDT_otc";
        let currentPayout = 0;
        let latestClosePrice = 0;
        let apiError = null;

        const C = { bg: "#050508", green: "#00FF66", greenBright: "#33FF99", red: "#FF3366", redBright: "#FF5C8A",
            yellow: "#FFCC00", yellowBright: "#FFE64D", cyan: "#00F2FE", blue: "#4FACFE", blue2: "#1a3a6c",
            white: "#F4F7FF", gray: "#7A889B", darkGray: "#141923", grid: "rgba(110,140,160,.12)" };

        let _drawScheduled = false;

        function requestDraw() {
            if (_drawScheduled) return;
            _drawScheduled = true;
            requestAnimationFrame(() => {
                _drawScheduled = false;
                draw();
            });
        }

        let resizeTimer = null;

        function chartResize() {
            const rect = canvas.getBoundingClientRect();
            if (rect.width < 2 || rect.height < 2) return;
            const dpr = Math.min(window.devicePixelRatio || 1, 2);
            canvas.width = Math.max(1, Math.round(rect.width * dpr));
            canvas.height = Math.max(1, Math.round(rect.height * dpr));
            const scaleX = canvas.width / W, scaleY = canvas.height / H;
            ctx.setTransform(scaleX, 0, 0, scaleY, 0, 0);
            ctx.imageSmoothingEnabled = true;
            ctx.imageSmoothingQuality = "high";
            requestDraw();
        }
        window.addEventListener("resize", () => { clearTimeout(resizeTimer); resizeTimer = setTimeout(chartResize, 80); });

        function clamp(v, min, max) { return Math.max(min, Math.min(max, v)); }

        function roundRect(x, y, w, h, r) { const rr = Math.min(r, w / 2, h / 2);
            ctx.beginPath();
            ctx.moveTo(x + rr, y);
            ctx.arcTo(x + w, y, x + w, y + h, rr);
            ctx.arcTo(x + w, y + h, x, y + h, rr);
            ctx.arcTo(x, y + h, x, y, rr);
            ctx.arcTo(x, y, x + w, y, rr);
            ctx.closePath(); }

        function text(value, x, y, size, color, align = "left", weight = "normal") {
            ctx.font = `${weight} ${size}px monospace`;
            ctx.fillStyle = color;
            ctx.textAlign = align;
            ctx.textBaseline = "middle";
            ctx.fillText(value, x, y);
        }

        function panel(x, y, w, h, glowColor = "rgba(0,242,254,.35)") {
            ctx.save();
            const grad = ctx.createLinearGradient(x, y, x, y + h);
            grad.addColorStop(0, "rgba(10,18,35,0.94)");
            grad.addColorStop(1, "rgba(5,10,20,0.97)");
            ctx.fillStyle = grad;
            ctx.strokeStyle = "rgba(0,242,254,0.45)";
            ctx.lineWidth = 1;
            ctx.shadowColor = glowColor;
            ctx.shadowBlur = 6;
            roundRect(x, y, w, h, 3);
            ctx.fill();
            ctx.stroke();
            ctx.restore();
        }

        function neonLine(points, color, width = 1) {
            if (!points || points.length < 2) return;
            ctx.save();
            ctx.beginPath();
            ctx.moveTo(points[0].x, points[0].y);
            for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y);
            ctx.strokeStyle = color;
            ctx.lineWidth = width;
            ctx.shadowColor = color;
            ctx.shadowBlur = 4;
            ctx.stroke();
            ctx.restore();
        }

        function priceFormat(v) { return Number(v).toFixed(5); }
        function timeFormat(v) { if (!v) return ""; if (v.length >= 16) return v.substring(11, 16); return v; }

        function calculateEMA(data, period) {
            if (!data.length) return [];
            const k = 2 / (period + 1);
            let ema = data[0].close;
            const out = [ema];
            for (let i = 1; i < data.length; i++) { ema = data[i].close * k + ema * (1 - k); out.push(ema); }
            return out;
        }

        function displayPairToApi(displayPair) { if (!displayPair) return "USDBDT_otc"; return displayPair.replace(/-OTC$/i, "_otc"); }
        function getChartType() { return document.getElementById('val-chartType').innerText.trim(); }

        function getChartStyle() {
            const el = document.getElementById('val-chartStyle');
            const t = el ? el.innerText.trim() : 'Style 1 - Classic';
            const m = t.match(/Style\s+(\d+)/i);
            const n = m ? parseInt(m[1], 10) : 1;
            return (n >= 1 && n <= 26) ? n : 1;
        }

        const CHART_THEMES = {
            1:  { name:'Classic', bg:'#050508', grid:'rgba(110,140,160,.12)', up:'#00FF66', down:'#FF3366', accent:'#00F2FE', wick:'#F4F7FF', label:'#7A889B', glow:false, neon:false },
            2:  { name:'Terminal', bg:'#0a0e0a', grid:'rgba(0,255,100,.08)', up:'#33ff66', down:'#ff2244', accent:'#00ff88', wick:'#aaffcc', label:'#66aa77', glow:false, neon:true },
            3:  { name:'Futuristic', bg:'#06061a', grid:'rgba(100,120,255,.12)', up:'#00e5ff', down:'#ff2d95', accent:'#7c5cff', wick:'#d0e0ff', label:'#8899cc', glow:true, neon:true },
            4:  { name:'Pro Finance', bg:'#0c1118', grid:'rgba(140,160,180,.10)', up:'#26a69a', down:'#ef5350', accent:'#42a5f5', wick:'#cfd8dc', label:'#90a4ae', glow:false, neon:false },
            5:  { name:'Neon Pulse', bg:'#050510', grid:'rgba(255,0,200,.08)', up:'#39ff14', down:'#ff073a', accent:'#ff00ff', wick:'#ffffff', label:'#ff66cc', glow:true, neon:true },
            6:  { name:'Deep Ocean', bg:'#020b18', grid:'rgba(0,180,255,.10)', up:'#00d4aa', down:'#ff6b6b', accent:'#00b4ff', wick:'#a0e0ff', label:'#5a9ab8', glow:true, neon:false },
            7:  { name:'Sunset Drive', bg:'#12080a', grid:'rgba(255,140,60,.10)', up:'#ffaa00', down:'#ff3355', accent:'#ff6b35', wick:'#ffe0c0', label:'#cc8866', glow:true, neon:false },
            8:  { name:'Royal Violet', bg:'#0c0618', grid:'rgba(180,100,255,.12)', up:'#b388ff', down:'#ff4d6d', accent:'#9c27b0', wick:'#e1bee7', label:'#ba68c8', glow:true, neon:true },
            9:  { name:'Cyber Grid', bg:'#030608', grid:'rgba(0,255,200,.15)', up:'#00ffc8', down:'#ff0055', accent:'#00ffaa', wick:'#ccfff0', label:'#00cc99', glow:false, neon:true },
            10: { name:'Galaxy', bg:'#050510', grid:'rgba(150,120,255,.10)', up:'#7c4dff', down:'#ff4081', accent:'#e040fb', wick:'#f3e5f5', label:'#ce93d8', glow:true, neon:true },
            11: { name:'Matrix', bg:'#000a00', grid:'rgba(0,255,0,.10)', up:'#00ff41', down:'#008f11', accent:'#00ff00', wick:'#00ff41', label:'#00aa00', glow:false, neon:true },
            12: { name:'Aurora', bg:'#041018', grid:'rgba(0,255,180,.10)', up:'#00e676', down:'#ff5252', accent:'#18ffff', wick:'#e0f7fa', label:'#80deea', glow:true, neon:true },
            13: { name:'Golden Bull', bg:'#100c04', grid:'rgba(255,200,50,.10)', up:'#ffd700', down:'#c62828', accent:'#ffc107', wick:'#fff8e1', label:'#ffcc80', glow:true, neon:false },
            14: { name:'Ice Crystal', bg:'#061018', grid:'rgba(180,230,255,.12)', up:'#80d8ff', down:'#ff8a80', accent:'#40c4ff', wick:'#e1f5fe', label:'#81d4fa', glow:true, neon:false },
            15: { name:'Retro Wave', bg:'#0a0414', grid:'rgba(255,0,170,.10)', up:'#ff2a6d', down:'#05d9e8', accent:'#d1f7ff', wick:'#ff71ce', label:'#b967ff', glow:true, neon:true },
            16: { name:'Holo 3D', bg:'#080814', grid:'rgba(200,180,255,.12)', up:'#64ffda', down:'#ff80ab', accent:'#ea80fc', wick:'#ffffff', label:'#b39ddb', glow:true, neon:true },
            17: { name:'Quantum', bg:'#04040c', grid:'rgba(100,255,255,.10)', up:'#18ffff', down:'#ff1744', accent:'#00e5ff', wick:'#e0ffff', label:'#84ffff', glow:true, neon:true },
            18: { name:'Stealth', bg:'#0a0a0a', grid:'rgba(120,120,120,.10)', up:'#76ff03', down:'#ff1744', accent:'#b0bec5', wick:'#eceff1', label:'#78909c', glow:false, neon:false },
            19: { name:'Plasma', bg:'#0c0410', grid:'rgba(255,50,200,.10)', up:'#e040fb', down:'#ff1744', accent:'#ff4081', wick:'#f8bbd0', label:'#f48fb1', glow:true, neon:true },
            20: { name:'Limon Pro', bg:'#050d08', grid:'rgba(50,205,50,.12)', up:'#32CD32', down:'#ff3366', accent:'#00F2FE', wick:'#e8ffe8', label:'#7dcea0', glow:true, neon:true },
            21: { name:'Aurora Q', bg:'#040c14', grid:'rgba(0,242,254,.12)', up:'#00e676', down:'#ff5252', accent:'#00f2fe', wick:'#e0f7fa', label:'#4dd0e1', glow:true, neon:true },
            22: { name:'Cyber Mx', bg:'#020808', grid:'rgba(0,255,170,.14)', up:'#00ff9f', down:'#ff005c', accent:'#00ffc6', wick:'#ccffee', label:'#00c896', glow:false, neon:true },
            23: { name:'Orbital', bg:'#060a12', grid:'rgba(140,180,255,.12)', up:'#4fc3f7', down:'#ef5350', accent:'#82b1ff', wick:'#e3f2fd', label:'#90caf9', glow:true, neon:false },
            24: { name:'Phoenix', bg:'#100505', grid:'rgba(255,80,40,.12)', up:'#ff6d00', down:'#d50000', accent:'#ff3d00', wick:'#ffccbc', label:'#ff8a65', glow:true, neon:true },
            25: { name:'Nexus', bg:'#05070f', grid:'rgba(0,200,255,.12)', up:'#00e5ff', down:'#ff1744', accent:'#2979ff', wick:'#e1f5fe', label:'#40c4ff', glow:true, neon:true },
            26: { name:'Quantum Glass', bg:'#04060d', grid:'rgba(160,220,255,.14)', up:'#32CD32', down:'#ff5566', accent:'#00f2fe', wick:'#e8f7ff', label:'#93c5fd', glow:true, neon:true }
        };

        function applyChartTheme(th) {
            C.bg = th.bg; C.grid = th.grid; C.green = th.up; C.red = th.down;
            C.cyan = th.accent; C.white = th.wick; C.gray = th.label;
            C.greenBright = th.up; C.redBright = th.down; C.yellow = th.accent;
        }

        let liveTickInterval = null;
        let livePollInterval = null;
        let loadInFlight = false;
        let livePollInFlight = false;
        let lastRunningKey = null;
        let lastRunningTime = null;

        function mapCandle(c) {
            return {
                open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close),
                volume: Number(c.volume || c.Volume || 0),
                signal: String(c.signal || '').trim().toUpperCase(),
                payout: Number(c.payout || 0), time: c.time || '', pair: c.pair || '',
                is_running: !!c.is_running, ticks: Number(c.ticks || 0)
            };
        }

        function applyRunningCandle(running) {
            if (!running) return false;
            const rc = mapCandle(running);
            if (!Number.isFinite(rc.open) || !Number.isFinite(rc.close)) return false;
            if (engine.currentSignal && engine.state !== 'idle' && engine.state !== 'resolved') {
                rc.signal = engine.currentSignal.direction;
            } else if (liveCandle && liveCandle.signal && liveCandle.time === rc.time) {
                rc.signal = liveCandle.signal;
            }
            rc._initialized = true;
            rc._fromQuotex = true;
            rc.is_running = true;

            if (lastRunningTime && rc.time && rc.time !== lastRunningTime && liveCandle && liveCandle._fromQuotex) {
                const promoted = {
                    open: liveCandle.open, high: liveCandle.high, low: liveCandle.low, close: liveCandle.close,
                    signal: liveCandle.signal || '', payout: liveCandle.payout || 0,
                    time: liveCandle.time, pair: liveCandle.pair
                };
                if (!candles.length || candles[candles.length - 1].time !== promoted.time) {
                    candles.push(promoted);
                    if (candles.length > 40) candles = candles.slice(-40);
                    allCandles.push(promoted);
                }
            }

            liveCandle = rc;
            latestClosePrice = rc.close;
            lastRunningKey = rc.time + '|' + rc.close + '|' + rc.ticks;
            lastRunningTime = rc.time;
            return true;
        }

        async function pollLiveRunning() {
            if (!currentApiPair || livePollInFlight) return;
            livePollInFlight = true;
            try {
                const url = API_BASE + '/latest?Pair=' + encodeURIComponent(currentApiPair) + '&Time=1m';
                const response = await fetch(url, { cache: 'no-store' });
                if (!response.ok) throw new Error('live ' + response.status);
                const json = await response.json();
                if (applyRunningCandle(json.running)) {
                    apiError = null;
                    setChartStatus('LIVE', 'ok');
                    evaluateWaitingResult();
                    requestDraw();
                } else if (json.data && (!liveCandle || !liveCandle._fromQuotex)) {
                    const last = mapCandle(json.data);
                    liveCandle = Object.assign({}, last, { _initialized: true, _fromQuotex: false, is_running: false });
                    latestClosePrice = last.close;
                    requestDraw();
                }
            } catch (e) {
            } finally {
                livePollInFlight = false;
            }
        }

        function startLiveTicks() {
            if (livePollInterval) clearInterval(livePollInterval);
            livePollInterval = setInterval(function () {
                if (currentApiPair) pollLiveRunning();
            }, 500);
            pollLiveRunning();
            if (liveTickInterval) clearInterval(liveTickInterval);
            liveTickInterval = setInterval(function () { if (liveCandle) requestDraw(); }, 1000);
        }

        function stopLiveTicks() {
            if (liveTickInterval) { clearInterval(liveTickInterval); liveTickInterval = null; }
            if (livePollInterval) { clearInterval(livePollInterval); livePollInterval = null; }
        }

        async function loadData(pairApi, quiet) {
            if (!pairApi) return false;
            if (loadInFlight) return false;
            loadInFlight = true;
            const url = API_BASE + '/?Pair=' + encodeURIComponent(pairApi) + '&Candle=200&Time=1m';
            if (!quiet) setChartStatus('SYNCING', 'ok');
            try {
                const response = await fetch(url, { cache: 'no-store' });
                if (!response.ok) throw new Error('API Error: ' + response.status);
                const json = await response.json();
                if (!json || !Array.isArray(json.data)) throw new Error('Invalid JSON');
                const all = json.data.map(mapCandle).filter(function (c) {
                    return Number.isFinite(c.open) && Number.isFinite(c.high) &&
                        Number.isFinite(c.low) && Number.isFinite(c.close);
                }).reverse();
                if (!all.length) {
                    if (!candles.length) {
                        apiError = 'NO DATA AVAILABLE';
                        setChartStatus(apiError, 'warn');
                        requestDraw();
                    }
                    if (json.running) applyRunningCandle(json.running);
                    loadInFlight = false;
                    return false;
                }
                allCandles = all;
                if (json.running && json.running.time && all.length && all[all.length - 1].time === json.running.time) {
                    all = all.slice(0, -1);
                    allCandles = allCandles.slice(0, -1);
                }
                candles = all.slice(-40);
                const last = all.length ? all[all.length - 1] : null;
                if (last) latestClosePrice = last.close;
                const hasRunning = applyRunningCandle(json.running);
                if (!hasRunning && last) {
                    if (!liveCandle || !liveCandle._fromQuotex) {
                        liveCandle = {
                            open: last.close, high: last.close, low: last.close, close: last.close,
                            time: last.time, pair: last.pair,
                            signal: (engine.currentSignal && engine.state !== 'idle') ? engine.currentSignal.direction : '',
                            _initialized: true, _fromQuotex: false, is_running: false
                        };
                    }
                }

                const payoutSample = all.slice(-30).map(function (c) { return c.payout; }).filter(function (p) { return p > 0; });
                currentPayout = payoutSample.length
                    ? Math.round(payoutSample.reduce(function (a, b) { return a + b; }, 0) / payoutSample.length) : 0;
                apiError = null;
                setChartStatus('LIVE', 'ok');
                evaluateWaitingResult();
                requestDraw();
                loadInFlight = false;
                return true;
            } catch (err) {
                console.error('Chart API Error:', err);
                if (!quiet || !candles.length) {
                    apiError = 'API CONNECTION ERROR';
                    setChartStatus(apiError, 'err');
                    requestDraw();
                }
                loadInFlight = false;
                return false;
            }
        }

        function setChartStatus(txt, level) {
            const box = document.getElementById('chartStatus');
            const txtEl = document.getElementById('chartStatusText');
            if (!box) return;
            box.classList.remove('err', 'warn');
            if (level === 'err') box.classList.add('err');
            else if (level === 'warn') box.classList.add('warn');
            if (txt === 'LIVE' && liveCandle && liveCandle._fromQuotex) {
                txtEl.innerText = 'LIVE' + (liveCandle.ticks ? (' · ' + liveCandle.ticks + 't') : '');
            } else {
                txtEl.innerText = txt;
            }
        }

        function draw() {
            ctx.save();
            ctx.setTransform(canvas.width / W, 0, 0, canvas.height / H, 0, 0);
            ctx.clearRect(0, 0, W, H);
            ctx.fillStyle = C.bg;
            ctx.fillRect(0, 0, W, H);
            ctx.strokeStyle = "rgba(0,242,254,.3)";
            ctx.lineWidth = 1;
            ctx.strokeRect(1, 1, W - 2, H - 2);
            drawHeader();
            if (apiError) { drawErrorState(); ctx.restore(); return; }
            if (!candles.length) { drawLoadingState(); ctx.restore(); return; }
            const chartType = getChartType();
            const styleNum = getChartStyle();
            const th = CHART_THEMES[styleNum] || CHART_THEMES[1];
            applyChartTheme(th);
            drawMainChart(chartType);
            try {
                ctx.save();
                ctx.font = 'bold 6px JetBrains Mono, monospace';
                ctx.fillStyle = th.accent;
                ctx.globalAlpha = 0.85;
                ctx.textAlign = 'left';
                ctx.fillText('S' + styleNum + ' · ' + th.name, 8, H - 8);
                ctx.restore();
            } catch (e) {}
            drawDashboard();
            drawExpiryPanel();
            drawBottomBar();
            drawWatermark();
            ctx.restore();
        }

        function drawLoadingState() { text("◈ LOADING MARKET DATA...", W / 2, H / 2, 8, "#00F2FE", "center", "bold"); }
        function drawErrorState() { text("⚠ " + apiError, W / 2, H / 2 - 6, 10, "#FF3366", "center", "bold");
            text("Retrying automatically…", W / 2, H / 2 + 8, 6, "#7A889B", "center", "normal"); }
        function drawHeader() { const pair = currentPair || "USDBDT-OTC";
            text(pair.toUpperCase() + " • M1 PRO", 6, 9, 5.5, "#00F2FE", "left", "bold"); }

        function drawMainChart(chartType) {
            if (!candles.length) return;
            const chartLeft = -4, chartRight = W - 35, chartTop = 4, chartBottom = H - 52;
            const chartW = chartRight - chartLeft, chartH = chartBottom - chartTop;
            const displayData = liveCandle ? [...candles, liveCandle] : candles;
            let plotData = displayData;
            if (chartType === 'Heikin Ashi') {
                plotData = [];
                let prevHA = null;
                for (let i = 0; i < displayData.length; i++) {
                    const c = displayData[i];
                    const haClose = (c.open + c.high + c.low + c.close) / 4;
                    let haOpen;
                    if (i === 0 || !prevHA) haOpen = (c.open + c.close) / 2;
                    else haOpen = (prevHA.open + prevHA.close) / 2;
                    const haHigh = Math.max(c.high, haOpen, haClose);
                    const haLow = Math.min(c.low, haOpen, haClose);
                    const ha = { open: haOpen, high: haHigh, low: haLow, close: haClose, time: c.time, pair: c.pair, signal: c.signal };
                    plotData.push(ha);
                    prevHA = ha;
                }
            }
            let min = Infinity, max = -Infinity;
            for (const c of plotData) { min = Math.min(min, c.low); max = Math.max(max, c.high); }
            const range = max - min || 0.0001;
            min -= range * .06;
            max += range * .06;

            function priceY(price) { return chartTop + ((max - price) / (max - min)) * chartH; }
            ctx.save();
            ctx.strokeStyle = C.grid;
            ctx.lineWidth = .6;
            for (let i = 0; i <= 10; i++) { const y = chartTop + chartH * i / 10;
                ctx.beginPath(); ctx.moveTo(chartLeft, y); ctx.lineTo(chartRight, y); ctx.stroke(); }
            for (let i = 0; i <= 12; i++) { const x = chartLeft + chartW * i / 12;
                ctx.beginPath(); ctx.moveTo(x, chartTop); ctx.lineTo(x, chartBottom); ctx.stroke(); }
            ctx.restore();
            const count = plotData.length;
            const spacing = chartW / count;
            const candleWidth = Math.max(5, spacing * .62);
            const ema20 = calculateEMA(plotData, 20);
            const emaPoints = ema20.map((v, i) => ({ x: chartLeft + i * spacing + spacing / 2, y: priceY(v) }));
            neonLine(emaPoints, "#FFCC00", 1.5);
            const ema9 = calculateEMA(plotData, 9);
            const ema9Points = ema9.map((v, i) => ({ x: chartLeft + i * spacing + spacing / 2, y: priceY(v) }));
            neonLine(ema9Points, "#00F2FE", 1.5);

            const recent = plotData.slice(Math.max(0, plotData.length - 15));
            const support = Math.min(...recent.map(c => c.low));
            const resistance = Math.max(...recent.map(c => c.high));
            drawHorizontalLevel(priceY(support), "#00FF66", "SUP");
            drawHorizontalLevel(priceY(resistance), "#FF3366", "RES");
            drawTrendLines(chartLeft, chartRight, chartTop, chartBottom);
            if (chartType === 'Candlestick' || chartType === 'Heikin Ashi') {
                drawCandlesticks(plotData, chartLeft, spacing, candleWidth, priceY);
            } else if (chartType === 'Line') {
                drawLineChart(plotData, chartLeft, spacing, priceY);
            } else if (chartType === 'Area') {
                drawAreaChart(plotData, chartLeft, spacing, priceY, chartBottom);
            }
            const lastIdx = plotData.length - 1;
            if (lastIdx >= 0 && engine.currentSignal && engine.state !== 'idle' && engine.state !== 'resolved') {
                const c = plotData[lastIdx];
                const x = chartLeft + lastIdx * spacing + spacing / 2;
                const openY = priceY(c.open), closeY = priceY(c.close);
                const highY = priceY(c.high), lowY = priceY(c.low);
                const top = Math.min(openY, closeY), bottom = Math.max(openY, closeY);
                drawSignalArrow(x, top, bottom, highY, lowY, engine.currentSignal.direction);
            }
            if (liveCandle) {
                const lastC = plotData[plotData.length - 1];
                if (lastC) {
                    const closeY = priceY(lastC.close);
                    ctx.save();
                    ctx.strokeStyle = "#00F2FE"; ctx.lineWidth = 0.8; ctx.setLineDash([2, 2]);
                    ctx.beginPath(); ctx.moveTo(chartLeft, closeY); ctx.lineTo(chartRight, closeY); ctx.stroke();
                    ctx.setLineDash([]);
                    const secLeft = 60 - new Date().getSeconds();
                    const secFormatted = secLeft < 10 ? '0' + secLeft : secLeft;
                    const x = chartLeft + (plotData.length - 1) * spacing + spacing / 2;
                    text(`⚡ 00:${secFormatted}`, x + candleWidth + 3, closeY, 5.5, "#FFCC00", "left", "bold");
                    ctx.restore();
                }
            }
            drawPriceScale(chartRight, chartTop, chartBottom, min, max);
            drawTimeScale(chartLeft, chartW, chartBottom, spacing, plotData);
        }

        function drawCandlesticks(plotData, chartLeft, spacing, candleWidth, priceY) {
            const th = CHART_THEMES[getChartStyle()] || CHART_THEMES[1];
            for (let i = 0; i < plotData.length; i++) {
                const c = plotData[i];
                const x = chartLeft + i * spacing + spacing / 2;
                const openY = priceY(c.open), closeY = priceY(c.close);
                const highY = priceY(c.high), lowY = priceY(c.low);
                const bullish = c.close >= c.open;
                ctx.save();
                if (th.glow || th.neon) { ctx.shadowColor = bullish ? th.up : th.down; ctx.shadowBlur = th.neon ? 8 : 4; }
                ctx.strokeStyle = bullish ? "#00FF66" : "#FF3366"; ctx.lineWidth = 1;
                ctx.beginPath(); ctx.moveTo(x, highY); ctx.lineTo(x, lowY); ctx.stroke();
                ctx.restore();
                const top = Math.min(openY, closeY), bottom = Math.max(openY, closeY);
                const bodyH = Math.max(bottom - top, 2);
                ctx.fillStyle = "rgba(0,0,0,.85)"; ctx.fillRect(x - candleWidth / 2 + 2, top + 2, candleWidth, bodyH);
                const grad = ctx.createLinearGradient(x - candleWidth / 2, 0, x + candleWidth / 2, 0);
                if (bullish) { grad.addColorStop(0, "#009933"); grad.addColorStop(.5, "#00FF66"); grad.addColorStop(1, "#008822"); }
                else { grad.addColorStop(0, "#990022"); grad.addColorStop(.5, "#FF3366"); grad.addColorStop(1, "#880011"); }
                ctx.fillStyle = grad; ctx.fillRect(x - candleWidth / 2, top, candleWidth, bodyH);
                ctx.strokeStyle = bullish ? "#33FF99" : "#FF6688"; ctx.lineWidth = .5;
                ctx.strokeRect(x - candleWidth / 2, top, candleWidth, bodyH);
            }
        }

        function drawLineChart(plotData, chartLeft, spacing, priceY) {
            ctx.save();
            ctx.beginPath();
            for (let i = 0; i < plotData.length; i++) {
                const x = chartLeft + i * spacing + spacing / 2;
                const y = priceY(plotData[i].close);
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.strokeStyle = "#00F2FE"; ctx.lineWidth = 2; ctx.shadowColor = "#00F2FE"; ctx.shadowBlur = 8;
            ctx.stroke(); ctx.restore();
            for (let i = 0; i < plotData.length; i += 2) {
                const x = chartLeft + i * spacing + spacing / 2;
                const y = priceY(plotData[i].close);
                ctx.save(); ctx.fillStyle = "#00F2FE"; ctx.shadowColor = "#00F2FE"; ctx.shadowBlur = 4;
                ctx.beginPath(); ctx.arc(x, y, 1.5, 0, Math.PI * 2); ctx.fill(); ctx.restore();
            }
        }

        function drawAreaChart(plotData, chartLeft, spacing, priceY, chartBottom) {
            ctx.save();
            ctx.beginPath();
            for (let i = 0; i < plotData.length; i++) {
                const x = chartLeft + i * spacing + spacing / 2;
                const y = priceY(plotData[i].close);
                if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
            }
            ctx.lineTo(chartLeft + (plotData.length - 1) * spacing + spacing / 2, chartBottom);
            ctx.lineTo(chartLeft + spacing / 2, chartBottom);
            ctx.closePath();
            const grad = ctx.createLinearGradient(0, 4, 0, chartBottom);
            grad.addColorStop(0, "rgba(0,242,254,0.3)"); grad.addColorStop(1, "rgba(0,242,254,0.02)");
            ctx.fillStyle = grad; ctx.fill();
            ctx.strokeStyle = "#00F2FE"; ctx.lineWidth = 2; ctx.shadowColor = "#00F2FE"; ctx.shadowBlur = 8;
            ctx.stroke(); ctx.restore();
        }

        function drawSignalArrow(x, top, bottom, highY, lowY, direction) {
            const isBuy = direction === "BUY" || direction === "CALL";
            const isSell = direction === "SELL" || direction === "PUT";
            if (!isBuy && !isSell) return;
            const arrowSize = 10, offset = 6;
            ctx.save();
            ctx.shadowColor = "#FFCC00"; ctx.shadowBlur = 16; ctx.fillStyle = "#FFCC00";
            if (isBuy) {
                const tipY = lowY + offset, baseY = tipY + arrowSize;
                ctx.beginPath(); ctx.moveTo(x, tipY); ctx.lineTo(x - 5, baseY - 3); ctx.lineTo(x - 2, baseY - 2); ctx.lineTo(x - 2, baseY + 2); ctx.lineTo(x + 2, baseY + 2); ctx.lineTo(x + 2, baseY - 2); ctx.lineTo(x + 5, baseY - 3); ctx.closePath(); ctx.fill();
                ctx.shadowBlur = 0; ctx.fillStyle = "#FFCC00"; ctx.font = "bold 5px monospace"; ctx.textAlign = "center"; ctx.textBaseline = "top"; ctx.fillText("BUY", x, baseY + 3);
            } else {
                const tipY = highY - offset, baseY = tipY - arrowSize;
                ctx.beginPath(); ctx.moveTo(x, tipY); ctx.lineTo(x - 5, baseY + 3); ctx.lineTo(x - 2, baseY + 2); ctx.lineTo(x - 2, baseY - 2); ctx.lineTo(x + 2, baseY - 2); ctx.lineTo(x + 2, baseY + 2); ctx.lineTo(x + 5, baseY + 3); ctx.closePath(); ctx.fill();
                ctx.shadowBlur = 0; ctx.fillStyle = "#FFCC00"; ctx.font = "bold 5px monospace"; ctx.textAlign = "center"; ctx.textBaseline = "bottom"; ctx.fillText("SELL", x, baseY - 3);
            }
            ctx.restore();
        }

        function drawHorizontalLevel(y, color, label) {
            ctx.save();
            ctx.strokeStyle = color; ctx.lineWidth = 1; ctx.shadowColor = color; ctx.shadowBlur = 3;
            ctx.beginPath(); ctx.moveTo(2, y); ctx.lineTo(W - 35, y); ctx.stroke();
            text(label, W - 145, y + 7, 4.5, color, "left", "bold");
            ctx.restore();
        }

        function drawTrendLines(left, right, top, bottom) {
            ctx.save(); ctx.strokeStyle = "rgba(0,242,254,.25)"; ctx.lineWidth = .7;
            ctx.beginPath(); ctx.moveTo(left + W * .28, top); ctx.lineTo(right, top + bottom * .55); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(left + W * .36, top); ctx.lineTo(right, bottom - 70); ctx.stroke();
            ctx.beginPath(); ctx.moveTo(left + W * .62, bottom); ctx.lineTo(right, bottom * .40); ctx.stroke();
            ctx.restore();
        }

        function drawPriceScale(x, top, bottom, min, max) {
            for (let i = 0; i < 11; i++) {
                const ratio = i / 10, y = top + (bottom - top) * ratio;
                const price = max - (max - min) * ratio;
                text(priceFormat(price), x + 3, y, 4.5, "#00F2FE", "left", "normal");
            }
        }

        function drawTimeScale(left, width, bottom, spacing, data) {
            if (!data.length) return;
            const step = Math.max(1, Math.floor(data.length / 10));
            for (let i = 0; i < data.length; i += step) {
                const c = data[i], x = left + i * spacing + spacing / 2;
                text(timeFormat(c.time), x, bottom + 16, 4, "#7A889B", "center", "normal");
            }
        }

        function drawDashboard() {
            const x = 10, y = 10, w = 126, h = 122;
            panel(x, y, w, h, "rgba(0,242,254,.4)");
            const headerH = 15;
            const headGrad = ctx.createLinearGradient(x + 4, y + 4, x + w - 4, y + 4);
            headGrad.addColorStop(0, "#0c2545"); headGrad.addColorStop(1, "#134074");
            ctx.fillStyle = headGrad; roundRect(x + 4, y + 4, w - 8, headerH, 2); ctx.fill();
            const dashName = document.getElementById('dashboardNameInput').value || "RAVITH PRO";
            text("◈ " + dashName.toUpperCase(), x + 7, y + 4 + headerH / 2, 5.5, "#00F2FE", "left", "bold");
            text("AI-V8", x + w - 7, y + 4 + headerH / 2, 4.5, "#FFCC00", "right", "bold");
            const wins = engine.stats.wins, losses = engine.stats.losses;
            const total = wins + losses, rate = total ? Math.round(wins / total * 100) : 0;
            const statY = y + 30;
            text(String(wins), x + 7, statY, 9.5, "#00FF66", "left", "bold");
            text(String(losses), x + 56, statY, 9.5, "#FF3366", "left", "bold");
            text(rate + "%", x + 98, statY, 9.5, "#F4F7FF", "left", "bold");
            const labelY = statY + 8;
            text("✓ WIN", x + 7, labelY, 3.8, "#33FF99", "left", "bold");
            text("× LOSS", x + 56, labelY, 3.8, "#FF6688", "left", "bold");
            text("GRADE", x + 98, labelY, 3.8, "#7A889B", "left", "bold");
            const progY = labelY + 6;
            ctx.fillStyle = "#141923"; roundRect(x + 7, progY, w - 14, 3.5, 1.5); ctx.fill();
            const ratePct = total ? clamp(rate / 100, 0, 1) : 0;
            const barGrad = ctx.createLinearGradient(x + 7, 0, x + 7 + (w - 14), 0);
            barGrad.addColorStop(0, "#00FF66"); barGrad.addColorStop(1, "#00F2FE");
            ctx.fillStyle = barGrad; roundRect(x + 7, progY, (w - 14) * ratePct, 3.5, 1.5); ctx.fill();
            const row1Y = progY + 10;
            text("▸ SIGNALS", x + 7, row1Y, 4.5, "#7A889B", "left", "normal");
            text(String(total), x + w - 7, row1Y, 5.5, "#F4F7FF", "right", "bold");
            const row2Y = row1Y + 8;
            text("▸ STREAK", x + 7, row2Y, 4.5, "#7A889B", "left", "normal");
            text(String(engine.stats.streakW) + "W", x + w - 21, row2Y, 5.5, "#00FF66", "right", "bold");
            text(String(engine.stats.streakL) + "L", x + w - 7, row2Y, 5.5, "#FF3366", "right", "bold");
            const row3Y = row2Y + 8;
            text("▸ TREND", x + 7, row3Y, 4.5, "#7A889B", "left", "normal");
            const trend = candles.length >= 5 ? candles[candles.length - 1].close > candles[candles.length - 5].close ? "BULLISH" : "BEARISH" : "WAIT";
            text(trend, x + w - 7, row3Y, 5.5, trend === "BULLISH" ? "#00FF66" : trend === "BEARISH" ? "#FF3366" : "#FFCC00", "right", "bold");
            const buttons = [["M1", "#00FF66"],["M5", "#4FACFE"],["M15", "#4FACFE"],["M30", "#4FACFE"],["H1", "#4FACFE"],["D1", "#4FACFE"]];
            const btnY = row3Y + 8, btnW = 15, btnH = 10;
            let bx = x + 7;
            const btnSpacing = (w - 14 - btnW * buttons.length) / (buttons.length - 1);
            for (const b of buttons) {
                ctx.fillStyle = b[0] === "M1" ? "rgba(0,255,102,.15)" : "#0c1628";
                ctx.strokeStyle = b[0] === "M1" ? "#00FF66" : "#1a3a6c"; ctx.lineWidth = 0.8;
                roundRect(bx, btnY, btnW, btnH, 2); ctx.fill(); ctx.stroke();
                text(b[0], bx + btnW / 2, btnY + btnH / 2, 4, b[1], "center", "bold");
                bx += btnW + btnSpacing;
            }
            const recent20 = candles.slice(-20);
            const bulls = recent20.filter(c => c.close >= c.open).length;
            const buyPct = recent20.length ? Math.round(bulls / recent20.length * 100) : 50;
            const sellPct = 100 - buyPct;
            const bsY = btnY + 14;
            text("BUY " + buyPct + "%", x + 7, bsY, 4.5, "#00FF66", "left", "bold");
            text("SELL " + sellPct + "%", x + w - 7, bsY, 4.5, "#FF3366", "right", "bold");
            const barY = bsY + 4;
            ctx.fillStyle = "#141923"; roundRect(x + 7, barY, w - 14, 3, 1); ctx.fill();
            ctx.fillStyle = "#00FF66"; roundRect(x + 7, barY, (w - 14) * (buyPct / 100), 3, 1); ctx.fill();
            const telY = barY + 9;
            text("⚡ LIVE SYNC", x + 7, telY, 4.5, "#00F2FE", "left", "bold");
            const clock = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
            text(clock, x + w - 7, telY, 5.5, "#FFCC00", "right", "bold");
        }

        function drawExpiryPanel() {
            const w = 105, h = 42, x = W - w - 10, y = 10;
            panel(x, y, w, h, "rgba(79,172,254,.3)");
            text("⚡ EXPIRY ENGINE", x + w / 2, y + 7, 4.2, "#4FACFE", "center", "bold");
            const items = [["M1", "#00F2FE"],["M2", "#00F2FE"],["M3", "#FFCC00"],["M5", "#B19CD9"]];
            const btnW = 19, btnH = 11, btnY = y + 13;
            let bx = x + 7;
            const btnSpacing = (w - 14 - btnW * items.length) / (items.length - 1);
            for (let i = 0; i < items.length; i++) {
                const active = i === 0;
                ctx.fillStyle = active ? "#00F2FE" : "#0c1628";
                ctx.strokeStyle = active ? "#33FF99" : "#1a3a6c"; ctx.lineWidth = 0.8;
                roundRect(bx, btnY, btnW, btnH, 2); ctx.fill(); ctx.stroke();
                text(items[i][0], bx + btnW / 2, btnY + btnH / 2, 4, active ? "#050508" : items[i][1], "center", "bold");
                bx += btnW + btnSpacing;
            }
            const futY = btnY + btnH + 4, futH = 11;
            const futGrad = ctx.createLinearGradient(x + 7, futY, x + 7 + (w - 14), futY);
            futGrad.addColorStop(0, "#1f1700"); futGrad.addColorStop(1, "#332600");
            ctx.fillStyle = futGrad; ctx.strokeStyle = "#FFCC00"; ctx.lineWidth = 0.8;
            roundRect(x + 7, futY, w - 14, futH, 2); ctx.fill(); ctx.stroke();
            text("⭐ QUANTUM SIGNAL", x + w / 2, futY + futH / 2, 4, "#FFCC00", "center", "bold");
        }

        function drawBottomBar() {
            const h = 14, y = H - h - 5;
            const items = [["CHART PRO", "70"],["×", "14"],["BUY", "32"],["SELL", "32"],["EXP 01:00", "42"],["➜ SYNC STREAM", "72"],[currentPair.toUpperCase().substring(0, 10), "53"],["▣ GUIDE", "45"],["➤ MODE : PRO", "60"]];
            let cursor = 10;
            for (let i = 0; i < items.length; i++) {
                const width = Number(items[i][1]);
                ctx.fillStyle = "rgba(12,22,40,0.9)"; ctx.strokeStyle = "rgba(0,242,254,0.3)"; ctx.lineWidth = 0.8;
                roundRect(cursor, y, width, h, 2); ctx.fill(); ctx.stroke();
                let color = "#F4F7FF";
                if (items[i][0].includes("BUY")) color = "#00FF66";
                if (items[i][0].includes("SELL")) color = "#FF3366";
                if (items[i][0].includes("EXP")) color = "#FFCC00";
                if (items[i][0].includes("SYNC")) color = "#00F2FE";
                text(items[i][0], cursor + width / 2, y + h / 2, 4, color, "center", "bold");
                cursor += width + 3;
            }
        }

        function drawWatermark() {
            const cx = W * .48, cy = H * .43;
            const wmText = document.getElementById('watermarkInput').value || "𝐑𝐀𝐕𝐈𝐓𝐇 𝐒𝐒";
            ctx.save();
            ctx.font = "bold 36px monospace"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
            for (let i = 5; i >= 1; i--) { ctx.fillStyle = `rgba(0,242,254,${0.04 + i * 0.015})`;
                ctx.fillText(wmText, cx + i * 0.8, cy + i * 0.8); }
            ctx.fillStyle = "rgba(0,242,254,0.12)"; ctx.fillText(wmText, cx, cy);
            ctx.shadowColor = "#00F2FE"; ctx.shadowBlur = 20;
            ctx.fillStyle = "rgba(0,242,254,0.04)"; ctx.fillText(wmText, cx, cy);
            ctx.restore();
        }

        function getChartScreenshot() {
            return new Promise((resolve) => {
                requestDraw();
                requestAnimationFrame(function () {
                    requestAnimationFrame(function () {
                        const scale = 4;
                        const hdCanvas = document.createElement('canvas');
                        hdCanvas.width = Math.round(W * scale);
                        hdCanvas.height = Math.round(H * scale);
                        const hdCtx = hdCanvas.getContext('2d', { alpha: false, willReadFrequently: false });
                        hdCtx.imageSmoothingEnabled = false;
                        hdCtx.fillStyle = (CHART_THEMES[getChartStyle()] || CHART_THEMES[1]).bg;
                        hdCtx.fillRect(0, 0, hdCanvas.width, hdCanvas.height);
                        hdCtx.imageSmoothingEnabled = true;
                        hdCtx.imageSmoothingQuality = 'high';
                        hdCtx.drawImage(canvas, 0, 0, canvas.width, canvas.height, 0, 0, hdCanvas.width, hdCanvas.height);
                        if (hdCanvas.toBlob) hdCanvas.toBlob(function (blob) { resolve(blob); }, 'image/png');
                        else { const dataUrl = hdCanvas.toDataURL('image/png');
                            fetch(dataUrl).then(function (r) { return r.blob(); }).then(resolve).catch(function () { resolve(null); }); }
                    });
                });
            });
        }

        function getTelegramConfig() {
            const token = (document.getElementById('botTokenInput').value || '').trim();
            const chatId = (document.getElementById('chatIdInput').value || '').trim();
            const autoSend = document.getElementById('autoTelegramToggle').classList.contains('active');
            return { token, chatId, autoSend };
        }

        function setTgStatus(msg, level) {
            const el = document.getElementById('tgStatus');
            if (!el) return;
            el.className = 'tg-status ' + (level || '');
            el.innerText = msg;
            if (msg) setTimeout(() => { if (el.innerText === msg) el.innerText = ''; }, 8000);
        }

        async function sendPhotoToTelegramWithRetry(blob, caption, maxAttempts = 3) {
            const { token, chatId } = getTelegramConfig();
            if (!token || !chatId) { setTgStatus('⚠ Bot Token & Chat ID required', 'error'); return false; }
            let attempt = 0, lastError = null;
            while (attempt < maxAttempts) {
                attempt++;
                setTgStatus(`📡 Sending... (${attempt}/${maxAttempts})`, 'sending');
                try {
                    const formData = new FormData();
                    formData.append('chat_id', chatId);
                    formData.append('photo', blob, 'chart.png');
                    formData.append('caption', caption);
                    formData.append('parse_mode', 'HTML');
                    const url = `https://api.telegram.org/bot${token}/sendPhoto`;
                    const resp = await fetch(url, { method: 'POST', body: formData });
                    const json = await resp.json();
                    if (json.ok) { setTgStatus('✅ Sent to Telegram!', 'success'); return true; }
                    else { lastError = json.description || 'Send failed';
                        setTgStatus(`❌ Attempt ${attempt}: ${lastError}`, 'error');
                        if (attempt < maxAttempts) await new Promise(r => setTimeout(r, Math.min(1500 * Math.pow(2, attempt - 1), 8000))); }
                } catch (err) {
                    lastError = err.message || 'Network error';
                    setTgStatus(`❌ Attempt ${attempt}: ${lastError}`, 'error');
                    if (attempt < maxAttempts) await new Promise(r => setTimeout(r, Math.min(1500 * Math.pow(2, attempt - 1), 8000)));
                }
            }
            setTgStatus(`❌ Failed after ${maxAttempts} attempts: ${lastError}`, 'error');
            return false;
        }

        async function sendTelegramWithRetry(blob, caption) { return await sendPhotoToTelegramWithRetry(blob, caption, 3); }

        function toMonospace(str) { return [...str].map(ch => { const code = ch.codePointAt(0);
            if (code >= 65 && code <= 90) return String.fromCodePoint(0x1D670 + (code - 65));
            if (code >= 97 && code <= 122) return String.fromCodePoint(0x1D68A + (code - 97));
            if (code >= 48 && code <= 57) return String.fromCodePoint(0x1D7F6 + (code - 48));
            return ch; }).join(''); }
        function toBold(str) { return [...str].map(ch => { const code = ch.codePointAt(0);
            if (code >= 65 && code <= 90) return String.fromCodePoint(0x1D5D4 + (code - 65));
            if (code >= 97 && code <= 122) return String.fromCodePoint(0x1D5EE + (code - 97));
            if (code >= 48 && code <= 57) return String.fromCodePoint(0x1D7EC + (code - 48));
            return ch; }).join(''); }
        function fmtPairMono(pair) { return [...String(pair)].map(ch => { if (ch === '-') return '⁻'; return toMonospace(ch); }).join(''); }
        function fmtDateMono(dateStr) { return [...String(dateStr)].map(ch => { if (ch === '.') return '．'; return toMonospace(ch); }).join(''); }

        function getSignalHeader() {
            const raw = (document.getElementById('signalNameInput').value || '').trim() || 'RAVITH AI PRO';
            const hasFancy = [...raw].some(ch => ch.codePointAt(0) > 0x2000);
            if (hasFancy) return raw;
            return '👑 ' + toBold(raw.toUpperCase());
        }

        function buildTelegramSignal(pair, timeHHMM, direction, price, payout, mtgTag) {
            const mPair = fmtPairMono(pair);
            const mTime = toMonospace(timeHHMM);
            const mDir = toMonospace(direction);
            const mPrice = toMonospace(String(price));
            const mPayout = toMonospace(String(payout));
            const mHeader = getSignalHeader();
            const mtgLine = mtgTag ? `\n⚙️ »» ${toMonospace(mtgTag)}` : '';
            const dirEmoji = (direction === 'BUY' || direction === 'CALL') ? '🟢' : '🔴';
            return (`╔═★═════════════════★═╗\n   ${mHeader}\n╚═★═════════════════★═╝\n\n╭━━━━━━━【⛨】━━━━━━━╮\n💎 »» ${mPair}\n⏰ »» ${mTime}\n${dirEmoji} »» ${mDir}\n💰 »» ${mPrice}\n💸 »» ${mPayout}٪${mtgLine}\n╰━━━━━━━━━━━━━━━━━━╯\n\n🔗 ${toMonospace('CREATE ACCOUNT')}\n🚀 ${toMonospace('BOT OWNER')}\n\n▰▰▰▰▰【 ${mHeader} 】▰▰▰▰▰`);
        }

        function buildTelegramResult(pair, timeHHMM, outcome, wins, losses, telegram) {
            const total = wins + losses;
            const rate = total ? Math.round(wins / total * 100) : 0;
            const mPair = fmtPairMono(pair);
            const mTime = toMonospace(timeHHMM);
            const mWins = toMonospace(String(wins));
            const mLosses = toMonospace(String(losses));
            const mRate = toMonospace(String(rate));
            const mHeader = getSignalHeader();
            const mTelegram = toMonospace(telegram || '@Mahabub_iX');
            const outcomeBlock = outcome === 'WIN' ? `        ✅✅✅ ${toMonospace('SURE SHOT')} ✅✅✅` : `        ❌❌❌ ${toMonospace('LOSS')} ❌❌❌`;
            return (`▰▱▰▱ ${toMonospace('R E S U L T')} ▰▱▰▱\n\n╭━━━━━━━【⛨】━━━━━━━╮\n🎃 ${mPair}  ┃  🕐 ${mTime}\n╰━━━━━━━━━━━━━━━━━━╯\n\n${outcomeBlock}\n\n╭━━━━━━━【⛨】━━━━━━━╮\n🔥 ${toMonospace('WIN')} ${mWins} │ ☃️ ${toMonospace('LOSS')} ${mLosses} │ (${mRate}٪)\n⚖️ ${toMonospace('PAIR')} ${mWins}×${mLosses} (${mRate}٪)\n╰━━━━━━━━━━━━━━━━━━╯\n\n🌐 ${toMonospace('TELEGRAM')} ${mTelegram}\n\n╔═★═════════════════★═╗\n      ${mHeader}\n╚═★═════════════════★═╝`);
        }

        function buildSignalCardText(pair, timeHHMM, direction, price, payout, mtgTag) {
            const dirEmoji = direction === "BUY" ? "🟢" : "🔴";
            const mtgLine = mtgTag ? `\n⚙️ »» ${toMonospace(mtgTag)}` : "";
            const header = getSignalHeader();
            const mPair = fmtPairMono(pair);
            return (`╔═★═════════════════★═╗\n   ${header}\n╚═★═════════════════★═╝\n\n╭━━━━━━━【⛨】━━━━━━━╮\n💎 »» ${mPair}\n⏰ »» ${toMonospace(timeHHMM)}\n${dirEmoji} »» ${toMonospace(direction)}\n💰 »» ${toMonospace(String(price))}\n💸 »» ${toMonospace(String(payout))}٪${mtgLine}\n╰━━━━━━━━━━━━━━━━━━╯\n\n🔗 ${toMonospace('CREATE ACCOUNT')}\n🚀 ${toMonospace('BOT OWNER')}\n\n▰▰▰▰▰【 ${header} 】▰▰▰▰▰`);
        }

        function buildResultCardText(pair, timeHHMM, outcome, wins, losses, telegram) {
            const total = wins + losses;
            const rate = total ? Math.round(wins / total * 100) : 0;
            const header = getSignalHeader();
            const mPair = fmtPairMono(pair);
            const mWins = toMonospace(String(wins));
            const mLosses = toMonospace(String(losses));
            const mRate = toMonospace(String(rate));
            const mTelegram = toMonospace(telegram || '@Mahabub_iX');
            const outcomeBlock = outcome === 'WIN' ? `        ✅✅✅ ${toMonospace('SURE SHOT')} ✅✅✅` : `        ❌❌❌ ${toMonospace('LOSS')} ❌❌❌`;
            return (`▰▱▰▱ ${toMonospace('R E S U L T')} ▰▱▰▱\n\n╭━━━━━━━【⛨】━━━━━━━╮\n🎃 ${mPair}  ┃  🕐 ${toMonospace(timeHHMM)}\n╰━━━━━━━━━━━━━━━━━━╯\n\n${outcomeBlock}\n\n╭━━━━━━━【⛨】━━━━━━━╮\n🔥 ${toMonospace('WIN')} ${mWins} │ ☃️ ${toMonospace('LOSS')} ${mLosses} │ (${mRate}٪)\n⚖️ ${toMonospace('PAIR')} ${mWins}×${mLosses} (${mRate}٪)\n╰━━━━━━━━━━━━━━━━━━╯\n\n🌐 ${toMonospace('TELEGRAM')} ${mTelegram}\n\n╔═★═════════════════★═╗\n      ${header}\n╚═★═════════════════★═╝`);
        }

        function buildPartialResultMessage() {
            if (tradeHistory.length === 0) return "📊 No trades recorded yet.";
            const now = new Date();
            const day = String(now.getDate()).padStart(2, '0');
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const year = now.getFullYear();
            const dateStr = fmtDateMono(`${day}.${month}.${year}`);
            const otcTrades = tradeHistory.filter(t => (t.pair || '').toUpperCase().includes('OTC'));
            const realTrades = tradeHistory.filter(t => !(t.pair || '').toUpperCase().includes('OTC'));
            let lines = [];
            lines.push(`========= ${toMonospace('PARTIAL RESULTS')} ==========`);
            lines.push(`━━━━━━━━━・━━━━━━━━━`);
            lines.push(`                  📆 — ${dateStr}`);
            lines.push(`━━━━━━━━━・━━━━━━━━━`);
            lines.push(`                  📈 ${toMonospace('REAL MARKET')}`);
            lines.push(`━━━━━━━━━・━━━━━━━━━`);
            let wins = 0, losses = 0, total = 0;
            const pushTrade = (trade) => {
                const timeStr = trade.time && trade.time.length >= 16 ? trade.time.substring(11, 16) : '--:--';
                const pairDisplay = fmtPairMono(trade.pair || '??');
                const dirDisplay = toMonospace(trade.direction === 'BUY' ? 'BUY' : 'PUT');
                let outcomeSymbol = '';
                if (trade.outcome === 'win') { outcomeSymbol = '✅'; wins++; }
                else if (trade.outcome === 'mtg-win') { outcomeSymbol = '✅¹'; wins++; }
                else if (trade.outcome === 'loss') { outcomeSymbol = '✖️'; losses++; }
                total++;
                lines.push(`⧉ ${toMonospace(timeStr)} - ${pairDisplay} - ${dirDisplay} ${outcomeSymbol}`);
            };
            if (realTrades.length === 0) lines.push(`——— ${toMonospace('NO REAL SIGNALS PLACED')} ———`);
            else realTrades.forEach(pushTrade);
            lines.push(`━━━━━━━━━・━━━━━━━━━`);
            lines.push(`                  📉 ${toMonospace('OTC MARKET')}`);
            lines.push(`━━━━━━━━━・━━━━━━━━━`);
            if (otcTrades.length === 0) lines.push(`——— ${toMonospace('NO OTC SIGNALS PLACED')} ———`);
            else otcTrades.forEach(pushTrade);
            const rate = total ? Math.round((wins / total) * 100) : 0;
            lines.push(`━━━━━━━━━・━━━━━━━━━`);
            lines.push(` 🧮 ${toMonospace('PLACER')} : ${toMonospace(String(total))} 𝘅 𝟸 ◈ (${toMonospace(String(rate))}٪)`);
            lines.push(`━━━━━━━━━・━━━━━━━━━`);
            lines.push(` 🚀 ${toMonospace('WIN')} : ${toMonospace(String(wins))} ┃ ${toMonospace('LOSS')} : ${toMonospace(String(losses))} ┃ ◈ (${toMonospace(String(rate))}٪)`);
            lines.push(`━━━━━━━━━・━━━━━━━━━`);
            return lines.join('\n');
        }

        function sendPartialResult() {
            const msg = buildPartialResultMessage();
            if (!msg || msg === "📊 No trades recorded yet.") { setTgStatus('⚠ No trades to report', 'error'); return; }
            const tgConfig = getTelegramConfig();
            if (tgConfig.autoSend && tgConfig.token && tgConfig.chatId) {
                setTgStatus('📤 Sending partial results...', 'sending');
                const url = `https://api.telegram.org/bot${tgConfig.token}/sendMessage`;
                fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ chat_id: tgConfig.chatId, text: msg, parse_mode: 'HTML' }) })
                    .then(res => res.json()).then(json => {
                        if (json.ok) setTgStatus('✅ Partial results sent!', 'success');
                        else setTgStatus('❌ Telegram error: ' + (json.description || 'unknown'), 'error');
                    }).catch(err => setTgStatus('❌ Failed to send: ' + err.message, 'error'));
            } else {
                const card = document.getElementById('resultCard');
                card.innerText = msg; card.className = 'result-card show';
                card.style.borderColor = 'rgba(139,92,246,0.5)';
                card.style.background = 'rgba(139,92,246,0.08)';
            }
        }

        const engine = { state: 'idle', currentSignal: null, initialDirection: null, initialTargetTime: null,
            signalPair: null, signalPairApi: null, mtgLevel: 0, mtgMax: 0, stats: { wins: 0, losses: 0, streakW: 0,
                streakL: 0 }, mtgWinCount: 0, mtgLossCount: 0 };
        let tradeHistory = [];
        let autoModeActive = false;
        let autoModeTimer = null;

        function getMtgMax() {
            const v = document.getElementById('val-martingale').innerText.trim();
            if (v === 'MTG1') return 1;
            if (v === 'MTG2') return 2;
            if (v === 'MTG3') return 3;
            return 0;
        }
        function getTelegram() { const input = document.getElementById('telegramInput'); return input ? input.value.trim() || '@Mahabub_iX' : '@Mahabub_iX'; }
        function getSelectedStrategy() { return document.getElementById('val-strategy').innerText.trim(); }
        function getSignalMode() { return document.getElementById('val-signalMode').innerText.trim(); }

        function setActionBtn(state) {
            const btn = document.getElementById('actionBtn');
            btn.classList.remove('waiting', 'mtg', 'analyzing', 'scanning', 'auto-active');
            switch (state) {
                case 'analyzing': btn.innerText = 'ANALYZING...'; btn.classList.add('analyzing'); break;
                case 'waiting': btn.innerText = 'WAITING RESULT'; btn.classList.add('waiting'); break;
                case 'mtg': btn.innerText = 'MTG WAITING'; btn.classList.add('mtg'); break;
                case 'scanning': btn.innerText = 'STOP AUTO'; btn.classList.add('auto-active'); break;
                default: btn.innerText = getSignalMode() === 'Auto' ? 'START AUTO' : 'GENERATE SIGNAL';
            }
        }

        function updateStatsUI() {
            document.getElementById('statWin').innerText = engine.stats.wins;
            document.getElementById('statLoss').innerText = engine.stats.losses;
            const total = engine.stats.wins + engine.stats.losses;
            const rate = total ? Math.round(engine.stats.wins / total * 100) + '%' : '--%';
            document.getElementById('statRate').innerText = rate;
            const prof = document.getElementById('profSignals'); if (prof) prof.innerText = total;
            const profRate = document.getElementById('profRate'); if (profRate) profRate.innerText = rate;
            saveSettings();
        }

        function showSignalCard(pair, targetTime, direction, price, payout, mtgTag) {
            const displayTime = engine.initialTargetTime || targetTime;
            const hhmm = displayTime.length >= 16 ? displayTime.substring(11, 16) : displayTime;
            const cardEl = document.getElementById('signalCard');
            cardEl.innerText = buildSignalCardText(pair, hhmm, direction, price, payout, mtgTag);
            cardEl.classList.add('show');
            document.getElementById('resultCard').classList.remove('show');
        }

        function showResultCard(pair, targetTime, outcome, wins, losses) {
            const displayTime = engine.initialTargetTime || targetTime;
            const hhmm = displayTime.length >= 16 ? displayTime.substring(11, 16) : displayTime;
            const cardEl = document.getElementById('resultCard');
            cardEl.innerText = buildResultCardText(pair, hhmm, outcome, wins, losses, getTelegram());
            cardEl.className = 'result-card show ' + (outcome === 'WIN' ? 'win' : 'loss');
            document.getElementById('signalCard').classList.remove('show');
        }

        function hideSignalCard() {
            document.getElementById('signalCard').classList.remove('show');
            document.getElementById('resultCard').classList.remove('show');
        }

        function setAutoStatusBar(msg, show, type = '') {
            const bar = document.getElementById('autoStatusBar');
            const txt = document.getElementById('autoStatusText');
            if (show) { txt.innerText = msg; txt.className = type || 'scanning-text'; bar.classList.add('show'); }
            else { bar.classList.remove('show'); }
        }

        function analyzeAdvancedAI(candlesArr) {
            if (!candlesArr || candlesArr.length < 20) return null;
            const currentIndex = candlesArr.length - 1;
            const data = candlesArr;

            function calcRSI(closes, period = 14) {
                if (closes.length < period + 1) return null;
                const changes = [];
                for (let i = 1; i < closes.length; i++) changes.push(closes[i] - closes[i - 1]);
                const gains = changes.map(c => c > 0 ? c : 0);
                const losses = changes.map(c => c < 0 ? Math.abs(c) : 0);
                let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
                let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
                if (avgLoss === 0) return 100;
                let rs = avgGain / avgLoss;
                let rsi = 100 - (100 / (1 + rs));
                for (let i = period; i < changes.length; i++) {
                    avgGain = (avgGain * (period - 1) + gains[i]) / period;
                    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
                    if (avgLoss === 0) return 100;
                    rs = avgGain / avgLoss;
                    rsi = 100 - (100 / (1 + rs));
                }
                return rsi;
            }

            function checkDivergence(data, idx, lookback = 5) {
                if (idx < lookback + 14) return "NO_DIVERGENCE";
                const closes = data.slice(idx - lookback, idx + 1).map(c => c.close);
                const rsiValues = [];
                for (let i = idx - lookback; i <= idx; i++) {
                    const slice = data.slice(0, i + 1);
                    const r = calcRSI(slice.map(c => c.close), 14);
                    if (r !== null) rsiValues.push(r);
                    else return "NO_DIVERGENCE";
                }
                if (rsiValues.length < lookback + 1) return "NO_DIVERGENCE";
                const recentHigh = Math.max(...closes);
                const recentLow = Math.min(...closes);
                let highIdx = closes.indexOf(recentHigh);
                let lowIdx = closes.indexOf(recentLow);
                if (highIdx === -1 || lowIdx === -1) return "NO_DIVERGENCE";
                if (closes[closes.length - 1] > recentHigh * 1.0001) { if (rsiValues[rsiValues.length - 1] < rsiValues[highIdx]) return "BEARISH_DIVERGENCE"; }
                if (closes[closes.length - 1] < recentLow * 0.9999) { if (rsiValues[rsiValues.length - 1] > rsiValues[lowIdx]) return "BULLISH_DIVERGENCE"; }
                return "NO_DIVERGENCE";
            }

            function calcTrend(data, idx) {
                if (idx < 5) return { strength: 0, direction: "SIDEWAYS" };
                const changes = [];
                for (let i = idx - 4; i <= idx; i++) { if (i > 0) { const prev = data[i - 1].close; const curr = data[i].close; if (prev > 0) changes.push((curr - prev) / prev * 100); } }
                if (!changes.length) return { strength: 0, direction: "SIDEWAYS" };
                const avg = changes.reduce((a, b) => a + b, 0) / changes.length;
                const variance = changes.reduce((a, b) => a + (b - avg) ** 2, 0) / changes.length;
                const vol = Math.sqrt(variance) || 0.001;
                const strength = Math.min(Math.abs(avg) / (vol + 0.001) * 10, 100);
                let dir = "SIDEWAYS";
                if (avg > 0.01) dir = "UPTREND"; else if (avg < -0.01) dir = "DOWNTREND";
                return { strength, direction: dir };
            }

            function calcReversalProb(data, idx) {
                if (idx < 3) return { prob: 0, type: "NO_REVERSAL" };
                const c = data[idx]; const p1 = data[idx - 1]; const p2 = data[idx - 2]; const p3 = data[idx - 3];
                let factors = 0, maxFactors = 8;
                const p1Body = Math.abs(p1.close - p1.open); const cBody = Math.abs(c.close - c.open);
                if (p1Body > 0 && cBody > p1Body * 0.7) { if ((p1.close > p1.open && c.close < c.open) || (p1.close < p1.open && c.close > c.open)) factors++; }
                const totalRange = c.high - c.low;
                if (totalRange > 0) {
                    const upperWick = c.high - Math.max(c.open, c.close);
                    const lowerWick = Math.min(c.open, c.close) - c.low;
                    if ((c.close > c.open && lowerWick > cBody * 2) || (c.close < c.open && upperWick > cBody * 2)) factors++;
                    else if (upperWick > totalRange * 0.3 || lowerWick > totalRange * 0.3) factors += 0.5;
                }
                if (c.volume && p1.volume && c.volume > p1.volume * 1.5) factors++;
                const recentHigh = Math.max(p1.high, p2.high, p3.high);
                const recentLow = Math.min(p1.low, p2.low, p3.low);
                if (c.close > recentHigh || c.close < recentLow) factors++;
                let consecutive = 0;
                for (let i = 1; i <= 3; i++) { if (idx - i >= 0) { const change = (data[idx - i + 1].close - data[idx - i].close) / data[idx - i].close * 100; if (Math.abs(change) > 0.05) consecutive++; } }
                if (consecutive >= 2) factors++;
                const rsi = calcRSI(data.slice(0, idx + 1).map(c => c.close), 14);
                if (rsi !== null) { if (rsi >= 70 && c.close < p1.close) factors++; if (rsi <= 30 && c.close > p1.close) factors++; }
                const recent = data.slice(Math.max(0, idx - 15), idx);
                const sup = Math.min(...recent.map(c => c.low));
                const res = Math.max(...recent.map(c => c.high));
                if (Math.abs(c.low - sup) / sup < 0.005 && c.close > c.open) factors++;
                if (Math.abs(c.high - res) / res < 0.005 && c.close < c.open) factors++;
                const prob = Math.min((factors / maxFactors) * 100, 100);
                let type = "NO_REVERSAL";
                if (prob >= 70) type = "HIGH_REVERSAL";
                else if (prob >= 50) type = "MEDIUM_REVERSAL";
                return { prob, type };
            }

            const last = data[currentIndex];
            const trend = calcTrend(data, currentIndex);
            const rev = calcReversalProb(data, currentIndex);
            const divergence = checkDivergence(data, currentIndex);
            const rsi = calcRSI(data.slice(0, currentIndex + 1).map(c => c.close), 14);

            if (trend.strength > 60) {
                const recent = data.slice(Math.max(0, currentIndex - 15), currentIndex);
                const sup = Math.min(...recent.map(c => c.low));
                const res = Math.max(...recent.map(c => c.high));
                if (trend.direction === "UPTREND" && Math.abs(last.close - sup) / sup < 0.005) return { direction: "BUY", confidence: 90, strategy: "PULLBACK", type: "BUY_PULLBACK_SUPPORT" };
                if (trend.direction === "DOWNTREND" && Math.abs(last.close - res) / res < 0.005) return { direction: "SELL", confidence: 90, strategy: "PULLBACK", type: "SELL_PULLBACK_RESISTANCE" };
            }
            if (divergence !== "NO_DIVERGENCE") {
                if ((divergence === "BEARISH_DIVERGENCE" && trend.direction === "UPTREND") || (divergence === "BULLISH_DIVERGENCE" && trend.direction === "DOWNTREND")) {
                    const dir = divergence === "BEARISH_DIVERGENCE" ? "SELL" : "BUY";
                    return { direction: dir, confidence: 85, strategy: "REVERSE", type: divergence };
                }
            }
            if (rev.prob >= 70 && trend.strength > 50) {
                const dir = rev.type === "HIGH_REVERSAL" ? (trend.direction === "UPTREND" ? "SELL" : "BUY") : (trend.direction === "UPTREND" ? "SELL" : "BUY");
                return { direction: dir, confidence: rev.prob, strategy: "REVERSE", type: rev.type };
            }
            if (rsi !== null) {
                if (rsi >= 70 && trend.direction === "UPTREND") return { direction: "SELL", confidence: Math.min(rev.prob * 0.5 + 60, 100), strategy: "REVERSE", type: "RSI_OVEREXTENDED" };
                if (rsi <= 30 && trend.direction === "DOWNTREND") return { direction: "BUY", confidence: Math.min(rev.prob * 0.5 + 60, 100), strategy: "REVERSE", type: "RSI_OVEREXTENDED" };
            }
            const recent2 = data.slice(Math.max(0, currentIndex - 15), currentIndex);
            const sup2 = Math.min(...recent2.map(c => c.low));
            const res2 = Math.max(...recent2.map(c => c.high));
            if (trend.direction === "UPTREND" && Math.abs(last.close - res2) / res2 < 0.005) return { direction: "SELL", confidence: 75, strategy: "REVERSE", type: "SNR_REJECTION" };
            if (trend.direction === "DOWNTREND" && Math.abs(last.close - sup2) / sup2 < 0.005) return { direction: "BUY", confidence: 75, strategy: "REVERSE", type: "SNR_REJECTION" };
            if (rev.prob <= 30 && trend.strength > 40) {
                const dir = trend.direction === "UPTREND" ? "BUY" : (trend.direction === "DOWNTREND" ? "SELL" : "BUY");
                return { direction: dir, confidence: trend.strength, strategy: "TRENDY", type: "TREND_CONTINUATION" };
            }
            const fallbackDir = trend.direction === "UPTREND" ? "BUY" : (trend.direction === "DOWNTREND" ? "SELL" : "BUY");
            return { direction: fallbackDir, confidence: Math.max(trend.strength, 100 - rev.prob), strategy: "TRENDY", type: "MIXED_CONDITIONS" };
        }

        function analyzeSupportResistanceTouch(candlesArr) {
            if (!candlesArr || candlesArr.length < 15) return null;
            const lookback = 30;
            const recent = candlesArr.slice(-lookback);
            const last = candlesArr[candlesArr.length - 1];
            const swingHighs = []; const swingLows = [];
            for (let i = 2; i < recent.length - 2; i++) {
                if (recent[i].high > recent[i - 1].high && recent[i].high > recent[i - 2].high && recent[i].high > recent[i + 1].high && recent[i].high > recent[i + 2].high) swingHighs.push(recent[i].high);
                if (recent[i].low < recent[i - 1].low && recent[i].low < recent[i - 2].low && recent[i].low < recent[i + 1].low && recent[i].low < recent[i + 2].low) swingLows.push(recent[i].low);
            }
            if (!swingHighs.length || !swingLows.length) return null;
            const resistance = Math.max(...swingHighs);
            const support = Math.min(...swingLows);
            const range = resistance - support || 0.0001;
            const tolerance = range * 0.01;
            const touchesResistance = (last.high >= resistance - tolerance) && (last.low <= resistance + tolerance);
            const touchesSupport = (last.high >= support - tolerance) && (last.low <= support + tolerance);
            if (touchesResistance) return { direction: "SELL", confidence: 85, strategy: "SUPPORT_RESISTANCE_TOUCH", type: "RESISTANCE_TOUCH" };
            if (touchesSupport) return { direction: "BUY", confidence: 85, strategy: "SUPPORT_RESISTANCE_TOUCH", type: "SUPPORT_TOUCH" };
            return null;
        }

        function analyzeEMATrend(candlesArr) {
            if (!candlesArr || candlesArr.length < 25) return null;
            const ema9 = calculateEMA(candlesArr, 9);
            const ema20 = calculateEMA(candlesArr, 20);
            if (ema9.length < 2 || ema20.length < 2) return null;
            const lastIdx = candlesArr.length - 1;
            const prevIdx = lastIdx - 1;
            const lastClose = candlesArr[lastIdx].close;
            const prevClose = candlesArr[prevIdx].close;
            const lastEma9 = ema9[lastIdx]; const prevEma9 = ema9[prevIdx];
            const lastEma20 = ema20[lastIdx]; const prevEma20 = ema20[prevIdx];
            if (lastClose > lastEma9 && lastClose > lastEma20 && (prevClose <= prevEma9 || prevClose <= prevEma20)) return { direction: "BUY", confidence: 78, strategy: "EMA_TREND", type: "BULLISH_CROSS" };
            if (lastClose < lastEma9 && lastClose < lastEma20 && (prevClose >= prevEma9 || prevClose >= prevEma20)) return { direction: "SELL", confidence: 78, strategy: "EMA_TREND", type: "BEARISH_CROSS" };
            return null;
        }

        function analyzeRSIReversal(candlesArr) {
            if (!candlesArr || candlesArr.length < 20) return null;
            const last = candlesArr[candlesArr.length - 1];
            const closes = candlesArr.map(c => c.close);
            function calcRSI_simple(closes, period = 14) {
                if (closes.length < period + 1) return null;
                const changes = [];
                for (let i = 1; i < closes.length; i++) changes.push(closes[i] - closes[i - 1]);
                const gains = changes.map(c => c > 0 ? c : 0);
                const losses = changes.map(c => c < 0 ? Math.abs(c) : 0);
                let avgGain = gains.slice(0, period).reduce((a, b) => a + b, 0) / period;
                let avgLoss = losses.slice(0, period).reduce((a, b) => a + b, 0) / period;
                if (avgLoss === 0) return 100;
                let rs = avgGain / avgLoss;
                let rsi_val = 100 - (100 / (1 + rs));
                for (let i = period; i < changes.length; i++) {
                    avgGain = (avgGain * (period - 1) + gains[i]) / period;
                    avgLoss = (avgLoss * (period - 1) + losses[i]) / period;
                    if (avgLoss === 0) return 100;
                    rs = avgGain / avgLoss;
                    rsi_val = 100 - (100 / (1 + rs));
                }
                return rsi_val;
            }
            const rsi = calcRSI_simple(closes, 14);
            if (rsi === null) return null;
            const lookback = 30;
            const recent = candlesArr.slice(-lookback);
            const swingHighs = []; const swingLows = [];
            for (let i = 2; i < recent.length - 2; i++) {
                if (recent[i].high > recent[i - 1].high && recent[i].high > recent[i - 2].high && recent[i].high > recent[i + 1].high && recent[i].high > recent[i + 2].high) swingHighs.push(recent[i].high);
                if (recent[i].low < recent[i - 1].low && recent[i].low < recent[i - 2].low && recent[i].low < recent[i + 1].low && recent[i].low < recent[i + 2].low) swingLows.push(recent[i].low);
            }
            if (!swingHighs.length || !swingLows.length) return null;
            const resistance = Math.max(...swingHighs);
            const support = Math.min(...swingLows);
            const range = resistance - support || 0.0001;
            const tolerance = range * 0.01;
            const touchesResistance = (last.high >= resistance - tolerance) && (last.low <= resistance + tolerance);
            const touchesSupport = (last.high >= support - tolerance) && (last.low <= support + tolerance);
            if (rsi >= 70 && touchesResistance) return { direction: "SELL", confidence: 82, strategy: "RSI_REVERSAL", type: "RSI_OVERBOUGHT_RESISTANCE" };
            if (rsi <= 30 && touchesSupport) return { direction: "BUY", confidence: 82, strategy: "RSI_REVERSAL", type: "RSI_OVERSOLD_SUPPORT" };
            return null;
        }

        function analyzeBollinger(candlesArr) {
            if (!candlesArr || candlesArr.length < 22) return null;
            const period = 20, mult = 2;
            const closes = candlesArr.map(c => c.close);
            const slice = closes.slice(-period);
            const mean = slice.reduce((a,b)=>a+b,0) / period;
            const variance = slice.reduce((a,b)=>a+(b-mean)*(b-mean),0) / period;
            const std = Math.sqrt(variance) || 0.0001;
            const upper = mean + mult * std, lower = mean - mult * std;
            const last = candlesArr[candlesArr.length - 1];
            const prev = candlesArr[candlesArr.length - 2];
            if (prev.close >= lower && last.close < lower && last.close < last.open) return { direction: 'BUY', confidence: 80, strategy: 'BOLLINGER', type: 'LOWER_BAND_BOUNCE' };
            if (prev.close <= upper && last.close > upper && last.close > last.open) return { direction: 'SELL', confidence: 80, strategy: 'BOLLINGER', type: 'UPPER_BAND_REJECT' };
            return null;
        }

        function analyzeMACD(candlesArr) {
            if (!candlesArr || candlesArr.length < 35) return null;
            function emaArr(data, p) { const k = 2/(p+1); let e = data[0]; const out=[e]; for (let i=1;i<data.length;i++){ e = data[i]*k + e*(1-k); out.push(e); } return out; }
            const closes = candlesArr.map(c => c.close);
            const ema12 = emaArr(closes, 12), ema26 = emaArr(closes, 26);
            const macd = ema12.map((v,i)=>v - ema26[i]);
            const signal = emaArr(macd, 9);
            const i = macd.length - 1;
            if (i < 1) return null;
            if (macd[i-1] <= signal[i-1] && macd[i] > signal[i]) return { direction: 'BUY', confidence: 78, strategy: 'MACD', type: 'BULLISH_CROSS' };
            if (macd[i-1] >= signal[i-1] && macd[i] < signal[i]) return { direction: 'SELL', confidence: 78, strategy: 'MACD', type: 'BEARISH_CROSS' };
            return null;
        }

        function analyzeStochastic(candlesArr) {
            if (!candlesArr || candlesArr.length < 16) return null;
            const period = 14;
            const slice = candlesArr.slice(-period);
            const last = candlesArr[candlesArr.length - 1];
            const hi = Math.max(...slice.map(c=>c.high));
            const lo = Math.min(...slice.map(c=>c.low));
            const range = hi - lo || 0.0001;
            const k = ((last.close - lo) / range) * 100;
            if (k <= 20 && last.close > last.open) return { direction: 'BUY', confidence: 81, strategy: 'STOCHASTIC', type: 'OVERSOLD_REVERSAL' };
            if (k >= 80 && last.close < last.open) return { direction: 'SELL', confidence: 81, strategy: 'STOCHASTIC', type: 'OVERBOUGHT_REVERSAL' };
            return null;
        }

        function analyzeTrendPullback(candlesArr) {
            if (!candlesArr || candlesArr.length < 25) return null;
            const ema9 = calculateEMA(candlesArr, 9);
            const ema21 = calculateEMA(candlesArr, 21);
            const i = candlesArr.length - 1;
            const last = candlesArr[i];
            if (ema9[i] > ema21[i] && last.low <= ema21[i] && last.close > ema21[i] && last.close > last.open) return { direction: 'BUY', confidence: 84, strategy: 'TREND_PULLBACK', type: 'BUY_PULLBACK_EMA' };
            if (ema9[i] < ema21[i] && last.high >= ema21[i] && last.close < ema21[i] && last.close < last.open) return { direction: 'SELL', confidence: 84, strategy: 'TREND_PULLBACK', type: 'SELL_PULLBACK_EMA' };
            return null;
        }

        function analyzeBreakoutSpike(candlesArr) {
            if (!candlesArr || candlesArr.length < 20) return null;
            const look = candlesArr.slice(-16, -1);
            const last = candlesArr[candlesArr.length - 1];
            const res = Math.max(...look.map(c=>c.high));
            const sup = Math.min(...look.map(c=>c.low));
            const body = Math.abs(last.close - last.open);
            const avgBody = look.reduce((a,c)=>a+Math.abs(c.close-c.open),0) / look.length || 0.0001;
            if (last.close > res && body > avgBody * 1.4) return { direction: 'BUY', confidence: 83, strategy: 'BREAKOUT', type: 'RESISTANCE_BREAK' };
            if (last.close < sup && body > avgBody * 1.4) return { direction: 'SELL', confidence: 83, strategy: 'BREAKOUT', type: 'SUPPORT_BREAK' };
            return null;
        }

        async function analyzeWithStrategy(candlesArr, strategy) {
            if (!candlesArr || candlesArr.length < 10) return null;
            const last = candlesArr[candlesArr.length - 1];
            const price = last.close;
            const time = last.time || '';

            switch (strategy) {
                case 'Support/Resistance Touch': { const r = analyzeSupportResistanceTouch(candlesArr); if (r) return { direction: r.direction, price, time, payout: currentPayout || 0, confidence: r.confidence, strategy: r.strategy, type: r.type }; return null; }
                case 'EMA Trend Cross': { const r = analyzeEMATrend(candlesArr); if (r) return { direction: r.direction, price, time, payout: currentPayout || 0, confidence: r.confidence, strategy: r.strategy, type: r.type }; return null; }
                case 'RSI Reversal': { const r = analyzeRSIReversal(candlesArr); if (r) return { direction: r.direction, price, time, payout: currentPayout || 0, confidence: r.confidence, strategy: r.strategy, type: r.type }; return null; }
                case 'Bollinger Bands': { const r = analyzeBollinger(candlesArr); if (r) return { direction: r.direction, price, time, payout: currentPayout || 0, confidence: r.confidence, strategy: r.strategy, type: r.type }; return null; }
                case 'MACD Momentum': { const r = analyzeMACD(candlesArr); if (r) return { direction: r.direction, price, time, payout: currentPayout || 0, confidence: r.confidence, strategy: r.strategy, type: r.type }; return null; }
                case 'Stochastic Reversal': { const r = analyzeStochastic(candlesArr); if (r) return { direction: r.direction, price, time, payout: currentPayout || 0, confidence: r.confidence, strategy: r.strategy, type: r.type }; return null; }
                case 'Trend Pullback': { const r = analyzeTrendPullback(candlesArr); if (r) return { direction: r.direction, price, time, payout: currentPayout || 0, confidence: r.confidence, strategy: r.strategy, type: r.type }; return null; }
                case 'Breakout Spike': { const r = analyzeBreakoutSpike(candlesArr); if (r) return { direction: r.direction, price, time, payout: currentPayout || 0, confidence: r.confidence, strategy: r.strategy, type: r.type }; return null; }
                case 'AI Smart Signal': default: { const r = analyzeAdvancedAI(candlesArr); if (r && r.confidence >= 60) return { direction: r.direction, price, time, payout: currentPayout || 0, confidence: r.confidence, strategy: r.strategy, type: r.type }; return null; }
            }
        }

        async function onActionClick() {
            const mode = getSignalMode();
            if (mode === 'Auto') {
                if (autoModeActive) stopAutoMode(); else startAutoMode();
                return;
            }
            if (engine.state !== 'idle') return;
            generateManualSignal();
        }

        async function generateManualSignal() {
            engine.state = 'analyzing';
            setActionBtn('analyzing');
            hideSignalCard();
            const strategy = getSelectedStrategy();
            const signalPair = currentPair;
            const signalPairApi = currentApiPair;
            await loadData(signalPairApi);
            if (!allCandles || allCandles.length < 10) { setChartStatus("NO DATA AVAILABLE", "warn"); engine.state = 'idle'; setActionBtn('idle'); return; }
            const result = await analyzeWithStrategy(allCandles, strategy);
            if (!result) { setChartStatus("NO SIGNAL — " + strategy, "warn"); engine.state = 'idle'; setActionBtn('idle'); return; }
            const direction = result.direction;
            const price = result.price;
            const payout = result.payout || currentPayout || 0;
            const liveBase = (liveCandle && liveCandle.time) ? liveCandle.time : result.time;
            const targetTime = nextMinuteTime(liveBase, 1);
            engine.currentSignal = { direction, price, targetTime, payout, mtgStep: 0, entryTime: liveBase };
            engine.initialDirection = direction;
            engine.initialTargetTime = targetTime;
            engine.signalPair = signalPair;
            engine.signalPairApi = signalPairApi;
            engine.mtgLevel = 0;
            engine.mtgMax = getMtgMax();
            if (liveCandle) liveCandle.signal = direction;
            showSignalCard(signalPair, targetTime, direction, price, payout, null);
            engine.state = 'waiting';
            setActionBtn('waiting');
            requestDraw();
            sendSignalToTelegram(signalPair, targetTime, direction, price, payout, null);
            startResultPolling();
        }

        function startAutoMode() {
            autoModeActive = true;
            setActionBtn('scanning');
            setAutoStatusBar('🔄 SCANNING MARKETS...', true, 'scanning-text');
            autoScanLoop();
        }

        function stopAutoMode() {
            autoModeActive = false;
            if (autoModeTimer) { clearTimeout(autoModeTimer); autoModeTimer = null; }
            stopResultPolling();
            setAutoStatusBar('', false);
            if (engine.state === 'idle') setActionBtn('idle');
        }

        async function autoScanLoop() {
            if (!autoModeActive) return;
            if (engine.state !== 'idle') { autoModeTimer = setTimeout(autoScanLoop, 5000); return; }
            const strategy = getSelectedStrategy();
            const markets = selectedAutoMarkets.length ? selectedAutoMarkets : ALL_MARKETS;
            setAutoStatusBar(`🔍 SCANNING ${markets.length} MARKETS (${strategy})...`, true, 'scanning-text');
            for (let i = 0; i < markets.length; i++) {
                if (!autoModeActive) return;
                if (engine.state !== 'idle') { autoModeTimer = setTimeout(autoScanLoop, 5000); return; }
                const pair = markets[i];
                const pairApi = displayPairToApi(pair);
                setAutoStatusBar(`📊 ANALYZING ${pair} (${i + 1}/${markets.length})...`, true, 'scanning-text');
                try {
                    const url = API_BASE + '/?Pair=' + encodeURIComponent(pairApi) + '&Candle=100&Time=1m';
                    const resp = await fetch(url, { cache: "no-store" });
                    const json = await resp.json();
                    if (!json || !Array.isArray(json.data) || json.data.length < 10) continue;
                    const candlesArr = json.data.map(c => ({ open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close), signal: String(c.signal || '').trim().toUpperCase(), payout: Number(c.payout || 0), time: c.time || '', pair: c.pair || '' })).filter(c => Number.isFinite(c.open) && Number.isFinite(c.close)).reverse();
                    if (candlesArr.length < 10) continue;
                    const result = await analyzeWithStrategy(candlesArr, strategy);
                    if (result) {
                        const last = candlesArr[candlesArr.length - 1];
                        const payoutSample = candlesArr.slice(-30).map(c => c.payout).filter(p => p > 0);
                        const payout = payoutSample.length ? Math.round(payoutSample.reduce((a, b) => a + b, 0) / payoutSample.length) : 0;
                        setAutoStatusBar(`🚀 SIGNAL FOUND: ${pair} ${result.direction}`, true, 'signal-found');
                        await executeAutoSignal(pair, pairApi, result.direction, result.price || last.close, payout || currentPayout || 0, result.time || last.time);
                        return;
                    }
                } catch (e) { console.error('Auto scan error:', pair, e); }
                await new Promise(r => setTimeout(r, 200));
            }
            if (autoModeActive) { setAutoStatusBar(`⏳ NO SIGNAL — RESCANNING IN 8s...`, true, 'no-signal'); autoModeTimer = setTimeout(autoScanLoop, 8000); }
        }

        async function executeAutoSignal(pair, pairApi, direction, price, payout, baseTime) {
            if (!autoModeActive) return;
            if (currentPair !== pair) { currentPair = pair; currentApiPair = pairApi; document.getElementById('val-market').innerText = pair;
                await loadData(pairApi);
                startLiveTicks(); }
            const liveBaseAuto = (pairApi === currentApiPair && liveCandle && liveCandle.time) ? liveCandle.time : (baseTime || (allCandles.length ? allCandles[allCandles.length - 1].time : ''));
            const targetTime = nextMinuteTime(liveBaseAuto, 1);
            engine.currentSignal = { direction, price, targetTime, payout, mtgStep: 0, entryTime: liveBaseAuto };
            engine.initialDirection = direction;
            engine.initialTargetTime = targetTime;
            engine.signalPair = pair;
            engine.signalPairApi = pairApi;
            engine.mtgLevel = 0;
            engine.mtgMax = getMtgMax();
            if (liveCandle) liveCandle.signal = direction;
            showSignalCard(pair, targetTime, direction, price, payout, null);
            setAutoStatusBar(`📈 ${pair} ${direction} @ ${price}`, true, 'signal-found');
            engine.state = 'waiting';
            setActionBtn('scanning');
            requestDraw();
            sendSignalToTelegram(pair, targetTime, direction, price, payout, null);
            startResultPolling();
        }

        function sendSignalToTelegram(pair, targetTime, direction, price, payout, mtgTag) {
            const tgConfig = getTelegramConfig();
            if (tgConfig.autoSend && tgConfig.token && tgConfig.chatId) {
                setTimeout(async () => {
                    try {
                        const chartBlob = await getChartScreenshot();
                        const displayTime = targetTime.length >= 16 ? targetTime.substring(11, 16) : targetTime;
                        const caption = buildTelegramSignal(pair, displayTime, direction, price, payout, mtgTag);
                        await sendTelegramWithRetry(chartBlob, caption);
                    } catch (err) { console.error('Telegram signal send error:', err); setTgStatus('❌ Screenshot error', 'error'); }
                }, 300);
            }
        }

        function sendResultToTelegram(pair, targetTime, outcome) {
            const tgConfig = getTelegramConfig();
            if (tgConfig.autoSend && tgConfig.token && tgConfig.chatId) {
                setTimeout(async () => {
                    try {
                        const chartBlob = await getChartScreenshot();
                        const displayTime = engine.initialTargetTime || targetTime;
                        const hhmm = displayTime && displayTime.length >= 16 ? displayTime.substring(11, 16) : '00:00';
                        const caption = buildTelegramResult(pair, hhmm, outcome, engine.stats.wins, engine.stats.losses, getTelegram());
                        await sendTelegramWithRetry(chartBlob, caption);
                    } catch (err) { console.error('Telegram result send error:', err); }
                }, 300);
            }
        }

        function generateMtgSignal() {
            const pair = engine.signalPair || currentPair;
            const direction = engine.initialDirection;
            const price = engine.currentSignal ? engine.currentSignal.price : latestClosePrice;
            const payout = engine.currentSignal ? engine.currentSignal.payout : currentPayout || 0;
            const currentTarget = engine.currentSignal.targetTime;
            const nextTarget = nextMinuteTime(currentTarget, 1);
            const step = engine.mtgLevel + 1;
            engine.currentSignal = { direction: direction, price: price, targetTime: nextTarget, payout: payout, mtgStep: step };
            engine.mtgLevel = step;
            if (liveCandle) liveCandle.signal = direction;
            showSignalCard(pair, nextTarget, direction, price, payout, 'MTG' + step);
            engine.state = 'mtg';
            setActionBtn('mtg');
            requestDraw();
            startResultPolling();
        }

        let resultPoller = null;
        function startResultPolling() { stopResultPolling(); resultPoller = setInterval(pollForTargetCandle, 5000); pollForTargetCandle(); }
        function stopResultPolling() { if (resultPoller) { clearInterval(resultPoller); resultPoller = null; } }

        async function pollForTargetCandle() {
            if (!engine.currentSignal) { stopResultPolling(); return; }
            const pairApi = engine.signalPairApi || currentApiPair;
            await loadData(pairApi);
        }

        function evaluateWaitingResult() {
            if (!engine.currentSignal) return;
            if (engine.state !== 'waiting' && engine.state !== 'mtg') return;
            const target = findCandleByTime(allCandles, engine.currentSignal.targetTime);
            if (!target) return;
            const dir = engine.currentSignal.direction;
            let outcome;
            if (target.close > target.open) outcome = (dir === 'BUY') ? 'WIN' : 'LOSS';
            else if (target.close < target.open) outcome = (dir === 'SELL') ? 'WIN' : 'LOSS';
            else outcome = 'LOSS';
            stopResultPolling();
            applyOutcome(outcome);
        }

        function applyOutcome(outcome) {
            const pair = engine.signalPair || currentPair;
            const targetTime = engine.currentSignal.targetTime;
            let outcomeType = '';
            let isMtg = engine.mtgLevel > 0;
            if (outcome === 'WIN') {
                engine.stats.wins++; engine.stats.streakW++; engine.stats.streakL = 0;
                outcomeType = isMtg ? 'mtg-win' : 'win';
                tradeHistory.push({ time: targetTime, pair: pair, direction: engine.initialDirection, outcome: outcomeType });
                updateStatsUI();
                showResultCard(pair, targetTime, 'WIN', engine.stats.wins, engine.stats.losses);
                if (liveCandle) liveCandle.signal = '';
                sendResultToTelegram(pair, targetTime, 'WIN');
                finalizeSession();
                return;
            }
            if (engine.mtgLevel < engine.mtgMax) { generateMtgSignal(); return; }
            engine.stats.losses++; engine.stats.streakL++; engine.stats.streakW = 0;
            outcomeType = 'loss';
            tradeHistory.push({ time: targetTime, pair: pair, direction: engine.initialDirection, outcome: outcomeType });
            updateStatsUI();
            showResultCard(pair, targetTime, 'LOSS', engine.stats.wins, engine.stats.losses);
            if (liveCandle) liveCandle.signal = '';
            sendResultToTelegram(pair, targetTime, 'LOSS');
            finalizeSession();
        }

        function finalizeSession() {
            engine.state = 'idle';
            engine.initialTargetTime = null;
            engine.signalPair = null;
            engine.signalPairApi = null;
            engine.mtgLevel = 0;
            if (autoModeActive) {
                setActionBtn('scanning');
                setAutoStatusBar('🔄 RESULT DONE — CONTINUING SCAN...', true, 'scanning-text');
                autoModeTimer = setTimeout(autoScanLoop, 3000);
            } else {
                setActionBtn('idle');
                setAutoStatusBar('', false);
            }
            requestDraw();
            saveSettings();
        }

        function resetResult() {
            stopResultPolling();
            stopAutoMode();
            engine.state = 'idle';
            engine.currentSignal = null;
            engine.initialDirection = null;
            engine.initialTargetTime = null;
            engine.signalPair = null;
            engine.signalPairApi = null;
            engine.mtgLevel = 0;
            engine.mtgMax = getMtgMax();
            engine.stats = { wins: 0, losses: 0, streakW: 0, streakL: 0 };
            tradeHistory = [];
            if (liveCandle) liveCandle.signal = '';
            setActionBtn('idle');
            hideSignalCard();
            setTgStatus('', '');
            setAutoStatusBar('', false);
            updateStatsUI();
            requestDraw();
            saveSettings();
        }

        function parseCandleTime(str) { if (!str) return null; const m = str.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})/); if (!m) return null; return new Date(+m[1], +m[2] - 1, +m[3], +m[4], +m[5], +m[6]); }
        function formatCandleTime(date) { const p = n => n < 10 ? "0" + n : "" + n; return `${date.getFullYear()}-${p(date.getMonth() + 1)}-${p(date.getDate())} ${p(date.getHours())}:${p(date.getMinutes())}:00`; }
        function nextMinuteTime(str, offsetMinutes = 1) { const d = parseCandleTime(str); if (!d) return ''; d.setSeconds(0); d.setMinutes(d.getMinutes() + offsetMinutes); return formatCandleTime(d); }
        function findCandleByTime(pool, timeStr) { if (!pool) return null; for (let i = pool.length - 1; i >= 0; i--) { if (pool[i].time === timeStr) return pool[i]; } return null; }

        async function onMarketChanged(newDisplayPair) {
            currentPair = newDisplayPair;
            currentApiPair = displayPairToApi(newDisplayPair);
            candles = []; allCandles = []; liveCandle = null;
            stopResultPolling();
            engine.state = 'idle';
            engine.currentSignal = null;
            engine.initialTargetTime = null;
            engine.mtgLevel = 0;
            setActionBtn('idle');
            hideSignalCard();
            setChartStatus("SWITCHING", "ok");
            requestDraw();
            await loadData(currentApiPair);
            startLiveTicks();
            saveSettings();
        }

        function onTimeframeChanged(newTf) {
            if (newTf !== '1 Minute') {
                setChartStatus("1M ENGINE", "warn");
                setTimeout(() => setChartStatus("LIVE", "ok"), 1800);
            }
            saveSettings();
        }

        async function initEngine() {
            currentPair = document.getElementById('val-market').innerText.trim();
            currentApiPair = displayPairToApi(currentPair);
            await loadSettings();
            currentPair = document.getElementById('val-market').innerText.trim();
            currentApiPair = displayPairToApi(currentPair);
            updateStatsUI();
            chartResize();
            loadData(currentApiPair).then(() => { startLiveTicks(); });
            const wm = document.getElementById('watermarkInput').value;
            if (wm) document.documentElement.style.setProperty('--watermark-text', '"' + wm + '"');
            const dn = document.getElementById('dashboardNameInput').value;
            if (dn) document.documentElement.style.setProperty('--dashboard-name', '"' + dn + '"');
        }

        // ======================== BOOT ========================
        initEngine();

        setInterval(function () { if (currentApiPair && isUnlocked()) loadData(currentApiPair, true); }, 8000);
        setInterval(() => { if (isUnlocked()) requestDraw(); }, 1000);

        window.addEventListener('beforeunload', () => { try { flushSettingsNow(); } catch (e) {} });
        window.addEventListener('pagehide', () => { try { flushSettingsNow(); } catch (e) {} });

        // Expose globals
        window.onActionClick = onActionClick;
        window.resetResult = resetResult;
        window.sendPartialResult = sendPartialResult;
        window.openDialog = openDialog;
        window.closeDialog = closeDialog;
        window.toggleSwitch = toggleSwitch;
        window.toggleDarkMode = toggleDarkMode;
        window.switchView = switchView;
        window.resetAll = resetAll;
        window.lockApp = lockApp;
        window.handlePasswordLogin = handlePasswordLogin;
        window.selectItem = selectItem;
        window.toggleAutoMarket = toggleAutoMarket;
        window.chartResize = chartResize;

        // ======================== FUTURE CHECKER ========================
        function fcLoadSample() {
            const el = document.getElementById('fcSignalInput');
            if (!el) return;
            const now = new Date();
            const hh = String(now.getHours()).padStart(2, '0');
            const mm = String(Math.max(0, now.getMinutes() - 5)).padStart(2, '0');
            el.value = `⧉ 𝚄𝚂𝙳𝙱𝙳𝚃-𝙾𝚃𝙲 - 𝟷𝟺⁚${mm} ⇨ 𝙱𝚄𝚈\n⧉ 𝙴𝚄𝚁𝚄𝚂𝙳-𝙾𝚃𝙲 - ${hh}:${mm} ⇨ 𝙿𝚄𝚃`;
        }

        function fcDefancyText(value) {
            let s = String(value || '').normalize('NFKD');
            const map = { '⁚': ':', '：': ':', '﹕': ':', '．': '.', '。': '.',
                '⇨': ' -> ', '➔': ' -> ', '➡': ' -> ', '→': ' -> ', '⟶': ' -> ',
                '⁻': '-', '−': '-', '—': '-', '–': '-', '﹣': '-', '＿': '_',
                '𝟎':'0','𝟏':'1','𝟐':'2','𝟑':'3','𝟒':'4','𝟓':'5','𝟔':'6','𝟕':'7','𝟖':'8','𝟗':'9',
                '𝟘':'0','𝟙':'1','𝟚':'2','𝟛':'3','𝟜':'4','𝟝':'5','𝟞':'6','𝟟':'7','𝟠':'8','𝟡':'9' };
            return [...s].map(ch => map[ch] !== undefined ? map[ch] : ch).join('')
                .replace(/[\u{1D400}-\u{1D7FF}]/gu, ch => {
                    const cp = ch.codePointAt(0);
                    if (cp >= 0x1D7CE && cp <= 0x1D7FF) return String((cp - 0x1D7CE) % 10);
                    return ch;
                });
        }

        function parseFcSignals(text) {
            const out = []; const seen = new Set();
            for (const raw of String(text || '').split(/\r?\n/)) {
                let line = fcDefancyText(raw).replace(/([A-Za-z])\s*\/\s*([A-Za-z])/g, '$1$2').replace(/[⧉•]/g, ' ').replace(/[;,|\t]+/g, ' ')
                    .replace(/\s+/g, ' ').trim();
                if (!line) continue;
                const tm = line.match(/\b([01]?\d|2[0-3]):([0-5]\d)\b/);
                const dm = line.match(/\b(BUY|SELL|CALL|PUT|UP|DOWN)\b/i);
                if (!tm || !dm) continue;
                let dir = dm[1].toUpperCase();
                dir = (dir === 'BUY' || dir === 'CALL' || dir === 'UP') ? 'CALL' : 'PUT';
                const tokens = line.match(/[A-Za-z0-9]+(?:[-_][A-Za-z0-9]+)?(?:\s*[-_ ]?\s*OTC)?/ig) || [];
                let token = null;
                for (const t of tokens) {
                    const candidate = t.replace(/\s+/g, '').replace(/[-_]OTC$/i, '').replace(/OTC$/i, '');
                    if (/^[A-Za-z]{3,12}$/.test(candidate) && !/^(BUY|SELL|CALL|PUT|UP|DOWN|OTC)$/.test(candidate.toUpperCase())) {
                        if (!token || candidate.length > token.length) token = candidate.toUpperCase();
                        if (token.length >= 6) break;
                    }
                }
                if (!token) continue;
                const isOtc = /\bOTC\b/i.test(line) || /[-_]OTC\b/i.test(line);
                const apiPair = isOtc ? token + '_otc' : token;
                const display = token + (isOtc ? '-OTC' : '');
                const time = tm[1].padStart(2, '0') + ':' + tm[2];
                const key = [apiPair, time, dir].join('|');
                if (seen.has(key)) continue;
                seen.add(key);
                out.push({ pair: apiPair, display, asset: apiPair, asset_display: display, time, direction: dir });
            }
            return out;
        }

        async function runFutureCheck() {
            const input = document.getElementById('fcSignalInput');
            const btn = document.getElementById('fcCheckBtn');
            const status = document.getElementById('fcStatus');
            const signals = parseFcSignals(input ? input.value : '');
            if (!signals.length) { if (status) status.innerText = '❌ No valid signals. Paste: ⧉ USDXXX-OTC - 14:45 ⇨ BUY/PUT'; return; }
            const mtgTxt = (document.getElementById('val-fcMtg') || {}).innerText || 'No MTG';
            const mtgMatch = mtgTxt.match(/(\d+)/);
            const mtg = mtgMatch ? Math.min(4, parseInt(mtgMatch[1], 10)) : 0;
            const payTxt = (document.getElementById('val-fcPayout') || {}).innerText || 'All Payout';
            const pm = payTxt.match(/(\d+)/);
            const payoutFilter = pm ? parseInt(pm[1], 10) : 0;
            const dayTxt = ((document.getElementById('val-fcDay') || {}).innerText || 'Today').trim();
            if (btn) { btn.disabled = true; btn.innerText = '⏳ CHECKING...'; }
            if (status) status.innerText = '🔄 Checking ' + signals.length + ' signals...';
            try {
                const res = await fetch(API_BASE + '/future-check', {
                    method: 'POST', headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ signals: signals.map(s => ({ pair: s.pair, asset: s.asset, time: s.time, direction: s.direction, display: s.display, asset_display: s.asset_display })), mtg_level: mtg, payout_filter: payoutFilter, day: dayTxt.toLowerCase() })
                });
                const json = await res.json();
                if (!json.success) throw new Error(json.message || 'Check failed');
                const setText = (id, val) => { const el = document.getElementById(id); if (el) el.innerText = val; };
                setText('fcSumWin', json.wins || 0); setText('fcSumLoss', json.losses || 0);
                setText('fcSumTie', json.ties || 0); setText('fcSumPend', json.pending || 0);
                setText('fcSumAcc', (Number(json.accuracy) || 0).toFixed(1) + '%');
                const summary = document.getElementById('fcSummaryBox'); if (summary) summary.style.display = 'block';

                const M = (typeof toMonospace === 'function') ? toMonospace : (v => v);
                const PM = (typeof fmtPairMono === 'function') ? fmtPairMono : M;
                const DM = (typeof fmtDateMono === 'function') ? fmtDateMono : M;
                const sups = { 1: '¹', 2: '²', 3: '³', 4: '⁴' };
                const fmtTime = t => M(String(t || '').replace(':', '⁚'));
                const fmtPair = a => PM(String(a || '').replace(/[_ ]OTC/i, '-OTC').toUpperCase());
                const fmtDir = d => M(String(d || '').toUpperCase() === 'CALL' ? 'BUY' : 'PUT');
                let resultLines = '';
                (json.results || []).forEach(r => {
                    let sym = '❓';
                    if (!r.checked) sym = '⏳';
                    else if (r.skipped) sym = ' 💰' + M(String(Math.round(r.payout || 0))) + '٪';
                    else if (r.result === 'WIN') sym = '✅' + (r.mtg_used > 0 ? (sups[r.mtg_used] || String(r.mtg_used)) : '');
                    else if (r.result === 'LOSS') sym = '✖️';
                    else if (r.result === 'TIE') sym = '➖';
                    resultLines += '⧉ ' + fmtPair(r.display || r.pair) + ' - ' + fmtTime(r.time) + ' ⇨ ' + fmtDir(r.direction) + ' ' + sym + '\n';
                });
                const acc = (Number(json.accuracy) || 0).toFixed(1);
                const dateStr = String(json.date || '');
                const dateDot = dateStr.replace(/-/g, '.');
                const dateDash = dateStr.replace(/-/g, '—');
                const msg = '▰▱▱ ' + M('BOT CHECKER') + ' ▱▰▰\n'
                    + '  ┏━━━━━━━━━━━┓\n'
                    + '    📆 ' + M(dayTxt.toUpperCase()) + ' — ' + DM(dateDot) + '\n'
                    + '  ┗━━━━━━━━━━━┛\n'
                    + '━━━━━━━━━━━ • ━━━━━━━━━━━\n'
                    + resultLines
                    + '━━━━━━━━━━━ • ━━━━━━━━━━━\n'
                    + '🏆 ' + M('Total') + ' : ' + M(String(json.total_checked || 0)) + '\n'
                    + '✅ ' + M('Win') + ': ' + M(String(json.wins || 0)) + '\n'
                    + '❌ ' + M('Loss') + ': ' + M(String(json.losses || 0)) + '\n'
                    + '🎯 ' + M('Accuracy') + ': ' + DM(acc) + '٪\n'
                    + '🔄 ' + M('MTG') + ': ' + M(String(mtg)) + '\n'
                    + '📅 ' + M('Date') + ': ' + M(dayTxt.toUpperCase()) + ' (' + M(dateDash) + ')\n'
                    + '━━━━━━━━━━━ • ━━━━━━━━━━━';
                const card = document.getElementById('fcResultCard');
                if (card) { card.innerText = msg; card.classList.add('show'); card.style.display = 'block'; }
                const copyBox = document.getElementById('fcCopyBox'); if (copyBox) copyBox.style.display = 'block';
                window.__fcLastResult = msg;
                if (status) status.innerText = '✅ ' + (json.total_checked || 0) + ' signal check complete';
            } catch (e) {
                if (status) status.innerText = '❌ ' + (e.message || e);
            } finally {
                if (btn) { btn.disabled = false; btn.innerText = '🚀 CHECK SIGNALS'; }
            }
        }

        function fcCopyResult() {
            const card = document.getElementById('fcResultCard');
            if (!card || !card.innerText) return;
            navigator.clipboard.writeText(card.innerText).then(function(){ showToast('Result copied!'); }).catch(function(){});
        }

        window.runFutureCheck = runFutureCheck;
        window.fcLoadSample = fcLoadSample;
        window.fcCopyResult = fcCopyResult;

        lucide.createIcons();
    </script>
</body>
</html>"""


INDEX_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover" />
    <meta http-equiv="Cache-Control" content="no-store, no-cache, must-revalidate" />
    <meta http-equiv="Pragma" content="no-cache" />
    <meta name="robots" content="noindex, nofollow" />
    <title>HyperTrade — RAVITH AI PRO</title>
    <style>
        html, body { margin: 0; height: 100%; background: #04060d; overflow: hidden; }
        #rv-boot { position: fixed; inset: 0; display: flex; flex-direction: column; align-items: center;
            justify-content: center; gap: 18px; font-family: monospace; z-index: 5; }
        .rv-ring { width: 52px; height: 52px; border-radius: 50%;
            border: 3px solid rgba(0, 242, 254, .12); border-top-color: #00F2FE;
            animation: rvspin 0.9s linear infinite; }
        @keyframes rvspin { to { transform: rotate(360deg); } }
        .rv-txt { color: #00F2FE; font-size: 12px; letter-spacing: 3px; text-transform: uppercase;
            animation: rvblink 1.2s ease-in-out infinite; }
        @keyframes rvblink { 50% { opacity: .35; } }
        .rv-err { color: #ff3d71; font-size: 12px; display: none; max-width: 80%; text-align: center; line-height: 1.7; }
        #rv-frame { position: fixed; inset: 0; width: 100%; height: 100%; border: 0; display: none; }
    </style>
</head>
<body>
    <div id="rv-boot">
        <div class="rv-ring"></div>
        <div class="rv-txt" id="rv-msg">Secure channel…</div>
        <div class="rv-err" id="rv-err"></div>
    </div>
    <iframe id="rv-frame" title="app"></iframe>
    <script>
    (function () {
        var msg = document.getElementById('rv-msg'), err = document.getElementById('rv-err');
        function fail(t) { msg.style.display = 'none'; err.style.display = 'block'; err.textContent = t; }
        var proto = location.protocol === 'https:' ? 'wss://' : 'ws://';
        var ws;
        try { ws = new WebSocket(proto + location.host + '/ws'); }
        catch (e) { fail('WebSocket unsupported in this browser.'); return; }
        var got = false;
        ws.onopen = function () { try { ws.send(JSON.stringify({ type: 'ui_request' })); } catch (e) {} };
        ws.onmessage = function (ev) {
            try {
                var d = JSON.parse(ev.data);
                if (d && d.type === 'ui_html' && typeof d.html === 'string' && d.html.length > 100) {
                    got = true;
                    var f = document.getElementById('rv-frame');
                    f.style.display = 'block';
                    f.srcdoc = d.html;
                    f.onload = function () { var b = document.getElementById('rv-boot'); if (b) b.remove(); };
                    setTimeout(function () { var b = document.getElementById('rv-boot'); if (b) b.remove(); }, 12000);
                }
            } catch (e) {}
        };
        ws.onerror = function () { if (!got) fail('Connection failed. Server unreachable or blocked.'); };
        ws.onclose = function () { if (!got) fail('Secure channel closed before UI delivery.'); };
        setTimeout(function () { if (!got) fail('Timeout — server did not respond.'); }, 20000);
    })();
    </script>
</body>
</html>"""


# ==========================================
# 1. QUOTEX & MARKET SETTINGS
# ==========================================
def _load_bot_config():
    try:
        with open(DATA_DIR / "bot_config.json", "r") as f:
            cfg = json.load(f)
        if isinstance(cfg, dict):
            return cfg
    except Exception:
        pass
    return {}

_BOT_CFG = _load_bot_config()
QUOTEX_SSID_TOKEN = os.getenv("QUOTEX_SSID_TOKEN", "").strip()
QUOTEX_CSRF_TOKEN = os.getenv("QUOTEX_CSRF_TOKEN", "").strip()
QUOTEX_USER_AGENT = os.getenv("QUOTEX_USER_AGENT", "Quotex/1.0").strip()
USE_DEMO = bool(_BOT_CFG.get("use_demo", True))
HOST = "0.0.0.0"
PORT = int(os.getenv("PORT", "5000"))
MAX_CANDLES = 5000

UTC_PLUS_6 = pytz.timezone('Asia/Dhaka')

MARKET_DATA = {}
ALL_INSTRUMENTS = []
q_instance = None
PAYOUT_HISTORY = {}

SIGNAL_HISTORY = {}
SIGNALS_FILE = str(DATA_DIR / "signals_data.json")
signals_lock = threading.Lock()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD") or os.urandom(32).hex()

BOT_FEED_STATE = {"logged_in": False, "status": "offline"}

def save_bot_config():
    try:
        from telegram_runtime import atomic_json
        atomic_json(DATA_DIR / "bot_config.json", {"use_demo": USE_DEMO})
    except Exception as e:
        print(f"[bot_config save error] {e}")

def build_quotex_client():
    if not QUOTEX_SSID_TOKEN:
        raise RuntimeError("Quotex SSID token is missing. Restart and enter your token.")
    client = Quotex(lang="en", ssid_token=QUOTEX_SSID_TOKEN,
                    csrf_token=QUOTEX_CSRF_TOKEN or None,
                    user_agent=QUOTEX_USER_AGENT)
    client.set_token_csrf(QUOTEX_SSID_TOKEN, QUOTEX_CSRF_TOKEN or None,
                          user_agent=QUOTEX_USER_AGENT)
    return client

RUNNING_CANDLES = {}
TIMEFRAMES = {"5s": 5, "10s": 10, "15s": 15, "30s": 30, "1m": 60, "2m": 120, "3m": 180,
              "5m": 300, "10m": 600, "15m": 900, "30m": 1800, "1h": 3600, "4h": 14400}
CHART_BACKGROUND_IMAGE_URL = "https://ik.imagekit.io/x5w5qvwgy/5480daadd66215acc0dd40e7d87bdd77.jpg"

# ==========================================
# 2. GMAIL & AUTH SETTINGS
# ==========================================
GMAIL_EMAIL = os.getenv("GMAIL_EMAIL", "")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD", "")
SENDER_NAME = "RAVITH TRADING"

USERS_FILE = str(DATA_DIR / "users_data.json")
otp_storage = {}
OTP_EXPIRE_SECONDS = 60
DEFAULT_FREE_CREDITS = 5

file_lock = threading.Lock()

ACTIVE_SESSIONS = {}
BAN_SUBSCRIBERS = {}
BAN_SUB_LOCK = threading.Lock()

def issue_session(email):
    token = "%016x" % int.from_bytes(os.urandom(8), "big")
    ACTIVE_SESSIONS.setdefault(email, set()).add(token)
    return token

def drop_sessions(email):
    ACTIVE_SESSIONS.pop(email, None)

def broadcast_ban(email, message):
    with BAN_SUB_LOCK:
        subs = list(BAN_SUBSCRIBERS.get(email, []))
    dead = []
    for q in subs:
        try:
            q.put_nowait({"type": "ban", "message": message})
        except Exception:
            dead.append(q)
    if dead:
        with BAN_SUB_LOCK:
            for q in dead:
                try:
                    BAN_SUBSCRIBERS.get(email, []).remove(q)
                except Exception:
                    pass
    print(f"\U0001f6ab [BAN EVENT] pushed to {len(subs)} active client(s): {email}")

DEFAULT_SETTINGS = {
    "market": "USDBDT-OTC",
    "timeframe": "1 Minute",
    "strategy": "AI Smart Signal",
    "chartType": "Candlestick",
    "chartStyle": "Style 1 - Classic",
    "uiStyle": "UI 1 - Classic",
    "martingale": "No MTG",
    "dialogAnim": "Scale",
    "signalMode": "Manual",
    "telegram": "@Mahabub_iX",
    "botToken": "",
    "chatId": "",
    "darkMode": True,
    "autoTelegram": True,
    "soundAlerts": True,
    "vibration": True,
    "speed": "2",
    "glass": "0.8",
    "fontSize": "12",
    "dashboardName": "RAVITH PRO",
    "watermarkText": "\U0001d411\U0001d400\U0001d40f\U0001d408\U0001d413\U0001d407 \U0001d412\U0001d412",
    "signalName": "RAVITH AI PRO",
    "autoMarkets": [],
    "stats": {"wins": 0, "losses": 0, "streakW": 0, "streakL": 0},
    "tradeHistory": [],
    "uiTheme": "default",
    "backgroundMedia": "",
    "backgroundType": "",
    "showIndicators": True,
    "showCountdown": True,
    "showTerminal": True,
    "showWinLoss": True,
    "autoAnalyze": True,
    "candleAlerts": True,
    "fcDay": "Today",
    "fcMtg": "No MTG",
    "fcPayout": "All Payout"
}

app = Flask(__name__)
CORS(app)
sock = Sock(app)


def get_secure_6_digit():
    num = int.from_bytes(os.urandom(4), 'big')
    return (num % 900000) + 100000

def load_users():
    with file_lock:
        if os.path.exists(USERS_FILE):
            try:
                with open(USERS_FILE, "r") as f:
                    return json.load(f)
            except:
                return {}
        return {}

def save_users(users):
    with file_lock:
        tmp = USERS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(users, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, USERS_FILE)

def generate_uid():
    users = load_users()
    existing_uids = [u.get("uid", "") for u in users.values()]
    while True:
        uid = str(get_secure_6_digit())
        if uid not in existing_uids:
            return uid

def generate_otp():
    return str(get_secure_6_digit())

def get_user_by_uid(uid):
    users = load_users()
    for email, data in users.items():
        if data.get("uid") == uid:
            return email, data
    return None, None


def send_gmail_otp(receiver_email, otp):
    subject = "Your Login Verification Code - RAVITH TRADING"
    text_body = f"Hello,\n\nYour login verification code is: {otp}\nThis code will expire in 1 minute.\n\nRAVITH TRADING"
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = formataddr((SENDER_NAME, GMAIL_EMAIL))
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(text_body, 'plain'))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print("Gmail OTP Error:", e)
        return False

def send_gmail_password(receiver_email, name, password):
    subject = "Your Account Password - RAVITH TRADING"
    text_body = f"Hello {name},\n\nYou requested your account password.\nYour password is: {password}\n\nRAVITH TRADING"
    try:
        msg = MIMEMultipart('alternative')
        msg['From'] = formataddr((SENDER_NAME, GMAIL_EMAIL))
        msg['To'] = receiver_email
        msg['Subject'] = subject
        msg.attach(MIMEText(text_body, 'plain'))
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login(GMAIL_EMAIL, GMAIL_APP_PASSWORD)
            server.send_message(msg)
        return True
    except Exception as e:
        print("Gmail Forgot Password Error:", e)
        return False


def ts_to_dt(ts):
    if ts is None: return None
    try:
        ts = int(ts)
        if ts > 1_000_000_000_000: ts = ts / 1000
        dt_utc = datetime.fromtimestamp(ts, tz=timezone.utc)
        return dt_utc.astimezone(UTC_PLUS_6)
    except:
        return None

def get_payout(q, pair_name):
    if not q or not hasattr(q, "api") or not q.api or not hasattr(q.api, "instruments"):
        return 0.0
    for inst in q.api.instruments:
        if len(inst) > 1 and inst[1] == pair_name:
            if len(inst) > 18 and inst[18] is not None: return float(inst[18])
            if len(inst) > 5 and inst[5] is not None: return float(inst[5])
            for value in reversed(inst):
                if isinstance(value, (int, float)) and 0 <= value <= 100:
                    return float(value)
            return 0.0
    return 0.0

def get_payout_for_time(pair, timeframe, time_str):
    storage_key = f"{pair}_{timeframe}"
    if storage_key in PAYOUT_HISTORY:
        payout_times = list(PAYOUT_HISTORY[storage_key].keys())
        if payout_times:
            if time_str in PAYOUT_HISTORY[storage_key]:
                return PAYOUT_HISTORY[storage_key][time_str]
            else:
                sorted_times = sorted(payout_times)
                for t in reversed(sorted_times):
                    if t <= time_str:
                        return PAYOUT_HISTORY[storage_key][t]
    return 0.0

def update_payout_history(pair, timeframe, time_str, payout):
    storage_key = f"{pair}_{timeframe}"
    if storage_key not in PAYOUT_HISTORY:
        PAYOUT_HISTORY[storage_key] = {}
    PAYOUT_HISTORY[storage_key][time_str] = payout

def detect_markets(q):
    if not q or not hasattr(q, "api") or not q.api:
        return []
    markets = []
    seen = set()
    try:
        for inst in q.api.instruments:
            if len(inst) < 2: continue
            pair = str(inst[1]).strip()
            if not pair or pair in seen: continue
            seen.add(pair)
            payout = get_payout(q, pair)
            pair_upper = pair.upper()
            if pair.endswith("_otc") or pair.endswith("_OTC"): category = "OTC"
            elif any(x in pair_upper for x in ["BTC","ETH","LTC","BNB","SOL","DOGE","XRP","ADA","DOT","TRX","AVAX"]): category = "Crypto"
            elif any(x in pair_upper for x in ["XAU","XAG","WTI","BRENT","NGAS"]): category = "Commodity"
            elif any(x in pair_upper for x in ["US30","NAS100","SPX","GER40","UK100","JP225","AUS200","FR40","EU50"]): category = "Index"
            else: category = "Forex"
            markets.append({"pair": pair, "display_name": pair.replace("_otc", "").replace("_OTC", ""), "payout": payout, "category": category})
    except Exception as e:
        print(f"❌ Market Detection Error: {e}")
    return sorted(markets, key=lambda x: x["pair"])

async def safe_fetch(q, pair, period):
    end_from = time.time()
    offset = 120
    try:
        raw = await q.get_candles(pair, end_from, offset, period)
        if raw: return raw
    except Exception: pass
    try:
        raw = await q.get_candles(pair, period)
        if raw: return raw
    except Exception: pass
    try:
        raw = await q.get_candle_v2(pair, period)
        if raw: return raw
    except Exception: pass
    try:
        raw = await q.get_candle_v2(pair, end_from, offset, period)
        if raw: return raw
    except Exception: pass
    return None

def load_signals():
    global SIGNAL_HISTORY
    try:
        with open(SIGNALS_FILE, "r") as f:
            SIGNAL_HISTORY = json.load(f)
    except Exception:
        SIGNAL_HISTORY = {}

def save_signals():
    try:
        from telegram_runtime import atomic_json
        atomic_json(SIGNALS_FILE, SIGNAL_HISTORY)
    except Exception as e:
        print(f"[signals save error] {e}")

def lookup_signal(pair, time_str):
    try:
        return SIGNAL_HISTORY.get(pair, {}).get(time_str, "")
    except Exception:
        return ""

def register_signal(pair, time_str, direction):
    with signals_lock:
        SIGNAL_HISTORY.setdefault(pair, {})[time_str] = direction.upper()
        keys = sorted(SIGNAL_HISTORY[pair].keys())
        if len(keys) > 500:
            for k in keys[:-500]:
                SIGNAL_HISTORY[pair].pop(k, None)
        save_signals()

def clear_signals(pair=None):
    with signals_lock:
        if pair: SIGNAL_HISTORY.pop(pair, None)
        else: SIGNAL_HISTORY.clear()
        save_signals()

def update_market_data(storage_key, candle_data):
    if storage_key not in MARKET_DATA:
        MARKET_DATA[storage_key] = deque(maxlen=MAX_CANDLES)
    existing = list(MARKET_DATA[storage_key])
    found = False
    for i, c in enumerate(existing):
        if c["time"] == candle_data["time"]:
            existing[i] = candle_data
            found = True
            break
    if not found:
        existing.append(candle_data)
    unique = {c["time"]: c for c in existing}
    sorted_data = sorted(unique.values(), key=lambda x: x["time"], reverse=True)
    new_deque = deque(maxlen=MAX_CANDLES)
    for c in sorted_data:
        new_deque.append(c)
    MARKET_DATA[storage_key] = new_deque


def get_last_closed_candle(pair, frame):
    storage_key = f"{pair}_1m"
    if storage_key in MARKET_DATA and MARKET_DATA[storage_key]:
        for candle in MARKET_DATA[storage_key]:
            return candle
    return None

def _promote_running_candle(asset, frame, rc):
    try:
        if frame != "1m": return
        storage_key = f"{asset}_1m"
        dt = ts_to_dt(rc["start"])
        if dt is None: return
        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
        payout = get_payout_for_time(asset, "1m", time_str) if storage_key in PAYOUT_HISTORY else 0.0
        candle_data = {"close": rc["close"], "high": rc["high"], "low": rc["low"], "open": rc["open"],
            "pair": asset.replace('_otc', '-OTC').upper(), "signal": lookup_signal(asset, time_str),
            "time": time_str, "payout": payout}
        update_market_data(storage_key, candle_data)
    except Exception as e:
        print(f"[promote error] {e}")


def update_running_candle(asset, frame, price, ts_sec):
    asset = _norm_asset(asset)
    if not asset or price is None: return
    try: price = float(price)
    except Exception: return
    if price <= 0: return
    duration = TIMEFRAMES.get(frame, 60)
    try: ts_sec = int(ts_sec)
    except Exception: ts_sec = int(time.time())
    candle_start = (ts_sec // duration) * duration
    if asset not in RUNNING_CANDLES:
        RUNNING_CANDLES[asset] = {}
    curr = RUNNING_CANDLES[asset].get(frame)
    if not curr or curr.get("start") != candle_start:
        if curr: _promote_running_candle(asset, frame, curr)
        prev_candle = get_last_closed_candle(asset, frame)
        prev_close = prev_candle["close"] if prev_candle else price
        RUNNING_CANDLES[asset][frame] = {"start": candle_start, "open": float(prev_close),
            "high": max(float(prev_close), price), "low": min(float(prev_close), price),
            "close": price, "ticks": 1, "updated": time.time()}
    else:
        if price > curr["high"]: curr["high"] = price
        if price < curr["low"]: curr["low"] = price
        curr["close"] = price
        curr["ticks"] = int(curr.get("ticks") or 0) + 1
        curr["updated"] = time.time()

def _norm_asset(asset):
    if not asset: return ""
    a = str(asset).strip().replace("-", "_").replace(" ", "_")
    if a.lower().endswith("_otc"):
        base = a[:-4]
        return base.upper() + "_otc"
    if a.upper().endswith("OTC") and "_" not in a:
        return a[:-3].upper() + "_otc"
    return a

def process_message(message):
    try:
        text = message.decode('utf-8', errors='ignore') if isinstance(message, bytes) else str(message)
        match = re.search(r'\[\[\s*("([^"]+)"|null)?,?\s*([\d.]+)\s*,\s*([\d.]+)', text)
        if match:
            asset_raw = match.group(2) if match.group(2) else None
            timestamp = float(match.group(3))
            price = float(match.group(4))
            if asset_raw and price > 0:
                asset = _norm_asset(asset_raw)
                ts_sec = int(timestamp // 1000) if timestamp > 1_000_000_000_000 else int(timestamp)
                for frame in TIMEFRAMES:
                    update_running_candle(asset, frame, price, ts_sec)
                return
        if text.startswith('[') or text.startswith('{'):
            try: payload = json.loads(text)
            except Exception: payload = None
            items = payload if isinstance(payload, list) else ([payload] if isinstance(payload, dict) else [])
            for item in items:
                if not isinstance(item, dict): continue
                asset_raw = item.get('asset') or item.get('symbol') or item.get('pair')
                price = item.get('price') or item.get('close') or item.get('bid') or item.get('value')
                ts = item.get('time') or item.get('timestamp') or item.get('t') or time.time()
                if not asset_raw or price is None: continue
                try:
                    price = float(price)
                    ts_sec = int(float(ts))
                    if ts_sec > 1_000_000_000_000: ts_sec //= 1000
                except Exception: continue
                if price > 0:
                    asset = _norm_asset(str(asset_raw))
                    for frame in TIMEFRAMES:
                        update_running_candle(asset, frame, price, ts_sec)
    except Exception as e:
        print(f"[tick error] {e}")


def running_to_api(pair, frame):
    pair = _norm_asset(pair)
    rc = RUNNING_CANDLES.get(pair, {}).get(frame)
    if not rc: return None
    dt = ts_to_dt(rc["start"])
    time_str = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""
    return {"close": float(rc["close"]), "high": float(rc["high"]), "low": float(rc["low"]),
        "open": float(rc["open"]), "pair": pair.replace('_otc', '-OTC').upper(),
        "signal": lookup_signal(pair, time_str), "time": time_str, "payout": 0.0,
        "is_running": True, "ticks": int(rc.get("ticks") or 0), "updated": float(rc.get("updated") or 0)}

def get_candles_with_running(pair, timeframe, limit):
    frame = timeframe if timeframe in TIMEFRAMES else "1m"
    pair = _norm_asset(pair) if pair else pair
    storage_key = f"{pair}_{timeframe}"
    if storage_key in MARKET_DATA:
        closed = list(MARKET_DATA[storage_key])
    else:
        fallback_key = f"{pair}_1m"
        closed = list(MARKET_DATA[fallback_key]) if fallback_key in MARKET_DATA else []
    running = running_to_api(pair, frame)
    if running and running.get("time"):
        closed = [c for c in closed if c.get("time") != running.get("time")]
    closed = closed[:limit]
    for c in closed:
        sig = lookup_signal(pair, c.get("time", ""))
        if sig: c["signal"] = sig
    if running and closed:
        running["payout"] = closed[0].get("payout", 0.0)
    elif running:
        running["payout"] = running.get("payout", 0.0)
    return closed, running


async def background_market_loop():
    global q_instance, ALL_INSTRUMENTS, AUTO_TRADE_LOOP, USE_DEMO
    AUTO_TRADE_LOOP = asyncio.get_running_loop()
    period = 60

    while True:
        cfg = _load_bot_config()
        USE_DEMO = bool(cfg.get("use_demo", USE_DEMO))

        if not BOT_FEED_STATE.get("logged_in") or not QUOTEX_SSID_TOKEN:
            BOT_FEED_STATE["status"] = "offline"
            await asyncio.sleep(5)
            continue

        try:
            q = build_quotex_client()
        except Exception as e:
            BOT_FEED_STATE["status"] = "error"
            print(f"❌ Quotex token setup error: {e}")
            await asyncio.sleep(10)
            continue

        print("🔌 Connecting to Quotex using SSID/CSRF session...")
        BOT_FEED_STATE["status"] = "connecting"
        try:
            connect_result = await asyncio.wait_for(q.connect(), timeout=45)
            if isinstance(connect_result, tuple):
                ok = bool(connect_result[0])
                reason = connect_result[1] if len(connect_result) > 1 else ""
            else:
                ok, reason = bool(connect_result), ""
            if ok and hasattr(q, "check_connect"):
                try:
                    chk = await q.check_connect()
                    if chk is False:
                        ok = False
                        reason = reason or "check_connect failed"
                except Exception: pass
        except Exception as e:
            print(f"❌ Data-feed connect error: {type(e).__name__}")
            ok, reason = False, str(e)
        if not ok:
            print(f"❌ Data-feed login failed! {reason or 'Check credentials'}. Retrying in 10s...")
            BOT_FEED_STATE["status"] = "error"
            try: await q.close()
            except Exception: pass
            await asyncio.sleep(10)
            continue

        print("✅ Data-feed login successful! Starting real-time data collection...")
        try:
            if hasattr(q, "change_account"):
                await q.change_account("PRACTICE" if USE_DEMO else "REAL")
            elif hasattr(q, "set_account_mode"):
                q.set_account_mode("practice" if USE_DEMO else "real")
        except Exception as e:
            print(f"⚠️ account mode switch: {e}")
        q_instance = q
        BOT_FEED_STATE["status"] = "online"
        BOT_FEED_STATE["logged_in"] = True

        try:
            ws_app = q.api.websocket_client.wss
            _orig_on_message = getattr(ws_app, 'on_message', None)
            def _tick_handler(ws, msg):
                try: process_message(msg)
                except Exception as _e: print(f"⚠️ tick handler error: {_e}")
                if _orig_on_message:
                    try: return _orig_on_message(ws, msg)
                    except: pass
            ws_app.on_message = _tick_handler
            print("✅ Real-time tick handler attached (running candle engine active)")
        except Exception as e:
            print(f"⚠️ Tick handler attach failed: {e}")

        while BOT_FEED_STATE.get("logged_in"):
            try:
                instruments = detect_markets(q)
                if instruments: ALL_INSTRUMENTS = instruments
                pairs = [m["pair"] for m in ALL_INSTRUMENTS] if ALL_INSTRUMENTS else ["USDPHP_otc", "USDARS_otc", "USDBRL_otc"]
                for pair in pairs:
                    if not BOT_FEED_STATE.get("logged_in"):
                        break
                    if not await q.check_connect():
                        raise ConnectionError("Quotex WebSocket disconnected")
                    current_payout = get_payout(q, pair)
                    raw_candles = await safe_fetch(q, pair, period)
                    if not raw_candles: continue
                    storage_key = f"{pair}_1m"
                    for r in raw_candles:
                        ts = r.get("time") or r.get("timestamp") or r.get("t") or r.get("date")
                        dt = ts_to_dt(ts)
                        if dt is None: continue
                        time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                        if storage_key in PAYOUT_HISTORY and time_str in PAYOUT_HISTORY[storage_key]:
                            payout_for_time = PAYOUT_HISTORY[storage_key][time_str]
                        else:
                            payout_for_time = current_payout
                            update_payout_history(pair, "1m", time_str, payout_for_time)
                        open_p = float(r.get("open") or r.get("o", 0))
                        close_p = float(r.get("close") or r.get("c", 0))
                        candle_data = {"close": close_p, "high": float(r.get("high") or r.get("h", 0)),
                            "low": float(r.get("low") or r.get("l", 0)), "open": open_p,
                            "pair": pair.replace('_otc', '-OTC').upper(), "signal": lookup_signal(pair, time_str),
                            "time": time_str, "payout": payout_for_time}
                        update_market_data(storage_key, candle_data)
                        try: update_running_candle(pair, "1m", close_p, int(time.time()))
                        except Exception: pass
                    await asyncio.sleep(0.05)
                print(f"🔄 [Cycle Complete] markets={len(pairs)} keys={len(MARKET_DATA)} running={len(RUNNING_CANDLES)} status={BOT_FEED_STATE.get('status')}")
                await asyncio.sleep(1.5)
            except Exception as e:
                print(f"⚠️ Error in background loop: {type(e).__name__}")
                BOT_FEED_STATE["status"] = "reconnecting"
                break

        BOT_FEED_STATE["status"] = "offline"
        if q_instance is q: q_instance = None
        try: await q.close()
        except Exception: pass
        await asyncio.sleep(3)


def start_async_loop():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(background_market_loop())


BAN_GUARDED_PATHS = {
    "/profile", "/use-credit", "/save-settings", "/get-settings", "/reset-results",
    "/save-signal", "/clear-signals", "/record-result", "/trade-history", "/session-remember",
    "/quotex-login", "/quotex-status", "/quotex-disconnect",
    "/auto-trade", "/auto-trade/decision", "/auto-trade/cancel"
}

@app.before_request
def enforce_ban_and_session():
    if request.path not in BAN_GUARDED_PATHS: return None
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or request.args.get("email") or "").strip()
    if not email: return None
    user = load_users().get(email)
    if not user:
        drop_sessions(email)
        print(f"\u26d4 [GUARD] account not found in database: {email} -> forcing auto-logout")
        return jsonify({"success": False, "account_deleted": True,
                        "message": "Your account is no longer registered on this server. You have been logged out."}), 401
    if user.get("banned"):
        drop_sessions(email)
        print(f"\u26d4 [GUARD] blocked request {request.path} from banned account: {email}")
        return jsonify({"success": False, "banned": True,
                        "message": "Your account has been banned by the administrator. Contact support: @MAHBAUB_iX"}), 403
    token = data.get("session") or request.headers.get("X-Session")
    if token and token not in ACTIVE_SESSIONS.get(email, set()):
        return jsonify({"success": False, "session_expired": True,
                        "message": "Session terminated. Please login again."}), 401
    return None

@app.route('/', methods=['GET'])
def index_or_candles():
    pair = request.args.get('Pair') or request.args.get('pair')
    if pair:
        candle_limit = request.args.get('Candle') or request.args.get('candle') or 5000
        timeframe = request.args.get('Time') or request.args.get('time') or "1m"
        try: candle_limit = int(candle_limit)
        except: candle_limit = 5000
        data_list, running = get_candles_with_running(pair, timeframe, candle_limit)
        return jsonify({"api_pair": pair, "timeframe": timeframe, "count": len(data_list),
                        "data": data_list, "running": running})
    if request.args.get('json') or request.args.get('api'):
        return jsonify({"success": True, "service": "RAVITH TRADING UNIFIED API", "endpoints": [
            "/?Pair=USDBDT_otc&Time=1m (Get Candles + running)",
            "/chart_image?Pair=USDBDT_otc&Candle=60&SS=RAVITH-PRO (Chart SS Image)",
            "/markets", "/latest", "/payout-history"]})
    r = app.make_response(INDEX_HTML)
    r.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    r.headers['Pragma'] = 'no-cache'
    r.headers['X-Content-Type-Options'] = 'nosniff'
    r.headers['X-Frame-Options'] = 'SAMEORIGIN'
    r.headers['Content-Security-Policy'] = "frame-ancestors 'self'"
    return r


@app.route("/session-remember", methods=["POST"])
def session_remember_route():
    data = request.get_json(silent=True) or {}
    email = str(data.get("email", "")).strip()
    if not email: return jsonify({"success": False, "message": "Email required"}), 400
    users = load_users()
    user = users.get(email)
    if not user:
        drop_sessions(email)
        return jsonify({"success": False, "account_deleted": True,
                        "message": "Your account is no longer registered on this server. You have been logged out."}), 401
    if user.get("banned"):
        drop_sessions(email)
        return jsonify({"success": False, "banned": True,
                        "message": "Your account has been banned by the administrator."}), 403
    token = data.get("session") or request.headers.get("X-Session")
    sessions = ACTIVE_SESSIONS.setdefault(email, set())
    if token and token in sessions:
        return jsonify({"success": True, "session": token, "reused": True})
    new_token = issue_session(email)
    return jsonify({"success": True, "session": new_token, "reused": False})


def _fc_time_to_min(t):
    try:
        hh, mm = str(t).strip().split(":")
        hh_i, mm_i = int(hh), int(mm)
        if 0 <= hh_i <= 23 and 0 <= mm_i <= 59: return hh_i * 60 + mm_i
    except Exception: pass
    return None


def _fc_check_one(closed, running, mkt_today, sig_time, direction, mtg_level):
    base_min = _fc_time_to_min(sig_time)
    if base_min is None:
        return {"result": "UNKNOWN", "mtg_used": 0, "checked": False, "error": "Invalid time", "payout": 0}
    def candle_win(c, d):
        if c is None: return None
        try:
            op = float(c.get("open")); cl = float(c.get("close"))
        except Exception: return None
        if op == cl: return None
        return (cl > op) if d in ("CALL", "BUY") else (cl < op)
    def find_at(total_min):
        if total_min < 0: return None
        hh_s = "%02d:%02d" % (total_min // 60, total_min % 60)
        target_prefix = mkt_today + " " + hh_s
        for c in closed:
            if str(c.get("time", "")).startswith(target_prefix): return c
        if running and str(running.get("time", "")).startswith(target_prefix): return running
        return None
    entry = find_at(base_min)
    if entry is None:
        return {"result": "PENDING", "mtg_used": 0, "checked": False, "error": "Candle not found", "payout": 0}
    try: payout = float(entry.get("payout") or 0)
    except Exception: payout = 0.0
    win = candle_win(entry, direction)
    if win is None: return {"result": "TIE", "mtg_used": 0, "checked": True, "payout": payout}
    if win: return {"result": "WIN", "mtg_used": 0, "checked": True, "payout": payout}
    mtg_used = 0
    mtg_win = False
    if mtg_level >= 1:
        for lvl in range(1, min(int(mtg_level), 4) + 1):
            mc = find_at(base_min + lvl)
            if mc is None: break
            if candle_win(mc, direction):
                mtg_used = lvl
                mtg_win = True
                break
    if mtg_win: return {"result": "WIN", "mtg_used": mtg_used, "checked": True, "payout": payout}
    return {"result": "LOSS", "mtg_used": mtg_used, "checked": True, "payout": payout}


@app.route("/future-check", methods=["POST"])
def future_check_route():
    data = request.get_json(silent=True) or {}
    signals = data.get("signals")
    if not isinstance(signals, list) or not signals:
        return jsonify({"success": False, "message": "signals array required"}), 400
    try: mtg_level = max(0, min(4, int(data.get("mtg_level", 0))))
    except Exception: mtg_level = 0
    try: payout_filter = float(data.get("payout_filter") or 0)
    except Exception: payout_filter = 0
    day = str(data.get("day") or "today").lower()
    now = datetime.now(UTC_PLUS_6)
    if day == "yesterday": now = now - timedelta(days=1)
    date_str = now.strftime("%Y-%m-%d")
    results = []
    for s in signals:
        pair = str(s.get("pair") or "").strip()
        if not pair: continue
        if not pair.endswith("_otc") and "otc" in pair.lower():
            pair = pair.replace("-OTC", "_otc").replace("-otc", "_otc")
        sig_time = str(s.get("time") or "")
        direction = str(s.get("direction") or "CALL").upper()
        display = str(s.get("display") or pair)
        closed, running = get_candles_with_running(pair, "1m", 500)
        r = _fc_check_one(list(closed), running, date_str, sig_time, direction, mtg_level)
        r["pair"] = pair; r["display"] = display; r["time"] = sig_time; r["direction"] = direction
        results.append(r)
    wins = losses = ties = pending = skipped = 0
    for r in results:
        r["skipped"] = False
        if not r.get("checked"): pending += 1
        elif payout_filter > 0 and float(r.get("payout", 0) or 0) < payout_filter:
            r["skipped"] = True
            skipped += 1
        elif r["result"] == "WIN": wins += 1
        elif r["result"] == "LOSS": losses += 1
        elif r["result"] == "TIE": ties += 1
    total_decided = wins + losses
    accuracy = (wins / total_decided * 100.0) if total_decided else 0.0
    return jsonify({"success": True, "date": date_str, "mtg_level": mtg_level,
        "payout_filter": payout_filter, "total_checked": len(results),
        "wins": wins, "losses": losses, "ties": ties, "pending": pending,
        "skipped_low_payout": skipped, "accuracy": accuracy,
        "results": sorted(results, key=lambda x: x.get("time", ""))})


@sock.route('/ws')
def ws_channel(ws):
    try:
        while True:
            raw = ws.receive(timeout=300)
            if raw is None: break
            try: data = json.loads(raw)
            except Exception: data = {}
            if isinstance(data, dict) and data.get('type') == 'ui_request':
                ws.send(json.dumps({'type': 'ui_html', 'html': UI_HTML}))
    except Exception: pass


@sock.route('/ws-ui')
def ws_ui_channel(ws):
    return ws_channel(ws)

@app.route('/markets', methods=['GET'])
def get_active_markets():
    return jsonify({"status": "success", "total_markets": len(ALL_INSTRUMENTS), "markets": ALL_INSTRUMENTS})

@app.route('/latest', methods=['GET'])
def get_latest_candle():
    pair = request.args.get('Pair') or request.args.get('pair') or "USDPHP_otc"
    timeframe = request.args.get('Time') or request.args.get('time') or "1m"
    candles, running = get_candles_with_running(pair, timeframe, 5)
    if not candles and not running:
        return jsonify({"status": "error", "message": f"No data found for {pair}"}), 404
    return jsonify({"status": "success", "data": candles[0] if candles else running, "running": running,
        "closed": candles[:3] if candles else [], "feed": BOT_FEED_STATE.get("status", "unknown"),
        "live": bool(running)})

@app.route('/payout-history', methods=['GET'])
def get_payout_history():
    pair = request.args.get('Pair') or request.args.get('pair') or "USDPHP_otc"
    timeframe = request.args.get('Time') or request.args.get('time') or "1m"
    storage_key = f"{pair}_{timeframe}"
    if storage_key in PAYOUT_HISTORY:
        return jsonify({"status": "success", "pair": pair, "timeframe": timeframe, "payout_history": PAYOUT_HISTORY[storage_key]})
    return jsonify({"status": "error", "message": f"No history found for {pair}"}), 404


# ==========================================
# LEGACY USER AUTH ENDPOINTS (kept for compatibility,
# UI no longer uses these — password system replaces them)
# ==========================================
@app.route("/send-otp", methods=["GET", "POST"])
def send_otp():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    if not email: return jsonify({"success": False, "message": "Email is required"}), 400
    otp = generate_otp()
    otp_storage[email] = {"otp": otp, "created": time.time()}
    if send_gmail_otp(email, otp):
        return jsonify({"success": True, "message": "OTP sent successfully", "expires_in": OTP_EXPIRE_SECONDS})
    otp_storage.pop(email, None)
    return jsonify({"success": False, "message": "Failed to send OTP"}), 500

@app.route("/resend-otp", methods=["POST"])
def resend_otp(): return send_otp()

@app.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    otp = data.get("otp")
    if not email or not otp: return jsonify({"success": False, "message": "Email and OTP required"}), 400
    saved = otp_storage.get(email)
    if not saved: return jsonify({"success": False, "message": "OTP not found"}), 400
    if (time.time() - saved["created"]) > OTP_EXPIRE_SECONDS:
        otp_storage.pop(email, None)
        return jsonify({"success": False, "message": "OTP expired"}), 400
    if str(otp) != str(saved["otp"]):
        return jsonify({"success": False, "message": "Invalid OTP"}), 400
    otp_storage.pop(email, None)
    return jsonify({"success": True, "message": "OTP verified successfully", "email": email})

@app.route("/otp-status", methods=["POST"])
def otp_status():
    data = request.get_json(silent=True) or {}
    email = data.get("email")
    if not email: return jsonify({"success": False, "message": "Email required"}), 400
    saved = otp_storage.get(email)
    if not saved: return jsonify({"success": True, "exists": False})
    remaining = max(0, OTP_EXPIRE_SECONDS - (time.time() - saved["created"]))
    return jsonify({"success": True, "exists": True, "remaining_seconds": int(remaining)})

@app.route("/forgot-password", methods=["POST"])
def forgot_password():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    if not email: return jsonify({"success": False, "message": "Email is required"}), 400
    users = load_users()
    if email not in users: return jsonify({"success": False, "message": "No account found"}), 404
    user = users[email]
    if send_gmail_password(email, user.get("name", "User"), user.get("password", "")):
        return jsonify({"success": True, "message": "Password sent to your email."})
    return jsonify({"success": False, "message": "Failed to send email."}), 500

@app.route("/register", methods=["POST"])
def register_user():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    name = data.get("name", "").strip()
    password = data.get("password", "")
    if not email or not name or not password:
        return jsonify({"success": False, "message": "All fields required"}), 400
    users = load_users()
    if email in users: return jsonify({"success": False, "message": "Account already exists"}), 400
    uid = generate_uid()
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    users[email] = {"name": name, "email": email, "password": password, "uid": uid,
        "credit": DEFAULT_FREE_CREDITS, "credit_type": "free", "created_at": now,
        "last_login": now, "last_credit_reset": time.strftime("%Y-%m-%d"),
        "settings": dict(DEFAULT_SETTINGS)}
    save_users(users)
    return jsonify({"success": True, "message": "Account created successfully", "uid": uid})

@app.route("/login", methods=["POST"])
def login_user():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    password = data.get("password", "")
    users = load_users()
    user = users.get(email)
    if not user or user.get("password") != password:
        return jsonify({"success": False, "message": "Invalid email or password"}), 400
    user["last_login"] = time.strftime("%Y-%m-%d %H:%M:%S")
    save_users(users)
    session_token = issue_session(email)
    return jsonify({"success": True, "name": user.get("name"), "uid": user.get("uid"),
        "email": email, "session": session_token, "settings": user.get("settings")})

@app.route("/profile", methods=["POST"])
def get_profile():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    users = load_users()
    user = users.get(email)
    if not user: return jsonify({"success": False, "message": "User not found"}), 404
    return jsonify({"success": True, "name": user.get("name"), "email": email, "uid": user.get("uid"),
        "settings": user.get("settings")})

@app.route("/use-credit", methods=["POST"])
def use_credit():
    return jsonify({"success": True, "credit": "unlimited", "credit_type": "pro"})

@app.route("/save-settings", methods=["POST"])
def save_settings_route():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    settings = data.get("settings")
    if not email or not isinstance(settings, dict):
        return jsonify({"success": False, "message": "Email and settings object required"}), 400
    users = load_users()
    if email not in users: return jsonify({"success": False, "message": "User not found"}), 404
    existing = users[email].get("settings", dict(DEFAULT_SETTINGS))
    if not isinstance(existing, dict): existing = dict(DEFAULT_SETTINGS)
    existing.update(settings)
    users[email]["settings"] = existing
    save_users(users)
    return jsonify({"success": True})

@app.route("/get-settings", methods=["POST"])
def get_settings_route():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip()
    users = load_users()
    if email not in users: return jsonify({"success": False, "message": "User not found"}), 404
    return jsonify({"success": True, "settings": users[email].get("settings", dict(DEFAULT_SETTINGS))})

@app.route("/save-signal", methods=["POST"])
def save_signal_route():
    data = request.get_json(silent=True) or {}
    pair = str(data.get("pair", "")).strip()
    time_str = str(data.get("time", "")).strip()
    direction = str(data.get("direction", "")).strip().upper()
    if not pair or not time_str or direction not in ("BUY", "SELL", "CALL", "PUT"):
        return jsonify({"success": False, "message": "pair, time and direction required"}), 400
    register_signal(pair, time_str, direction)
    return jsonify({"success": True, "pair": pair, "time": time_str, "direction": direction})

@app.route("/clear-signals", methods=["POST"])
def clear_signals_route():
    data = request.get_json(silent=True) or {}
    pair = str(data.get("pair", "")).strip()
    clear_signals(pair or None)
    return jsonify({"success": True, "cleared": pair or "ALL"})

@app.route("/reset-results", methods=["POST"])
def reset_results_route():
    clear_signals(None)
    return jsonify({"success": True, "message": "Results reset"})

@app.route("/record-result", methods=["POST"])
def record_result_route():
    return jsonify({"success": True, "stats": {"wins": 0, "losses": 0, "streakW": 0, "streakL": 0}})

@app.route("/trade-history", methods=["POST"])
def trade_history_route():
    return jsonify({"success": True, "stats": {"wins": 0, "losses": 0, "streakW": 0, "streakL": 0}, "history": []})

@app.route("/total-users", methods=["GET"])
def total_users():
    return jsonify({"success": True, "count": 1, "total": 1})

@app.route("/bot-status", methods=["GET"])
def bot_status_route():
    return jsonify({"success": True, "online": bool(q_instance is not None and BOT_FEED_STATE.get("logged_in")),
        "status": BOT_FEED_STATE.get("status", "unknown")})

@app.route("/ban-status", methods=["POST"])
def ban_status_route():
    return jsonify({"success": True, "banned": False})

@app.route("/admin-check", methods=["POST"])
def admin_check_route():
    return jsonify({"success": True, "is_admin": False})


def draw_dashed_line(draw, start, end, color, width=1, dash_length=5):
    import math
    x1, y1 = start
    x2, y2 = end
    dx, dy = x2 - x1, y2 - y1
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0: return
    dx /= length; dy /= length
    drawn = 0.0
    while drawn < length:
        seg = min(dash_length, length - drawn)
        draw.line([(x1 + dx * drawn, y1 + dy * drawn),
                   (x1 + dx * (drawn + seg), y1 + dy * (drawn + seg))], fill=color, width=width)
        drawn += dash_length * 2

def create_chart_image_api(pair, candles, signal_name="RAVITH-PRO"):
    if not candles or Image is None: return None
    candles = list(reversed(candles))
    WIDTH, HEIGHT = 900, 500
    BACKGROUND_COLOR = (10, 10, 20)
    GREEN = (0, 200, 0); RED = (255, 50, 50); BLUE = (0, 150, 255)
    YELLOW = (255, 255, 0); WHITE = (255, 255, 255); GRAY = (100, 100, 100)
    DARK_GRAY = (50, 50, 50); LIGHT_BLUE = (100, 200, 255); DARK_BLUE = (20, 20, 40)
    img = Image.new('RGB', (WIDTH, HEIGHT), color=BACKGROUND_COLOR)
    try:
        with urllib.request.urlopen(CHART_BACKGROUND_IMAGE_URL, timeout=5) as url:
            bg_img = Image.open(BytesIO(url.read())).convert("RGBA").resize((WIDTH, HEIGHT))
        bg_img.putdata([(p[0], p[1], p[2], 100) if p[3] > 0 else p for p in bg_img.getdata()])
        img = Image.alpha_composite(Image.new('RGBA', (WIDTH, HEIGHT), BACKGROUND_COLOR + (255,)), bg_img).convert('RGB')
    except Exception as e:
        print(f"bg image error: {e}")
    draw = ImageDraw.Draw(img)
    try:
        font_large = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 24)
        font_medium = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
        font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
        font_tiny = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 10)
    except:
        font_large = font_medium = font_small = font_tiny = ImageFont.load_default()
    header_y = 15
    title_text = f"{pair.replace('_otc', '-OTC').upper()} {signal_name} SIGNAL: "
    draw.text((20, header_y), title_text, fill=LIGHT_BLUE, font=font_large)
    title_w = draw.textlength(title_text, font=font_large)
    latest = candles[-1]
    latest_dir = "BUY" if latest['close'] > latest['open'] else "SELL"
    draw.text((20 + title_w, header_y), latest_dir, fill=GREEN if latest_dir == "BUY" else RED, font=font_large)
    count_text = f" | Candles: {len(candles)}"
    draw.text((20 + title_w + draw.textlength(latest_dir, font=font_large) + 10, header_y + 5),
              count_text, fill=YELLOW, font=font_medium)
    bma_y = 50
    x_pos = 20
    for t, c in zip(["BMA 9", "BMA 21", "BMA 30", "3IGNAL"], [YELLOW, BLUE, RED, GREEN]):
        draw.text((x_pos, bma_y), t, fill=c, font=font_medium)
        x_pos += draw.textlength(t, font=font_medium) + 20
    draw.text((x_pos, bma_y), "EMA: BULLISH", fill=GREEN, font=font_medium)
    all_prices = [c['high'] for c in candles] + [c['low'] for c in candles]
    min_price = min(all_prices) * 0.9998
    max_price = max(all_prices) * 1.0002
    price_range = max_price - min_price or max_price * 0.001
    CHART_AREA_LEFT, CHART_AREA_TOP, CHART_AREA_WIDTH, CHART_AREA_HEIGHT = 100, 80, 650, 350
    draw.rectangle([CHART_AREA_LEFT, CHART_AREA_TOP, CHART_AREA_LEFT + CHART_AREA_WIDTH,
                    CHART_AREA_TOP + CHART_AREA_HEIGHT], outline=DARK_GRAY, width=2)
    def sy(p): return CHART_AREA_TOP + CHART_AREA_HEIGHT - int((p - min_price) / price_range * CHART_AREA_HEIGHT)
    for i in range(5):
        y = CHART_AREA_TOP + int(i * CHART_AREA_HEIGHT / 4)
        draw.line([(CHART_AREA_LEFT, y), (CHART_AREA_LEFT + CHART_AREA_WIDTH, y)], fill=DARK_GRAY, width=1)
    ideal_w, ideal_sp = 10, 5
    n = len(candles)
    total_w = n * (ideal_w + ideal_sp) - ideal_sp
    if total_w > CHART_AREA_WIDTH:
        sf = CHART_AREA_WIDTH / total_w
        cw, sp = max(3, int(ideal_w * sf)), int(ideal_sp * sf)
    else:
        cw, sp = ideal_w, ideal_sp
    start_x = CHART_AREA_LEFT + cw // 2
    for i, candle in enumerate(candles):
        xc = start_x + i * (cw + sp)
        if xc > CHART_AREA_LEFT + CHART_AREA_WIDTH: break
        xl, xr = xc - cw // 2, xc + cw // 2
        yh, yl = sy(candle['high']), sy(candle['low'])
        draw.line([(xc, yh), (xc, yl)], fill=WHITE, width=1)
        bull = candle['close'] > candle['open']
        bc = GREEN if bull else RED
        yo, yc = sy(candle['open']), sy(candle['close'])
        yt, yb = min(yo, yc), max(yo, yc)
        yb = max(yb, yt + 2)
        draw.rectangle([xl + 1, yt, xr - 1, yb], fill=bc, outline=bc)
        draw.rectangle([xl, yt, xr, yb], outline=bc, width=1)
    lp = latest['close']
    yp = sy(lp)
    draw_dashed_line(draw, (CHART_AREA_LEFT, yp), (CHART_AREA_LEFT + CHART_AREA_WIDTH, yp), YELLOW, 2, 8)
    draw.rectangle([CHART_AREA_LEFT + CHART_AREA_WIDTH - 60, yp - 10,
                    CHART_AREA_LEFT + CHART_AREA_WIDTH, yp + 10], fill=YELLOW)
    draw.text((CHART_AREA_LEFT + CHART_AREA_WIDTH - 55, yp - 7), f"{lp:.4f}", fill=(0, 0, 0), font=font_tiny)
    ix, iy = CHART_AREA_LEFT + CHART_AREA_WIDTH + 20, CHART_AREA_TOP
    draw.rectangle([ix - 10, iy - 10, WIDTH - 20, iy + 250], fill=DARK_BLUE, outline=GRAY)
    draw.text((ix, iy), "BULLTERMINAL", fill=GREEN, font=font_medium)
    draw.text((ix, iy + 25), "PRICE TERMINAL", fill=BLUE, font=font_medium)
    closes = [c['close'] for c in candles]
    sma9 = sum(closes[-9:]) / min(9, len(closes))
    sma21 = sum(closes[-21:]) / min(21, len(closes))
    sma30 = sum(closes[-30:]) / min(30, len(closes))
    sig = latest.get('signal') or ('CALL' if latest['close'] > latest['open'] else 'PUT')
    info = [(f"SMA 9: {sma9:.4f}", GREEN if sma9 > lp else RED),
            (f"SMA 21: {sma21:.4f}", GREEN if sma21 > lp else RED),
            (f"SMA 30: {sma30:.4f}", GREEN if sma30 > lp else RED),
            (f"Current: {lp:.4f}", GREEN if sig == "CALL" else RED),
            (f"High: {latest['high']:.4f}", GREEN),
            (f"Low: {latest['low']:.4f}", RED),
            (f"Open: {latest['open']:.4f}", GRAY),
            (f"Signal: {sig}", GREEN if sig == "CALL" else RED)]
    for i, (t, c) in enumerate(info): draw.text((ix, iy + 55 + i * 20), t, fill=c, font=font_small)
    draw.line([(ix, iy + 210), (WIDTH - 30, iy + 210)], fill=GRAY, width=1)
    draw.text((ix, iy + 220), f"BULLTERMINAL + {len(candles)} CANDLES", fill=GREEN, font=font_medium)
    by = HEIGHT - 40
    draw.rectangle([10, by - 5, WIDTH - 10, by + 30], fill=DARK_BLUE, outline=GRAY)
    tstr = (latest.get('time') or '')[11:] or "00:00:00"
    draw.text((20, by), f"TIME: {tstr}", fill=WHITE, font=font_small)
    draw.text((200, by), f"OPEN: {latest['open']:.5f}", fill=GRAY, font=font_small)
    draw.text((350, by), f"CLOSE: {latest['close']:.5f}", fill=GREEN if sig == "CALL" else RED, font=font_small)
    draw.text((500, by), f"HIGH: {latest['high']:.5f}", fill=GREEN, font=font_small)
    draw.text((650, by), f"LOW: {latest['low']:.5f}", fill=RED, font=font_small)
    sbx = WIDTH - 120
    sc = GREEN if sig == "CALL" else RED
    draw.rectangle([sbx, by, sbx + 100, by + 25], fill=sc, outline=WHITE)
    st = f"SIGNAL: {sig}"
    draw.text((sbx + (100 - draw.textlength(st, font=font_medium)) // 2, by + 3), st, fill=(0, 0, 0), font=font_medium)
    draw.rectangle([5, 5, WIDTH - 5, HEIGHT - 5], outline=GRAY, width=2)
    img = img.resize((WIDTH * 2, HEIGHT * 2), Image.LANCZOS)
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer

@app.route('/chart_image', methods=['GET'])
def chart_image_handler():
    pair = request.args.get("Pair") or request.args.get("pair")
    ss_name = request.args.get("SS", "RAVITH-PRO")
    timeframe = request.args.get("Time") or request.args.get("time") or "1m"
    candle_param = request.args.get("Candle")
    candle_count = 60
    if candle_param:
        try:
            candle_count = int(candle_param)
            if candle_count < 1 or candle_count > 500:
                return jsonify({"error": "Candle count must be 1-500"}), 400
        except ValueError:
            return jsonify({"error": "Candle count must be a number"}), 400
    if not pair: return jsonify({"error": "Use: ?Pair=USDPHP_otc"}), 400
    if Image is None: return jsonify({"error": "Pillow not installed on server (pip install pillow)"}), 500
    candles, running = get_candles_with_running(pair, timeframe, candle_count)
    if not candles: return jsonify({"error": f"No data for {pair}"}), 404
    try:
        buf = create_chart_image_api(pair, candles, ss_name)
        if buf: return send_file(buf, mimetype='image/png')
        return jsonify({"error": "Chart generation failed"}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


AUTO_TRADE_LOOP = None
QUOTEX_AUTO_LOCK = threading.Lock()
QUOTEX_AUTO_STATE = {}


def _candle_start_key(time_str):
    try:
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2}):(\d{2})", str(time_str or ""))
        if not m: return None
        y, mo, d, h, mi, s = (int(x) for x in m.groups())
        return int(datetime(y, mo, d, h, mi, s, tzinfo=timezone.utc).timestamp())
    except Exception:
        return None

def _live_candle_key(pair):
    rc = RUNNING_CANDLES.get(pair, {}).get("1m")
    if rc and isinstance(rc.get("start"), (int, float)): return int(rc["start"])
    return None

def _live_candle_info(pair):
    rc = RUNNING_CANDLES.get(pair, {}).get("1m")
    if not rc: return None, None
    key = int(rc["start"]) if isinstance(rc.get("start"), (int, float)) else None
    dt = ts_to_dt(rc.get("start"))
    tstr = dt.strftime("%Y-%m-%d %H:%M:%S") if dt else None
    return key, tstr


async def _live_candle_wait_for(trade, pair, target_time, poll=0.25, max_grace_sec=180):
    target_key = _candle_start_key(target_time)
    if target_key is None: return "no-target"
    last_seen_key = None
    last_change = time.monotonic()
    while True:
        if trade.get("cancelled"): return "cancelled"
        live_key, _live_t = _live_candle_info(pair)
        if live_key is None:
            if time.monotonic() - last_change > max_grace_sec: return "stalled"
            await asyncio.sleep(0.5)
            continue
        if live_key != last_seen_key:
            last_seen_key = live_key
            last_change = time.monotonic()
        elif time.monotonic() - last_change > max_grace_sec:
            return "stalled"
        if live_key == target_key: return "entered"
        if live_key > target_key: return "missed"
        await asyncio.sleep(poll)


def _auto_new_account():
    return {"client": None, "connected": False, "account_type": "demo", "balance": 0.0,
        "settings": {"enabled": False, "trade_amount": 2.0, "take_profit": 10.0,
                     "stop_loss": 20.0, "mtg_steps": 0, "account_type": "demo"},
        "session": {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0},
        "trade": None, "last_result": None}

def _auto_get(email):
    with QUOTEX_AUTO_LOCK:
        if email not in QUOTEX_AUTO_STATE:
            QUOTEX_AUTO_STATE[email] = _auto_new_account()
        return QUOTEX_AUTO_STATE[email]

def _auto_update_settings(acc, s):
    if not isinstance(s, dict): return
    st = acc["settings"]
    try:
        if "enabled" in s: st["enabled"] = bool(s["enabled"])
        if "trade_amount" in s: st["trade_amount"] = max(1.0, float(s["trade_amount"]))
        if "take_profit" in s: st["take_profit"] = float(s["take_profit"])
        if "stop_loss" in s: st["stop_loss"] = abs(float(s["stop_loss"]))
        if "mtg_steps" in s: st["mtg_steps"] = max(0, min(3, int(s["mtg_steps"])))
        if s.get("account_type") in ("demo", "real"): st["account_type"] = s["account_type"]
    except Exception: pass

def _auto_stop_limits_hit(acc):
    pnl = acc["session"]["pnl"]
    if acc["settings"]["take_profit"] > 0 and pnl >= acc["settings"]["take_profit"]: return "TP"
    if acc["settings"]["stop_loss"] > 0 and pnl <= -abs(acc["settings"]["stop_loss"]): return "SL"
    return None

def _auto_status_dict(acc):
    d = {"success": True, "connected": bool(acc["connected"]), "account_type": acc["account_type"],
         "balance": acc["balance"], "session": dict(acc["session"]), "settings": dict(acc["settings"]),
         "last_result": acc.get("last_result")}
    if acc["trade"]:
        d["trade"] = {k: acc["trade"].get(k) for k in ("pair", "direction", "amount", "pending", "target_time", "mtg_level")}
    return d


async def _auto_trade_cycle(email, pair, direction, target_time, payout, mtg_level, amount):
    acc = _auto_get(email)
    trade = acc["trade"]
    client = acc["client"]
    try:
        trade["pending"] = True
        wait_result = await _live_candle_wait_for(trade, pair, target_time)
        trade["pending"] = False
        if wait_result == "cancelled": return
        if wait_result == "missed": acc["last_result"] = "MISSED"; return
        if wait_result == "stalled": acc["last_result"] = "FEED-DEAD"; return
        if wait_result != "entered": acc["last_result"] = "NO-TARGET"; return
        if not acc["connected"] or client is None: return
        if trade.get("entry_triggered"): return
        trade["entry_triggered"] = True
        try:
            bal = await client.get_balance()
            if isinstance(bal, (int, float)):
                acc["balance"] = float(bal)
                if acc["balance"] < amount: return
        except Exception: pass
        status, info = False, {}
        try: status, info = await client.buy(amount, pair, direction, 1)
        except Exception as e: print(f"⚠️ auto-trade buy error: {e}")
        if not status: return
        order_id = info.get("id") if isinstance(info, dict) else None
        await asyncio.sleep(65)
        win = None
        if order_id:
            try: win = await client.check_win(order_id)
            except Exception: win = None
        ses = acc["session"]
        ses["trades"] += 1
        if win is True:
            profit = round(amount * (float(payout) if payout else 80.0) / 100.0, 2)
            ses["pnl"] = round(ses["pnl"] + profit, 2); ses["wins"] += 1
            acc["last_result"] = "WIN"
        elif win is False:
            ses["pnl"] = round(ses["pnl"] - amount, 2); ses["losses"] += 1
            acc["last_result"] = "LOSS"
        else: acc["last_result"] = "UNKNOWN"
        if _auto_stop_limits_hit(acc): acc["settings"]["enabled"] = False
    except Exception as e:
        print(f"⚠️ auto-trade cycle error: {e}")
    finally:
        acc["trade"] = None

def _auto_launch(email, pair, direction, target_time, payout, mtg_level, amount):
    acc = _auto_get(email)
    if AUTO_TRADE_LOOP is None: return False
    acc["trade"] = {"pair": pair, "direction": direction, "amount": amount,
        "target_time": target_time, "payout": payout, "mtg_level": mtg_level,
        "pending": True, "cancelled": False, "entry_triggered": False}
    asyncio.run_coroutine_threadsafe(
        _auto_trade_cycle(email, pair, direction, target_time, payout, mtg_level, amount),
        AUTO_TRADE_LOOP)
    return True


@app.route("/quotex-login", methods=["POST"])
def quotex_login_route():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip() or "default"
    ssid_token = (data.get("ssid_token") or "").strip()
    csrf_token = (data.get("csrf_token") or "").strip()
    account_type = str(data.get("account_type", "demo")).lower()
    if account_type not in ("demo", "real"): account_type = "demo"
    if not ssid_token:
        return jsonify({"success": False, "message": "Quotex SSID token required"}), 400
    acc = _auto_get(email)
    _auto_update_settings(acc, data.get("settings"))
    acc["settings"]["account_type"] = account_type
    async def _do_connect():
        client = Quotex(lang="en", ssid_token=ssid_token,
                        csrf_token=csrf_token or None,
                        user_agent=QUOTEX_USER_AGENT)
        client.set_token_csrf(ssid_token, csrf_token or None,
                              user_agent=QUOTEX_USER_AGENT)
        try: success, reason = await client.connect()
        except Exception as e: return None, str(e)
        if not success: return None, str(reason)
        try: await client.change_account("PRACTICE" if account_type == "demo" else "REAL")
        except Exception: pass
        bal = 0.0
        try: bal = await client.get_balance()
        except Exception: pass
        return client, bal
    if AUTO_TRADE_LOOP is None:
        return jsonify({"success": False, "message": "Trade engine starting, retry in a moment"}), 200
    try:
        future = asyncio.run_coroutine_threadsafe(_do_connect(), AUTO_TRADE_LOOP)
        client, bal = future.result(timeout=60)
    except Exception as e:
        return jsonify({"success": False, "message": f"Connection error: {e}"}), 200
    if client is None:
        return jsonify({"success": False, "message": f"Login failed: {bal}"}), 200
    acc["client"] = client
    acc["connected"] = True
    acc["account_type"] = account_type
    acc["balance"] = float(bal) if isinstance(bal, (int, float)) else 0.0
    acc["session"] = {"pnl": 0.0, "trades": 0, "wins": 0, "losses": 0}
    return jsonify({"success": True, "connected": True, "account_type": account_type, "balance": acc["balance"]})

@app.route("/quotex-disconnect", methods=["POST"])
def quotex_disconnect_route():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip() or "default"
    acc = _auto_get(email)
    acc["connected"] = False
    acc["settings"]["enabled"] = False
    if acc["trade"]:
        acc["trade"]["cancelled"] = True
        acc["trade"] = None
    client = acc.get("client")
    acc["client"] = None
    if client is not None and AUTO_TRADE_LOOP is not None:
        async def _close(c):
            try: await c.close()
            except Exception: pass
        try: asyncio.run_coroutine_threadsafe(_close(client), AUTO_TRADE_LOOP)
        except Exception: pass
    return jsonify({"success": True, "message": "Disconnected"})

@app.route("/quotex-status", methods=["POST"])
def quotex_status_route():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip() or "default"
    acc = _auto_get(email)
    _auto_update_settings(acc, data.get("settings"))
    return jsonify(_auto_status_dict(acc))

@app.route("/auto-trade", methods=["POST"])
def auto_trade_route():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip() or "default"
    pair = (data.get("pair") or "").replace("-OTC", "_otc")
    time_str = data.get("time") or ""
    direction = str(data.get("direction") or "").upper()
    payout = data.get("payout") or 0
    acc = _auto_get(email)
    _auto_update_settings(acc, data.get("settings"))
    if not acc["settings"]["enabled"]:
        return jsonify({"success": True, "queued": False, "reason": "disabled", "message": "Auto trade is OFF"})
    if not acc["connected"] or acc["client"] is None:
        return jsonify({"success": False, "queued": False, "reason": "offline", "message": "Quotex not connected"})
    if acc["trade"] is not None:
        return jsonify({"success": False, "queued": False, "reason": "busy"})
    if direction not in ("BUY", "SELL"):
        return jsonify({"success": False, "queued": False, "reason": "bad-direction"})
    amount = round(float(acc["settings"]["trade_amount"]), 2)
    ok = _auto_launch(email, pair, "call" if direction == "BUY" else "put", time_str, payout, 0, amount)
    if not ok:
        return jsonify({"success": False, "queued": False, "message": "Engine loop not ready"}), 503
    return jsonify({"success": True, "queued": True, "pair": pair, "direction": direction, "amount": amount})

@app.route("/auto-trade/decision", methods=["POST"])
def auto_trade_decision_route():
    return jsonify({"success": True, "place": False, "reason": "not-needed"})

@app.route("/auto-trade/cancel", methods=["POST"])
def auto_trade_cancel_route():
    data = request.get_json(silent=True) or {}
    email = data.get("email", "").strip() or "default"
    acc = _auto_get(email)
    cancelled = False
    if acc["trade"] and acc["trade"].get("pending"):
        acc["trade"]["cancelled"] = True
        acc["trade"] = None
        cancelled = True
    return jsonify({"success": True, "cancelled": cancelled})


if __name__ == "__main__":
    import sys
    from telegram_runtime import run
    run(sys.modules[__name__])
