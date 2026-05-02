"""
ui_server.py — Chat UI for atomicAquaLangGraph AgentCore agent
Uses ONLY Python stdlib (http.server) — plus boto3 (already required by main.py).
Run:  python ui_server.py
Then open: http://localhost:8080
"""

import asyncio
import base64
import io
import json
import os
import sys
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

# ── Config (must be set BEFORE importing main.py) ─────────────────────
os.environ.setdefault("S3_BUCKET", "naspocuser-s3")
os.environ.setdefault("AWS_REGION", "ap-south-1")
os.environ.setdefault("KB_ID", "FH00WKSBPL")
# os.environ.setdefault("MEMORY_ID", "your-memory-id")
# os.environ.setdefault("GUARDRAIL_ID", "your-guardrail-id")

import boto3
from boto3.s3.transfer import TransferConfig
from botocore.config import Config as BotocoreConfig

# ── Import the agent's invoke function directly ───────────────────────
sys.path.insert(0, str(Path(__file__).parent))

import importlib
if 'main' in sys.modules:
    importlib.reload(sys.modules['main'])

from main import invoke as agent_invoke

# ── Keep the local constants in sync ──────────────────────────────────
S3_BUCKET      = os.environ["S3_BUCKET"]
S3_REGION      = os.environ["AWS_REGION"]
SIZE_THRESHOLD = 5 * 1024 * 1024
MAX_UPLOAD     = 350 * 1024 * 1024  # Increased to 350 MB to support 315 MB files

# ── Session management ────────────────────────────────────────────────
_sessions = {}
_uploads: dict[str, dict] = {}
_uploads_lock = threading.Lock()

_s3_client = None
def get_s3_client():
    global _s3_client
    if _s3_client is None:
        _s3_client = boto3.client(
            "s3",
            region_name=S3_REGION,
            config=BotocoreConfig(read_timeout=300),
        )
    return _s3_client


