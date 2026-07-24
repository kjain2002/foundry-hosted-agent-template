"""Browser test UI for the deployed Foundry hosted agent."""

import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path

import httpx
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from flask import Flask, Response, jsonify, render_template_string, request
from werkzeug.utils import secure_filename

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent


def _load_azd_env() -> dict[str, str]:
    env_path = _PROJECT_ROOT / ".azure" / "agent-framework-agent-basic-responses-dev" / ".env"
    values: dict[str, str] = {}
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip().strip('"')
    return values


_ENV = _load_azd_env()
AGENT_ENDPOINT = os.getenv("AGENT_ENDPOINT") or _ENV.get(
    "AGENT_AGENT_FRAMEWORK_AGENT_BASIC_RESPONSES_RESPONSES_ENDPOINT", ""
)
PROJECT_ENDPOINT = os.getenv("FOUNDRY_PROJECT_ENDPOINT") or _ENV.get("FOUNDRY_PROJECT_ENDPOINT", "")
OPENAI_BASE = f"{PROJECT_ENDPOINT.rstrip('/')}/openai/v1"
MODEL = _ENV.get("AZURE_AI_MODEL_DEPLOYMENT_NAME", "gpt-4.1")

_credential = DefaultAzureCredential()
_get_token = get_bearer_token_provider(_credential, "https://ai.azure.com/.default")

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = int(os.getenv("MAX_UPLOAD_BYTES", 100 * 1024 * 1024))

_container_lock = threading.Lock()
_container_id: str | None = None
_history_lock = threading.Lock()
_history: list[dict] = []
_attachments: list[dict[str, str]] = []
_LOG_DIR = _HERE / "logs"
_SKILL_MARKER_RE = re.compile(r"^SKILL_USED:\s*(.+)$", re.IGNORECASE)


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_get_token()}"}


def _ensure_container() -> str:
    global _container_id
    with _container_lock:
        if _container_id:
            try:
                response = httpx.get(f"{OPENAI_BASE}/containers/{_container_id}", headers=_headers(), timeout=30.0)
                if response.status_code == 200:
                    return _container_id
            except Exception:
                pass
            _container_id = None
        response = httpx.post(
            f"{OPENAI_BASE}/containers",
            headers={**_headers(), "Content-Type": "application/json"},
            json={"name": "ui-client-created-ci"},
            timeout=60.0,
        )
        response.raise_for_status()
        _container_id = response.json()["id"]
        return _container_id


def _list_file_ids(container_id: str) -> set[str]:
    try:
        response = httpx.get(f"{OPENAI_BASE}/containers/{container_id}/files", headers=_headers(), timeout=30.0)
        if response.status_code == 200:
            return {item.get("id") for item in response.json().get("data", [])}
    except Exception:
        pass
    return set()


