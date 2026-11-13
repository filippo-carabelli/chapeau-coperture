"""Configurazione locale, percorsi e utilità comuni."""
import json
import platform
import re
import subprocess
import sys
import unicodedata
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.local.json"
TIPI = ("video", "foto", "articolo")


def load_config():
    if not CONFIG_PATH.exists():
        sys.exit("Manca config.local.json: rilancia l'installazione (incolla di nuovo il prompt di installazione).")
    with open(CONFIG_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def lavori_dir(cfg=None):
    cfg = cfg or load_config()
    d = Path(cfg.get("cartella_lavori") or ROOT / "lavori").expanduser()
    d.mkdir(parents=True, exist_ok=True)
    return d


def job_path(name):
    p = Path(name)
    if p.is_absolute() or p.exists():
        return p
    return lavori_dir() / name


def slug(text):
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()[:50] or "timeline"


def now():
    return datetime.now().isoformat(timespec="seconds")


def read_json(path, default=None):
    path = Path(path)
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(path)


def secs_to_hms(s):
    s = max(0.0, float(s))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    if h >= 1:
        return f"{int(h)}:{int(m):02d}:{sec:04.1f}"
    return f"{int(m)}:{sec:04.1f}"


def parse_time(t):
    """'1:23.5', '01:02:03', '83.5' -> secondi."""
    if isinstance(t, (int, float)):
        return float(t)
    parts = [float(p) for p in str(t).strip().split(":")]
    v = 0.0
    for p in parts:
        v = v * 60 + p
    return v


def tc_to_seconds(tc, fps=25):
    h, m, s, f = (int(x) for x in tc.replace(";", ":").split(":"))
    return h * 3600 + m * 60 + s + f / round(fps)


def frames_to_tc(frames, fps=25):
    n = round(fps)
    f = int(frames) % n
    s = int(frames) // n
    return f"{s // 3600:02d}:{s // 60 % 60:02d}:{s % 60:02d}:{f:02d}"


def resolve_python(cfg=None):
    """Interprete con cui lanciare il ponte verso Resolve."""
    cfg = cfg or load_config()
    p = cfg.get("resolve_python")
    if p and Path(p).exists():
        return p
    if sys.platform == "darwin":
        p = "/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Applications/ResolvePython"
    elif sys.platform.startswith("win"):
        p = r"C:\Program Files\Blackmagic Design\DaVinci Resolve\ResolvePython\ResolvePython.exe"
    else:
        p = "/opt/resolve/bin/ResolvePython"
    return p if Path(p).exists() else sys.executable


def run_bridge(*args):
    cmd = [resolve_python(), str(ROOT / "chapeau" / "resolve_bridge.py"), *map(str, args)]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(r.stdout)
    except json.JSONDecodeError:
        return {"ok": False, "errore": (r.stderr or r.stdout).strip()[-800:]}


def is_apple_silicon():
    return sys.platform == "darwin" and platform.machine() == "arm64"