HTML = b"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>NovAtel Agent</title>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500&display=swap" rel="stylesheet"/>
<style>
  *,*::before,*::after{box-sizing:border-box;margin:0;padding:0;}
  :root{
    --black:#ffffff;
    --hexa-blue:#27a0bf;
    --hexa-dark-blue:#00516f;
    --bg:#f0f7fa;
    --surface:#ffffff;
    --border:#b8d9e6;
    --accent:#27a0bf;
    --accent-dim:#d0ecf4;
    --muted:#7ab5c9;
    --text:#00516f;
    --text-dim:#5a8fa0;
    --user-bg:#ddf0f7;
    --agent-bg:#ffffff;
    --radius:6px;
    --font-ui:'IBM Plex Sans',sans-serif;
    --font-mono:'IBM Plex Mono',monospace;
  }
  html,body{height:100%;background:var(--bg);color:var(--text);font-family:var(--font-ui);}
  .shell{display:grid;grid-template-rows:52px 1fr auto 72px;height:100vh;max-width:860px;margin:0 auto;}
  header{display:flex;align-items:center;gap:12px;padding:0 20px;border-bottom:1px solid #004560;background:#00516f;}
  .logo{width:28px;height:28px;background:#27a0bf;border-radius:4px;display:grid;place-items:center;flex-shrink:0;}
  .logo svg{width:16px;height:16px;}
  .title{font-family:var(--font-mono);font-size:13px;font-weight:500;letter-spacing:.04em;color:#ffffff;}
  .subtitle{font-size:11px;color:rgba(255,255,255,0.6);margin-top:1px;}
  .pill{margin-left:auto;font-family:var(--font-mono);font-size:10px;padding:3px 8px;border-radius:20px;border:1px solid rgba(39,160,191,0.5);color:#c8eef7;background:rgba(39,160,191,0.18);}
  #messages{overflow-y:auto;padding:24px 20px;display:flex;flex-direction:column;gap:16px;scroll-behavior:smooth;}
  #messages::-webkit-scrollbar{width:4px;}
  #messages::-webkit-scrollbar-thumb{background:var(--muted);border-radius:2px;}
  .msg{display:flex;gap:12px;animation:fadeUp .18s ease both;}
  @keyframes fadeUp{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:translateY(0)}}
  .msg.user{flex-direction:row-reverse;}
  .avatar{width:28px;height:28px;border-radius:50%;display:grid;place-items:center;font-family:var(--font-mono);font-size:10px;font-weight:500;flex-shrink:0;margin-top:2px;}
  .avatar.agent{background:var(--accent-dim);color:#00516f;border:1px solid #7dcce0;}
  .avatar.user{background:#b8e0ed;color:#00516f;border:1px solid #5ab8d4;}
  .bubble{max-width:680px;padding:12px 16px;border-radius:var(--radius);font-size:14px;line-height:1.65;white-space:pre-wrap;word-break:break-word;font-family:var(--font-mono);}
  .msg.agent .bubble{background:var(--agent-bg);border:1px solid var(--border);color:var(--text);}
  .msg.user .bubble{background:var(--user-bg);border:1px solid #7dcce0;color:#00516f;}
  .ts{font-size:10px;color:var(--text-dim);margin-top:4px;font-family:var(--font-mono);}
  .msg.user .ts{text-align:right;}
  .typing .bubble{display:flex;gap:5px;align-items:center;padding:14px 18px;}
  .dot{width:6px;height:6px;border-radius:50%;background:#27a0bf;animation:blink 1s infinite;}
  .dot:nth-child(2){animation-delay:.15s;}.dot:nth-child(3){animation-delay:.3s;}
  @keyframes blink{0%,80%,100%{opacity:.2}40%{opacity:1}}
  .session-badge{text-align:center;font-family:var(--font-mono);font-size:10px;color:var(--text-dim);padding:4px 0 8px;}
  .session-badge span{background:var(--surface);border:1px solid var(--border);border-radius:20px;padding:2px 10px;}
  .file-chip{display:inline-flex;align-items:center;gap:6px;background:var(--accent-dim);color:#00516f;border:1px solid #7dcce0;padding:3px 10px;border-radius:20px;font-family:var(--font-mono);font-size:10px;}
  .file-chip .x{cursor:pointer;opacity:.6;}
  .file-chip .x:hover{opacity:1;}
  #progress-row{display:none;padding:8px 20px 10px;background:var(--surface);border-top:1px solid var(--border);font-family:var(--font-mono);font-size:11px;color:var(--text-dim);}
  #progress-row.active{display:block;}
  .progress-head{display:flex;justify-content:space-between;margin-bottom:5px;}
  .progress-head .name{color:var(--text);}
  .bar{height:4px;background:var(--bg);border-radius:2px;overflow:hidden;}
  .bar .fill{height:100%;background:#27a0bf;width:0%;transition:width .2s ease;}
  footer{display:flex;align-items:center;gap:10px;padding:0 20px;border-top:1px solid var(--border);background:var(--surface);}
  #attach{width:38px;height:38px;border-radius:var(--radius);background:transparent;border:1px solid var(--border);cursor:pointer;display:grid;place-items:center;transition:border-color .15s,background .15s;flex-shrink:0;color:var(--text-dim);}
  #attach:hover:not(:disabled){border-color:#27a0bf;color:#27a0bf;}
  #attach:disabled{opacity:.4;cursor:not-allowed;}
  #attach svg{width:16px;height:16px;}
  #file-input{display:none;}
  #input{flex:1;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);padding:10px 14px;color:var(--text);font-family:var(--font-mono);font-size:13.5px;resize:none;max-height:120px;outline:none;transition:border-color .15s;line-height:1.5;}
  #input:focus{border-color:#27a0bf;}
  #input::placeholder{color:var(--muted);}
  #send{width:38px;height:38px;border-radius:var(--radius);background:#27a0bf;border:none;cursor:pointer;display:grid;place-items:center;transition:background .15s,transform .1s;flex-shrink:0;}
  #send:hover:not(:disabled){background:#00516f;}#send:active{transform:scale(.94);}#send:disabled{background:var(--muted);cursor:not-allowed;}
  #send svg{width:16px;height:16px;fill:#ffffff;}
  .welcome{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;height:100%;color:var(--text-dim);font-family:var(--font-mono);font-size:13px;text-align:center;padding:40px;}
  .welcome .icon{font-size:36px;margin-bottom:8px;}
  .welcome strong{color:#00516f;font-size:15px;}
  .chips{display:flex;flex-wrap:wrap;gap:8px;justify-content:center;margin-top:8px;}
  .chip{padding:6px 14px;border:1px solid var(--border);border-radius:20px;cursor:pointer;font-size:11px;transition:border-color .15s,color .15s;}
  .chip:hover{border-color:#27a0bf;color:#27a0bf;}
</style>
</head>
<body>
<div class="shell">
  <header>
    <div class="logo">
      <svg viewBox="0 0 16 16" fill="none" xmlns="http://www.w3.org/2000/svg">
        <circle cx="8" cy="8" r="3" fill="#ffffff"/>
        <circle cx="8" cy="2" r="1.2" fill="#ffffff"/>
        <circle cx="8" cy="14" r="1.2" fill="#ffffff"/>
        <circle cx="2" cy="8" r="1.2" fill="#ffffff"/>
        <circle cx="14" cy="8" r="1.2" fill="#ffffff"/>
      </svg>
    </div>
    <div>
      <div class="title">NovAtel AI Assistant</div>
      <div class="subtitle">Query documentation. Analyze logs. Get actionable GNSS insights.</div>
    </div>
    <div class="pill" id="status-pill">&#9679; READY</div>
  </header>
  <div id="messages">
    <div class="welcome" id="welcome">
      <div class="icon">&#128225;</div>
      <strong>NovAtel Agent</strong>
      <div>Ask about logs, message formats, or upload a receiver log file.</div>
      <div class="chips">
        <div class="chip" onclick="sendChip(this)">What logs show receiver status?</div>
        <div class="chip" onclick="sendChip(this)">Explain BESTPOS message fields</div>
        <div class="chip" onclick="sendChip(this)">Common Positioning Logs</div>
      </div>
    </div>
  </div>
  <div id="progress-row">
    <div class="progress-head">
      <span class="name" id="prog-name">uploading...</span>
      <span id="prog-pct">0%</span>
    </div>
    <div class="bar"><div class="fill" id="prog-fill"></div></div>
    <div id="prog-status" style="margin-top:4px;"></div>
  </div>
  <footer>
    <input type="file" id="file-input" accept=".log,.txt,.asc,.ascii,.dat,.bin,.json,.csv"/>
    <button id="attach" title="Attach log file">
      <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" xmlns="http://www.w3.org/2000/svg">
        <path d="M10.5 4.5L5 10a2 2 0 0 0 2.8 2.8l6.2-6.2a3.5 3.5 0 0 0-5-5L2.8 8a5 5 0 1 0 7 7l4.7-4.7"/>
      </svg>
    </button>
    <textarea id="input" rows="1" placeholder="Ask about NovAtel logs, message formats, GNSS..." maxlength="2000"></textarea>
    <button id="send" title="Send (Enter)">
      <svg viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><path d="M1 8l13-6-5 6 5 6z"/></svg>
    </button>
    <button id="mic" title="Speak"> voice
    </button>
  </footer>
</div>
<script>
  const messagesEl=document.getElementById('messages'),inputEl=document.getElementById('input'),sendBtn=document.getElementById('send'),pill=document.getElementById('status-pill'),welcome=document.getElementById('welcome');
  const attachBtn=document.getElementById('attach'),fileInput=document.getElementById('file-input');
  const progRow=document.getElementById('progress-row'),progName=document.getElementById('prog-name'),progPct=document.getElementById('prog-pct'),progFill=document.getElementById('prog-fill'),progStatus=document.getElementById('prog-status');

  let clientId=null,sessionId=null,busy=false;

  const SMALL_FILE_LIMIT = 5 * 1024 * 1024;
  const MAX_FILE         = 350 * 1024 * 1024;  // 350 MB max upload

  inputEl.addEventListener('input',()=>{inputEl.style.height='auto';inputEl.style.height=Math.min(inputEl.scrollHeight,120)+'px';});
  inputEl.addEventListener('keydown',e=>{if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();send();}});
  sendBtn.addEventListener('click',send);
  attachBtn.addEventListener('click',()=>fileInput.click());
  fileInput.addEventListener('change',handleFile);

  function sendChip(el){inputEl.value=el.textContent;send();}
  function now(){return new Date().toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'});}
  function fmtMB(b){return (b/(1024*1024)).toFixed(1)+' MB';}

  function appendMsg(role,text,opts){
    if(welcome)welcome.style.display='none';
    const wrap=document.createElement('div');wrap.className='msg '+role;
    const av=document.createElement('div');av.className='avatar '+role;av.textContent=role==='user'?'YOU':'AI';
    const col=document.createElement('div');
    const bubble=document.createElement('div');bubble.className='bubble';
    if(opts&&opts.html){bubble.innerHTML=text;}else{bubble.textContent=text;}
    const ts=document.createElement('div');ts.className='ts';ts.textContent=now();
    col.appendChild(bubble);col.appendChild(ts);wrap.appendChild(av);wrap.appendChild(col);
    messagesEl.appendChild(wrap);messagesEl.scrollTop=messagesEl.scrollHeight;
    return bubble;
  }
  function showTyping(){
    const w=document.createElement('div');w.className='msg agent typing';w.id='typing';
    w.innerHTML='<div class="avatar agent">AI</div><div><div class="bubble"><div class="dot"></div><div class="dot"></div><div class="dot"></div></div></div>';
    messagesEl.appendChild(w);messagesEl.scrollTop=messagesEl.scrollHeight;
  }
  function removeTyping(){document.getElementById('typing')?.remove();}
  function showSessionBadge(sid){
    const existing=document.getElementById('sess-badge');
    if(existing)existing.remove();
    const d=document.createElement('div');d.className='session-badge';d.id='sess-badge';
    d.innerHTML='<span>session &middot; '+sid+'</span>';
    messagesEl.insertBefore(d,messagesEl.firstChild);
  }

  function setBusy(on,label){
    busy=on;sendBtn.disabled=on;attachBtn.disabled=on;
    if(on){pill.innerHTML='&#9679; '+(label||'THINKING');pill.style.color='#f0c060';pill.style.borderColor='#c88000';}
    else{pill.innerHTML='&#9679; READY';pill.style.color='';pill.style.borderColor='';}
  }

  function showProgress(name,pct,status){
    progRow.classList.add('active');
    progName.textContent=name;
    progPct.textContent=pct+'%';
    progFill.style.width=pct+'%';
    progStatus.textContent=status||'';
  }
  function hideProgress(){progRow.classList.remove('active');progFill.style.width='0%';}

  async function handleFile(e){
    const f=e.target.files[0];
    fileInput.value='';
    if(!f)return;
    if(f.size>MAX_FILE){appendMsg('agent','File is '+fmtMB(f.size)+'. Max allowed is '+fmtMB(MAX_FILE)+'.');return;}
    if(welcome)welcome.style.display='none';
    appendMsg('user','<span class="file-chip">&#128206; '+f.name+' &middot; '+fmtMB(f.size)+'</span>',{html:true});
    setBusy(true,'UPLOADING');
    try{
      if(f.size<=SMALL_FILE_LIMIT){await uploadSmall(f);}
      else{await uploadLarge(f);}
    }catch(err){
      hideProgress();
      appendMsg('agent','Upload failed: '+(err.message||err));
      setBusy(false);
    }
  }

  async function uploadSmall(f){
    showProgress(f.name,10,'Encoding...');
    const b64=await fileToBase64(f);
    showProgress(f.name,60,'Sending to agent...');
    const res=await fetch('/upload-small',{
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body:JSON.stringify({filename:f.name,file_b64:b64,client_id:clientId}),
    });
    if(!res.ok){const e=await res.json().catch(()=>({detail:res.statusText}));throw new Error(e.detail||'upload failed');}
    const data=await res.json();
    showProgress(f.name,100,'Done');
    finishUpload(data,f.name);
  }

  function fileToBase64(f){
    return new Promise((resolve,reject)=>{
      const r=new FileReader();
      r.onload=()=>resolve(r.result.split(',')[1]);
      r.onerror=()=>reject(new Error('read error'));
      r.readAsDataURL(f);
    });
  }

  async function uploadLarge(f){
    const uploadId=crypto.randomUUID ? crypto.randomUUID() : String(Math.random());
    showProgress(f.name,0,'Uploading to S3...');
    let pollActive=true;
    (async function poll(){
      while(pollActive){
        try{
          const r=await fetch('/upload-progress?id='+uploadId);
          if(r.ok){
            const p=await r.json();
            if(p.total>0){
              const pct=Math.min(99,Math.round(p.done/p.total*100));
              showProgress(f.name,pct,p.status||'Uploading to S3...');
            }
            if(p.status==='done'||p.status==='error')break;
          }
        }catch(_){}
        await new Promise(r=>setTimeout(r,500));
      }
    })();
    const fd=new FormData();
    fd.append('file',f);
    fd.append('upload_id',uploadId);
    if(clientId)fd.append('client_id',clientId);
    const res=await fetch('/upload-large',{method:'POST',body:fd});
    pollActive=false;
    if(!res.ok){const e=await res.json().catch(()=>({detail:res.statusText}));throw new Error(e.detail||'upload failed');}
    const data=await res.json();
    showProgress(f.name,100,'Done');
    finishUpload(data,f.name);
  }

  function finishUpload(data,filename){
    clientId=data.client_id;sessionId=data.session_id;
    showSessionBadge(sessionId);
    appendMsg('agent',data.reply||('Processed '+filename+'. You can now ask questions about this log.'));
    setTimeout(hideProgress,800);
    setBusy(false);
    inputEl.focus();
  }

  async function send(){
    const text=inputEl.value.trim();if(!text||busy)return;
    setBusy(true,'THINKING');
    inputEl.value='';inputEl.style.height='auto';
    appendMsg('user',text);showTyping();
    try{
      const res=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text,client_id:clientId})});
      console.log(res, "response")
      removeTyping();
      if(!res.ok){const err=await res.json().catch(()=>({detail:res.statusText}));appendMsg('agent','Error: '+(err.detail||'Unknown'));}
      else{const data=await res.json();clientId=data.client_id;sessionId=data.session_id;showSessionBadge(sessionId);appendMsg('agent',data.reply); } // speak(data.reply);
    }catch(e){removeTyping();appendMsg('agent','Network error - is ui_server.py running?');}
    setBusy(false);
    inputEl.focus();
  }

  function speak(text) {
  if (!('speechSynthesis' in window)) return;

  const utterance = new SpeechSynthesisUtterance(text);

  const voices = speechSynthesis.getVoices();

  //  Try to pick a female voice
  const femaleVoice = voices.find(v =>
    v.name.toLowerCase().includes('female') ||
    v.name.toLowerCase().includes('zira') ||     // Windows female
    v.name.toLowerCase().includes('google uk english female') ||
    v.name.toLowerCase().includes('samantha') || // Mac female
    v.name.toLowerCase().includes('aria')        // Edge/Windows neural
  );

  if (femaleVoice) {
    utterance.voice = femaleVoice;
  }

  utterance.rate = 1;
  utterance.pitch = 1;

  speechSynthesis.speak(utterance);
}

const micBtn = document.getElementById('mic');

let recognition;
let listening = false;

if ('webkitSpeechRecognition' in window) {
  recognition = new webkitSpeechRecognition();
  recognition.continuous = false;
  recognition.interimResults = false;
  recognition.lang = 'en-US'; // change if needed

  recognition.onstart = () => {
    listening = true;
    micBtn.textContent = 'stop';
  };

  recognition.onend = () => {
    listening = false;
    micBtn.textContent = 'mic';
  };

  recognition.onresult = (event) => {
    const transcript = event.results[0][0].transcript;
    
    // Put into input box
    inputEl.value = transcript;

    //  auto send
    send();
  };
}

micBtn.addEventListener('click', () => {
  if (!recognition) {
    alert("Speech recognition not supported in this browser");
    return;
  }

  if (listening) {
    recognition.stop();
  } else {
    recognition.start();
  }
});
</script>
</body>
</html>"""


# ── Multipart form parser (stdlib) ────────────────────────────────────
from email.parser import BytesParser
from email.policy import default as email_default_policy

def parse_multipart(body: bytes, content_type: str) -> dict:
    """Return {field_name: (filename_or_None, bytes_or_str)}"""
    header = f"Content-Type: {content_type}\r\n\r\n".encode("utf-8")
    msg    = BytesParser(policy=email_default_policy).parsebytes(header + body)
    out    = {}
    for part in msg.iter_parts():
        disp = part.get("Content-Disposition", "")
        if "name=" not in disp:
            continue
        params = {}
        for kv in disp.split(";"):
            kv = kv.strip()
            if "=" in kv:
                k, v = kv.split("=", 1)
                params[k.strip().lower()] = v.strip().strip('"')
        name     = params.get("name")
        filename = params.get("filename")
        payload  = part.get_payload(decode=True)
        if filename is None and isinstance(payload, (bytes, bytearray)):
            try:
                payload = payload.decode("utf-8")
            except UnicodeDecodeError:
                pass
        out[name] = (filename, payload)
    return out


# ── Upload helpers ────────────────────────────────────────────────────
def _session_for_client(client_id: str, new_for_file: bool = False) -> str:
    if new_for_file or client_id not in _sessions:
        _sessions[client_id] = "session-" + uuid.uuid4().hex[:10]
    return _sessions[client_id]


def _s3_upload_with_progress(file_bytes: bytes, filename: str, upload_id: str) -> str:
    key   = f"logs/{filename}"
    total = len(file_bytes)

    with _uploads_lock:
        _uploads[upload_id] = {"done": 0, "total": total, "status": "uploading"}

    cfg = TransferConfig(
        multipart_threshold = 8 * 1024 * 1024,
        multipart_chunksize = 8 * 1024 * 1024,
        max_concurrency     = 4,
        use_threads         = True,
    )

    def cb(n):
        with _uploads_lock:
            if upload_id in _uploads:
                _uploads[upload_id]["done"] += n

    get_s3_client().upload_fileobj(
        io.BytesIO(file_bytes),
        S3_BUCKET,
        key,
        Config=cfg,
        Callback=cb,
    )

    with _uploads_lock:
        if upload_id in _uploads:
            _uploads[upload_id]["status"] = "processing"
    return key


# ── HTTP handler ──────────────────────────────────────────────────────
class Handler(BaseHTTPRequestHandler):

    def log_message(self, format, *args):
        pass

    def _json(self, code: int, obj: dict):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML)
            return

        if self.path == "/debug":
            import main as m
            debug_info = {
                "log_store_sessions": list(m._log_store.keys()),
                "ui_sessions": dict(_sessions),
                "log_store_details": {
                    sid: {
                        "filename": entry.get("filename"),
                        "records": len(entry.get("df", [])),
                    }
                    for sid, entry in m._log_store.items()
                }
            }
            self._json(200, debug_info)
            return

        if self.path.startswith("/upload-progress"):
            upload_id = ""
            if "?" in self.path:
                q = self.path.split("?", 1)[1]
                for kv in q.split("&"):
                    if kv.startswith("id="):
                        upload_id = kv[3:]
                        break
            with _uploads_lock:
                p = _uploads.get(upload_id)
                payload = dict(p) if p else {"done": 0, "total": 0, "status": "unknown"}
            self._json(200, payload)
            return

        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/chat":
            return self._handle_chat()
        if self.path == "/upload-small":
            return self._handle_upload_small()
        if self.path == "/upload-large":
            return self._handle_upload_large()
        self.send_response(404)
        self.end_headers()

    def _handle_chat(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        print(f"\n{'='*60}\n[UI_SERVER] Received chat request\n{'='*60}")
        try:
            req        = json.loads(body)
            message    = req.get("message", "")
            client_id  = req.get("client_id") or str(uuid.uuid4())
            session_id = _session_for_client(client_id)

            print(f"[UI_SERVER] message={message!r} session_id={session_id!r}")
            result = asyncio.run(agent_invoke({"prompt": message, "session_id": session_id}))
            answer = result.get("result", str(result))
            print(f"[UI_SERVER] answer length={len(answer)}")

            self._json(200, {"reply": answer, "client_id": client_id, "session_id": session_id})
        except Exception as e:
            print(f"[UI_SERVER] ERROR: {e}")
            self._json(500, {"detail": str(e)})

    def _handle_upload_small(self):
        length = int(self.headers.get("Content-Length", 0))
        body   = self.rfile.read(length)
        try:
            req        = json.loads(body)
            file_b64   = req.get("file_b64", "")
            filename   = req.get("filename", "log.txt")
            client_id  = req.get("client_id") or str(uuid.uuid4())

            session_id = _session_for_client(client_id, new_for_file=True)

            result = asyncio.run(agent_invoke({
                "file":       file_b64,
                "filename":   filename,
                "session_id": session_id,
            }))
            reply = result.get("result", str(result))
            self._json(200, {"reply": reply, "client_id": client_id, "session_id": session_id})
        except Exception as e:
            self._json(500, {"detail": str(e)})

    def _handle_upload_large(self):
        import main as _m
        print(f"[DEBUG] main.S3_BUCKET = {_m.S3_BUCKET!r}")
        length       = int(self.headers.get("Content-Length", 0))
        content_type = self.headers.get("Content-Type", "")
        if length > MAX_UPLOAD:
            self._json(413, {"detail": f"File exceeds {MAX_UPLOAD // (1024*1024)} MB limit"})
            return

        try:
            body   = self.rfile.read(length)
            fields = parse_multipart(body, content_type)

            upload_id  = fields.get("upload_id", (None, ""))[1]
            client_id  = fields.get("client_id", (None, None))[1] or str(uuid.uuid4())
            file_tuple = fields.get("file")
            if not file_tuple or not file_tuple[0]:
                self._json(400, {"detail": "no file uploaded"})
                return
            filename   = file_tuple[0]
            file_bytes = file_tuple[1]
            if isinstance(file_bytes, str):
                file_bytes = file_bytes.encode("utf-8")

            s3_key = _s3_upload_with_progress(file_bytes, filename, upload_id)

            session_id = _session_for_client(client_id, new_for_file=True)
            result     = asyncio.run(agent_invoke({
                "s3_key":     s3_key,
                "filename":   filename,
                "session_id": session_id,
            }))
            reply = result.get("result", str(result))

            with _uploads_lock:
                if upload_id in _uploads:
                    _uploads[upload_id]["status"] = "done"
                    _uploads[upload_id]["done"]   = _uploads[upload_id]["total"]

            self._json(200, {"reply": reply, "client_id": client_id, "session_id": session_id})

        except Exception as e:
            with _uploads_lock:
                upload_id = locals().get("upload_id", "")
                if upload_id in _uploads:
                    _uploads[upload_id]["status"] = "error"
            self._json(500, {"detail": str(e)})


# ── Threaded server so progress polls work during large upload ────────
from http.server import ThreadingHTTPServer

if __name__ == "__main__":
    port   = 8080
    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    print("NovAtel Agent UI running at http://localhost:" + str(port))
    print("Upload files with the paperclip icon. S3 bucket: " + S3_BUCKET)
    print("Press Ctrl+C to stop.")
    server.serve_forever()



    #     cd atomicAquaLangGraph
# .venv\Scripts\activate
# python src/ui_server.py