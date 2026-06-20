# Note per Claude Code

Questo progetto viene sviluppato in parallelo da sessioni Claude Code su PC
diversi. Questo file riassume lo stato e le decisioni recenti che non sono
ovvie dal solo codice, per chi riprende il lavoro su un'altra macchina.

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
