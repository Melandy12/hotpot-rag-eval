# -*- coding: utf-8 -*-
"""本地问答演示界面（全本地、零外发）

为什么不用 SAG 桌面端：桌面端走的是"模型自己发起工具调用"的 agent 循环，
7B 在只有 schema、没有格式示例的提示下会把调用写坏（缺 <tool_call> 开标签、
自己编 path），于是只检索不回答。这里改成**检索先行**：程序自己检索、自己拼证据、
模型只负责照着证据写答案——30 题整批 30/30 走的就是这条链路。

用法：
    python ui_server.py            # 默认 127.0.0.1:8600
    python ui_server.py 8700       # 换端口
前置：Ollama 11434 在线（模型 qwen25-7b-local）
"""
import importlib.util
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
LA_PATH = os.path.join(HERE, "11_local_answer.py")

spec = importlib.util.spec_from_file_location("la", LA_PATH)
la = importlib.util.module_from_spec(spec)
spec.loader.exec_module(la)

PAGE = """<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>火锅底料风味稳定性管控 · 本地问答</title>
<style>
:root{--bg:#0f1419;--panel:#171d24;--line:#28323c;--txt:#e6edf3;--dim:#8b98a5;--acc:#2ea043;--warn:#d29922}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);font:15px/1.65 "Microsoft YaHei","Segoe UI",sans-serif}
.wrap{max-width:980px;margin:0 auto;padding:28px 20px 64px}
h1{font-size:20px;margin:0 0 4px}
.sub{color:var(--dim);font-size:13px;margin-bottom:22px}
.tag{display:inline-block;border:1px solid var(--line);border-radius:999px;padding:2px 10px;font-size:12px;color:var(--dim);margin-right:6px}
.tag.on{color:var(--acc);border-color:#2a5535}
.box{display:flex;gap:10px;margin-bottom:14px}
input[type=text]{flex:1;background:var(--panel);border:1px solid var(--line);border-radius:10px;color:var(--txt);padding:12px 14px;font-size:15px;outline:none}
input[type=text]:focus{border-color:#3d5568}
button{background:var(--acc);border:0;border-radius:10px;color:#fff;padding:12px 22px;font-size:15px;cursor:pointer}
button:disabled{opacity:.55;cursor:default}
.hints{color:var(--dim);font-size:12.5px;margin-bottom:20px}
.hints span{cursor:pointer;border-bottom:1px dashed #3d5568;margin-right:14px}
.sec{margin-top:22px}
.sec h2{font-size:13px;letter-spacing:.05em;color:var(--dim);font-weight:400;margin:0 0 10px;text-transform:uppercase}
.ans{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--acc);border-radius:10px;padding:16px 18px;white-space:pre-wrap}
.ev{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin-bottom:8px}
.ev .hd{font-size:13px;color:var(--txt)}
.ev .id{color:var(--acc);font-weight:600;margin-right:8px}
.ev .file{color:var(--dim);font-size:12px;margin-top:2px}
.meta{color:var(--dim);font-size:12.5px;margin-top:10px}
.err{color:#f85149}
</style></head><body><div class="wrap">
<h1>火锅底料风味稳定性 · 本地知识库问答</h1>
<div class="sub">SAG Wiki 检索（FTS5 + BM25 + Jev 词法决策）→ 重排 → 本地 qwen25-7b-local 生成 · 全程 127.0.0.1，无外发</div>
<div class="box">
  <input id="q" type="text" placeholder="例如：水分 有没有限值 超多少算超标" autocomplete="off">
  <button id="go">提问</button>
</div>
<div class="hints">试试：
  <span class="h" onclick="fill(this)">底料煮出来汤发黑是咋回事</span>
  <span class="h" onclick="fill(this)">水分 有没有限值 超多少算超标</span>
  <span class="h" onclick="fill(this)">底料放两个月就不香了，是不是坏了</span>
  <span class="h" onclick="fill(this)">酸价限值按哪几个标准</span>
</div>
<div id="out"></div>
</div>
<script>
function fill(el){const t=document.getElementById('q');t.value=el.textContent.trim();t.focus();}
const go=document.getElementById('go'),q=document.getElementById('q'),out=document.getElementById('out');
async function ask(){
  const s=q.value.trim(); if(!s) return;
  go.disabled=true; out.innerHTML='<div class="meta">检索中…（约 7 秒）</div>';
  try{
    const r=await fetch('/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({q:s})});
    const d=await r.json();
    if(d.error){out.innerHTML='<div class="meta err">'+d.error+'</div>';return;}
    const tags=d.rules.map(x=>'<span class="tag on">'+x+'</span>').join('');
    let h='<div class="sec"><h2>回答</h2><div class="ans">'+esc(d.answer)+'</div>'+
          '<div class="meta">耗时 '+d.secs+' 秒 · 证据 '+d.ev.length+' 条 '+(tags?'· '+tags:'')+'</div></div>';
    h+='<div class="sec"><h2>命中的证据（前五）</h2>';
    d.ev.forEach(function(e,i){h+='<div class="ev"><div class="hd"><span class="id">'+(i+1)+'</span>'+esc(e.heading||'(无标题)')+
      '</div><div class="file">'+esc(e.path)+'</div></div>';});
    h+='</div>';
    out.innerHTML=h;
  }catch(e){out.innerHTML='<div class="meta err">请求失败：'+esc(e.message)+'</div>';}
  finally{go.disabled=false;}
}
function esc(s){return (s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
go.onclick=ask; q.addEventListener('keydown',function(e){if(e.key==='Enter')ask();});
</script></body></html>"""


def rules_of(q, items):
    tags = []
    if ("水分" in q) and any(k in q for k in ("限值", "超标", "多少", "判定", "合格", "上限", "临界")):
        tags.append("水分口径规则")
    if any(k in q for k in ("煮", "加热", "下锅", "涮", "开锅", "烧")):
        tags.append("使用端归因")
    elif any(k in q for k in ("放两个月", "放三个月", "存放", "储存", "保质期", "货架", "久了", "不香")):
        tags.append("货架端归因")
    return tags


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, ctype, body):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self._send(200, "text/html; charset=utf-8", PAGE.encode("utf-8"))
        else:
            self._send(404, "text/plain", b"not found")

    def do_POST(self):
        if self.path != "/ask":
            self._send(404, "text/plain", b"not found")
            return
        try:
            n = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(n).decode("utf-8") or "{}")
            q = (data.get("q") or "").strip()
            if not q:
                self._send(200, "application/json", json.dumps({"error": "问题为空"}, ensure_ascii=False).encode("utf-8"))
                return
            t0 = time.time()
            items, ans = la.ask(q)
            secs = round(time.time() - t0, 1)
            ev = [{"path": it["path"], "heading": it["heading"]} for it in items]
            body = json.dumps({"answer": ans, "ev": ev, "secs": secs, "rules": rules_of(q, items)},
                              ensure_ascii=False).encode("utf-8")
            self._send(200, "application/json; charset=utf-8", body)
        except Exception as e:
            self._send(200, "application/json",
                       json.dumps({"error": "%s: %s" % (type(e).__name__, e)}, ensure_ascii=False).encode("utf-8"))


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8600
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    print("本地问答界面已启动：http://127.0.0.1:%d" % port, flush=True)
    print("按 Ctrl+C 停止", flush=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        srv.shutdown()
        print("已停止", flush=True)
