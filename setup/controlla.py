"""Controllo dell'installazione. Solo libreria standard: gira con qualsiasi Python 3.9+.

    python3 setup/controlla.py            controlla tutto e stampa cosa manca
    python3 setup/controlla.py --rileva   stampa solo edizione/versione di Resolve e cartelle Drive (JSON)

Ogni riga: OK / MANCA / ATTENZIONE + come sistemare. Codice di uscita 0 se è tutto a posto.
"""
import glob
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAC = sys.platform == "darwin"
WIN = sys.platform.startswith("win")
HOME = Path.home()


def resolve_info():
    """Edizione e versione di DaVinci Resolve, dal log dell'ultimo avvio."""
    if MAC:
        app = Path("/Applications/DaVinci Resolve/DaVinci Resolve.app")
        log = HOME / "Library/Application Support/Blackmagic Design/DaVinci Resolve/logs/davinci_resolve.log"
        rpy = app / "Contents/Applications/ResolvePython"
    elif WIN:
        app = Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve\Resolve.exe")
        log = Path(os.environ.get("APPDATA", "")) / r"Blackmagic Design\DaVinci Resolve\Support\logs\davinci_resolve.log"
        rpy = Path(r"C:\Program Files\Blackmagic Design\DaVinci Resolve\ResolvePython\ResolvePython.exe")
    else:
        app = Path("/opt/resolve/bin/resolve")
        log = HOME / ".local/share/DaVinciResolve/logs/davinci_resolve.log"
        rpy = Path("/opt/resolve/bin/ResolvePython")
    info = {"installato": app.exists(), "edizione": None, "versione": None,
            "resolve_python": str(rpy) if rpy.exists() else None}
    if MAC and app.exists():
        try:
            out = subprocess.run(["defaults", "read", str(app / "Contents/Info"), "CFBundleShortVersionString"],
                                 capture_output=True, text=True).stdout.strip()
            info["versione"] = out or None
        except OSError:
            pass
    if log.exists():
        try:
            text = log.read_text(errors="ignore")[:200000]
        except OSError:
            text = ""
        m = re.search(r"Running DaVinci Resolve( Studio)? v?([\d.]+)", text)
        if m:
            info["edizione"] = "studio" if m.group(1) else "gratuita"
            info["versione"] = info["versione"] or m.group(2)
    return info


def drive_folders():
    """Cartelle Google Drive (Drive per desktop) presenti sul computer."""
    roots = []
    if MAC:
        roots = glob.glob(str(HOME / "Library/CloudStorage/GoogleDrive-*"))
    elif WIN:
        for letter in "GHIJKLMNOPQRSTUVWXYZ":
            p = Path(f"{letter}:/")
            if (p / "Il mio Drive").exists() or (p / "My Drive").exists():
                roots.append(str(p))
    found = []
    for r in roots:  # solo i primi livelli: con Drive in streaming una ricerca profonda è lentissima
        for pattern in ("*/stile_chapeau", "*/*/stile_chapeau", "*/*/*/stile_chapeau"):
            found += glob.glob(os.path.join(r, pattern))
    return {"drive": roots, "stile_chapeau_trovate": found}


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return False, str(e)


def main():
    if "--rileva" in sys.argv:
        print(json.dumps({"sistema": platform.system(), "chip": platform.machine(), **resolve_info(),
                          **drive_folders()}, ensure_ascii=False, indent=1))
        return 0
    problems = 0

    def line(ok, what, fix=""):
        nonlocal problems
        tag = "OK       " if ok is True else ("ATTENZIONE" if ok is None else "MANCA    ")
        if ok is False:
            problems += 1
        print(f"{tag} {what}" + (f"  →  {fix}" if fix and ok is not True else ""))

    ri = resolve_info()
    line(ri["installato"], f"DaVinci Resolve {ri['versione'] or ''} ({ri['edizione'] or 'edizione non rilevata'})",
         "Installa DaVinci Resolve e aprilo almeno una volta.")
    for tool in ("git", "ffmpeg", "ffprobe", "deno"):
        line(bool(shutil.which(tool)), tool, f"Installa {tool}.")
    venv_py = ROOT / (".venv/Scripts/python.exe" if WIN else ".venv/bin/python")
    line(venv_py.exists(), "ambiente Python del progetto (.venv)", "Crea .venv con Python 3.12 e installa requirements.txt.")
    cfg_path = ROOT / "config.local.json"
    cfg = json.loads(cfg_path.read_text(encoding="utf-8")) if cfg_path.exists() else None
    line(cfg is not None, "config.local.json", "Crealo seguendo INSTALLA.md.")
    if venv_py.exists():
        ok, out = run([str(venv_py), "-c", "import yt_dlp, PIL, certifi; print(yt_dlp.version.__version__)"])
        line(ok, f"yt-dlp + Pillow {out if ok else ''}".strip(), "pip install -r requirements.txt nella .venv")
        mod = "mlx_whisper" if (MAC and platform.machine() == "arm64") else "faster_whisper"
        ok, _ = run([str(venv_py), "-c", f"import {mod}"])
        line(ok, f"Whisper ({mod})", "pip install -r requirements.txt nella .venv")
        cop = [str(ROOT / "cop.cmd")] if WIN else [str(ROOT / "cop")]
        ok, out = run(cop + ["probe", "https://www.youtube.com/watch?v=jWDJ4_QSdt8"])
        line(ok and '"risoluzione_max"' in out, "lettura video YouTube (yt-dlp + deno)",
             "Aggiorna yt-dlp (pip install -U 'yt-dlp[default]') e controlla che deno sia installato.")
    if cfg:
        mem = Path(os.path.expanduser(cfg.get("cartella_memoria") or "")) if cfg.get("cartella_memoria") else None
        if mem:
            ok = mem.exists() and os.access(mem, os.W_OK)
            line(ok, f"memoria di stile condivisa: {mem}", "Controlla che Google Drive sia attivo e la cartella sincronizzata.")
        else:
            line(None, "memoria di stile solo locale (nessuna cartella Drive condivisa)",
                 "Indica la cartella stile_chapeau su Google Drive in config.local.json.")
        if cfg.get("edizione") == "studio" and venv_py.exists():
            ok, out = run(cop + ["info"])
            if '"ok": true' in out:
                line(True, "collegamento a DaVinci Resolve Studio")
            else:
                line(None, "collegamento a DaVinci Resolve Studio non verificato",
                     "Apri Resolve con un progetto; Preferenze > Sistema > Generali > External scripting using = Local.")
    print("\nTUTTO PRONTO" if problems == 0 else f"\n{problems} cose da sistemare")
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
