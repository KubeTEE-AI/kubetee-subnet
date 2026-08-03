# KubeTEE Cluster Naming Convention

> **Validator contract (2026-07-24):** the validator binds a miner to its
> cluster by the **hotkey** alone — `kubetee.ai/hotkey` (alias
> `kubetee.ai/miner-hotkey`), one cluster per hotkey — plus an operator safety
> switch `kubetee.ai/ban` (value `"true"` ⇒ score 0). The former rich
> enrollment labels (`binding-id`, `coldkey`, `provider-id`, `binding-status`,
> `generation`, `netuid`, `network`, `origin-fp-prefix`, `enrollment-uid`) are
> **no longer read by the validator** — they remain as optional legacy
> enrollment metadata (see the "Legacy Enrollment Binding" section below).
> The naming/geo labels below are operator/dashboard metadata the validator
> ignores. See `validator/rancher_client.py` for the implemented label
> contract.

## Format

```
<continent-2letter>-<country-2letter>-<city-fullname>-<miner-uid>
```

## Components

### 1. Continent Code (2 letters)

| Code | Continent |
|------|-----------|
| `eu` | Europe |
| `na` | North America |
| `sa` | South America |
| `as` | Asia |
| `af` | Africa |
| `oc` | Oceania |
| `me` | Middle East |

### 2. Country Code (2 letters)

Use ISO 3166-1 alpha-2 country codes:
- `fr` - France
- `us` - United States
- `jp` - Japan
- `de` - Germany
- `gb` - United Kingdom
- `ca` - Canada
- `au` - Australia
- `sg` - Singapore
- `in` - India
- etc.

### 3. City Name (full name, lowercase)

Use the full city name in lowercase with no spaces:
- `paris`
- `newyork`
- `tokyo`
- `berlin`
- `london`
- `toronto`
- `sydney`
- `singapore`
- `delhi`

### 4. Miner UID (numeric)

The current UID of the miner on the Bittensor subnet.

**Note**: UID can change if a miner deregisters and re-registers. Machine
identity comes from the **hotkey** (`kubetee.ai/hotkey`), which is the only
label the validator reads for binding; never infer identity from the
human-readable cluster name alone. The legacy `kubetee.ai/coldkey` and binding
ID labels (see "Legacy Enrollment Binding" below) are no longer read by the
validator but may be present on older clusters.

## Examples

| Cluster Name | Location | Description |
|--------------|----------|-------------|
| `eu-fr-paris-123` | Europe, France, Paris | Miner UID 123 in Paris |
| `na-us-newyork-456` | North America, USA, New York | Miner UID 456 in New York |
| `as-jp-tokyo-789` | Asia, Japan, Tokyo | Miner UID 789 in Tokyo |
| `eu-de-berlin-234` | Europe, Germany, Berlin | Miner UID 234 in Berlin |
| `na-ca-toronto-567` | North America, Canada, Toronto | Miner UID 567 in Toronto |
| `as-sg-singapore-890` | Asia, Singapore, Singapore | Miner UID 890 in Singapore |
| `oc-au-sydney-345` | Oceania, Australia, Sydney | Miner UID 345 in Sydney |
| `me-ae-dubai-678` | Middle East, UAE, Dubai | Miner UID 678 in Dubai |

## Legacy Enrollment Binding (optional, not read by the validator)

The cluster name may include the UID for human readability. Machine identity
comes from the **hotkey** alone (`kubetee.ai/hotkey`), which the validator
reads. The platform may also write a richer enrollment binding for operator
record-keeping and legacy tooling; the **validator does not read these labels**
— they are kept here for reference only:

```yaml
# OPTIONAL legacy enrollment metadata — NOT read by the validator.
# The validator reads only kubetee.ai/hotkey (+ alias miner-hotkey) and
# kubetee.ai/ban. These labels are platform/operator metadata.
labels:
  kubetee.ai/binding-id: <OPAQUE_BINDING_ID>
  kubetee.ai/hotkey: <MINER_HOTKEY_SS58_ADDRESS>
  kubetee.ai/coldkey: <MINER_COLDKEY_SS58_ADDRESS>
  kubetee.ai/provider-id: <PROVIDER_UUID>
  kubetee.ai/binding-status: ENROLLED
  kubetee.ai/generation: "1"
  kubetee.ai/netuid: <SUBNET_NETUID>
  kubetee.ai/network: <CHAIN_NETWORK>
  kubetee.ai/origin-fp-prefix: <63_LOWERCASE_HEX_CHARACTERS>
annotations:
  kubetee.ai/enrollment-uid: <MINER_UID_NUMBER>
```

