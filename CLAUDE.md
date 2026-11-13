# Coperture Chapeau

Strumento interno di Chapeau Media: parte dai marker "video" / "foto" / "articolo" di una timeline
DaVinci Resolve, cerca le coperture migliori, le fa approvare in una pagina web locale e scrive
link e minutaggi nei marker. Il comando principale è `/coperture`
(`.claude/commands/coperture.md`); la ricerca per singolo marker la fa il subagente
`ricercatore-coperture` (`.claude/agents/`).

Chi usa questo progetto è un montatore, non un programmatore: rispondi in italiano semplice.

## Regole fisse
- Non scaricare mai le coperture: solo link, minutaggi, fonti. I fotogrammi in `lavori/*/analisi`
  e `lavori/*/anteprime` servono solo all'analisi e alla pagina di revisione.
- Aggiorna solo i marker esistenti, non crearne di nuovi. Prima di scrivere viene fatto un backup
  (`./cop ripristina <lavoro>`).
- Nessun percorso personale o credenziale nei file versionati: tutto in `config.local.json`.
- La memoria di stile (`./cop memoria`) si legge all'inizio di ogni ricerca.

## Struttura
- `cop` / `cop.cmd` → riga di comando (`chapeau/__main__.py`), vedi `./cop -h`.
- `chapeau/resolve_bridge.py` → scripting ufficiale di Resolve Studio (gira con ResolvePython).
- `chapeau/edl.py` → marker EDL per DaVinci gratuito (21.1+ non ha più scripting).
- `chapeau/media.py` → yt-dlp + ffmpeg: fogli provini, verifica stacchi, anteprime; Wikimedia.
- `chapeau/lavoro.py` → stato di un lavoro (round, scelte, note finali).
- `chapeau/memoria.py` → memoria di stile condivisa su Google Drive (un file per persona).
- `revisione/` → pagina di revisione; l'aspetto Chapeau sta solo in `revisione/brand.css` e
  `revisione/logo.svg`.
- `setup/controlla.py` → controllo installazione; `INSTALLA.md` → procedura per Claude Code.
