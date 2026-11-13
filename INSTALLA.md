# Installazione — istruzioni per Claude Code

Questo file lo legge ed esegue **Claude Code** sul computer di un collaboratore Chapeau.
Il collaboratore non è un tecnico: parla italiano semplice, un passaggio alla volta, e fagli solo
le domande indispensabili. Fai tu tutto quello che puoi fare da solo. Quando serve un'azione sua
(una password, un clic in una finestra, un'impostazione di DaVinci) spiega esattamente dove
cliccare e cosa scrivere, poi **aspetta che risponda "fatto"** prima di andare avanti. Se qualcosa
va storto, leggi l'errore, sistemalo tu se puoi, altrimenti spiegagli in una riga cosa fare.

Parti dal presupposto che sul computer non ci sia niente oltre a DaVinci Resolve.
Se un passaggio è già fatto (programma già installato, cartella già presente), saltalo senza dirlo.
Nessun percorso personale o credenziale va scritto nei file del progetto: solo in
`config.local.json` (che non viene mai condiviso).

Tieni il collaboratore aggiornato con una riga per fase ("Sto installando i programmi che servono…").

---

## 1. Sistema
Capisci se è un Mac (e se Apple Silicon o Intel) o Windows. Tutto il resto dipende da questo.

## 2. Programmi di base

**Mac**
1. Homebrew: se `brew` non c'è, va installato con la password del Mac, che solo il collaboratore
   può scrivere. Digli: «Apri l'app **Terminale** (premi Cmd+Spazio, scrivi Terminale, Invio),
   incolla questa riga, premi Invio. Quando chiede la password del Mac scrivila (non vedrai i
   caratteri, è normale) e premi Invio. Alla fine dimmi "fatto".» e dagli la riga:
   `/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"`
   Poi rendi `brew` disponibile (su Apple Silicon `eval "$(/opt/homebrew/bin/brew shellenv)"` e
   aggiungilo a `~/.zprofile` se manca).
   Se il collaboratore non è amministratore del Mac, fermati e digli di chiedere a Fil.
2. `brew install git python@3.12 ffmpeg deno`

**Windows**
1. `winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements`
   e lo stesso per `Python.Python.3.12`, `Gyan.FFmpeg`, `DenoLand.Deno`.
   Se compare una finestra «Vuoi consentire…?», digli di cliccare **Sì**.
2. Riapri la shell o aggiorna il PATH della sessione prima di proseguire.

Python 3.12 è la versione scelta perché è compatibile sia con lo scripting di DaVinci sia con
Whisper.

## 3. Scaricare il progetto
Cartella: `~/Documents/chapeau-coperture` (Windows: `%USERPROFILE%\Documents\chapeau-coperture`).
- Se non esiste: `git clone https://github.com/filippo-carabelli/chapeau-coperture.git <cartella>`
- Se esiste già: `git -C <cartella> pull` (non toccare `config.local.json` e `lavori/`).
Da qui in avanti lavora dentro quella cartella.

## 4. Ambiente Python del progetto
- Mac: `python3.12 -m venv .venv && .venv/bin/pip install -U pip && .venv/bin/pip install -r requirements.txt`
- Windows: `py -3.12 -m venv .venv` poi `.venv\Scripts\pip install -r requirements.txt`
Avvisa che ci vuole qualche minuto.

## 5. DaVinci Resolve: Studio o gratuito
Lancia `python3 setup/controlla.py --rileva` (Windows: `py -3.12 setup\controlla.py --rileva`).
- Se `installato` è falso: chiedigli di installare DaVinci Resolve e aprirlo una volta.
- Se `edizione` è nullo (Resolve mai aperto su questo computer) chiedi soltanto:
  «Quando apri DaVinci, nella schermata iniziale c'è scritto **DaVinci Resolve Studio**?»

**Studio** → flusso completo automatico.
1. Digli: «Apri DaVinci Resolve. In alto a sinistra clicca **DaVinci Resolve > Preferences**
   (Windows: **DaVinci Resolve > Preferences**), scheda **System > General**, alla voce
   **External scripting using** scegli **Local**, clicca **Save** e riavvia DaVinci.»
2. Variabili d'ambiente per lo scripting (servono al connettore MCP e ai Python esterni):
   - Mac: aggiungi a `~/.zprofile` (se mancano)
     ```
     export RESOLVE_SCRIPT_API="/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting"
     export RESOLVE_SCRIPT_LIB="/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so"
     export PYTHONPATH="$PYTHONPATH:$RESOLVE_SCRIPT_API/Modules/"
     ```
   - Windows: `setx RESOLVE_SCRIPT_API "%PROGRAMDATA%\Blackmagic Design\DaVinci Resolve\Support\Developer\Scripting"`,
     `setx RESOLVE_SCRIPT_LIB "C:\Program Files\Blackmagic Design\DaVinci Resolve\fusionscript.dll"`,
     `setx PYTHONPATH "%RESOLVE_SCRIPT_API%\Modules\"` (usa i valori espansi).
3. Connettore **davinci-resolve-mcp** (utile per controlli al volo su Resolve; il flusso
   /coperture legge e scrive i marker con lo script del progetto, che sa anche aggiornare le note):
   - `git clone https://github.com/samuelgursky/davinci-resolve-mcp.git ~/.chapeau-coperture/davinci-resolve-mcp`
     (Windows: `%USERPROFILE%\.chapeau-coperture\davinci-resolve-mcp`)
   - usa il suo installer con Python 3.12: `python3.12 install.py --clients manual` (crea il
     venv del connettore e stampa la configurazione); leggi prima il README del connettore se
     l'installer è cambiato
   - registralo per l'utente con il Python del venv creato dall'installer:
     `claude mcp add davinci-resolve --scope user -e RESOLVE_SCRIPT_API=… -e RESOLVE_SCRIPT_LIB=… -e PYTHONPATH=…/Modules -- <venv>/bin/python <repo>/src/server.py`
   - se qualcosa fallisce qui, NON bloccare l'installazione: segnalalo alla fine.

**Gratuito** → da DaVinci Resolve 21.1 la versione gratuita non permette più nessuno script.
Il flusso funziona lo stesso: il collaboratore esporta marker (EDL) e audio, Claude Code
trascrive con Whisper e alla fine prepara un file di marker da reimportare. /coperture lo guida
passo passo ogni volta. Qui serve solo:
1. Creare la cartella `~/Documents/Chapeau Coperture/Export` (Windows: in Documenti).
2. Scaricare in anticipo il modello di Whisper (circa 1,6 GB) così la prima trascrizione non
   aspetta: `./cop` non serve, basta
   - Mac Apple Silicon: `.venv/bin/python -c "from huggingface_hub import snapshot_download as s; s('mlx-community/whisper-large-v3-turbo')"`
   - altrimenti: `.venv/bin/python -c "from faster_whisper import WhisperModel as W; W('large-v3-turbo', compute_type='int8')"`
   Avvisa che il download richiede qualche minuto.

## 6. Memoria di stile condivisa (Google Drive)
Le approvazioni e gli scarti di tutti finiscono nella cartella condivisa **stile_chapeau** su
Google Drive, così il sistema impara dai gusti di tutto il team.
1. `setup/controlla.py --rileva` elenca le cartelle Drive e le eventuali `stile_chapeau` trovate.
2. Se Google Drive per desktop non c'è: guidalo a installarlo (https://www.google.com/drive/download/),
   accedere con l'account che usa per Chapeau e aspettare che compaia nel Finder / Esplora file.
3. Se la cartella `stile_chapeau` non compare: Fil l'ha condivisa con lui. Digli: «Apri
   drive.google.com, sezione **Condivisi con me**, clic destro sulla cartella **stile_chapeau** >
   **Organizza > Aggiungi scorciatoia** > **Il mio Drive**.» Poi ricontrolla.
4. Se c'è più di una cartella candidata, chiedi quale usare. Se proprio non c'è Drive, usa la
   cartella locale `stile_chapeau/` del progetto e segnalalo alla fine.

## 7. Configurazione locale
Unica domanda personale: «Come ti chiami? (serve solo a firmare le tue scelte nella memoria
condivisa)». Poi scrivi `config.local.json` partendo da `config.example.json`:
`nome`, `edizione` ("studio"/"gratuita"), `versione_resolve`, `resolve_python` (dal rilevamento,
o vuoto), `cartella_memoria`, `cartella_export`, `whisper.motore` ("mlx" su Mac Apple Silicon,
altrimenti "faster").

## 8. Avvio facile
Crea sulla Scrivania un'icona che apre Claude Code nella cartella giusta:
- Mac: `~/Desktop/Coperture Chapeau.command` con
  `cd "$HOME/Documents/chapeau-coperture" && claude` e `chmod +x`.
- Windows: `Coperture Chapeau.bat` sul Desktop con `cd /d "%USERPROFILE%\Documents\chapeau-coperture" && claude`.
Se il collaboratore usa l'app desktop di Claude, spiegagli invece di scegliere la cartella
`chapeau-coperture` quando apre una nuova sessione Code.

## 9. Test finale
1. `python3 setup/controlla.py` (Windows: `py -3.12 setup\controlla.py`): deve dire TUTTO PRONTO
   (le righe ATTENZIONE vanno spiegate ma non bloccano).
2. `./cop cerca-yt "Archivio Luce" -n 3` deve restituire risultati.
3. Studio: chiedi di aprire DaVinci con un progetto qualsiasi e lancia `./cop info`.
4. Gratuito: crea un piccolo audio di prova con ffmpeg e trascrivilo per verificare Whisper.

## 10. Fine
Riepilogo in 3 righe, senza gergo:
- cosa è stato installato e se è Studio o gratuito;
- come si usa: «Doppio clic su **Coperture Chapeau** sulla Scrivania, poi scrivi **/coperture**»;
- eventuali cose rimaste in sospeso (es. connettore MCP non installato, Drive da collegare).
