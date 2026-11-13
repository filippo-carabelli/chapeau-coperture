"""Server locale della pagina di revisione.

Apre il browser, serve proposte e anteprime, aspetta il bottone «Conferma»,
salva le scelte e si chiude da solo (così Claude Code sa che può proseguire).
"""
import json
import mimetypes
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

from .core import ROOT, load_config, read_json

PAGE_DIR = ROOT / "revisione"


def _free_port(start=8765):
    for p in range(start, start + 50):
        with socket.socket() as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    raise RuntimeError("Nessuna porta libera")


def servi(job_dir, apri=True, demo=False):
    job_dir = Path(job_dir)
    stato = read_json(job_dir / "stato.json", {"round": 0, "markers": {}})
    rnd = stato["round"] + 1 if not demo else 1
    proposte = read_json(job_dir / f"proposte_round{rnd}.json")
    if not proposte:
        raise SystemExit(f"Mancano le proposte del round {rnd}: lancia prima `cop unisci`.")
    marker = read_json(job_dir / "marker.json", {})
    gia = []
    for m in marker.get("markers", []):
        st = stato["markers"].get(m["id"], {})
        if st.get("chiuso"):
            gia.append({"id": m["id"], "tc": m["tc"], "tipo": m["tipo"],
                        "scelte": [p.get("titolo") or p.get("url") for p in st.get("approvati", [])]
                        + [c["url"] for c in st.get("aggiunti", [])]})
    cfg = load_config()
    payload = {**proposte, "lavoro": job_dir.name, "progetto": marker.get("progetto"),
               "collaboratore": cfg.get("nome"), "edizione": cfg.get("edizione"), "gia_approvati": gia,
               "totale_marker": len(marker.get("markers", []))}
    result = {}
    done = threading.Event()

    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _file(self, base, rel):
            p = (base / rel).resolve()
            if base.resolve() not in p.parents or not p.is_file():
                return self._send(404, "{}")
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            self._send(200, p.read_bytes(), ctype)

        def do_GET(self):
            path = unquote(urlparse(self.path).path)
            if path in ("/", "/index.html"):
                return self._file(PAGE_DIR, "index.html")
            if path == "/dati":
                return self._send(200, json.dumps(payload, ensure_ascii=False))
            if path.startswith("/lavoro/"):
                return self._file(job_dir, path[len("/lavoro/"):])
            return self._file(PAGE_DIR, path.lstrip("/"))

        def do_POST(self):
            if urlparse(self.path).path != "/conferma":
                return self._send(404, "{}")
            n = int(self.headers.get("Content-Length", 0))
            try:
                data = json.loads(self.rfile.read(n).decode("utf-8"))
            except json.JSONDecodeError:
                return self._send(400, '{"ok":false}')
            data["round"] = rnd
            result.update(data)
            self._send(200, '{"ok":true}')
            done.set()

    port = _free_port()
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{port}/"
    print(f"Pagina di revisione: {url}", flush=True)
    if apri:
        webbrowser.open(url)
    if demo:
        done.wait(timeout=None)
    else:
        done.wait()
    threading.Timer(0.5, srv.shutdown).start()
    return result
