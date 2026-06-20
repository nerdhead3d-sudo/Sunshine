# Desktop Pet "Sunshine"

Pet animato sempre in primo piano sul monitor secondario. Parla solo a
voce (ascolto continuo, niente finestre di chat), riconosce automaticamente
le persone e i gatti di casa via webcam senza bisogno di un enrollment
manuale, e mantiene una memoria separata per ciascuna identità.

## Setup

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Il "cervello" conversazionale è **completamente locale e offline**
(`gpt4all`, nessun server esterno, nessuna GPU/compilatore richiesti): al
primo messaggio viene scaricato una volta da Hugging Face un modello GGUF
leggero (~770MB, `config.LOCAL_LLM_REPO_ID`/`LOCAL_LLM_FILENAME`) e tenuto
in cache in `pet/local_models/`. Gira bene anche su PC senza GPU dedicata
con 8GB di RAM (es. Surface Pro 7).

**Consumo di RAM misurato** (macchina di sviluppo, non il PC target):
con i 6 classificatori di umore + l'LLM locale + Whisper tutti caricati
insieme (il picco tipico durante una conversazione), il processo usa
circa **690MB di working set** — meno di quanto ci si aspetterebbe dalla
sola somma dei file (`gpt4all`/llama.cpp carica il modello via
memory-mapping, non lo duplica tutto in RAM privata). Su un PC con 8GB
totali questo lascia margine per il resto, ma se senti il sistema
appesantito puoi alleggerire scegliendo un modello Whisper più piccolo
(`config.STT_WHISPER_MODEL = "base"` o `"tiny"` invece di `"small"`).

Se preferisci usare Ollama invece (es. per un modello più grande con GPU
dedicata), imposta `USE_LOCAL_LLM = False` in `config.py` e assicurati che
Ollama sia in esecuzione con il modello scaricato:

```powershell
ollama pull llama3.2:1b
```

## Avvio

Doppio click su **`Avvia Sunshine.vbs`**: lancia l'app con `pythonw.exe`
(stesso venv, ma senza finestra di console — chiudendo una console
accidentalmente non si chiude più il pet). In alternativa, da terminale:

```powershell
python main.py
```

(questa seconda forma apre anche una finestra di console, perché usa
`python.exe` invece di `pythonw.exe`; chiuderla termina il pet).

Al primo avvio vengono generati sprite placeholder in
`pet/assets/sprites/`. Per usare grafica personalizzata, sostituisci i PNG
in quelle cartelle mantenendo la stessa convenzione di nome
(`<stato>_<indice>.png`, 64x64px).

Il pet appare sul monitor secondario (indice configurabile in `config.py`,
`SECONDARY_SCREEN_INDEX`), camminando nell'area di lavoro sopra la barra
delle applicazioni (non sotto/dietro). Alterna autonomamente tra stato
idle e camminata e, ogni tanto, si arrampica sul bordo superiore di una
finestra visibile sullo schermo e ci cammina sopra per un po' prima di
tornare a terra (parametri `CLIMB_*`/`WINDOW_SCAN_INTERVAL_MS` in
`config.py`).

Per chiudere l'app: premi **Esc** col pet in primo piano, oppure usa
**"Esci"** dal menu della sua icona nella system tray (vicino
all'orologio — se non la vedi, controlla la freccetta `^` delle icone
nascoste).

## Chat vocale continua

Niente fumetti né campi di testo: Sunshine ascolta sempre dal microfono
predefinito (rilevamento automatico dell'inizio/fine del parlato, nessun
tasto da premere), trascrive **completamente offline** con `faster-whisper`
(modello Whisper scaricato una volta da Hugging Face, `STT_WHISPER_MODEL`
in `config.py`), genera la risposta con il modello locale `gpt4all`
(`USE_LOCAL_LLM`/`LOCAL_LLM_*` in `config.py`) e la legge ad alta voce. Le
risposte vengono lette frase per frase non appena il modello le genera,
invece di aspettare il testo completo, per ridurre l'attesa percepita.

La voce ha tre livelli, dal migliore al più semplice:
1. **edge-tts** (voce neurale online, richiede internet) — usata di default
2. **Piper** (voce neurale offline, buona qualità, modello ~60MB scaricato
   una volta da Hugging Face) — entra in gioco automaticamente se manca
   internet
3. **pyttsx3/SAPI5** (offline, più robotica) — ultima spiaggia, solo se
   anche Piper non riesce a partire

Con questa catena **l'intera app funziona offline** (chat, riconoscimento
vocale e voce), con qualità migliore quando c'è internet e un degrado
controllato (mai muto) quando non c'è.

## Lingue

Sunshine capisce e parla **italiano, inglese, francese, spagnolo, tedesco
e portoghese** (`config.SUPPORTED_LANGUAGES`). Di default rileva la
lingua automaticamente a ogni frase (`faster-whisper`); puoi anche
fissarla a voce dicendo ad esempio "parla in inglese" / "speak english" /
"parle en français" / "habla español" / "sprich deutsch" / "fala
português" (riconosciuto indipendentemente dalla lingua in cui lo dici).
Per tornare al rilevamento automatico: "torna automatico". La scelta
viene **ricordata per ogni identità** (salvata in `pet_memory.db`) e
recuperata ai riavvii.

