# v2b_c — experiments

Optional research variants around **`v2b_child`** rules (`orb_open_limit_v2b_child.py`). Parent **`v2b_c/`** remains the primary chart builder for the canonical CSVs in `../v2b_child/`.

Each subfolder documents one hypothesis, example CLI, and (when checked in) a pinned CSV output from that run.

## Contents

| Folder | Topic |
|--------|--------|
| [`child_stop_midrange/`](child_stop_midrange/) | Child partial stop at **OR midpoint** `(RH+RL)/2` vs default **edge** (RH / RL) |
| [`child_stop_15m_close/`](child_stop_15m_close/) | Child partial stop only after a completed **15 m close** back inside the near OR boundary |
