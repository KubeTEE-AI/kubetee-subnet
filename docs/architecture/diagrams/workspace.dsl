workspace "KubeTEE Subnet" "Repository-scoped C4 model for repos/subnet/kubetee-subnet (Bittensor-style validator/miner subnet for confidential inference)." {
    model {
        operator = person "Operator" "Runs the local compose stack, labels miner clusters, and remediates degraded mode."

        bittensorChain = softwareSystem "Bittensor Chain (Subtensor)" "Localnet in the dev stack; testnet/finney otherwise. Holds the metagraph, hyperparameters, and set_weights."

        rancher = softwareSystem "Rancher" "Cluster-management API the validator reads (read-only v3 API, plus one guarded reconciliation DELETE). Dev stack runs a self-contained containerised Rancher." {
            minerCluster = container "miner-cluster" "Disposable downstream k3s/RKE2 cluster labelled kubetee.ai/miner-hotkey with a miner hotkey; plays the role of a miner's cluster." "rancher/k3s"
        }

        miners = softwareSystem "Subnet Miners" "Registered metagraph hotkeys (dev: bob) whose node liveness is scored via their labelled Rancher clusters."

        dozzle = softwareSystem "Dozzle" "Live container log viewer at http://localhost:8080." {
            tags "Observability"
        }

        kubeteeSubnet = softwareSystem "KubeTEE Subnet" "Basic validator (g004): metagraph-driven miner discovery, Rancher-based liveness scoring, and alice-signed set_weights." {
            validatorContainer = container "validator container" "Single container (Dockerfile.validator) that runs btcli setup, background loops, and the basic validator." "Python 3.13, uv, Docker" {
                entrypoint = component "validator_entrypoint.py" "Runs btcli registration + hyperparam setup, then execs the basic validator." "scripts/validator_entrypoint.py"
                setup = component "setup_single_node.py" "Creates subnet if needed, registers/stakes the owner/alice/bob triad from pinned dev seeds, starts emissions, attempts conviction/recycle hypers guarded by a live ownership check." "scripts/setup_single_node.py"
                convictionLoop = component "conviction-setter loop" "Background btcli sudo loop keeping owner_cut_auto_lock_enabled and recycle_or_burn=Recycle; backs off hard when ownership is verified absent." "docker-compose.yml validator command"
                statsPrinter = component "print_subnet_stats.py" "Background loop printing hypers, stake, ownership, and metagraph stats over one reused chain connection." "scripts/print_subnet_stats.py"
            }

            basicValidator = container "basic_validator.py" "One validator loop, one chain connection, one Rancher session: metagraph -> Rancher enumeration -> reconciliation -> scoring -> weights -> log + metrics." "Python process (foreground)" {
                configLoader = component "load_config / ValidatorConfig" "Fail-fast validation of all static config (share, poll interval, skip cap, reconcile params, hotkeys, RANCHER_URL/RANCHER_BEARER_TOKEN); refuses to start on any violation without echoing secrets." "scripts/basic_validator.py"
                validatorLoop = component "BasicValidator cycle loop" "Per-cycle: read metagraph, enumerate Rancher, run reconciliation, score miners, set alice-signed weights, log + export metrics. Never exits on runtime error; skips set_weights on Rancher outage; degraded mode after KUBETEE_MAX_CONSECUTIVE_SKIPS." "scripts/basic_validator.py"
                scoring = component "miner_scoring.py" "Binary fail-closed liveness score: 1 iff exactly one labelled active cluster with an active node; weight split KUBETEE_MINER_SHARE to scoring miners, rest to owner recycle UID." "scripts/miner_scoring.py"
                chainState = component "chain_state.py" "Chain query helpers: subnet ownership, wallet stake, coldkey/hotkey SS58 resolution." "scripts/chain_state.py"
                reconciliation = component "ReconciliationEngine" "Single guarded Rancher mutation: deletes labelled clusters whose hotkey left the metagraph, after persistence bounds and a same-cycle pre-delete recheck; 404/409 idempotent; unauthorized fails closed." "scripts/reconciliation.py"
                rancherClient = component "RancherClient" "Structurally GET-only client apart from the guarded DELETE; one pinned https origin, no redirects, complete pagination, never logs the token." "scripts/rancher_client.py"
                metrics = component "ValidatorMetrics" "Prometheus text metrics on KUBETEE_METRICS_PORT 9100 (compose-internal only): rancher errors, set_weights results, skips, degraded flag, reconciliation counters." "scripts/validator_metrics.py"
            }

            rancherInit = container "rancher-init" "One-shot provisioner: logs in to Rancher, mints the validator API token, imports and labels the miner-cluster, publishes token + CA to a shared volume." "scripts/rancher_provision.sh (alpine)"

            minerStub = container "miner-1 (stub)" "Optional with-miners profile stub reusing the validator image; placeholder for mock miners." "Docker (profile: with-miners)"
        }

        operator -> kubeteeSubnet "docker compose up -d --build; views logs via Dozzle"
        operator -> rancher "Manually sets kubetee.ai/miner-hotkey cluster label (Early Access registration)"
        operator -> dozzle "Views live validator logs"

        entrypoint -> setup "Runs btcli registration and hyperparam setup"
        setup -> bittensorChain "Creates subnet, registers/stakes triad, starts emissions, sets hypers (ownership permitting)"
        convictionLoop -> bittensorChain "btcli sudo set owner_cut_auto_lock_enabled + recycle_or_burn"
        statsPrinter -> bittensorChain "Reads hypers, stake, and metagraph stats"
        entrypoint -> basicValidator "execs as foreground process"

        configLoader -> validatorLoop "Supplies validated config or refuses startup"
        validatorLoop -> chainState "Resolves ownership and hotkeys"
        validatorLoop -> bittensorChain "Reads metagraph; sets alice-signed weights"
        validatorLoop -> scoring "Scores discovered miners"
        validatorLoop -> reconciliation "Runs guarded deregistration reconciliation"
        validatorLoop -> metrics "Exports cycle metrics"
        scoring -> rancherClient "Enumerates labelled clusters and nodes"
        reconciliation -> rancherClient "Re-validates and deletes stale labelled clusters"
        rancherClient -> rancher "Read-only v3 API over pinned https origin + guarded DELETE"
        chainState -> bittensorChain "Substrate queries"

        rancherInit -> rancher "Mints token; imports miner-cluster"
        rancherInit -> minerCluster "Labels with miner hotkey"
        basicValidator -> bittensorChain "Reads metagraph; submits set_weights"
        bittensorChain -> miners "Metagraph registration and emissions"
        miners -> minerCluster "Operate labelled clusters (dev: bob)"

        minerStub -> bittensorChain "Connects (stub)"
    }

    views {
        systemContext kubeteeSubnet "kubetee-subnet-context" {
            include *
            autoLayout lr
        }

        container kubeteeSubnet "kubetee-subnet-containers" {
            include *
            autoLayout lr
        }

        component basicValidator "kubetee-subnet-basic-validator-components" {
            include *
            autoLayout lr
        }

        component validatorContainer "kubetee-subnet-validator-container-components" {
            include *
            autoLayout lr
        }

        styles {
            element "Person" {
                shape person
                background "#08427b"
                color "#ffffff"
            }
            element "Software System" {
                background "#1168bd"
                color "#ffffff"
            }
            element "Container" {
                background "#438dd5"
                color "#ffffff"
            }
            element "Component" {
                background "#85bbf0"
                color "#111827"
            }
            element "Observability" {
                background "#6b7280"
                color "#ffffff"
            }
            relationship "Relationship" {
                color "#666666"
            }
        }
    }
}
