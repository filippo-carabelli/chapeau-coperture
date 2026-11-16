---
description: Fase di ricerca di /coperture per i marker indicati (usata in automatico da ./cop ricerca-auto)
argument-hint: "<lavoro> <id marker...>"
---

Stai eseguendo, senza nessuno a cui fare domande, la FASE DI RICERCA delle coperture Chapeau.
Argomenti: `$ARGUMENTS` → la prima parola è il nome del lavoro, le altre sono gli id dei marker
da cercare in questo giro (es. `stand-kimbo-2026-11-13 m001 m004`).

1. Leggi `lavori/<lavoro>/contesto.md` (è già aggiornato: non rigenerarlo) e lancia `./cop memoria`.
2. Per ogni marker indicato lancia un subagente `ricercatore-coperture` (strumento Agent), fino a 5
   in parallelo, in ordine di timecode. Nel prompt di ciascuno metti, presi da `contesto.md`:
   nome lavoro, id marker, tipo, timecode, "cosa serve (approvato da Fil)" o, se manca, la tua
   deduzione dal contesto, la nota di Fil, le frasi della trascrizione attorno al marker, la durata
   da coprire e l'eventuale "SERVONO 2 VIDEO DIVERSI", gli scarti dei giri precedenti con i motivi,
   le coperture già usate in questo video e il riassunto della memoria di stile. Ricordagli di
   lanciare `./cop usate --lavoro <lavoro> --id <id>` prima di scrivere il risultato e di usare
   `./cop` sempre dalla cartella del progetto, senza `cd`.
3. Aspetta che finiscano tutti. Non lanciare `./cop unisci` né `./cop revisione`: ci pensa il
   programma che ti ha avviato.
4. Se un ricercatore si ferma per il limite di utilizzo, non insistere: chiudi e scrivi nella
   risposta la frase esatta del limite (con l'orario di reset). Il programma riprenderà da solo
   i marker mancanti dopo il reset.
5. Chiudi con una riga per marker: id, quante proposte, la migliore.
