"""Stato di un lavoro (una timeline): marker, contesto, round di proposte e scelte."""
import re
import shutil
from datetime import date
from pathlib import Path

from . import edl, memoria
from .core import frames_to_tc, job_path, lavori_dir, read_json, slug, write_json

SINONIMI = {"video": "video", "filmato": "video", "clip": "video", "foto": "foto", "immagine": "foto",
            "img": "foto", "articolo": "articolo", "art": "articolo", "giornale": "articolo"}


def tipo_e_nota(name, note):
    """Il tipo sta nel nome o nella nota del marker; il resto della nota è l'indicazione di Fil."""
    tipo = None
    for txt in (name, note):
        w = re.findall(r"[a-zàèéìòù]+", (txt or "").lower())
        if w and w[0] in SINONIMI:
            tipo = SINONIMI[w[0]]
            break
    extra = (note or "").strip()
    if extra and re.fullmatch(r"(?i)\s*(video|foto|articolo|filmato|immagine)\s*[.:]?\s*", extra):
        extra = ""
    elif tipo and extra.lower().startswith(tipo):
        extra = extra[len(tipo):].lstrip(" :-–.").strip()
    return tipo, extra


def crea(raw, fonte_audio=None):
    """raw: dict dal ponte Resolve o dal parser EDL -> nuova cartella lavoro."""
    name = f"{slug(raw['timeline'])}-{date.today().isoformat()}"
    d = lavori_dir() / name
    k = 2
    while (d / "marker.json").exists():
        d = lavori_dir() / f"{name}-{k}"
        k += 1
    d.mkdir(parents=True, exist_ok=True)
    fps = raw.get("fps", 25)
    start = raw.get("start_tc", "01:00:00:00")
    sh, sm, ss, sf = (int(x) for x in start.replace(";", ":").split(":"))
    start_frames = ((sh * 60 + sm) * 60 + ss) * round(fps) + sf
    markers, senza_tipo = [], []
    for i, m in enumerate(sorted(raw["markers"], key=lambda x: x["frame"]), 1):
        tipo, extra = tipo_e_nota(m.get("name"), m.get("note"))
        mk = {**m, "id": f"m{i:03d}", "tipo": tipo, "nota_fil": extra,
              "tc": frames_to_tc(start_frames + m["frame"], fps)}
        if m.get("custom") == "chapeau-coperture":
            mk["gia_fatto"] = True
        (markers if tipo else senza_tipo).append(mk)
    meta = {k2: raw.get(k2) for k2 in ("timeline", "timeline_id", "progetto", "fps", "start_tc", "fonte")}
    write_json(d / "marker.json", {**meta, "markers": markers, "ignorati": senza_tipo})
    write_json(d / "stato.json", {"round": 0, "markers": {m["id"]: {"approvati": [], "aggiunti": [], "scartati": [],
                                                                      "chiuso": False} for m in markers}})
    return d, markers, senza_tipo


def carica(job):
    d = job_path(job)
    if not (d / "marker.json").exists():
        raise SystemExit(f"Lavoro non trovato: {job}")
    return d, read_json(d / "marker.json"), read_json(d / "stato.json")


def ultimo_lavoro():
    jobs = sorted(lavori_dir().glob("*/marker.json"), key=lambda p: p.stat().st_mtime)
    return jobs[-1].parent.name if jobs else None


def da_fare(mdata, stato):
    return [m for m in mdata["markers"] if not stato["markers"][m["id"]]["chiuso"]]


