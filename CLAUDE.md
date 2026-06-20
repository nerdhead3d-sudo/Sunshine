# Note per Claude Code

Questo progetto viene sviluppato in parallelo da sessioni Claude Code su PC
diversi. Questo file riassume lo stato e le decisioni recenti che non sono
ovvie dal solo codice, per chi riprende il lavoro su un'altra macchina.

## Coordinamento tra sessioni parallele

- **Prima di iniziare**: `git pull` sempre, e leggi questo file per intero
  prima di toccare aree che potrebbero essere state cambiate dall'altra
  macchina (vedi sezioni sotto).
- **Push frequenti e piccoli** invece di accumulare giorni di lavoro non
  pushato: riduce le probabilità di conflitto reale con l'altra sessione.
- **Mai force-push** su `master` per "vincere" un conflitto: se i due
  remoti divergono, fai un merge/rebase normale e risolvi a mano.
- **`python -m unittest discover -s tests` deve passare prima di ogni
  push** — c'è anche una CI (`.github/workflows/tests.yml`, GitHub
  Actions) che lo verifica automaticamente a ogni push/PR su
  `windows-latest`; controlla che sia verde prima di continuare a
  costruirci sopra.
- **Aggiorna questo file** quando prendi una decisione strutturale non
  ovvia dal codice (scelte di design, cose provate e scartate, perché).
  Non limitarti ad aggiungere: se una sezione descrive qualcosa che hai
  appena cambiato/rimosso, aggiornala invece di lasciarla obsoleta.

## Pipeline sprite

Solo `generate_placeholders.py` (procedurale, forme PIL, nessuna foto/AI),
richiamato da `main.py:ensure_sprites()` quando `pet/assets/sprites/` non
esiste o è vuota (cartella in `.gitignore`, sempre rigenerata). Genera
tutti gli stati: `idle`, `walk_left`/`walk_right`, `sit`, `react`, `sleep`,
`dragged`.

Una sessione parallela su un'altra macchina aveva aggiunto una pipeline
basata su due foto di riferimento (`generate_from_reference.py` +
`pet/assets/reference/*.png`, derivava gli sprite con trasformazioni
geometriche). **Rimossa di nuovo su richiesta esplicita dell'utente**
("non usiamo immagini di quell'altro") — se l'idea va ripresa in futuro,
va richiesta di nuovo esplicitamente, non va reintrodotta di default.

## Comportamenti pet

`pet/behavior/state_machine.py` ha `IDLE`/`WALK_LEFT`/`WALK_RIGHT`/`REACT`/
`SIT`/`SLEEP`/`DRAGGED`:
- `SIT`: durante l'idle, con probabilità `config.SIT_CHANCE` si siede invece
  di camminare.
- `SLEEP`: da seduto, con probabilità `config.SLEEP_CHANCE` si addormenta.
- `DRAGGED`: priorità assoluta, forzato da `pet/overlay/pet_window.py`
  quando l'utente tiene premuto e sposta il mouse oltre
  `config.DRAG_MOVE_THRESHOLD_PX` (sotto soglia resta un click normale, vedi
  "Click sul pet" sotto). Al rilascio, se il pet è a mezz'aria, cade con
  una breve accelerazione di gravità (`config.FALL_ACCEL`/`FALL_MAX_SPEED`)
  invece di teletrasportarsi; se durante la caduta una finestra è
  direttamente sotto (sovrapposizione orizzontale >= 50% della larghezza
  del pet), atterra sul suo bordo superiore invece che a terra
  (`PetWindow._compute_landing`/`_land`). Fa un piccolo rimbalzo
  (`config.LAND_REACT_TICKS`) all'atterraggio in entrambi i casi.

Il pet si arrampica anche autonomamente sulle finestre ogni tanto
(`config.CLIMB_*`, indipendente dal drag) — vedi `_maybe_climb`.

## Click sul pet

Un click (senza trascinare) ha due comportamenti, in ordine di priorità:
1. Se Sunshine sta parlando o pensando una risposta, **lo interrompe**
   (`VoiceChatController.interrupt()` — ferma sintesi/riproduzione vocale
   in corso, scarta la coda di frasi e lo streaming dal modello).
2. Altrimenti, attiva/disattiva il microfono (mute toggle, comportamento
   preesistente).

