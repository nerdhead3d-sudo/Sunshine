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

## Funzionalità ispirate a "Lumo" (compagno AI fisico su Raspberry Pi)

Lumo (lumodevice.com, non quello di Proton — vedi sotto) è un progetto
maker non affiliato: compagno AI locale su Raspberry Pi con schermo/LED,
wake word, riconoscimento facciale anti-foto, enrollment guidato. Quattro
sue idee sono state portate in Sunshine:

- **Wake word** (`config.WAKE_WORD_ENABLED`, default `False`): se attivata,
  `VoiceChatController` ignora ogni frase che non contenga `config.WAKE_WORD`
  (default = `PET_NAME`, "Sunshine") e la rimuove dal resto prima di
  trattarlo come comando. Disattivata di default perché cambia
  l'esperienza in modo non banale (bisogna sempre nominare il pet) — vedi
  `_on_utterance` in `pet/overlay/voice_chat.py`.
- **Carezza** (`config.PET_STROKE_*`): un tocco prolungato col mouse che
  rimane sotto la soglia di drag ma percorre un certo cammino cumulativo
  (rigirando avanti e indietro) viene riconosciuto come carezza invece di
  un tentativo di trascinamento o un click — vedi `mouseMoveEvent` in
  `pet/overlay/pet_window.py`. Dà una piccola spinta positiva al mood
  (`VoiceChatController.register_pat`).
- **Anti-foto/liveness** (`config.LIVENESS_*`): euristico, non biometria
  reale (nessun sensore di profondità) — un volto vero ha sempre un
  minimo di micro-movimento naturale; se la posizione del volto resta
  perfettamente immobile per tutta la finestra di conferma
  (`RECOGNITION_CONSECUTIVE_FRAMES`), l'identità non viene confermata
  (niente privilegio `allow_open_apps`), come se fosse ancora sconosciuta
  — vedi `_passes_liveness`/`_update_candidate` in
  `pet/recognition/recognizer.py`.
- **Enrollment guidato multi-posa**: `pet/recognition/enroll.py` per le
  persone non acquisisce più 30 frame qualunque, ma guida attraverso 5
  pose (frontale, sinistra, destra, su, giù) con conto alla rovescia —
  dà all'embedding centroide una varietà di pose migliore. Usa lo stesso
  rilevatore InsightFace della pipeline live (non più Haar cascade per le
  persone), salvando ritagli a colori invece che in scala di grigi
  (qualità migliore); `train_person()` ora legge i campioni a colori di
  default (compatibile comunque con i vecchi campioni in scala di grigi).
  I gatti restano sul vecchio percorso Haar+LBPH, senza pose guidate.

Altre quattro, aggiunte in una sessione successiva:

- **Sveglia** ("svegliami alle 7:30", "metti la sveglia tutti i giorni
  alle 7"): nuova tabella `alarms` in `pet_memory.db` (ora, minuto,
  ricorrente, `last_fired_date` per non doppio-suonare dopo un riavvio lo
  stesso giorno). Riprogrammata a ogni avvio (`_reschedule_active_alarms`
  in `pet/overlay/voice_chat.py`); al suono, 3 beep (`winsound.Beep` su
  thread separato per non bloccare la UI Qt) + frase parlata; se
  ricorrente si riprogramma da sola per il giorno dopo, altrimenti si
  disabilita.
- **YouTube embedded**: `pet/overlay/youtube_player.py`,
  `QWebEngineView` (già incluso in PySide6, nessuna dipendenza nuova —
  verificato). Finestra normale (non trasparente, ha barra del titolo:
  mostra contenuto video reale, deve essere chiudibile). "Cerca su
  youtube X" apre i risultati di ricerca; play/pausa video iniettano un
  piccolo snippet JS (`document.querySelector('video').play()/pause()`)
  invece di integrare la IFrame API completa — sufficiente per comandi
  vocali semplici, molto meno codice. La ricerca (apre contenuto nuovo)
  è soggetta allo stesso gate `allow_open_apps` di "apri X"; play/pausa/
  chiudi su un video già aperto no.
- **Routine mattina/sera**: `VoiceChatController.greet()` (chiamato da
  `_on_identity_recognized` in `pet/overlay/pet_window.py` invece del
  vecchio `announce(f"Ciao {name}!")` diretto) capisce se è la prima
  volta che riconosce quella persona in quel periodo del giorno (mattina
  5-12, sera 18-24; il resto della giornata resta un saluto semplice) via
  nuova colonna `identities.last_routine` (marker `"YYYY-MM-DD:periodo"`)
  e in tal caso dice ora/data/promemoria in sospeso invece del semplice
  saluto.