Ogni lingua ha la sua voce (edge-tts/Piper, `config.TTS_VOICES`/
`PIPER_VOICE_BASENAMES`) e il suo classificatore di umore (vedi sotto).
I comandi PC (sezione successiva) e un paio di risposte dirette ("chi
sono io?") restano per ora solo in italiano: nelle altre lingue quelle
frasi specifiche passano semplicemente al modello di chat, che risponde
comunque nella lingua attiva.

## Umore (rete neurale nostra, allenata da zero)

A differenza di tutto il resto (LLM, voce, STT: modelli pre-allenati da
altri, solo scaricati e usati), il classificatore di umore è una piccola
rete neurale **scritta e allenata da zero da noi** con PyTorch — un
modello separato per ciascuna lingua, ognuno sul proprio dataset scritto
a mano (`pet/mood/datasets/<lingua>.py`, 7 categorie ciascuno). Nessun
peso pre-addestrato, nessun embedding esterno: solo tokenizzazione nostra
(`pet/mood/vocab.py`) e una rete embedding + 3 strati nascosti +
temperatura imparata (`pet/mood/model.py`, 10 tensori, ~20.000
parametri), inizializzata a caso e allenata sul dataset.

L'italiano è il più ricco (~950 frasi); le altre lingue sono punti di
partenza più piccoli (~95-230 frasi ciascuna) — facili da ampliare
aggiungendo righe al relativo file e riallenando:

```powershell
python -m pet.mood.train             # riallena tutte le lingue
python -m pet.mood.train --lang en   # solo una
```

Ogni frase che dici viene classificata e aggiorna un punteggio di umore
per la tua identità (colonna `mood` in `pet/data/pet_memory.db`, con una
media mobile esponenziale — `MOOD_EMA_ALPHA` in `config.py`); quando
l'umore è abbastanza positivo, Sunshine fa una piccola animazione di
gioia. Il tono rilevato viene anche passato al modello di chat come
contesto, così la risposta può tenerne conto.

## Rilevamento cambiamenti d'aspetto (sperimentale)

Quando riconosce una persona già nota, Sunshine confronta periodicamente
il volto attuale con la prima foto mai salvata per quell'identità,
regione per regione (fronte/capelli vs. mento/barba), tramite una
semplice differenza media dei pixel — niente di semantico, solo "qui è
cambiato parecchio". Se il cambiamento supera una soglia (config.py,
`APPEARANCE_*`), te lo chiede a voce ("ti sei tagliato i capelli?",
"ti sei fatto la barba?"), una volta per regione a sessione. È
volutamente euristico: cambi di luce o angolazione possono generare
falsi positivi.

## Comandi PC (stile "Alexa")

Prima di passare la frase al modello, Sunshine controlla se corrisponde a
un comando conosciuto (`pet/skills/intents.py`) e in tal caso lo esegue
subito, senza passare da Ollama:

- **Info**: "che ore sono", "che giorno è", "batteria", "quanto spazio
  libero [su disco]"
- **Volume/musica**: "alza/abbassa il volume", "muta", "metti in pausa",
  "prossima/canzone precedente"
- **App e siti**: "apri il blocco note / calcolatrice / paint / esplora
  file", "apri youtube / google / gmail / il browser"
- **Promemoria e timer**: "ricordami di...", "metti un timer di N
  minuti/secondi" — Sunshine risponde a voce allo scadere

Le frasi non riconosciute proseguono normalmente verso la chat con
Ollama. App/siti e mappature sono in `pet/skills/commands.py`, facilmente
estendibili.

Clicca sul pet per silenziare/riattivare il microfono in qualsiasi
momento.

## Memoria per identità

Ogni identità (persona riconosciuta, o il profilo predefinito `Io` quando
nessuno è ancora stato riconosciuto) ha la propria cronologia di
conversazione e i propri "fatti" salvati in `pet/data/pet_memory.db`
(SQLite), ricaricati e inseriti nel system prompt a ogni riavvio.

## Riconoscimento via webcam (ad apprendimento automatico)

Sunshine riconosce le persone (volto) e i gatti (muso) inquadrati dalla
webcam con Haar cascade + LBPH (OpenCV) — **non serve nessun enrollment
manuale**: quando vede una faccia/muso che non riconosce per qualche
secondo di seguito, la impara da sola, le assegna un nome temporaneo
(`Persona1`, `Gatto1`, ...) e addestra il modello al volo
(`pet/recognition/models/`).

- Per una **persona** appena imparata, Sunshine chiede a voce "come ti
  chiami?" e rinomina l'identità (sia nel riconoscimento webcam che nella
  memoria di conversazione) con il nome che risponde.
- Per un **gatto**, annuncia semplicemente di averlo imparato con il nome
  temporaneo (i gatti non possono rispondere al posto loro).

I parametri di apprendimento (`AUTO_LEARN_SAMPLE_COUNT`,
`RECOGNITION_CONFIDENCE_THRESHOLD`, ecc.) sono in `config.py`. È comunque
disponibile un comando manuale opzionale, se preferisci pre-assegnare un
nome invece di aspettare l'apprendimento automatico:

```powershell
python -m pet.recognition.enroll --identity Marco --kind person
python -m pet.recognition.enroll --identity Birba --kind cat
```

## Log e diagnostica

Gli errori che avvengono in background (sintesi/riproduzione vocale,
riconoscimento webcam, microfono non disponibile) vengono scritti in
`pet/data/pet.log` invece di sparire silenziosamente — utile per capire
perché qualcosa non ha funzionato senza dover rilanciare l'app da un
terminale.

## Test

```powershell
python -m unittest discover -s tests
```

Coprono la logica pura: parsing dei comandi vocali (`pet/skills/intents.py`),
rilevamento dei comandi di cambio lingua (`pet/skills/language_commands.py`),
il classificatore di umore (`pet/mood/classifier.py`) e la macchina a stati
del comportamento (`pet/behavior/state_machine.py`). Il resto (overlay Qt,
webcam, audio) richiede un avvio reale dell'app per essere verificato.
