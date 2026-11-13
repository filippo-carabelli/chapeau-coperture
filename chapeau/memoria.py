"""Memoria di stile condivisa (cartella stile_chapeau/ su Google Drive).

Ogni collaboratore scrive solo il PROPRIO file (stile_chapeau/<nome>.json), così
Google Drive non crea mai copie in conflitto; la lettura unisce tutti i file.
"""
import json
from collections import Counter
from pathlib import Path
from urllib.parse import urlparse

from .core import load_config, now, read_json, slug, write_json


def cartella(cfg=None):
    cfg = cfg or load_config()
    d = Path(cfg.get("cartella_memoria") or Path(__file__).resolve().parent.parent / "stile_chapeau").expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def _mio_file(cfg):
    return cartella(cfg) / f"{slug(cfg.get('nome', 'anonimo'))}.json"


def _carica_tutti(cfg):
    eventi, regole = [], []
    for f in sorted(cartella(cfg).glob("*.json")):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        eventi += d.get("eventi", [])
        regole += d.get("regole", [])
    return eventi, regole


def aggiungi_eventi(nuovi):
    cfg = load_config()
    path = _mio_file(cfg)
    d = read_json(path, {"versione": 1, "autore": cfg.get("nome"), "eventi": [], "regole": []})
    d["eventi"].extend(nuovi)
    write_json(path, d)


def aggiungi_regola(testo):
    cfg = load_config()
    path = _mio_file(cfg)
    d = read_json(path, {"versione": 1, "autore": cfg.get("nome"), "eventi": [], "regole": []})
    d["regole"].append({"quando": now(), "chi": cfg.get("nome"), "regola": testo})
    write_json(path, d)


def dominio(url):
    try:
        h = urlparse(url).netloc.lower()
        return h[4:] if h.startswith("www.") else h
    except ValueError:
        return ""


def riassunto(max_esempi=12):
    """Testo compatto da leggere prima di ogni ricerca."""
    cfg = load_config()
    eventi, regole = _carica_tutti(cfg)
    if not eventi and not regole:
        return "Memoria di stile vuota: è la prima volta. Nessuna preferenza registrata."
    out = [f"MEMORIA DI STILE CHAPEAU — {len(eventi)} decisioni registrate"]
    if regole:
        out.append("\nRegole imparate (valgono sempre):")
        out += [f"- {r['regola']} ({r.get('chi')})" for r in regole]
    for tipo in ("video", "foto", "articolo"):
        ev = [e for e in eventi if e.get("tipo") == tipo]
        if not ev:
            continue
        def fonte(e):
            return e.get("fonte") if e.get("fonte") and e["fonte"] != "scelto a mano" else dominio(e["url"])
        ok = Counter(fonte(e) for e in ev if e["esito"] in ("approvato", "aggiunto"))
        ko = Counter(fonte(e) for e in ev if e["esito"] == "scartato")
        motivi = Counter(m for e in ev if e["esito"] == "scartato" for m in e.get("motivi", []))
        out.append(f"\n[{tipo.upper()}] approvati {sum(ok.values())}, scartati {sum(ko.values())}")
        if ok:
            out.append("  Fonti che funzionano: " + ", ".join(f"{d} ({n})" for d, n in ok.most_common(8)))
        if ko:
            out.append("  Fonti spesso scartate: " + ", ".join(f"{d} ({n})" for d, n in ko.most_common(6)))
        if motivi:
            out.append("  Motivi di scarto più frequenti: " + ", ".join(f"{m} ({n})" for m, n in motivi.most_common(6)))
        commenti = [e for e in ev if e.get("commento")][-max_esempi:]
        for e in commenti:
            out.append(f"  - «{e['commento']}» su: {e.get('capito', '')[:90]} → {e['esito']}")
        aggiunti = [e for e in ev if e["esito"] == "aggiunto"][-6:]
        for e in aggiunti:
            out.append(f"  + scelto a mano da {e.get('chi')}: {e['url']} per «{e.get('capito', '')[:80]}»")
    return "\n".join(out)


def eventi_da_scelte(job_name, marker_by_id, proposte_by_pid, scelte):
    cfg = load_config()
    eventi = []
    for mid, s in (scelte.get("markers") or {}).items():
        mk = marker_by_id.get(mid, {})
        base = {"quando": now(), "chi": cfg.get("nome"), "lavoro": job_name, "tipo": mk.get("tipo"),
                "capito": mk.get("capito", "")}
        for pid, dec in (s.get("decisioni") or {}).items():
            p = proposte_by_pid.get(pid, {})
            if dec.get("ok") is None:
                continue
            eventi.append({**base, "url": p.get("url", ""), "fonte": p.get("fonte", ""),
                           "esito": "approvato" if dec["ok"] else "scartato", "motivi": dec.get("motivi", []),
                           "commento": dec.get("commento", "")})
        for c in s.get("aggiunti") or []:
            eventi.append({**base, "url": c.get("url", ""), "fonte": "scelto a mano", "esito": "aggiunto",
                           "motivi": [], "commento": c.get("nota", "")})
    return eventi

