"""Analisi di video e foto candidati SENZA scaricare le coperture.

Dei video si leggono solo pochi fotogrammi in streaming (yt-dlp risolve l'URL,
ffmpeg legge solo i secondi che servono). I fotogrammi finiscono nella cartella
del lavoro solo come anteprime per l'analisi e per la pagina di revisione.
"""
import json
import re
import subprocess
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .core import secs_to_hms

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"
API_UA = "ChapeauCoperture/1.0 (strumento interno di ricerca d'archivio)"


# ---------------------------------------------------------------- yt-dlp
def _ydl(opts=None):
    import yt_dlp
    base = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True}
    base.update(opts or {})
    return yt_dlp.YoutubeDL(base)


def cerca_yt(query, n=12):
    with _ydl({"extract_flat": "in_playlist"}) as y:
        info = y.extract_info(f"ytsearch{n}:{query}", download=False)
    res = []
    for e in info.get("entries") or []:
        res.append({"url": e.get("url") or f"https://www.youtube.com/watch?v={e.get('id')}",
                    "titolo": e.get("title"), "canale": e.get("channel") or e.get("uploader"),
                    "durata": secs_to_hms(e["duration"]) if e.get("duration") else None,
                    "visualizzazioni": e.get("view_count")})
    return res


def probe(url):
    with _ydl() as y:
        info = y.extract_info(url, download=False)
    heights = sorted({f.get("height") for f in info.get("formats") or [] if f.get("height")})
    return {"url": info.get("webpage_url") or url, "titolo": info.get("title"),
            "canale": info.get("channel") or info.get("uploader"), "piattaforma": info.get("extractor_key"),
            "data": info.get("upload_date"), "durata_s": info.get("duration"),
            "risoluzione_max": max(heights) if heights else info.get("height"),
            "descrizione": (info.get("description") or "")[:600]}


def _section(url, start, end, max_h, out_dir, tag):
    """Scarica SOLO i secondi [start, end] in un file temporaneo (poi va cancellato)."""
    import yt_dlp
    from yt_dlp.utils import download_range_func
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob(f"_tmp_{tag}.*"):
        old.unlink()
    opts = {"quiet": True, "no_warnings": True, "noplaylist": True, "noprogress": True,
            "format": f"bv*[height<={max_h}]/b[height<={max_h}]/bv*/b",
            "outtmpl": str(out_dir / f"_tmp_{tag}.%(ext)s"),
            "download_ranges": download_range_func(None, [(max(0.0, start), end)]),
            "force_keyframes_at_cuts": False}
    with yt_dlp.YoutubeDL(opts) as y:
        info = y.extract_info(url, download=True)
    files = [f for f in out_dir.glob(f"_tmp_{tag}.*") if not f.name.endswith((".part", ".ytdl"))]
    if not files:
        raise RuntimeError("Download della sezione non riuscito")
    return files[0], info


def _duration(path):
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return None


# ---------------------------------------------------------------- immagini
def _font(size):
    for p in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
              "C:/Windows/Fonts/arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(p, size)
        except OSError:
            continue
    return ImageFont.load_default()


