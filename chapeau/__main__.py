"""Riga di comando del progetto: `./cop <comando>` (Windows: `cop.cmd <comando>`).

Pensata per essere usata da Claude Code dentro /coperture, non a mano.
"""
import argparse
import json
import sys
from pathlib import Path

from . import edl, lavoro, media, memoria
from .core import ROOT, job_path, load_config, read_json, run_bridge, write_json


def jprint(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=1))


def _job(a):
    j = getattr(a, "lavoro", None) or lavoro.ultimo_lavoro()
    if not j:
        sys.exit("Nessun lavoro trovato: lancia prima /coperture.")
    return j


def _riepilogo(d, markers, ignorati):
    jprint({"lavoro": d.name, "cartella": str(d), "marker_da_cercare": len(markers),
            "per_tipo": {t: sum(m["tipo"] == t for m in markers) for t in ("video", "foto", "articolo")},
            "gia_completati_in_passato": [m["tc"] for m in markers if m.get("gia_fatto")],
            "marker_ignorati_senza_tipo": [f"{m['tc']} «{m.get('name')}»" for m in ignorati]})


def main():
    ap = argparse.ArgumentParser(prog="cop")
    sp = ap.add_subparsers(dest="cmd", required=True)

    sp.add_parser("info", help="Resolve risponde? (solo Studio)")
    s = sp.add_parser("nuovo-studio", help="legge marker e trascrizione dalla timeline aperta")
    s.add_argument("--trascrivi", action="store_true", help="se manca, fa trascrivere la timeline a Resolve")
    s = sp.add_parser("nuovo-edl", help="versione gratuita: marker da EDL + audio esportato")
    s.add_argument("edl")
    s.add_argument("audio", nargs="?")
    s.add_argument("--fps", type=float, default=25)
    s.add_argument("--inizio", default=None, help="timecode di inizio timeline (default: dall'EDL)")
    s = sp.add_parser("trascrivi", help="trascrizione con Whisper")
    s.add_argument("lavoro", nargs="?")
    s.add_argument("--audio")
    s = sp.add_parser("contesto")
    s.add_argument("lavoro", nargs="?")
    sp.add_parser("memoria", help="riassunto della memoria di stile")
    s = sp.add_parser("regola", help="aggiunge una regola alla memoria di stile")
    s.add_argument("testo")
    s = sp.add_parser("cerca-yt")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=12)
    s = sp.add_parser("commons")
    s.add_argument("query")
    s.add_argument("-n", type=int, default=15)
    s = sp.add_parser("probe")
    s.add_argument("url")
    for name in ("scan", "verifica", "anteprime", "foto"):
        s = sp.add_parser(name)
        s.add_argument("url")
        s.add_argument("--lavoro")
        s.add_argument("--id", default="x", help="id marker (es. m003) per nominare i file")
        if name == "scan":
            s.add_argument("--da", type=float, default=0)
            s.add_argument("--a", type=float)
            s.add_argument("--ogni", type=float)
        if name == "verifica":
            s.add_argument("--at", type=float, required=True, help="secondo del video da verificare")
            s.add_argument("--span", type=float, default=8)
        if name == "anteprime":
            s.add_argument("--inizio", type=float, required=True)
            s.add_argument("--fine", type=float, required=True)
            s.add_argument("--k", type=int, default=1, help="numero proposta (1-3)")
        if name == "foto":
            s.add_argument("--k", type=int, default=1)
    s = sp.add_parser("usate", help="coperture già approvate o proposte negli altri marker")
    s.add_argument("--lavoro")
    s.add_argument("--id", help="marker da escludere (quello che stai cercando)")
    s = sp.add_parser("unisci")
    s.add_argument("lavoro", nargs="?")
    s = sp.add_parser("revisione", help="apre la pagina e aspetta «Conferma»")
    s.add_argument("lavoro", nargs="?")
    s.add_argument("--non-aprire", action="store_true")
    s = sp.add_parser("stato")
    s.add_argument("lavoro", nargs="?")
    s = sp.add_parser("scrivi", help="scrive le coperture nei marker (o crea l'EDL)")
    s.add_argument("lavoro", nargs="?")
    s.add_argument("--prova", action="store_true", help="mostra le note senza scrivere")
    s = sp.add_parser("ripristina", help="rimette i marker com'erano")
    s.add_argument("lavoro", nargs="?")
    a = ap.parse_args()
    cfg = load_config()

    if a.cmd == "info":
        return jprint(run_bridge("info"))

    if a.cmd == "nuovo-studio":
        tmp = ROOT / "lavori" / "_lettura"
        r = run_bridge("leggi", tmp, *(["--trascrivi"] if a.trascrivi else []))
        if not r.get("ok"):
            return jprint(r)
        raw = read_json(tmp / "marker_resolve.json")
        d, mk, ign = lavoro.crea(raw)
        tr = tmp / "trascrizione.json"
        if tr.exists():
            tr.replace(d / "trascrizione.json")
        _riepilogo(d, mk, ign)
        return jprint({"trascrizione_pronta": (d / "trascrizione.json").exists(),
                       "nota_trascrizione": r.get("nota_trascrizione")})

    if a.cmd == "nuovo-edl":
        text = Path(a.edl).expanduser().read_text(encoding="utf-8", errors="replace")
        raw = edl.parse(text, a.fps, a.inizio)
        d, mk, ign = lavoro.crea(raw)
        if a.audio:
            write_json(d / "audio.json", {"file": str(Path(a.audio).expanduser())})
        return _riepilogo(d, mk, ign)

    if a.cmd == "trascrivi":
        d = job_path(_job(a))
        audio = a.audio or (read_json(d / "audio.json") or {}).get("file")
        if not audio and cfg.get("edizione") == "studio":
            r = run_bridge("audio", d)
            if not r.get("ok"):
                return jprint(r)
            audio = r["file"]
        if not audio:
            sys.exit("Serve il file audio esportato dalla timeline.")
        from .transcribe import transcribe
        tr = transcribe(audio, cfg.get("lingua", "it"))
        write_json(d / "trascrizione.json", tr)
        return jprint({"ok": True, "segmenti": len(tr["segments"]), "fonte": tr["fonte"]})

    if a.cmd == "contesto":
        p, n = lavoro.contesto(_job(a))
        return jprint({"file": str(p), "marker_da_cercare": n})

    if a.cmd == "memoria":
        return print(memoria.riassunto())
    if a.cmd == "regola":
        memoria.aggiungi_regola(a.testo)
        return print("Regola salvata nella memoria di stile.")

    if a.cmd == "cerca-yt":
        return jprint(media.cerca_yt(a.query, a.n))
    if a.cmd == "commons":
        return jprint(media.cerca_commons(a.query, a.n))
    if a.cmd == "probe":
        return jprint(media.probe(a.url))
    if a.cmd in ("scan", "verifica", "anteprime", "foto"):
        base = job_path(a.lavoro or _job(a)) / "analisi" / a.id
        if a.cmd == "scan":
            return jprint(media.scan(a.url, base, a.ogni, a.da, a.a))
        if a.cmd == "verifica":
            return jprint(media.verifica(a.url, a.at, base, a.span, prefix=f"v{int(a.at)}"))
        if a.cmd == "anteprime":
            paths = media.anteprime_video(a.url, a.inizio, a.fine, base, f"{a.id}-p{a.k}")
            return jprint({"anteprime": paths})
        return jprint(media.foto(a.url, base, f"{a.id}-p{a.k}"))

    if a.cmd == "usate":
        return jprint(lavoro.usate(a.lavoro or _job(a), a.id))

    if a.cmd == "unisci":
        p, problemi, _ = lavoro.unisci(_job(a))
        return jprint({"proposte": str(p), "problemi": problemi})

    if a.cmd == "revisione":
        from .revisione import servi
        j = _job(a)
        scelte = servi(job_path(j), apri=not a.non_aprire)
        stato, pend = lavoro.registra(j, scelte)
        return jprint({"round": stato["round"], "ok_finale": stato.get("ok_finale"),
                       "approvati": sum(1 for s in stato["markers"].values() if s["chiuso"]),
                       "da_rifare": [{"id": m["id"], "tc": m["tc"], "tipo": m["tipo"],
                                      "scarti": stato["markers"][m["id"]]["scartati"][-3:]} for m in pend]})

    if a.cmd == "stato":
        d, mdata, stato = lavoro.carica(_job(a))
        return jprint({"lavoro": d.name, "round": stato["round"], "ok_finale": stato.get("ok_finale"),
                       "marker": [{"id": m["id"], "tc": m["tc"], "tipo": m["tipo"],
                                   "chiuso": stato["markers"][m["id"]]["chiuso"],
                                   "capito": stato["markers"][m["id"]].get("capito")} for m in mdata["markers"]]})

    if a.cmd == "scrivi":
        j = _job(a)
        d, mdata, notes = lavoro.note_finali(j)
        if a.prova:
            return jprint(notes)
        if cfg.get("edizione") == "studio" and mdata.get("fonte") == "studio":
            req = d / "note_da_scrivere.json"
            write_json(req, {"timeline": mdata["timeline"], "timeline_id": mdata.get("timeline_id"), "markers": notes})
            return jprint(run_bridge("scrivi", req))
        path, n = lavoro.scrivi_edl(j)
        return jprint({"ok": True, "file_edl": str(path), "marker_con_coperture": n})

    if a.cmd == "ripristina":
        d = job_path(_job(a))
        backups = sorted(d.glob("backup_marker_*.json"))
        if not backups:
            sys.exit("Nessun backup dei marker in questo lavoro.")
        return jprint(run_bridge("ripristina", backups[0]))


if __name__ == "__main__":
    main()
