"""Ricerca in automatico, a prova di limiti di utilizzo.

`./cop ricerca-auto <lavoro>` lancia Claude Code in modalità automatica (`claude -p`) solo per i
marker ancora da cercare. Se l'account raggiunge il limite di utilizzo, il lavoro si mette in
pausa, aspetta l'orario di reset e riparte da dove era rimasto: i risultati di ogni marker sono
già salvati su file, quindi non si perde niente. A ricerca finita unisce le proposte e apre da
sola la pagina di revisione.

Gira in un processo separato: continua anche se si chiude la finestra di Claude Code, finché il
computer resta acceso (sul Mac impedisce lo stop automatico per inattività).
"""
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timedelta

from . import lavoro
from .core import ROOT, job_path

PROMPT_FILE = ROOT / ".claude" / "commands" / "coperture-ricerca.md"
STRUMENTI = ["Agent", "Task", "Bash(./cop:*)", "Bash(cop.cmd:*)", "Read", "Glob", "Grep",
             "Write(./lavori/**)", "Edit(./lavori/**)", "WebSearch", "WebFetch"]
ATTESA_SENZA_PROGRESSI = 15 * 60      # nessun marker nuovo: forse limite non dichiarato, riprovo tra 15 min
MAX_GIRI_A_VUOTO = 30                 # ~7,5 ore senza progressi: mi fermo e avviso
ATTESA_MAX = int(os.environ.get("COP_ATTESA_MAX", 6 * 3600))   # i test la abbassano
MARGINE = 120                         # dopo il reset aspetto 2 minuti in più
MIN_ATTESA = min(60, ATTESA_MAX)


def _log(job_dir, msg):
    riga = f"[{datetime.now():%H:%M}] {msg}"
    print(riga, flush=True)
    with open(job_dir / "ricerca_auto.log", "a", encoding="utf-8") as f:
        f.write(riga + "\n")


def avvisa(msg):
    """Notifica di sistema (Mac); altrove basta il messaggio nel terminale."""
    if sys.platform == "darwin":
        testo = msg.replace('"', "'")
        subprocess.run(["osascript", "-e", f'display notification "{testo}" with title "Coperture Chapeau"'],
                       capture_output=True)


def resta_sveglio():
    if sys.platform == "darwin" and shutil.which("caffeinate"):
        subprocess.Popen(["caffeinate", "-i", "-w", str(os.getpid())])


def secondi_al_reset(testo, adesso=None):
    """Se il testo dice che è finito il limite di utilizzo, quanti secondi aspettare (altrimenti None)."""
    t = testo or ""
    if not re.search(r"(usage limit|hit your .{0,20}limit|limit reached|rate.?limit|\b429\b)", t, re.I):
        return None
    adesso = adesso or datetime.now()
    m = re.search(r"limit reached\|(\d{10})", t) or re.search(r"\breset\w*\D{0,20}(\d{10})\b", t)
    if m:
        return max(MIN_ATTESA, min(ATTESA_MAX, int(m.group(1)) - int(adesso.timestamp()) + MARGINE))
    m = re.search(r"resets?\s+(?:at\s+)?(?:(mon|tue|wed|thu|fri|sat|sun)\w*\s+)?(\d{1,2})(?:[:.](\d{2}))?\s*(am|pm)?",
                  t, re.I)
    if m:
        giorno = (m.group(1) or "").lower()[:3]
        h, mi, ap = int(m.group(2)), int(m.group(3) or 0), (m.group(4) or "").lower()
        if ap == "pm" and h < 12:
            h += 12
        if ap == "am" and h == 12:
            h = 0
        reset = adesso.replace(hour=h % 24, minute=mi, second=0, microsecond=0)
        if giorno:   # limite settimanale: "resets Mon 12:00am"
            target = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"].index(giorno)
            reset += timedelta(days=(target - adesso.weekday()) % 7)
            if reset <= adesso:
                reset += timedelta(days=7)
            return max(MIN_ATTESA, int((reset - adesso).total_seconds()) + MARGINE)   # niente tetto: può durare giorni
        if reset <= adesso:
            reset += timedelta(days=1)
        return max(MIN_ATTESA, min(ATTESA_MAX, int((reset - adesso).total_seconds()) + MARGINE))
    return min(ATTESA_MAX, 30 * 60)   # limite senza orario: riprovo tra mezz'ora


def senza_accesso(testo):
    """Claude Code da terminale non è collegato all'account (serve rifare il login)."""
    return bool(re.search(r"(Failed to authenticate|OAuth session expired|Please run /login|Invalid API key|"
                          r"not logged in|authentication_error)", testo or "", re.I))