def contact_sheet(items, out_path, cols=5, width=360):
    """items: [(path, label)] -> un'unica immagine con le etichette (più economica da analizzare)."""
    imgs = []
    for p, label in items:
        try:
            im = Image.open(p).convert("RGB")
        except OSError:
            continue
        im.thumbnail((width, width * 2))
        imgs.append((im, label))
    if not imgs:
        return None
    h = max(i.height for i, _ in imgs)
    rows = (len(imgs) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * width, rows * (h + 26)), "white")
    d = ImageDraw.Draw(sheet)
    font = _font(18)
    for k, (im, label) in enumerate(imgs):
        x, y = (k % cols) * width, (k // cols) * (h + 26)
        sheet.paste(im, (x, y + 26))
        d.text((x + 6, y + 3), label, fill="black", font=font)
    sheet.save(out_path, quality=85)
    return str(out_path)


# ---------------------------------------------------------------- video
def _durata_video(url):
    with _ydl() as y:
        return (y.extract_info(url, download=False) or {}).get("duration")


def scan(url, out_dir, every=None, start=0.0, end=None, max_frames=40):
    """Panoramica: un fotogramma ogni `every` secondi -> un foglio provini con i minutaggi.

    Legge il video a bassa risoluzione solo nel tratto richiesto, poi cancella il file temporaneo.
    """
    out_dir = Path(out_dir)
    duration = _durata_video(url)
    end = min(end or duration or 600, duration or end or 600)
    every = every or max(2.0, (end - start) / max_frames)
    tag = re.sub(r"\W+", "", url)[-10:] + f"_{int(start)}"
    tmp, info = _section(url, start, end, 360, out_dir, tag)
    fr = out_dir / f"scan_{tag}"
    fr.mkdir(exist_ok=True)
    for old in fr.glob("*.jpg"):
        old.unlink()
    try:
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(tmp), "-vf",
                        f"fps=1/{every:.3f}:start_time={every / 2:.3f},scale=480:-2", "-q:v", "4",
                        str(fr / "%03d.jpg")], capture_output=True, timeout=600)
    finally:
        tmp.unlink(missing_ok=True)
    frames = sorted(fr.glob("*.jpg"))[:max_frames]
    items = [(p, secs_to_hms(start + every / 2 + i * every)) for i, p in enumerate(frames)]
    sheet = contact_sheet(items, out_dir / f"provini_{tag}.jpg")
    return {"foglio_provini": sheet, "ogni_s": round(every, 1), "da": secs_to_hms(start), "a": secs_to_hms(end),
            "durata_video": secs_to_hms(duration) if duration else None, "fotogrammi": len(items)}


def verifica(url, at, out_dir, span=8.0, max_h=1080, prefix="clip"):
    """Analisi ravvicinata attorno ad `at`: 2 fotogrammi/s in alta qualità + rilevamento stacchi.

    Restituisce gli intervalli continui (senza stacchi) >= 2 s e un foglio provini da guardare.
    """
    out_dir = Path(out_dir)
    fr_dir = out_dir / f"{prefix}_frames"
    fr_dir.mkdir(parents=True, exist_ok=True)
    for old in fr_dir.glob("*.jpg"):
        old.unlink()
    start = max(0.0, at - span / 2)
    tmp, info = _section(url, start, start + span, max_h, out_dir, prefix)
    try:
        real_span = _duration(tmp) or span
        # il file può partire dal keyframe precedente: allineiamo la fine al punto richiesto
        lead = max(0.0, real_span - span) if real_span > span + 0.3 else 0.0
        fc = ("[0:v]split=2[a][b];[a]fps=2[f];"
              "[b]select='gt(scene,0.15)',showinfo[s]")
        r = subprocess.run(["ffmpeg", "-hide_banner", "-y", "-ss", f"{lead:.2f}", "-i", str(tmp),
                            "-filter_complex", fc, "-map", "[f]", "-q:v", "2", str(fr_dir / "%03d.jpg"),
                            "-map", "[s]", "-f", "null", "-"], capture_output=True, text=True, timeout=240)
        with Image.open(sorted(fr_dir.glob("*.jpg"))[0]) as im:
            w, h = im.size
    finally:
        tmp.unlink(missing_ok=True)
    span = min(span, real_span - lead)
    cuts = sorted({round(float(x), 2) for x in re.findall(r"pts_time:([\d.]+)", r.stderr)})
    cuts = [c for c in cuts if 0.2 < c < span - 0.2]
    frames = sorted(fr_dir.glob("*.jpg"))
    bounds = [0.0, *cuts, span]
    segs = []
    for x, y in zip(bounds, bounds[1:]):
        if y - x >= 2.0:
            segs.append({"inizio": secs_to_hms(start + x), "fine": secs_to_hms(start + y),
                         "inizio_s": round(start + x, 2), "fine_s": round(start + y, 2), "durata_s": round(y - x, 2)})
    items = [(p, secs_to_hms(start + i * 0.5)) for i, p in enumerate(frames)]
    sheet = contact_sheet(items, out_dir / f"{prefix}_verifica.jpg", cols=4, width=420)
    return {"risoluzione": f"{w}x{h}", "finestra": [secs_to_hms(start), secs_to_hms(start + span)],
            "stacchi": [secs_to_hms(start + c) for c in cuts], "intervalli_continui": segs,
            "foglio_provini": sheet, "fotogrammi": [str(p) for p in frames],
            "nota": "Stacchi rilevati automaticamente: controlla comunque a vista dissolvenze, zoom e loghi."}