def contesto(job, prima=45.0, dopo=20.0):
    d, mdata, stato = carica(job)
    tr = read_json(d / "trascrizione.json", {"segments": []})["segments"]
    righe = [f"# Contesto marker — {mdata['timeline']} (round {stato['round'] + 1})", ""]
    for m in da_fare(mdata, stato):
        t = m["seconds"]
        before = " ".join(s["text"] for s in tr if t - prima <= s["end"] and s["start"] <= t)
        after = " ".join(s["text"] for s in tr if t < s["start"] <= t + dopo)
        st = stato["markers"][m["id"]]
        righe += [f"## {m['id']} · {m['tc']} · {m['tipo'].upper()}"]
        if m.get("nota_fil"):
            righe.append(f"**Nota di Fil (ha la precedenza):** {m['nota_fil']}")
        if st.get("capito"):
            righe.append(f"Capito al round precedente: {st['capito']}")
        righe += [f"**Prima del marker:** {before or '(nessuna frase)'}", f"**Subito dopo:** {after or '(nessuna frase)'}"]
        for s in st["scartati"]:
            mot = ", ".join(s.get("motivi") or []) or "nessun motivo"
            com = f" — «{s['commento']}»" if s.get("commento") else ""
            righe.append(f"- SCARTATO: {s['url']} ({mot}){com}")
        righe.append("")
    path = d / "contesto.md"
    path.write_text("\n".join(righe), encoding="utf-8")
    return path, len(da_fare(mdata, stato))


def _yt_t(url, start_s):
    if start_s is None or not re.search(r"youtu\.?be", url):
        return url
    url = re.sub(r"([?&])t=\d+s?&?", r"\1", url).rstrip("?&")
    return f"{url}{'&' if '?' in url else '?'}t={int(start_s)}"


def unisci(job):
    """ricerca/<id>.json (scritti dai ricercatori) -> proposte_round<N>.json per la pagina."""
    d, mdata, stato = carica(job)
    rnd = stato["round"] + 1
    by_id = {m["id"]: m for m in mdata["markers"]}
    out, problemi = [], []
    for m in da_fare(mdata, stato):
        r = read_json(d / "ricerca" / f"{m['id']}.json")
        if not r:
            problemi.append(f"{m['id']}: manca ricerca/{m['id']}.json")
            continue
        props = []
        for k, p in enumerate(r.get("proposte", [])[:3], 1):
            pid = f"{m['id']}-r{rnd}-{k}"
            prev = []
            for a in p.get("anteprime", []):
                src = Path(a) if Path(a).is_absolute() else d / a
                if src.exists():
                    dst = d / "anteprime" / f"{pid}-{len(prev) + 1}{src.suffix or '.jpg'}"
                    dst.parent.mkdir(exist_ok=True)
                    if src.resolve() != dst.resolve():
                        shutil.copyfile(src, dst)
                    prev.append(str(dst.relative_to(d)))
            if not prev and not p.get("articolo"):
                problemi.append(f"{pid}: nessuna anteprima")
            props.append({**p, "pid": pid, "anteprime": prev})
        if len(props) < 3:
            problemi.append(f"{m['id']}: solo {len(props)} proposte")
        stato["markers"][m["id"]]["capito"] = r.get("capito", "")
        out.append({"id": m["id"], "tc": m["tc"], "tipo": m["tipo"], "nota_fil": m.get("nota_fil", ""),
                    "capito": r.get("capito", ""), "proposte": props})
    write_json(d / f"proposte_round{rnd}.json", {"round": rnd, "timeline": mdata["timeline"], "markers": out})
    write_json(d / "stato.json", stato)
    return d / f"proposte_round{rnd}.json", problemi, by_id


