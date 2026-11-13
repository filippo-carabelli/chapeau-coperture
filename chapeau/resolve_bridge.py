"""Ponte con DaVinci Resolve Studio (scripting ufficiale).

Usa solo la libreria standard: gira sia con il Python incluso in Resolve 21.1+
(ResolvePython) sia con un Python esterno 3.10-3.12 con le variabili
RESOLVE_SCRIPT_API / RESOLVE_SCRIPT_LIB impostate.

Comandi (output sempre JSON su stdout):
  info                                  progetto e timeline correnti
  leggi  <cartella_lavoro> [--trascrivi] marker + trascrizione della timeline corrente
  audio  <cartella_lavoro>               renderizza l'audio della timeline (fallback Whisper)
  scrivi <file_note.json>                aggiorna le note dei marker esistenti
  ripristina <file_backup.json>          rimette i marker com'erano prima della scrittura
"""
import json
import os
import sys
import time

MARKER_TAG = "chapeau-coperture"


def _import_dvr():
    try:
        import DaVinciResolveScript as dvr  # Resolve 21.1+ ResolvePython
        return dvr
    except ImportError:
        pass
    candidates = []
    api = os.environ.get("RESOLVE_SCRIPT_API")
    if api:
        candidates.append(os.path.join(api, "Modules"))
    if sys.platform == "darwin":
        candidates.append("/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules")
        os.environ.setdefault("RESOLVE_SCRIPT_LIB", "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so")
    elif sys.platform.startswith("win"):
        pd = os.environ.get("PROGRAMDATA", r"C:\ProgramData")
        candidates.append(os.path.join(pd, r"Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting\Modules"))
        os.environ.setdefault("RESOLVE_SCRIPT_LIB", r"C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll")
    else:
        candidates.append("/opt/resolve/Developer/Scripting/Modules")
        os.environ.setdefault("RESOLVE_SCRIPT_LIB", "/opt/resolve/libs/Fusion/fusionscript.so")
    for c in candidates:
        if os.path.isdir(c) and c not in sys.path:
            sys.path.append(c)
    import DaVinciResolveScript as dvr
    return dvr


def out(obj, code=0):
    print(json.dumps(obj, ensure_ascii=False, indent=1))
    sys.exit(code)


def fail(msg, hint=None):
    out({"ok": False, "errore": msg, "suggerimento": hint}, 1)


def connect():
    try:
        dvr = _import_dvr()
    except Exception as e:  # noqa: BLE001
        fail(f"Modulo di scripting di Resolve non trovato ({e})",
             "Reinstalla DaVinci Resolve oppure rilancia l'installazione del progetto.")
    resolve = dvr.scriptapp("Resolve")
    if resolve is None:
        fail("DaVinci Resolve non risponde.",
             "Apri DaVinci Resolve Studio con il progetto. Se è già aperto: Preferenze > Sistema > Generali > "
             "'External scripting using' = Local, poi riavvia Resolve.")
    pm = resolve.GetProjectManager()
    project = pm.GetCurrentProject() if pm else None
    if not project:
        fail("Nessun progetto aperto in DaVinci Resolve.", "Apri il progetto con l'intervista montata.")
    return resolve, project


def fps_of(project, timeline):
    for getter in (lambda: timeline.GetSetting("timelineFrameRate"),
                   lambda: project.GetSetting("timelineFrameRate")):
        try:
            v = getter()
            if v:
                return float(str(v).split()[0])
        except Exception:  # noqa: BLE001
            pass
    return 25.0


def tc_to_frames(tc, fps):
    tc = tc.replace(";", ":")
    h, m, s, f = (int(x) for x in tc.split(":"))
    nominal = round(fps)
    return ((h * 60 + m) * 60 + s) * nominal + f