def anteprime_video(url, start_s, end_s, out_dir, prefix, n=3):
    """Salva n fotogrammi dell'intervallo proposto per la pagina di revisione."""
    out_dir = Path(out_dir)
    tmp, _ = _section(url, start_s, end_s, 720, out_dir, prefix)
    res = []
    try:
        dur = _duration(tmp) or (end_s - start_s)
        lead = max(0.0, dur - (end_s - start_s))
        length = dur - lead
        for k in range(n):
            t = lead + length * (k + 0.5) / n
            p = out_dir / f"{prefix}-{k + 1}.jpg"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-ss", f"{t:.2f}", "-i", str(tmp), "-frames:v", "1",
                            "-vf", "scale=640:-2", "-q:v", "3", str(p)], capture_output=True, timeout=60)
            if p.exists():
                res.append(str(p))
    finally:
        tmp.unlink(missing_ok=True)
    return res


# ---------------------------------------------------------------- foto
def _get(url, headers=None):
    import ssl

    import certifi
    ctx = ssl.create_default_context(cafile=certifi.where())
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=40, context=ctx) as r:
        return r.read(), r.headers.get_content_type()


def foto(url, out_dir, prefix):
    """Scarica l'immagine SOLO per analisi/anteprima: dimensioni reali + miniatura."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    data, ctype = _get(url)
    raw = out_dir / f"{prefix}_analisi"
    raw.write_bytes(data)
    with Image.open(raw) as im:
        w, h = im.size
        im = im.convert("RGB")
        full = out_dir / f"{prefix}_analisi.jpg"
        im.save(full, quality=90)
        im.thumbnail((900, 900))
        prev = out_dir / f"{prefix}.jpg"
        im.save(prev, quality=85)
    raw.unlink()
    return {"risoluzione": f"{w}x{h}", "megapixel": round(w * h / 1e6, 1), "tipo": ctype,
            "per_analisi": str(full), "anteprima": str(prev)}


def cerca_commons(query, n=15):
    """Wikimedia Commons: foto d'archivio a piena risoluzione con autore e licenza."""
    q = urllib.parse.urlencode({"action": "query", "generator": "search", "gsrnamespace": 6, "gsrsearch": query,
                                "gsrlimit": n, "prop": "imageinfo", "iiprop": "url|size|extmetadata",
                                "iiurlwidth": 640, "format": "json"})
    data, _ = _get(f"https://commons.wikimedia.org/w/api.php?{q}", {"User-Agent": API_UA})
    pages = (json.loads(data).get("query") or {}).get("pages") or {}
    res = []
    for p in sorted(pages.values(), key=lambda x: x.get("index", 0)):
        ii = (p.get("imageinfo") or [{}])[0]
        meta = ii.get("extmetadata") or {}

        def mv(k):
            return re.sub(r"<[^>]+>", "", (meta.get(k) or {}).get("value", ""))[:160]
        res.append({"titolo": p.get("title"), "pagina": ii.get("descriptionurl"), "url": ii.get("url"),
                    "miniatura": ii.get("thumburl"), "risoluzione": f"{ii.get('width')}x{ii.get('height')}",
                    "data": mv("DateTimeOriginal"), "autore": mv("Artist"), "licenza": mv("LicenseShortName"),
                    "descrizione": mv("ImageDescription")})
    return res