Geographic and Fleet labels such as `environment`,
`kubetee.ai/continent`, `kubetee.ai/country`, and `kubetee.ai/city` remain
optional deployment metadata; they are not enrollment identity.

**Why `kubetee.ai/` prefix?**
- Follows Kubernetes best practices for custom labels
- Prevents conflicts with standard Kubernetes or Rancher labels
- Makes it clear these are KubeTEE-specific labels
- `environment` doesn't need prefix as it's a common standard label

**Legacy synthetic shape** (optional — the validator reads only `hotkey` + `ban`):
```yaml
# Legacy enrollment metadata — NOT read by the validator.
labels:
  environment: production
  kubetee.ai/continent: eu
  kubetee.ai/country: fr
  kubetee.ai/city: paris
  kubetee.ai/binding-id: "binding-example"
  kubetee.ai/hotkey: "5CcPtWDUmeMgxzp3pwPtRVEuU1N4CjVK5D6iAmb12JNiFBdx"
  kubetee.ai/coldkey: "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"
  kubetee.ai/provider-id: "00000000-0000-4000-8000-000000000123"
  kubetee.ai/binding-status: "ENROLLED"
  kubetee.ai/generation: "1"
  kubetee.ai/netuid: "90"
  kubetee.ai/network: "finney"
  kubetee.ai/origin-fp-prefix: "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcde"
annotations:
  kubetee.ai/enrollment-uid: "123"
```

**Optional labels** (can be added for advanced targeting):
```yaml
labels:
  # Optional infrastructure labels
  kubetee.ai/tee-enabled: <true|false>
  kubetee.ai/gpu-enabled: <true|false>
  kubetee.ai/gpu-type: <h100|h200|b200|b300>
```

## Why Use Both Name and Labels?

**Cluster Name**: 
- Human-readable identification
- Easy to understand location and current UID
- Used for display purposes

**Binding metadata**:
- `kubetee.ai/hotkey` is the **only** label the validator reads for miner
  binding — one cluster per hotkey, else ambiguous ⇒ score 0.
- `kubetee.ai/ban` is the operator safety switch — value `"true"` ⇒ score 0.
- `kubetee.ai/coldkey`, `binding-id`, `provider-id`, `generation`, `netuid`,
  `network`, `origin-fp-prefix`, and `enrollment-uid` are **legacy enrollment
  metadata** the platform may write for operator record-keeping; the
  validator does **not** read them. `binding-status=ENROLLED` means onboarding
  completed; it does not mean infrastructure validation or serving readiness
  passed.

**When chain identity changes**:

Do not patch binding labels or annotations manually. Deregistration,
re-registration, hotkey/coldkey rotation, or UID changes must go through the
platform enrollment/rotation workflow so generation and origin evidence stay
coherent. Fleet selectors that use the canonical hotkey continue to work only
after the platform commits the replacement binding.

## Creating a Cluster

```bash
#!/bin/bash

# Cluster naming components
CONTINENT="eu"           # 2-letter continent code
COUNTRY="fr"             # 2-letter country code
CITY="paris"             # Full city name (lowercase)
MINER_UID="123"          # Current miner UID

# Current chain identity (committed by platform enrollment, not this script)
MINER_HOTKEY="5CcPtWDUmeMgxzp3pwPtRVEuU1N4CjVK5D6iAmb12JNiFBdx"
MINER_COLDKEY="5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"

# Build cluster name
CLUSTER_NAME="${CONTINENT}-${COUNTRY}-${CITY}-${MINER_UID}"

echo "Creating cluster: ${CLUSTER_NAME}"
echo "Hotkey: ${MINER_HOTKEY}"
echo "Coldkey: ${MINER_COLDKEY}"
echo "UID: ${MINER_UID}"
```

## Updating Enrollment Identity

