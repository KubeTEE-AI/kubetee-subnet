# validator container
Single container (Dockerfile.validator) that runs btcli setup, background loops, and the basic validator.
**Technology:** Python 3.13, uv, Docker
## Purpose
(fill)
## Components
- validator_entrypoint.py (Runs btcli registration + hyperparam setup, then execs the basic validator.)
- setup_single_node.py (Creates subnet if needed, registers/stakes the owner/alice/bob triad from pinned dev seeds, starts emissions, attempts conviction/recycle hypers guarded by a live ownership check.)
- conviction-setter loop (Background btcli sudo loop keeping owner_cut_auto_lock_enabled and recycle_or_burn=Recycle; backs off hard when ownership is verified absent.)
- print_subnet_stats.py (Background loop printing hypers, stake, ownership, and metagraph stats over one reused chain connection.)

## Data Flow
(fill)

## Invariants
(fill)
