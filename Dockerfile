FROM cloudflare/cloudflared:latest AS tunnel
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data
WORKDIR /app
COPY --from=tunnel /usr/local/bin/cloudflared /usr/local/bin/cloudflared
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN python vendor_bootstrap.py && python -m py_compile HyperTrade_TokenCSRF.py telegram_runtime.py server.py
EXPOSE 5000
CMD ["python", "HyperTrade_TokenCSRF.py"]