def _upload_attachment(container_id: str, uploaded_file) -> dict[str, str]:
    filename = secure_filename(uploaded_file.filename or "attachment")
    if not filename:
        raise ValueError("Attachment filename is invalid")
    response = httpx.post(
        f"{OPENAI_BASE}/containers/{container_id}/files",
        headers=_headers(),
        files={"file": (filename, uploaded_file.stream, uploaded_file.mimetype or "application/octet-stream")},
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    return {"filename": filename, "path": data.get("path") or f"/mnt/data/{filename}"}


def _parse_response(data: dict, container_id: str, previous_file_ids: set[str]) -> dict:
    parsed = {"text": "", "consent_link": None, "consent_label": None, "files": [], "tool_activity": [], "skills_used": [], "error": None}
    error = data.get("error")
    if isinstance(error, dict):
        parsed["error"] = error.get("message") or str(error)
    elif error:
        parsed["error"] = str(error)
    texts: list[str] = []
    for item in data.get("output", []) or []:
        item_type = item.get("type")
        if item_type and item_type not in ("message", "response.completed"):
            parsed["tool_activity"].append({key: item.get(key) for key in ("type", "status", "name", "server_label", "id") if item.get(key) is not None})
        if item_type == "oauth_consent_request":
            parsed["consent_link"] = item.get("consent_link")
            parsed["consent_label"] = item.get("server_label")
        for content in item.get("content", []) or []:
            if content.get("type") == "output_text":
                texts.append(content.get("text", ""))
    kept_lines: list[str] = []
    for line in "\n".join(texts).splitlines():
        marker = _SKILL_MARKER_RE.match(line.strip())
        if marker:
            parsed["skills_used"].append(marker.group(1).strip())
        else:
            kept_lines.append(line)
    parsed["text"] = "\n".join(kept_lines).strip()
    try:
        response = httpx.get(f"{OPENAI_BASE}/containers/{container_id}/files", headers=_headers(), timeout=30.0)
        if response.status_code == 200:
            for item in response.json().get("data", []):
                if item.get("source") == "assistant":
                    file_id = item.get("id")
                    path = item.get("path") or file_id
                    name = path.rsplit("/", 1)[-1]
                    parsed["files"].append({"name": name, "url": f"/download/{container_id}/{file_id}?name={name}", "new": file_id not in previous_file_ids})
    except Exception:
        pass
    return parsed


def _write_debug_log(user_message: str, container_id: str, status: int, raw: dict, parsed: dict) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S_%f")
        record = {"user_message": user_message, "container_id": container_id, "http_status": status, "raw_response": raw, "parsed": parsed}
        (_LOG_DIR / f"turn-{timestamp}.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    except Exception:
        pass


@app.post("/upload")
def upload():
    global _attachments
    uploaded_files = [item for item in request.files.getlist("attachments") if item.filename]
    if not uploaded_files:
        return jsonify({"error": "Choose at least one file first"}), 400
    try:
        container_id = _ensure_container()
        uploaded = [_upload_attachment(container_id, item) for item in uploaded_files]
    except Exception as exc:
        return jsonify({"error": f"attachment upload failed: {exc}"}), 502
    with _history_lock:
        _attachments.extend(uploaded)
    return jsonify({"ok": True, "attachments": uploaded})


@app.post("/chat")
def chat():
    user_message = (request.json or {}).get("message", "").strip()
    if not user_message:
        return jsonify({"error": "empty message"}), 400
    if not AGENT_ENDPOINT:
        return jsonify({"error": "AGENT_ENDPOINT not configured"}), 500
    try:
        container_id = _ensure_container()
    except Exception as exc:
        return jsonify({"error": f"container create failed: {exc}"}), 502
    previous_file_ids = _list_file_ids(container_id)
    with _history_lock:
        history = list(_history)
        attachments = list(_attachments)
    hint = f"USE_CONTAINER_ID={container_id}"
    if attachments:
        manifest = "\n".join(f"- {item['filename']}: {item['path']}" for item in attachments)
        hint += "\nUser attachments are available in the Code Interpreter container. Use code_interpreter to inspect or use them when relevant:\n" + manifest
    body = {"model": MODEL, "input": history + [{"role": "user", "content": f"{hint}\n\n{user_message}"}], "stream": False, "store": False}
    try:
        response = httpx.post(AGENT_ENDPOINT, headers={**_headers(), "Content-Type": "application/json"}, json=body, timeout=300.0)
        data = response.json()
    except Exception as exc:
        return jsonify({"error": f"agent call failed: {exc}", "container_id": container_id}), 502
    parsed = _parse_response(data, container_id, previous_file_ids)
    parsed["http_status"] = response.status_code
    parsed["container_id"] = container_id
    _write_debug_log(user_message, container_id, response.status_code, data, parsed)
    if parsed["text"] and not parsed["consent_link"]:
        with _history_lock:
            _history.extend([{"role": "user", "content": user_message}, {"role": "assistant", "content": parsed["text"]}])
    return jsonify(parsed)


@app.post("/reset")
def reset():
    global _attachments
    with _history_lock:
        _history.clear()
        _attachments = []
    return jsonify({"ok": True})


@app.get("/download/<container_id>/<file_id>")
def download(container_id: str, file_id: str):
    name = request.args.get("name", "download.bin")
    response = httpx.get(f"{OPENAI_BASE}/containers/{container_id}/files/{file_id}/content", headers=_headers(), timeout=120.0)
    if response.status_code != 200:
        return Response(f"download failed: HTTP {response.status_code}", status=502)
    return Response(response.content, headers={"Content-Disposition": f'attachment; filename="{name}"', "Content-Type": "application/octet-stream"})


_PAGE = """
<!doctype html><html><head><meta charset="utf-8"><title>Hosted Agent</title><style>
:root{color-scheme:dark;--bg:#212121;--panel:#2f2f2f;--line:#454545;--text:#ececec;--muted:#a3a3a3}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font-family:ui-sans-serif,system-ui,"Segoe UI",sans-serif}header{height:56px;display:flex;align-items:center;justify-content:space-between;padding:0 20px;border-bottom:1px solid var(--line);font-size:15px;font-weight:600}header small{color:var(--muted);font-size:12px;font-weight:400;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:45vw}.icon{display:grid;place-items:center;width:34px;height:34px;padding:0;border:0;border-radius:6px;background:transparent;color:var(--text);font-size:20px;cursor:pointer}.icon:hover{background:#454545}.conversation{width:min(820px,100%);min-height:calc(100vh - 56px);margin:0 auto;padding:28px 18px 156px}.empty{padding-top:15vh;text-align:center;color:var(--muted)}.msg{margin:0 0 22px;white-space:pre-wrap;line-height:1.55}.user{margin-left:auto;width:fit-content;max-width:82%;padding:10px 14px;border-radius:18px;background:#303030}.bot{padding:0 4px}.sys{padding:12px 14px;border-radius:8px;background:#4a2929;color:#ffd0c9}.file-link,.consent-link{display:inline-block;margin:9px 8px 0 0;color:var(--text);text-decoration:none;border:1px solid var(--line);border-radius:7px;padding:7px 10px}.consent-link{background:#426535;border:0}.tools{margin-top:12px;padding:8px 10px;border:1px solid var(--line);border-radius:7px;font-size:12px}.tools summary{cursor:pointer}.tools .ti-list{margin-top:8px;display:flex;flex-direction:column;gap:4px}.tools .ti{padding:4px 6px;border-radius:5px;background:#3a3a3a;color:var(--muted);font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.bot code{background:#3a3a3a;padding:1px 5px;border-radius:4px;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:.92em}.bot strong{color:#fff;font-weight:600}.skills{margin-top:10px;display:inline-block;padding:4px 9px;border-radius:6px;background:#2d3b2d;color:#bfe3bf;font-size:12px}.composer-wrap{position:fixed;bottom:0;left:0;right:0;padding:14px 16px 20px;background:linear-gradient(transparent,var(--bg) 24%)}.composer{width:min(820px,100%);margin:0 auto;padding:8px;border:1px solid var(--line);border-radius:18px;background:var(--panel);box-shadow:0 8px 28px rgba(0,0,0,.22)}.attachments{display:flex;flex-wrap:wrap;gap:6px;padding:2px 4px 8px}.attachment{display:flex;align-items:center;gap:7px;max-width:220px;padding:6px 8px;border:1px solid var(--line);border-radius:7px;background:#383838;font-size:12px}.attachment span{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.remove{border:0;background:transparent;color:var(--muted);font-size:16px;cursor:pointer}.input-row{display:flex;align-items:flex-end;gap:7px}.input-row textarea{flex:1;min-height:38px;max-height:160px;resize:none;padding:9px 4px;border:0;outline:0;background:transparent;color:var(--text);font:inherit;line-height:1.4}.send{background:#fff;color:#1e1e1e;font-weight:700}.send:disabled{opacity:.45;cursor:default}#file-input{display:none}@media(max-width:560px){header small{display:none}.conversation{padding-left:14px;padding-right:14px}.user{max-width:92%}}
</style></head><body><header><span>Hosted Agent</span><small>{{ endpoint }}</small><button id="newchat" class="icon" title="Start a new chat">+</button></header><main id="log" class="conversation"><div class="empty">How can I help?</div></main><div class="composer-wrap"><form id="form" class="composer"><div id="attachments" class="attachments"></div><div class="input-row"><input id="file-input" type="file" multiple><button id="attach" class="icon" type="button" title="Attach files">+</button><textarea id="message" placeholder="Message Hosted Agent" rows="1"></textarea><button id="send" class="icon send" type="submit" title="Send message">&gt;</button></div></form></div><script>
const log=document.getElementById('log'),message=document.getElementById('message'),fileInput=document.getElementById('file-input'),attachmentList=document.getElementById('attachments'),send=document.getElementById('send');let attachments=[];const esc=value=>(value||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');const fmt=text=>{let s=esc(text);s=s.replace(/`([^`]+)`/g,'<code>$1</code>').replace(/[*][*]([^*]+)[*][*]/g,'<strong>$1</strong>');return s};const add=(kind,html)=>{const node=document.createElement('div');node.className='msg '+kind;node.innerHTML=html;log.appendChild(node);window.scrollTo(0,document.body.scrollHeight);return node};function renderAttachments(){attachmentList.innerHTML='';attachments.forEach((file,index)=>{const chip=document.createElement('div'),name=document.createElement('span'),remove=document.createElement('button');chip.className='attachment';name.textContent=file.name;name.title=file.name;remove.className='remove';remove.type='button';remove.title='Remove attachment';remove.textContent='x';remove.onclick=()=>{attachments.splice(index,1);renderAttachments()};chip.append(name,remove);attachmentList.appendChild(chip)})}function resize(){message.style.height='auto';message.style.height=Math.min(message.scrollHeight,160)+'px'}async function upload(){if(!attachments.length)return;const data=new FormData();attachments.forEach(file=>data.append('attachments',file));const response=await fetch('/upload',{method:'POST',body:data}),result=await response.json();if(!response.ok||result.error)throw Error(result.error||'Attachment upload failed');attachments=[];fileInput.value='';renderAttachments()}document.getElementById('attach').onclick=()=>fileInput.click();fileInput.onchange=()=>{attachments.push(...fileInput.files);renderAttachments()};message.oninput=resize;message.onkeydown=event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();document.getElementById('form').requestSubmit()}};document.getElementById('newchat').onclick=async()=>{await fetch('/reset',{method:'POST'});attachments=[];fileInput.value='';renderAttachments();log.innerHTML='<div class="empty">How can I help?</div>'};document.getElementById('form').onsubmit=async event=>{event.preventDefault();const text=message.value.trim();if(!text&&!attachments.length)return;log.querySelector('.empty')?.remove();const shown=text||(attachments.length?'(sent '+attachments.length+' attachment'+(attachments.length>1?'s':'')+')':'');if(shown)add('user',esc(shown));message.value='';resize();const pending=add('bot','Thinking...');send.disabled=true;try{await upload();const response=await fetch('/chat',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:text||'Please inspect the attached files.'})}),data=await response.json();let html=data.error?'Error: '+esc(data.error):fmt(data.text);if(data.consent_link)html+='<br><a class="consent-link" href="'+data.consent_link+'" target="_blank" rel="noopener">Sign in</a>';if(data.skills_used?.length)html+='<div class="skills">Skill used: '+data.skills_used.map(esc).join(', ')+'</div>';(data.files||[]).forEach(file=>html+='<a class="file-link" href="'+file.url+'">'+esc(file.name)+(file.new?' (new)':'')+'</a>');if(data.tool_activity?.length){html+='<details class="tools"><summary>Response activity ('+data.tool_activity.length+')</summary><div class="ti-list">';data.tool_activity.forEach(t=>{const parts=[t.type,t.name||t.server_label,t.status].filter(Boolean).map(esc);html+='<div class="ti">'+parts.join(' \u00b7 ')+'</div>'});html+='</div></details>'}pending.className='msg '+(data.error?'sys':'bot');pending.innerHTML=html||'(no content)'}catch(error){pending.className='msg sys';pending.textContent='Error: '+error}finally{send.disabled=false;message.focus()}};
</script></body></html>
"""


@app.get("/")
def index():
    return render_template_string(_PAGE, endpoint=AGENT_ENDPOINT or "(not configured)")


if __name__ == "__main__":
    print(f"AGENT_ENDPOINT = {AGENT_ENDPOINT}")
    print("Open http://localhost:5005")
    app.run(host="127.0.0.1", port=5005, debug=False)
