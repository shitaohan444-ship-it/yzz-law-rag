"""局域网反向代理：把本机局域网端口转发到阿里云企业微信聊天归档后台。

用法：
    python lan_proxy.py

默认：
    监听  0.0.0.0:18192   （本机所有网卡，含局域网 192.168.0.88）
    转发  http://127.0.0.1:18191  （SSH 隧道到阿里云 wecom-archive 的归档后台）

局域网其他设备访问： http://192.168.0.88:18192/admin
依赖：仅 requests（venv 已装）。流式转发以支持 ZIP 导出下载。
"""
from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import requests

LISTEN_HOST = os.getenv("LAN_PROXY_HOST", "0.0.0.0")
LISTEN_PORT = int(os.getenv("LAN_PROXY_PORT", "18192"))
# 转发目标 = SSH 隧道在本机的回环端口（127.0.0.1:18191 -> 阿里云归档后台）
TARGET = os.getenv("LAN_PROXY_TARGET", "http://127.0.0.1:18191").rstrip("/")

# 不转发/不回写的逐跳头（hop-by-hop）
HOP_BY_HOP = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "content-length",
    "host", "content-encoding",
}


class ProxyHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _proxy(self) -> None:
        url = TARGET + self.path
        body = None
        length = self.headers.get("Content-Length")
        if length:
            body = self.rfile.read(int(length))
        fwd_headers = {
            k: v for k, v in self.headers.items() if k.lower() not in HOP_BY_HOP
        }
        try:
            resp = requests.request(
                self.command, url, headers=fwd_headers, data=body,
                stream=True, timeout=120, allow_redirects=False,
            )
        except requests.RequestException as exc:  # 隧道断开/后端不可达
            msg = f"502 Bad Gateway: cannot reach archive backend ({exc})".encode()
            self.send_response(502)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)
            return

        self.send_response(resp.status_code)
        for k, v in resp.headers.items():
            if k.lower() in HOP_BY_HOP:
                continue
            self.send_header(k, v)
        # 流式回写（ZIP 导出可能较大，不能整读进内存）
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()
        try:
            for chunk in resp.iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                self.wfile.write(b"%X\r\n" % len(chunk))
                self.wfile.write(chunk)
                self.wfile.write(b"\r\n")
            self.wfile.write(b"0\r\n\r\n")
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            resp.close()

    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_DELETE = _proxy
    do_PATCH = _proxy
    do_HEAD = _proxy
    do_OPTIONS = _proxy

    def log_message(self, fmt: str, *args) -> None:  # 静默访问日志
        return


if __name__ == "__main__":
    server = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), ProxyHandler)
    print(f"[lan-proxy] listening on {LISTEN_HOST}:{LISTEN_PORT} -> {TARGET}")
    print(f"[lan-proxy] LAN 访问: http://192.168.0.88:{LISTEN_PORT}/admin")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
