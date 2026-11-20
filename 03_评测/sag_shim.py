# -*- coding: utf-8 -*-
"""SAG 桌面端 ↔ 本地链路 的适配层（OpenAI 兼容）

背景：
  SAG 桌面问答页的工作方式是"把问题丢给模型 → 模型自己发工具调用 → SAG 拿 path 去检索"，
  但它的"全库模式"传的是空 path，直接报 os error 3；7B 还会把工具名写错成 sag2_search。
  与其逼模型学会 agent 协议，不如让它收不到 tools：本服务对 SAG 表现为一个 OpenAI 接口，
  收到请求后自己完成"检索 + 生成"，把答案当成普通回复返回。桌面端界面完全不用改。

用法：
  python sag_shim.py            # 127.0.0.1:8700
  python sag_shim.py 8701

SAG 设置里把"问答模型"填：
  Base URL: http://127.0.0.1:8700/v1
  API Key:  sk-local
  模型名:   local-rag
"""
import importlib.util
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
LA_PATH = os.path.join(HERE, "11_local_answer.py")

spec = importlib.util.spec_from_file_location("la", LA_PATH)
la = importlib.util.module_from_spec(spec)
spec.loader.exec_module(la)

MODEL_NAME = "local-rag"
LOG = os.path.join(os.environ.get("ZJ_TOOLS_DIR", "<请配置外部工具目录 _tools>"), 'sag_shim.log')


def log(msg):
    try:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write("%s %s\n" % (time.strftime("%H:%M:%S"), msg))
    except Exception:
        pass


def last_user_text(messages):
    """取最后一条用户消息。SAG 传过来的不是纯问题，而是一段 JSON：
    {"question": "...", "scope": [...], "references": ...}，需要把 question 抽出来。"""
    raw = ""
    for m in reversed(messages or []):
        if m.get("role") == "user":
            c = m.get("content")
            if isinstance(c, str):
                raw = c.strip()
            elif isinstance(c, list):
                raw = "".join(p.get("text", "") for p in c if isinstance(p, dict)).strip()
            break
    if raw.startswith("{"):
        try:
            obj = json.loads(raw)
            q = (obj.get("question") or obj.get("query") or "").strip()
            if q:
                return q
        except Exception:
            # 半截 JSON 也能救：抓 "question":"..." 这一段
            i = raw.find('"question"')
            if i >= 0:
                rest = raw[i + len('"question"'):]
                rest = rest.lstrip(" :")
                if rest.startswith('"'):
                    j = rest.find('"', 1)
                    if j > 0:
                        return rest[1:j].encode("utf-8").decode("unicode_escape", "ignore") if "\\u" in rest[1:j] else rest[1:j]
    return raw


def rag_answer(q):
    items, ans = la.ask(q)
    return items, ans


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json({"object": "list", "data": [
                {"id": MODEL_NAME, "object": "model", "owned_by": "local", "created": 0}
            ]})
        elif self.path in ("/", "/health"):
            self._json({"status": "ok", "model": MODEL_NAME})
        else:
            self._json({"error": "not found"}, 404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
        try:
            req = json.loads(raw.decode("utf-8") or "{}")
        except Exception:
            self._json({"error": {"message": "bad json"}}, 400)
            return
        path = self.path.rstrip("/")
        if not (path.endswith("/chat/completions") or path.endswith("/completions")):
            self._json({"error": {"message": "only chat/completions supported"}}, 404)
            return

        stream = bool(req.get("stream"))
        t0 = time.time()
        log("REQ stream=%s tools=%s bodyhead=%s" % (
            stream, "yes" if req.get("tools") else "no",
            raw.decode("utf-8", "ignore")[:300].replace("\n", " ")))
        try:
            q = last_user_text(req.get("messages"))
            if not q:
                raise ValueError("empty user message")
            items, ans = rag_answer(q)
            secs = round(time.time() - t0, 1)
            log("Q=%s | %d 证据 | %.1fs" % (q[:40], len(items), secs))
        except Exception as e:
            ans = "本地链路出错：%s: %s" % (type(e).__name__, e)
            log("ERR %s" % ans)
            items = []
            secs = round(time.time() - t0, 1)

        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        cid = "chatcmpl-%d" % int(time.time() * 1000)

        if stream:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True

            def emit(obj):
                s = "data: " + json.dumps(obj, ensure_ascii=False) + "\n\n"
                self.wfile.write(s.encode("utf-8"))

            base = {"id": cid, "object": "chat.completion.chunk", "created": int(time.time()), "model": MODEL_NAME}
            emit(dict(base, choices=[{"index": 0, "delta": {"role": "assistant"}, "finish_reason": None}]))
            buf = ans
            step = 60
            for i in range(0, len(buf), step):
                emit(dict(base, choices=[{"index": 0, "delta": {"content": buf[i:i + step]}, "finish_reason": None}]))
            emit(dict(base, choices=[{"index": 0, "delta": {}, "finish_reason": "stop"}], usage=usage))
            self.wfile.write(b"data: [DONE]\n\n")
            try:
                self.wfile.flush()
            except Exception:
                pass
        else:
            self._json({
                "id": cid,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": MODEL_NAME,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": ans}, "finish_reason": "stop"}],
                "usage": usage,
            })


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8700
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print("SAG 适配层已启动：http://127.0.0.1:%d/v1  模型名 %s" % (port, MODEL_NAME), flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        srv.shutdown()
