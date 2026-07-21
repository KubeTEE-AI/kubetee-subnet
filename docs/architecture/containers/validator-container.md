# validator container

Single container (Dockerfile) that runs btcli setup, background loops, and the basic validator.

**Technology:** Python 3.13, uv, Docker

## Purpose

Single container (Dockerfile) that runs btcli setup, background loops, and the basic validator.

## Components

- validator_entrypoint.py (`scripts/validator_entrypoint.py`)
- setup_single_node.py (`scripts/setup_single_node.py`)
- conviction-setter loop (`docker-compose.yml validator command`)
- print_subnet_stats.py (`scripts/print_subnet_stats.py`)

## Data Flow

_No relationships modeled for this container yet — add `->` edges in workspace.dsl to populate this section._ <!-- gsd:fill -->

## Invariants

_No invariants documented yet. Replace this note with the properties that must always hold for this container (ordering, idempotency, security boundaries)._ <!-- gsd:fill -->