Non c'è interruzione "a voce" (parlare sopra mentre sta parlando): il
microfono resta sempre in pausa mentre parla per evitare che si senta da
solo tramite gli speaker e si interrompa continuamente (niente
cancellazione d'eco nello stack attuale).

## Multilingua

Sunshine capisce/parla italiano, inglese, francese, spagnolo, tedesco,
portoghese (`config.SUPPORTED_LANGUAGES`). Rilevamento automatico per
frase via `faster-whisper`; si può fissare a voce ("parla in inglese" /
"speak english" / ... — vedi `pet/skills/language_commands.py`), e la
scelta si ricorda per identità in `pet_memory.db`. Il classificatore di
umore (sotto) e le voci TTS sono separati per lingua. I comandi PC
(sezione sotto) e un paio di risposte dirette ("chi sono io?") restano
italiano-only per ora: nelle altre lingue quelle frasi passano al modello
di chat, che risponde comunque nella lingua attiva.

## Umore (rete neurale nostra)

Non un modello pre-allenato: rete scritta e allenata da zero con PyTorch
(`pet/mood/model.py`, 10 tensori, ~20k parametri), un modello separato per
lingua su dataset scritti a mano (`pet/mood/datasets/<lingua>.py`).
L'italiano è il più ricco (~950 frasi); le altre lingue sono punti di
partenza più piccoli (~95-230 frasi), ampliabili aggiungendo righe e
rilanciando `python -m pet.mood.train` (riallena tutte le lingue, o
`--lang en` per una sola).

## Sicurezza minima

I comandi PC con effetti reali (aprire programmi/siti — `intents.py`,
pattern "apri X") si attivano solo se lo speaker attuale è un'identità
**riconosciuta con nome reale** (non il profilo default "Io", non un
placeholder "Persona1"/"Gatto1" non ancora nominato) — vedi
`VoiceChatController._is_known_identity()` e
`intents.try_handle(..., allow_open_apps=...)`. Le altre info (ora,
batteria, volume, promemoria) restano disponibili per chiunque, sono a
basso rischio.

## Riconoscimento volti: deep learning per le persone, LBPH per i gatti

Sostituito LBPH per le persone con embedding facciali deep-learning
(`pet/recognition/face_embeddings.py`, InsightFace "buffalo_sc" via
ONNX Runtime, CPU-only, ~15MB scaricato una volta da GitHub releases).
Motivo: LBPH confronta texture di pixel locali, fragile a luce/posa;
gli embedding restano vicini per la stessa persona indipendentemente da
questi fattori. **I gatti restano su Haar cascade + LBPH** — il
rilevatore/allineatore di InsightFace capisce solo geometria di volti
umani, non musi felini.

Dettagli di installazione: `insightface` dichiara una dipendenza da
`opencv-python`, che è in conflitto con `opencv-contrib-python` già
installato (stesso modulo `cv2`, nome di pacchetto diverso — installarli
insieme rischia di mischiare i file dei due pacchetti). Si installa con
`--no-deps` e si aggiungono a mano le altre dipendenze (vedi
`requirements.txt`).

Storage: un embedding centroide (512 numeri) per persona in
`pet/recognition/models/person/<nome>.npy`, calcolato dalla media degli
embedding accumulati durante l'apprendimento automatico (o dal CLI
manuale `enroll.py`, che però lavora su ritagli grayscale salvati su
disco — qualità inferiore a quella dal vivo). Soglia di corrispondenza:
similarità coseno, `config.FACE_EMBEDDING_SIMILARITY_THRESHOLD`.

Migrazione: le identità "Daniele"/"Persona1-3" già imparate col vecchio
LBPH sono state convertite al nuovo formato rilanciando `train_person()`
sui campioni grayscale già salvati su disco (qualità un po' inferiore
rispetto a embedding calcolati da frame a colori dal vivo, ma
funzionante — verificato che si distinguono correttamente tra loro). Il
vecchio `pet/recognition/models/humans.yml`/`humans_labels.json` è stato
rimosso, non più usato.

## Rilevamento cambiamenti d'aspetto (sperimentale)

Confronta il volto attuale con la prima foto salvata per quell'identità,
regione per regione (fronte/capelli vs. mento/barba), via differenza
media dei pixel — euristico, non semantico, soggetto a falsi positivi per
luce/angolazione (`config.APPEARANCE_*`, `pet/recognition/recognizer.py`).

## CI e test

`.github/workflows/tests.yml` esegue `python -m unittest discover -s
tests` su `windows-latest` a ogni push/PR (necessario: il codice usa
`ctypes.windll`/`winsound`, niente Linux/Mac). Installa l'intero
`requirements.txt` perché `tests/test_pet_window.py` importa
`pet.overlay.pet_window`, che porta dentro tutto lo stack (PySide6,
gpt4all, ecc.) anche se i test stessi non istanziano mai un'app Qt vera
(usano `PetWindow.__new__` per evitare `__init__`).
