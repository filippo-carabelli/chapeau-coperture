# Coperture Chapeau

Ricerca automatica di coperture (video, foto, articoli) per i video lunghi di Chapeau Media,
partendo dai marker di una timeline DaVinci Resolve.

1. In DaVinci metti dei marker con scritto `video`, `foto` o `articolo` (una nota sul marker ha la
   precedenza sul contesto).
2. In Claude Code, nella cartella del progetto, scrivi **`/coperture`**.
3. Si apre una pagina nel browser con 3 proposte per marker: Sì / No, motivo dello scarto, link tuoi.
4. Premi **Conferma**: i marker scartati vengono ricercati di nuovo finché non dai l'ok finale.
5. Link, minutaggi e fonti finiscono nei marker di DaVinci (Studio) o in un file da reimportare
   (versione gratuita).

**Installazione:** incolla in Claude Code il testo di `PROMPT_INSTALLAZIONE.md`; fa tutto lui
seguendo `INSTALLA.md`.

| | DaVinci Resolve Studio | DaVinci Resolve gratuito |
|---|---|---|
| Lettura marker | automatica (scripting) | export EDL guidato |
| Trascrizione | quella di Resolve (o Whisper) | Whisper |
| Scrittura | nei marker esistenti, con backup | file EDL da reimportare |

Le coperture non vengono mai scaricate: solo link, minutaggi e fonti. I diritti li valuta Chapeau.