def _claude():
    cmd = os.environ.get("COP_CLAUDE")          # i test usano un finto claude
    if cmd:
        return cmd.split()
    exe = shutil.which("claude") or str(os.path.expanduser("~/.local/bin/claude"))
    return [exe]


def _prompt(job, ids):
    testo = PROMPT_FILE.read_text(encoding="utf-8")
    testo = re.sub(r"^---.*?---\s*", "", testo, flags=re.S)        # via l'intestazione del comando
    return testo.replace("$ARGUMENTS", f"{job} {' '.join(ids)}")


def esegui_claude(job_dir, job, ids):
    cmd = _claude() + ["-p", _prompt(job, ids), "--model", "sonnet", "--output-format", "json",
                       "--permission-prompts", "none", "--allowedTools", *STRUMENTI]
    # Primo tentativo: Claude Code stesso aspetta il reset del limite (se la versione lo supporta);
    # se non lo fa ed esce, ci pensa il ciclo qui sotto.
    env = {**os.environ, "CLAUDE_CODE_RETRY_WATCHDOG": "1",
           "CLAUDE_CODE_RETRY_WATCHDOG_MAX_USAGE_LIMIT_WAIT_MS": str(6 * 3600 * 1000)}
    try:
        r = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=12 * 3600, env=env)
        out = (r.stdout or "") + "\n" + (r.stderr or "")
    except subprocess.TimeoutExpired as e:
        out = f"timeout dopo 12 ore\n{e.stdout or ''}"
    with open(job_dir / "ricerca_auto_claude.log", "a", encoding="utf-8") as f:
        f.write(f"\n===== {datetime.now():%Y-%m-%d %H:%M} marker {' '.join(ids)}\n{out[-6000:]}\n")
    return out


def ricerca_auto(job, revisione=True):
    d = job_path(job)
    resta_sveglio()
    lavoro.contesto(job)                       # aggiorna il contesto (non azzera il giro già iniziato)
    a_vuoto = 0
    while True:
        manc = lavoro.mancanti(job)
        if not manc:
            break
        _log(d, f"Ricerca in corso: {len(manc)} marker da fare ({', '.join(manc)})")
        out = esegui_claude(d, job, manc)
        if senza_accesso(out):
            _log(d, "Claude Code da terminale non è collegato all'account: serve il login. Mi fermo.")
            avvisa("Ricerca ferma: serve rifare il login di Claude Code nel Terminale.")
            return 3
        dopo = lavoro.mancanti(job)
        fatti = len(manc) - len(dopo)
        attesa = secondi_al_reset(out)
        if attesa is not None and dopo:
            alle = (datetime.now() + timedelta(seconds=attesa)).strftime("%H:%M")
            _log(d, f"Limite di utilizzo raggiunto ({fatti} marker fatti in questo giro). In pausa: riprendo alle {alle}.")
            avvisa(f"Limite raggiunto: ricerca in pausa, riprende da sola alle {alle}.")
            time.sleep(attesa)
            a_vuoto = 0
            continue
        if fatti > 0:
            a_vuoto = 0
            continue
        a_vuoto += 1
        if a_vuoto >= MAX_GIRI_A_VUOTO:
            _log(d, "Nessun progresso da molte ore: mi fermo. Rilancia /coperture per riprendere.")
            avvisa("Ricerca ferma: nessun progresso da ore. Rilancia /coperture.")
            return 2
        _log(d, f"Nessun marker completato in questo giro: riprovo tra {ATTESA_SENZA_PROGRESSI // 60} minuti.")
        time.sleep(min(ATTESA_SENZA_PROGRESSI, ATTESA_MAX))

    path, problemi, _ = lavoro.unisci(job)
    _log(d, "Ricerca finita. " + (f"Da controllare: {'; '.join(problemi)}" if problemi else "Nessun problema."))
    if not revisione:
        print(json.dumps({"ok": True, "proposte": str(path), "problemi": problemi}, ensure_ascii=False, indent=1))
        return 0
    avvisa("Ricerca finita: si apre la pagina di revisione.")
    from .revisione import servi
    scelte = servi(d, apri=True)
    stato, pend = lavoro.registra(job, scelte)
    avvisa("Scelte salvate. Torna su Claude Code e scrivi /coperture per continuare.")
    print(json.dumps({"round": stato["round"], "ok_finale": stato.get("ok_finale"),
                      "approvati": sum(1 for s in stato["markers"].values() if s["chiuso"]),
                      "da_rifare": [{"id": m["id"], "tc": m["tc"], "tipo": m["tipo"],
                                     "scarti": stato["markers"][m["id"]]["scartati"][-3:]} for m in pend],
                      "problemi_ricerca": problemi}, ensure_ascii=False, indent=1))
    return 0
