"""Marker EDL di DaVinci Resolve (versione gratuita).

Resolve esporta i marker con File > Esporta > Marker della timeline in EDL.
Ogni evento ha una riga di timecode seguita da una riga di commento del tipo:
    <nota> |C:ResolveColorBlue |M:<nome> |D:<durata>
Il parser è tollerante: legge colore, nome, durata e tratta il resto come nota.
"""
import re

from .core import frames_to_tc, tc_to_seconds

TC = r"(\d\d[:;]\d\d[:;]\d\d[:;]\d\d)"
EVENT_RE = re.compile(rf"^\s*(\d+)\s+\S+\s+\S+\s+\S+\s+{TC}\s+{TC}\s+{TC}\s+{TC}")


def _tc_frames(tc, fps):
    h, m, s, f = (int(x) for x in tc.replace(";", ":").split(":"))
    return ((h * 60 + m) * 60 + s) * round(fps) + f


def parse(text, fps=25, start_tc=None):
    title, events, cur = None, [], None
    for raw in text.splitlines():
        line = raw.rstrip("\n")
        if line.startswith("TITLE:"):
            title = line.split(":", 1)[1].strip()
            continue
        m = EVENT_RE.match(line)
        if m:
            cur = {"rec_in": m.group(4), "comment": []}
            events.append(cur)
            continue
        if cur is not None and line.strip():
            cur["comment"].append(line.strip())
    if not events:
        raise ValueError("Nessun marker trovato nel file EDL.")
    if start_tc is None:
        first_h = int(events[0]["rec_in"][:2])
        start_tc = f"{first_h:02d}:00:00:00"
    start = _tc_frames(start_tc, fps)
    markers = []
    for e in events:
        comment = " ".join(e["comment"])
        color = re.search(r"\|C:(?:ResolveColor)?(\w+)", comment)
        name = re.search(r"\|M:(.*?)(?=\s\|[A-Z]:|$)", comment)
        dur = re.search(r"\|D:(\d+)", comment)
        note = re.split(r"\s?\|[CMD]:", comment)[0].strip()
        if note.startswith("*"):
            note = note.lstrip("* ").strip()
        frame = _tc_frames(e["rec_in"], fps) - start
        markers.append({"frame": frame, "seconds": round(frame / fps, 3), "tc_registrazione": e["rec_in"],
                        "name": name.group(1).strip() if name else "", "note": note,
                        "color": color.group(1) if color else "Blue",
                        "duration": int(dur.group(1)) if dur else 1, "custom": ""})
    return {"timeline": title or "timeline", "fps": fps, "start_tc": start_tc, "fonte": "edl", "markers": markers}


def write(markers, title, fps=25, start_tc="01:00:00:00"):
    """markers: [{frame, name, note, color, duration}] -> testo EDL da reimportare."""
    start = _tc_frames(start_tc, fps)
    lines = [f"TITLE: {title}", "FCM: NON-DROP FRAME", ""]
    for i, mk in enumerate(sorted(markers, key=lambda x: x["frame"]), 1):
        a = frames_to_tc(start + mk["frame"], fps)
        b = frames_to_tc(start + mk["frame"] + max(1, mk.get("duration", 1)), fps)
        note = " ".join(mk["note"].split())  # l'EDL è una riga: niente a capo
        lines.append(f"{i:03d}  001      V     C        {a} {b} {a} {b}  ")
        lines.append(f"{note} |C:ResolveColor{mk.get('color', 'Blue')} |M:{mk.get('name', '')} |D:{max(1, mk.get('duration', 1))}")
        lines.append("")
    return "\n".join(lines)


__all__ = ["parse", "write", "tc_to_seconds"]