def registra(job, scelte):
    """Applica le scelte della pagina allo stato e alla memoria di stile."""
    d, mdata, stato = carica(job)
    rnd = scelte.get("round") or stato["round"] + 1
    proposte = read_json(d / f"proposte_round{rnd}.json", {"markers": []})
    by_pid = {p["pid"]: {**p, "_mid": m["id"]} for m in proposte["markers"] for p in m["proposte"]}
    caps = {m["id"]: {"tipo": m["tipo"], "capito": m["capito"]} for m in proposte["markers"]}
    write_json(d / f"scelte_round{rnd}.json", scelte)
    for mid, s in (scelte.get("markers") or {}).items():
        st = stato["markers"].get(mid)
        if st is None:
            continue
        for pid, dec in (s.get("decisioni") or {}).items():
            p = by_pid.get(pid)
            if not p or dec.get("ok") is None:
                continue
            if dec["ok"]:
                st["approvati"].append(p)
            else:
                st["scartati"].append({"url": p.get("url"), "fonte": p.get("fonte"), "motivi": dec.get("motivi", []),
                                       "commento": dec.get("commento", "")})
        for c in s.get("aggiunti") or []:
            if c.get("url"):
                st["aggiunti"].append(c)
        if st["approvati"] or st["aggiunti"] or s.get("salta"):
            st["chiuso"] = True
    stato["round"] = rnd
    stato["ok_finale"] = bool(scelte.get("ok_finale"))
    write_json(d / "stato.json", stato)
    if not stato.get("prova"):  # i lavori di prova non sporcano la memoria condivisa
        memoria.aggiungi_eventi(memoria.eventi_da_scelte(d.name, caps, by_pid, scelte))
    pend = [m for m in mdata["markers"] if not stato["markers"][m["id"]]["chiuso"]]
    return stato, pend


def nota_marker(m, st):
    righe = []
    for p in st["approvati"]:
        if m["tipo"] == "video":
            r = f"VIDEO ▸ {_yt_t(p['url'], p.get('inizio_s'))} | {p.get('inizio', '?')}–{p.get('fine', '?')}"
            r += f" | {p.get('fonte', '')}"
            if p.get("logo_fonte"):
                r += f" | Attenzione: logo in sovrimpressione {p['logo_fonte']}"
            if p.get("epoca"):
                r += " | Materiale d'epoca: usa Super Scale"
        elif m["tipo"] == "foto":
            r = f"FOTO ▸ {p['url']} | {p.get('fonte', '')}"
        else:
            a = p.get("articolo") or {}
            r = f"ARTICOLO ▸ {p['url']} | {a.get('testata', p.get('fonte', ''))}, {a.get('data', '')}"
            if a.get("frase"):
                r += f" | «{a['frase']}»"
                if a.get("traduzione") and a.get("lingua", "it") != "it":
                    r += f" → «{a['traduzione']}»"
        righe.append(r)
    for c in st["aggiunti"]:
        righe.append(f"{m['tipo'].upper()} (scelto a mano) ▸ {c['url']}" + (f" | {c['nota']}" if c.get("nota") else ""))
    if not righe:
        return None
    testo = "\n".join(righe)
    if m.get("note") and m["note"].strip().lower() != m["tipo"]:
        testo = f"{m['note'].strip()}\n—\n{testo}"
    return testo


def note_finali(job):
    d, mdata, stato = carica(job)
    res = []
    for m in mdata["markers"]:
        n = nota_marker(m, stato["markers"][m["id"]])
        if n:
            res.append({"frame": m["frame"], "id": m["id"], "note": n, "name": m.get("name", ""),
                        "color": m.get("color", "Blue"), "duration": m.get("duration", 1)})
    return d, mdata, res


def scrivi_edl(job):
    d, mdata, notes = note_finali(job)
    by_frame = {n["frame"]: n for n in notes}
    tutti = []
    for m in mdata["markers"] + mdata.get("ignorati", []):
        n = by_frame.get(m["frame"])
        tutti.append({"frame": m["frame"], "name": m.get("name", ""), "color": m.get("color", "Blue"),
                      "duration": m.get("duration", 1), "note": n["note"] if n else m.get("note", "")})
    testo = edl.write(tutti, mdata["timeline"], mdata.get("fps", 25), mdata.get("start_tc", "01:00:00:00"))
    path = d / f"MARKER_DA_REIMPORTARE_{slug(mdata['timeline'])}.edl"
    path.write_text(testo, encoding="utf-8")
    return path, len(notes)