def find_timeline(project, uid=None, name=None):
    current = project.GetCurrentTimeline()
    if current and (uid is None or current.GetUniqueId() == uid):
        return current
    for i in range(1, project.GetTimelineCount() + 1):
        tl = project.GetTimelineByIndex(i)
        if tl and ((uid and tl.GetUniqueId() == uid) or (not uid and name and tl.GetName() == name)):
            project.SetCurrentTimeline(tl)
            return tl
    return None


def cmd_info():
    resolve, project = connect()
    tl = project.GetCurrentTimeline()
    out({"ok": True, "versione": resolve.GetVersionString(), "prodotto": resolve.GetProductName(),
         "progetto": project.GetName(), "timeline": tl.GetName() if tl else None,
         "marker": len(tl.GetMarkers() or {}) if tl else 0})


def read_transcription(project, tl, fps, start_frames, do_transcribe):
    mpi = None
    try:
        mpi = tl.GetMediaPoolItem()
    except Exception:  # noqa: BLE001
        pass
    if mpi is None:
        return None, "La timeline non espone un MediaPoolItem (versione di Resolve troppo vecchia?)."
    tr = mpi.GetTranscription(True) or {}
    if not tr.get("segments") and do_transcribe:
        if not mpi.TranscribeAudio(False, True):
            return None, "Resolve ha rifiutato la trascrizione (Studio richiesto o pacchetto lingua mancante)."
        t0 = time.time()
        while time.time() - t0 < 3600:
            st = project.GetTranscribeAudioStatus() or {}
            if st.get("JobStatus") in ("Complete", "Cancelled", "Inactive") and time.time() - t0 > 5:
                break
            time.sleep(3)
        tr = mpi.GetTranscription(True) or {}
    segs = tr.get("segments") or []
    if not segs:
        return None, "Nessuna trascrizione disponibile in Resolve."
    # I timecode possono essere assoluti (01:00:..) o relativi all'inizio timeline.
    first = tc_to_frames(segs[0]["start"], fps)
    offset = start_frames if first >= start_frames - fps else 0
    clean = []
    for s in segs:
        text = (s.get("text") or "").replace("(...)", "").strip()
        if not text:
            continue
        clean.append({"start": round((tc_to_frames(s["start"], fps) - offset) / fps, 2),
                      "end": round((tc_to_frames(s["end"], fps) - offset) / fps, 2),
                      "text": text, "speaker": s.get("speaker")})
    return {"language": tr.get("language"), "segments": clean, "fonte": "resolve"}, None