- Meteo e radio internet **non implementati** (proposti ma non scelti
  dall'utente in questa sessione — entrambi richiederebbero servizi
  online, in tensione con l'offline-first del progetto).

Nota terminologica (chiarita durante la sessione): "Lumo" di Proton è un
chatbot **cloud**, non gira offline nonostante il marketing suggerisca il
contrario ("niente ricerca web" ≠ "gira senza internet") — non è la fonte
di queste funzionalità, è un prodotto diverso con lo stesso nome.

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

## Backend di chat selezionabile dall'utente (locale/Ollama/online)

In vista del programma di installazione, è stato aggiunto un meccanismo
per cambiare backend di chat **a runtime, dal tray menu**, senza toccare
`config.py` né riavviare l'app:

- `pet/settings_store.py`: piccolo store JSON (`pet/data/settings.json`,
  in `.gitignore` come gli altri file dati) per `chat_backend` (`"local"`
  gpt4all / `"ollama"` / `"openai"`) e `openai_api_key`/`openai_model`.
  Separato da `config.py` apposta: `config.py` resta "default di chi
  sviluppa", questo è "scelta dell'utente finale", persistita per
  identità della macchina, non del codice.
- `pet/openai_client.py`: nuovo backend online (chiave API propria
  dell'utente, mai distribuita con l'app), stessa interfaccia
  `build_messages`/`stream_reply` di `OllamaClient` — drop-in replacement.
- `pet/overlay/voice_chat.py::make_chat_client()`: factory che legge
  `settings_store` e istanzia il client giusto (con fallback al backend
  locale se è selezionato "openai" ma non è stata ancora inserita una
  chiave, invece di andare in errore); `VoiceChatController.
  reload_chat_backend()` lo richiama per cambiare client senza perdere
  cronologia/identità attive.
- `pet/overlay/pet_window.py::SettingsDialog`: nuova voce "Impostazioni..."
  nel tray menu (prima di "Esci"), combobox backend + campo chiave API
  OpenAI (mascherato).

## Programma di installazione Windows (PyInstaller + Inno Setup)

Cartella `installer/`, separata dal codice dell'app:
- `sunshine.spec`: build PyInstaller in modalità `--onedir` (non
  `--onefile` — l'app scarica/usa già modelli pesanti da una cartella
  reale su disco, un unico exe che si autoestrae in temp a ogni avvio non
  avrebbe senso). Include i pesi del mood classifier (`pet/mood/model/`,
  mai generati a runtime); sprite e modelli di riconoscimento/voce restano
  esclusi perché generati/scaricati al primo avvio come già accade oggi.
- `setup.iss`: script Inno Setup. Installa in `{autopf}` ma con
  `PrivilegesRequired=lowest` (default per-utente, niente prompt UAC, come
  VS Code) — cambiabile a `admin` se in futuro serve un'installazione
  macchina-wide. Pagine/funzionalità:
  - Wizard multilingua nativo (italiano/inglese) — sceglie sia la lingua
    dell'installer **sia** la lingua di default in cui Sunshine
    parla/ascolta (scritta in `install_settings.json`, vedi sotto).
  - Pagina custom per scegliere il monitor (`GetSystemMetrics(SM_CMONITORS)`
    per il conteggio reale, elenco "Monitor 1/2/3..." anziché provare a
    enumerarne la geometria via Pascal Script — più semplice, comunque
    coincide con l'indice che `config.SECONDARY_SCREEN_INDEX` si aspetta).
  - Check Ollama: lancia `Sunshine.exe --check-ollama` (vedi `main.py`)
    subito dopo aver copiato i file; se assente, avvisa e offre di aprire
    ollama.com — non lo installa in autonomia (non si esegue mai un
    installer esterno silenziosamente).
  - Task opzionale "scarica modelli ora" (default selezionato): lancia
    `Sunshine.exe --download-models --lang=<lingua scelta>`
    (`installer/download_models.py`) invece di far scoprire all'utente i
    download silenziosi al primo avvio reale.
  - Checkbox avvio automatico al login (collegamento in `{userstartup}`,
    sostituisce `Avvia Sunshine.vbs` per chi installa così — il `.vbs`
    resta per chi lancia da sorgente).
  - Disinstallazione: chiede se cancellare anche `%LOCALAPPDATA%\Sunshine`
    (conversazioni, volti imparati, modelli scaricati) — non lo fa mai
    senza chiedere, e di default i dati restano.
  - **Niente firma del codice** (vedi conversazione: EV/OV richiedono una
    persona giuridica registrata e un costo annuo, non ancora
    giustificato) — SmartScreen avviserà al primo avvio, comportamento
    atteso finché non si firma.
- `download_models.py`: stessa logica di download usata pigramente dai
  vari moduli (`pet/voice/stt.py`, `tts.py`, `local_llm_client.py`), solo
  richiamata tutta insieme all'avvio invece che al bisogno.
- `build.ps1`: automatizza i due passi (PyInstaller poi `ISCC.exe`).
  Richiede Inno Setup 6 installato a parte (non scaricato/installato da
  questo script).

**Path scrivibili quando installato**: `config.py` ora distingue dev/CI
(`sys.frozen` assente → path relativi a `BASE_DIR` come sempre, per non
rompere `.gitignore`/test esistenti) da installazione reale (`sys.frozen`
presente, tipico di un eseguibile PyInstaller → sprite, DB, modelli e
volti imparati vanno tutti sotto `%LOCALAPPDATA%\Sunshine`, scrivibile
senza admin anche se l'app è in `Program Files`). Le scelte di lingua/
monitor fatte nel wizard vengono scritte da `setup.iss` in
`%LOCALAPPDATA%\Sunshine\data\install_settings.json` e applicate da
`config.py::_apply_install_settings()` come override sopra i default
hardcoded — assente per chi non installa così, quindi nessun impatto su
dev/CI.

**Verificato con una build reale** (PyInstaller installato ad-hoc nel venv
di sviluppo, non è una dipendenza dell'app): il primo tentativo di
`sunshine.spec` mancava di due gruppi di file dati non-Python che
l'analisi statica di PyInstaller non scopre da sola (segue solo gli
import, non le letture a percorso runtime) — **bug reale trovato e
corretto**, non solo teorico:
- `pet/memory/schema.sql` (letto da `pet/memory/store.py`,
  `FileNotFoundError` al primo avvio dell'eseguibile congelato).
- `cv2/data/*.xml` (i cascade Haar per il riconoscimento gatti — l'hook
  PyInstaller per `cv2` porta `cv2/data/__init__.py` ma non i file `.xml`
  accanto).
Dopo il fix, `dist\Sunshine\Sunshine.exe` lanciato da una cartella pulita
(senza venv attivo) genera correttamente gli sprite, scarica i modelli
(Whisper, InsightFace) sotto `%LOCALAPPDATA%\Sunshine\`, scrive
`pet_memory.db` e gira stabile per oltre un minuto senza errori in
`pet.log`. **Non verificato**: la compilazione `setup.iss` con Inno Setup
(non installato su questa macchina) e l'installazione/disinstallazione
vere e proprie — solo l'exe PyInstaller è stato testato direttamente.

## Porting Raspberry Pi (progetto separato `c:\Users\Wolfg\progetti\sunshinepi\`)

Su richiesta dell'utente è stato avviato un porting headless di questo
progetto per Raspberry Pi, in una cartella **separata**
(`c:\Users\Wolfg\progetti\sunshinepi\`, repo/venv proprio, non un
sottoprogetto di questo) — non toccare quella cartella aspettandosi che
sia sincronizzata con questa: è stata scritta una volta, copiando e
adattando il codice da qui, e non viene mantenuta in parallelo
automaticamente. Se questo progetto cambia (es. nuove skill, nuovo schema
DB), il porting sul Pi va aggiornato a mano se serve.

Scritto/portato da una sessione Claude Code su **PC Windows senza hardware
Pi reale disponibile** — verificato solo a livello di sintassi/import e
con qualche test di logica pura (intents, store, mood classifier,
language_commands) lanciati nel venv del progetto Pi su Windows. **Non
testato su un Raspberry Pi vero**: vedi `sunshinepi/README_PI.md`, sezione
"Cosa va verificato sul Pi vero", prima di considerarlo pronto per la
produzione.

Decisioni principali del porting (dettagli completi in
`sunshinepi/README_PI.md`):
- **Niente GUI**: rimossa interamente la dipendenza da PySide6/Qt, non
  solo l'overlay grafico — anche `Signal`/`QObject`/`QThread`/`QTimer`
  sono stati sostituiti con un sostituto minimale sincrono
  (`pet/util/events.py`: `Signal` a callback-list + `call_later()` via
  `threading.Timer`), per evitare di portarsi dietro Qt su un Pi headless
  che non lo userebbe mai.
- **LLM**: solo Ollama (non gpt4all/llama.cpp come l'opzione di default
  qui) — Ollama ha build ARM64 ufficiali mantenute, modello consigliato
  `llama3.2:1b` (un Pi senza GPU non sopporta nulla di più grande con
  latenza accettabile).
- **Riconoscimento volti via webcam: non portato** (`config.
  FACE_RECOGNITION_ENABLED = False`, nessun codice di recognition copiato)
  — gli wheel ARM di InsightFace/onnxruntime non sono garantiti su ogni
  distro Pi, e un Pi può stare benissimo senza telecamera puntata su una
  scrivania. Conseguenza: sul Pi esiste **una sola identità** ("Io"),
  niente saluti per nome né routine mattina/sera per persona specifica.
- **YouTube embedded e "apri X" (app/siti): rimossi**, non solo
  disabilitati — su un Pi headless senza display/browser non c'è nulla in
  cui mostrare un video o cosa aprire.
- **winsound/ctypes.windll → equivalenti Linux**: `ffplay` (ffmpeg) per la
  riproduzione TTS, `speaker-test` per il beep della sveglia, `amixer`/
  `playerctl` per volume/media keys.
- **Wake word attiva di default sul Pi** (`WAKE_WORD_ENABLED = True`,
  diverso dal default `False` di qui) — senza mouse/schermo non c'è altro
  modo per evitare che risponda a rumori di fondo.
- Mood classifier, memoria SQLite, STT (faster-whisper) e TTS (cascata
  edge-tts → Piper → pyttsx3) sono stati portati **quasi invariati**,
  cambiando solo la riproduzione audio e rimuovendo la base Qt.
