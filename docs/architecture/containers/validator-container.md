# validator container

Single validator image whose startup command and healthcheck are owned by the
root Docker Compose deployment.

**Technology:** Python 3.13, uv, Docker

## Purpose

The local Compose command runs btcli setup and background loops before
starting the validator; the external Compose command starts the validator
directly.

## Components

- validator.py (`scripts/validator.py`)
- setup_single_node.py (`scripts/setup_single_node.py`)
- conviction-setter loop (`docker-compose.yml validator command`)
- print_subnet_stats.py (`scripts/print_subnet_stats.py`)

## Data Flow

_No relationships modeled for this container yet — add `->` edges in workspace.dsl to populate this section._ <!-- gsd:fill -->

## Invariants

_No invariants documented yet. Replace this note with the properties that must always hold for this container (ordering, idempotency, security boundaries)._ <!-- gsd:fill -->
