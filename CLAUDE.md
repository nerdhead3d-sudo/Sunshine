# Note per Claude Code

Questo progetto viene sviluppato in parallelo da sessioni Claude Code su PC
diversi. Questo file riassume lo stato e le decisioni recenti che non sono
ovvie dal solo codice, per chi riprende il lavoro su un'altra macchina.

## Pipeline sprite (in corso, qualità ancora da migliorare)

Due generatori in `pet/assets/`, entrambi richiamati da `main.py:ensure_sprites()`
quando `pet/assets/sprites/` non esiste o è vuota (la cartella è in
`.gitignore`, non è mai committata — viene sempre rigenerata):

1. **`generate_placeholders.py`** (sempre eseguito prima): genera
   proceduralmente (forme PIL, nessun modello AI) tutti gli stati —
   `idle`, `walk_left`/`walk_right`, `sit`, `react`, `sleep`, `dragged`.
   Stile cartoon semplice, palette nero/rosa/oro pensata per somigliare al
   gatto vero dell'utente, ma giudicata "brutta" anche dopo aver aggiunto
   zampe visibili — è solo un fallback che garantisce che l'app parta
   sempre, anche senza foto di riferimento.

2. **`generate_from_reference.py`** (eseguito dopo, sovrascrive se
   `pet/assets/reference/neutro.png` e `occhi_chiusi.png` esistono — questi
   **sono** committati, sono due foto/illustrazioni reali del gatto
   dell'utente fornite a mano, non generate da questo repo): deriva
   `idle`, `sit`, `walk_left`/`walk_right`, `react` dalle due foto con
   trasformazioni geometriche (zoom/squash/rotazione), non con nuove
   generazioni AI — niente deriva di ombre/stile tra i frame perché sono
   sempre gli stessi pixel sorgente. Qualità molto più alta del
   procedurale, approvato dall'utente come direzione giusta.

   **`sleep` e `dragged` restano col placeholder procedurale**: le pose
   (sdraiato, a penzoloni) sono troppo diverse dalla foto seduta per essere
   derivate con trasformazioni semplici. Deciso con l'utente di rimandare
   ("poi ci pensiamo") — prossimo passo naturale: nuove foto di riferimento
   dedicate per quelle due pose, stesso trattamento.

Se l'utente fornisce nuove foto di riferimento, rimpiazza i file in
`pet/assets/reference/` e rilancia `python -m pet.assets.generate_from_reference`
(o cancella `pet/assets/sprites/` e fai ripartire l'app).

## Comportamenti pet (aggiunti di recente)

`pet/behavior/state_machine.py` ora ha, oltre a `IDLE`/`WALK_LEFT`/
`WALK_RIGHT`/`REACT`:
- `SIT`: durante l'idle, con probabilità `config.SIT_CHANCE` si siede invece
  di camminare.
- `SLEEP`: da seduto, con probabilità `config.SLEEP_CHANCE` si addormenta.
- `DRAGGED`: priorità assoluta, forzato da `pet/overlay/pet_window.py`
  quando l'utente tiene premuto e sposta il mouse oltre
  `config.DRAG_MOVE_THRESHOLD_PX` (sotto soglia resta un click normale =
  toggle mute, comportamento preesistente invariato). Al rilascio, se il
  pet è a mezz'aria, cade con una breve accelerazione di gravità
  (`config.FALL_ACCEL`/`FALL_MAX_SPEED`) invece di teletrasportarsi, e fa
  un piccolo rimbalzo (`config.LAND_REACT_TICKS`) all'atterraggio.

## Altro

- Test in `tests/test_state_machine.py` aggiornati per i nuovi stati.
- `python -m unittest discover -s tests` deve sempre passare prima di
  pushare.