def cmd_leggi(job_dir, do_transcribe):
    resolve, project = connect()
    tl = project.GetCurrentTimeline()
    if not tl:
        fail("Nessuna timeline aperta.", "Apri la timeline con l'intervista e i marker.")
    fps = fps_of(project, tl)
    start_tc = tl.GetStartTimecode() or "01:00:00:00"
    start_frames = tc_to_frames(start_tc, fps)
    markers = []
    for frame, info in sorted((tl.GetMarkers() or {}).items()):
        frame = int(frame)
        markers.append({"frame": frame, "seconds": round(frame / fps, 3), "name": info.get("name", ""),
                        "note": info.get("note", ""), "color": info.get("color", "Blue"),
                        "duration": int(info.get("duration", 1)), "custom": info.get("customData", "")})
    os.makedirs(job_dir, exist_ok=True)
    data = {"timeline": tl.GetName(), "timeline_id": tl.GetUniqueId(), "progetto": project.GetName(),
            "fps": fps, "start_tc": start_tc, "fonte": "studio", "markers": markers}
    with open(os.path.join(job_dir, "marker_resolve.json"), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    tr, err = read_transcription(project, tl, fps, start_frames, do_transcribe)
    if tr:
        with open(os.path.join(job_dir, "trascrizione.json"), "w", encoding="utf-8") as f:
            json.dump(tr, f, ensure_ascii=False, indent=1)
    out({"ok": True, "timeline": tl.GetName(), "fps": fps, "marker": len(markers),
         "trascrizione": bool(tr), "nota_trascrizione": err})


def cmd_audio(job_dir):
    resolve, project = connect()
    tl = project.GetCurrentTimeline()
    if not tl:
        fail("Nessuna timeline aperta.")
    os.makedirs(job_dir, exist_ok=True)
    presets = project.GetRenderPresetList() or []
    preset = next((p for p in presets if p.lower() in ("audio only", "solo audio")), None)
    if preset:
        project.LoadRenderPreset(preset)
    project.SetRenderSettings({"SelectAllFrames": True, "TargetDir": job_dir, "CustomName": "audio_timeline",
                               "ExportVideo": False, "ExportAudio": True})
    job = project.AddRenderJob()
    if not job:
        fail("Impossibile creare il render dell'audio.")
    project.StartRendering([job], False)
    while project.IsRenderingInProgress():
        time.sleep(2)
    status = project.GetRenderJobStatus(job) or {}
    project.DeleteRenderJob(job)
    files = [f for f in os.listdir(job_dir) if f.startswith("audio_timeline")]
    if not files:
        fail(f"Render audio non riuscito: {status}")
    out({"ok": True, "file": os.path.join(job_dir, sorted(files)[-1])})


def cmd_scrivi(notes_file):
    with open(notes_file, encoding="utf-8") as f:
        req = json.load(f)
    resolve, project = connect()
    tl = find_timeline(project, req.get("timeline_id"), req.get("timeline"))
    if not tl:
        fail(f"Timeline '{req.get('timeline')}' non trovata nel progetto aperto.",
             "Apri in Resolve il progetto in cui hai lanciato /coperture.")
    current = {int(k): v for k, v in (tl.GetMarkers() or {}).items()}
    backup_path = os.path.join(os.path.dirname(notes_file), f"backup_marker_{int(time.time())}.json")
    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump({"timeline": tl.GetName(), "timeline_id": tl.GetUniqueId(),
                   "markers": {str(k): v for k, v in current.items()}}, f, ensure_ascii=False, indent=1)
    done, missing = [], []
    for item in req["markers"]:
        frame = int(item["frame"])
        info = current.get(frame)
        if info is None:
            missing.append(frame)
            continue
        tl.DeleteMarkerAtFrame(frame)
        ok = tl.AddMarker(frame, info.get("color", "Blue"), info.get("name", ""), item["note"],
                          int(info.get("duration", 1)), MARKER_TAG)
        if not ok:  # rimetti il marker originale
            tl.AddMarker(frame, info.get("color", "Blue"), info.get("name", ""), info.get("note", ""),
                         int(info.get("duration", 1)), info.get("customData", "") or None)
            missing.append(frame)
        else:
            done.append(frame)
    out({"ok": not missing, "aggiornati": len(done), "non_trovati": missing, "backup": backup_path})


def cmd_ripristina(backup_file):
    with open(backup_file, encoding="utf-8") as f:
        b = json.load(f)
    resolve, project = connect()
    tl = find_timeline(project, b.get("timeline_id"), b.get("timeline"))
    if not tl:
        fail("Timeline del backup non trovata.")
    n = 0
    for frame, info in b["markers"].items():
        frame = int(frame)
        tl.DeleteMarkerAtFrame(frame)
        tl.AddMarker(frame, info.get("color", "Blue"), info.get("name", ""), info.get("note", ""),
                     int(info.get("duration", 1)), info.get("customData", "") or None)
        n += 1
    out({"ok": True, "ripristinati": n})


if __name__ == "__main__":
    a = sys.argv[1:]
    if not a:
        fail(__doc__)
    cmd = a[0]
    if cmd == "info":
        cmd_info()
    elif cmd == "leggi":
        cmd_leggi(a[1], "--trascrivi" in a)
    elif cmd == "audio":
        cmd_audio(a[1])
    elif cmd == "scrivi":
        cmd_scrivi(a[1])
    elif cmd == "ripristina":
        cmd_ripristina(a[1])
    else:
        fail(f"Comando sconosciuto: {cmd}")