Use the platform rotation or re-enrollment workflow. Direct `kubectl label`
or `kubectl annotate` changes to the hotkey binding are unsupported: the
validator compares the hotkey to the fresh metagraph and fails closed on
stale, duplicate, or malformed values. Legacy enrollment metadata (coldkey,
binding-id, etc.) is operator record-keeping and is not validated.

## Fleet GitOps Targeting

Fleet supports two main targeting strategies:

### 1. Target All Clusters by Environment

Target all staging or production clusters using environment labels:

```yaml
apiVersion: fleet.cattle.io/v1alpha1
kind: GitRepo
metadata:
  name: shared-infrastructure
  namespace: fleet-default
spec:
  targets:
  - name: all-production-clusters
    clusterSelector:
      matchLabels:
        environment: production
```

```yaml
apiVersion: fleet.cattle.io/v1alpha1
kind: GitRepo
metadata:
  name: staging-workloads
  namespace: fleet-default
spec:
  targets:
  - name: all-staging-clusters
    clusterSelector:
      matchLabels:
        environment: staging
```

### 2. Target One Specific Cluster by Name

Target a specific cluster by its exact name:

```yaml
apiVersion: fleet.cattle.io/v1alpha1
kind: GitRepo
metadata:
  name: miner-specific-workload
  namespace: fleet-default
spec:
  targets:
  - name: specific-cluster
    clusterName: eu-fr-paris-123
```

**Alternative**: Target by the canonical hotkey binding (recommended for
programmatic miner targeting):

```yaml
apiVersion: fleet.cattle.io/v1alpha1
kind: GitRepo
metadata:
  name: miner-workloads
  namespace: fleet-default
spec:
  targets:
  - name: miner-cluster
    clusterSelector:
      matchLabels:
        kubetee.ai/hotkey: "5CcPtWDUmeMgxzp3pwPtRVEuU1N4CjVK5D6iAmb12JNiFBdx"
```

**Target all clusters in a specific continent**:
```yaml
apiVersion: fleet.cattle.io/v1alpha1
kind: GitRepo
metadata:
  name: europe-workloads
  namespace: fleet-default
spec:
  targets:
  - name: europe-clusters
    clusterSelector:
      matchLabels:
        kubetee.ai/continent: eu
```

**Target all clusters in a specific city**:
```yaml
apiVersion: fleet.cattle.io/v1alpha1
kind: GitRepo
metadata:
  name: paris-config
  namespace: fleet-default
spec:
  targets:
  - name: paris-clusters
    clusterSelector:
      matchLabels:
        kubetee.ai/city: paris
```

### Comparison

| Method | Use Case | Example |
|--------|----------|---------|
| **Environment Label** | Deploy to all staging or production clusters | `environment: production` |
| **Cluster Name** | Deploy to one specific cluster | `clusterName: eu-fr-paris-123` |
| **Canonical Hotkey Label** | Deploy to the cluster bound to a miner hotkey | `kubetee.ai/hotkey: "5Grw..."` |
| **Continent** | Deploy to all clusters in a continent | `kubetee.ai/continent: eu` |
| **Country** | Deploy to all clusters in a country | `kubetee.ai/country: fr` |
| **City** | Deploy to all clusters in a city | `kubetee.ai/city: paris` |

### Advanced: Combined Selectors

You can combine multiple labels for precise targeting:

```yaml
apiVersion: fleet.cattle.io/v1alpha1
kind: GitRepo
metadata:
  name: gpu-workloads
  namespace: fleet-default
spec:
  targets:
  - name: production-gpu-clusters
    clusterSelector:
      matchLabels:
        environment: production
        gpu-enabled: "true"
        gpu-type: h100
```

This ensures workloads deploy correctly even if cluster names or UIDs change.

## Summary

✅ **Cluster Name**: `<continent>-<country>-<city>-<uid>` for human readability
✅ **Cluster Binding**: The validator reads only `kubetee.ai/hotkey` (one cluster per hotkey) and `kubetee.ai/ban`; legacy enrollment labels are optional operator metadata
✅ **Fleet Targeting**: Use `kubetee.ai/hotkey` when a miner-specific selector is required
✅ **Identity Changes**: Use platform rotation/re-enrollment; never patch the hotkey binding manually
