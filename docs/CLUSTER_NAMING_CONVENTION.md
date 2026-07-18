# KubeTEE Cluster Naming Convention

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

**Note**: UID can change if a miner deregisters and re-registers. For permanent identification, always use the `miner-hotkey` and `miner-coldkey` labels.

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

## Required Cluster Labels

While the cluster name includes the UID for human readability, clusters **MUST** be labeled with these identifiers:

```yaml
labels:
  # Required labels
  environment: <staging|production>
  kubetee.ai/continent: <eu|na|sa|as|af|oc|me>
  kubetee.ai/country: <2-letter-country-code>
  kubetee.ai/city: <city-name-lowercase>
  kubetee.ai/miner-hotkey: <MINER_HOTKEY_SS58_ADDRESS>
  kubetee.ai/miner-coldkey: <MINER_COLDKEY_SS58_ADDRESS>
  kubetee.ai/miner-uid: <MINER_UID_NUMBER>
```

**Why `kubetee.ai/` prefix?**
- Follows Kubernetes best practices for custom labels
- Prevents conflicts with standard Kubernetes or Rancher labels
- Makes it clear these are KubeTEE-specific labels
- `environment` doesn't need prefix as it's a common standard label

**Example**:
```yaml
labels:
  environment: production
  kubetee.ai/continent: eu
  kubetee.ai/country: fr
  kubetee.ai/city: paris
  kubetee.ai/miner-hotkey: "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
  kubetee.ai/miner-coldkey: "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"
  kubetee.ai/miner-uid: "123"
```

**Optional labels** (can be added for advanced targeting):
```yaml
labels:
  # Optional infrastructure labels
  kubetee.ai/tee-enabled: <true|false>
  kubetee.ai/gpu-enabled: <true|false>
  kubetee.ai/gpu-type: <h100|h200|a100>
```

## Why Use Both Name and Labels?

**Cluster Name**: 
- Human-readable identification
- Easy to understand location and current UID
- Used for display purposes

**Labels**:
- `kubetee.ai/continent`, `kubetee.ai/country`, `kubetee.ai/city`: Geographic identification
- `kubetee.ai/miner-hotkey` / `kubetee.ai/miner-coldkey`: Permanent identification that never changes
- `kubetee.ai/miner-uid`: Current UID as a label that can be updated when UID changes
- Used for programmatic cluster selection and geographic targeting
- Prevents issues when targeting clusters after UID changes

**When UID Changes**:
If a miner deregisters and re-registers (UID changes from 123 to 456):
1. Update the `kubetee.ai/miner-uid` label: `kubectl label cluster.management.cattle.io/${CLUSTER_ID} kubetee.ai/miner-uid=456 --overwrite`
2. Optionally rename the cluster from `eu-fr-paris-123` to `eu-fr-paris-456`
3. Hotkey, coldkey, and geographic labels remain unchanged
4. Deployments targeting by hotkey/coldkey continue to work without changes

## Creating a Cluster

```bash
#!/bin/bash

# Cluster naming components
CONTINENT="eu"           # 2-letter continent code
COUNTRY="fr"             # 2-letter country code
CITY="paris"             # Full city name (lowercase)
MINER_UID="123"          # Current miner UID

# Permanent identifiers
MINER_HOTKEY="5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
MINER_COLDKEY="5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty"

# Build cluster name
CLUSTER_NAME="${CONTINENT}-${COUNTRY}-${CITY}-${MINER_UID}"

echo "Creating cluster: ${CLUSTER_NAME}"
echo "Hotkey: ${MINER_HOTKEY}"
echo "Coldkey: ${MINER_COLDKEY}"
echo "UID: ${MINER_UID}"
```

## Updating UID Label When UID Changes

```bash
#!/bin/bash

# When miner UID changes (e.g., after deregistration/re-registration)
CLUSTER_ID="c-xxxxx"
NEW_MINER_UID="456"

# Update the miner-uid label
kubectl label cluster.management.cattle.io/${CLUSTER_ID} \
  kubetee.ai/miner-uid=${NEW_MINER_UID} \
  --overwrite

echo "Updated kubetee.ai/miner-uid label to: ${NEW_MINER_UID}"
echo "Note: Hotkey, coldkey, and geographic labels remain unchanged"
echo "Fleet deployments targeting by hotkey/coldkey continue to work"
```

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

**Alternative**: Target by permanent hotkey/coldkey labels (recommended for programmatic targeting):

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
        kubetee.ai/miner-hotkey: "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY"
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
| **Hotkey/Coldkey Label** | Deploy to specific miner's cluster (survives UID changes) | `kubetee.ai/miner-hotkey: "5Grw..."` |
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
✅ **Cluster Labels**: Use `miner-hotkey` and `miner-coldkey` for permanent identification  
✅ **Fleet Targeting**: Always use hotkey/coldkey labels in cluster selectors  
✅ **UID Changes**: Don't affect cluster targeting when using proper labels  

