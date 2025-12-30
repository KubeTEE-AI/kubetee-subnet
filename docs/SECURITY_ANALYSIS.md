# NeMo Microservices Security Analysis for KubeTEE Subnet

**Date**: October 7, 2025  
**Reference**: [NVIDIA NeMo Microservices Security Guidelines](https://docs.nvidia.com/nemo/microservices/latest/set-up/security.html)  
**Infrastructure**: [KubeTEE Subnet Architecture](../kubetee-subnet/README.md)

---

## Table of Contents

- [Executive Summary](#executive-summary)
- [Infrastructure Context](#infrastructure-context)
- [Security Assessment](#security-assessment)
  - [1. Rate Limiting](#1-rate-limiting)
  - [2. Authentication & Authorization](#2-authentication--authorization)
  - [3. Network Security](#3-network-security)
  - [4. Data Protection](#4-data-protection)
  - [5. Confidential Computing Integration](#5-confidential-computing-integration)
  - [6. Multi-Tenancy Isolation](#6-multi-tenancy-isolation)
- [Current Configuration Analysis](#current-configuration-analysis)
- [Security Gaps & Recommendations](#security-gaps--recommendations)
- [Implementation Roadmap](#implementation-roadmap)
- [Compliance & Audit](#compliance--audit)

---

## Executive Summary

This document analyzes the security posture of the NeMo Microservices Helm Chart deployment within the KubeTEE Subnet infrastructure. The analysis considers:

✅ **Strengths**:
- Enterprise-grade infrastructure with FIPS-140-2 certified RKE2 Kubernetes
- Confidential Computing with Intel TDX/SGX and NVIDIA Hopper TEE
- Linkerd mTLS for service-to-service communication
- Rancher RBAC for namespace isolation
- TLS termination with Let's Encrypt certificates
- Network policies enabled at infrastructure level

⚠️ **Areas for Enhancement**:
- Rate limiting not configured (NVIDIA requirement)
- Application-level authentication/authorization needs external proxy
- Data Store access controls require additional hardening
- Service mesh policies need to be explicitly defined for NeMo services

---

## Infrastructure Context

### KubeTEE Subnet Security Architecture

The NeMo microservices will be deployed within the following security context:

#### Confidential Computing Features
- **Intel TDX/SGX**: Hardware-based Trusted Execution Environment
- **NVIDIA Hopper/Blackwell PCIe Protected Mode**: GPU confidential computing
- **Kata Containers**: Workload isolation with VM-level security
- **Confidential Containers**: Workload identity validation

#### Network Security
- **Linkerd mTLS**: Automatic mutual TLS for all service-to-service communication
- **Network Policies**: Kubernetes NetworkPolicy enforcement
- **RBAC**: Rancher-managed role-based access control
- **Namespace Isolation**: Per-user/miner isolated namespaces

#### Data Protection
- **Rancher Longhorn**: Encrypted storage with 3 replicas
- **Encrypted Container Repository**: Secure image storage
- **External Secrets Manager**: Vault integration
- **TLS Ingress**: Let's Encrypt automated certificate management

#### Monitoring & Audit
- **Prometheus Metrics**: Comprehensive resource and performance monitoring
- **Kubernetes Events**: Audit trail of all cluster activities
- **ElasticSearch Audit Logs**: Centralized logging and audit

### Multi-Cluster Topology

**Staging Environment** (Permissionless):
- Testing and validation infrastructure
- Kata Containers community staging
- Gateway to production

**Production Environment** (KYC Required):
- Multi-cluster deployment (one per data center per miner UID)
- Rancher Fleet GitOps multi-cluster orchestration
- Full compliance and security validation

---

## Security Assessment

### 1. Rate Limiting

#### NVIDIA Requirement
> "The NeMo microservices do not impose rate limits. You must implement a rate-limiting strategy to restrict access to your application."

#### Current Status: ⚠️ **NOT IMPLEMENTED**

The current Helm chart configuration does not include rate limiting.

#### Recommended Implementation

**Option A: Ingress-Level Rate Limiting (Recommended for KubeTEE)**

Add to `values-nemo-kubetee.yaml`:

```yaml
ingress:
  enabled: true
  annotations:
    # Rate limiting per IP
    nginx.ingress.kubernetes.io/limit-rps: "100"
    nginx.ingress.kubernetes.io/limit-connections: "50"
    nginx.ingress.kubernetes.io/limit-rpm: "1000"
    
    # Burst handling
    nginx.ingress.kubernetes.io/limit-burst-multiplier: "5"
    
    # Rate limit by authenticated user (if JWT/auth implemented)
    nginx.ingress.kubernetes.io/auth-response-headers: "X-Auth-Request-User"
    nginx.ingress.kubernetes.io/limit-whitelist: "10.0.0.0/8"  # Internal cluster IPs
```

**Option B: Envoy Proxy with Rate Limiting**

Deploy Envoy as a sidecar or gateway with rate limiting configuration:

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: envoy-ratelimit-config
data:
  envoy.yaml: |
    rate_limits:
      - actions:
        - request_headers:
            header_name: "x-user-id"
            descriptor_key: "user_id"
        limit:
          requests_per_unit: 1000
          unit: HOUR
      - actions:
        - generic_key:
            descriptor_value: "global"
        limit:
          requests_per_unit: 10000
          unit: MINUTE
```

**Option C: Linkerd Service Profile Rate Limiting**

Since KubeTEE uses Linkerd, leverage service profiles:

```yaml
apiVersion: policy.linkerd.io/v1alpha1
kind: HTTPRoute
metadata:
  name: nemo-rate-limit
  namespace: nemo
spec:
  parentRefs:
    - name: nemo-entity-store
      kind: Service
  rules:
    - matches:
      - path:
          type: PathPrefix
          value: "/v1/"
      filters:
        - type: RequestHeaderModifier
          requestHeaderModifier:
            set:
              - name: X-Rate-Limit
                value: "1000"
```

**Recommendation**: Implement **Option A** at the ingress level as the first line of defense, complemented by service mesh policies for inter-service rate limiting.

---

### 2. Authentication & Authorization

#### NVIDIA Requirement
> "The NeMo microservices do not have an internal notion of a user. To restrict authorization to specific endpoints or users, implement an external mechanism such as an Envoy proxy."

#### Current Status: ⚠️ **PARTIALLY IMPLEMENTED**

**What's Currently Configured**:
- TLS termination at ingress (Let's Encrypt)
- NGC API key authentication for pulling images
- Kubernetes RBAC for cluster resources
- Namespace isolation via Rancher

**What's Missing**:
- Application-level user authentication
- API endpoint authorization
- Request signing/verification
- User identity propagation

#### Recommended Implementation

**Strategy**: Leverage KubeTEE's existing Bittensor wallet/hotkey authentication model

**Architecture**:

```
Client Request → Ingress (TLS) → Auth Proxy → NeMo Services
                                      ↓
                                 Bittensor Verification
                                      ↓
                                 JWT Token Generation
```

**Implementation Options**:

**Option A: OAuth2 Proxy with Custom Bittensor Authenticator**

```yaml
# Deploy oauth2-proxy as authentication gateway
apiVersion: apps/v1
kind: Deployment
metadata:
  name: oauth2-proxy
  namespace: nemo
spec:
  template:
    spec:
      containers:
      - name: oauth2-proxy
        image: quay.io/oauth2-proxy/oauth2-proxy:latest
        args:
        - --provider=oidc
        - --oidc-issuer-url=https://auth.kubetee.ai
        - --upstream=http://nemo-entity-store:8000
        - --http-address=0.0.0.0:4180
        - --email-domain=*
        - --pass-access-token=true
        - --pass-user-headers=true
        - --set-xauthrequest=true
        env:
        - name: OAUTH2_PROXY_CLIENT_ID
          valueFrom:
            secretKeyRef:
              name: oauth2-proxy-secret
              key: client-id
        - name: OAUTH2_PROXY_CLIENT_SECRET
          valueFrom:
            secretKeyRef:
              name: oauth2-proxy-secret
              key: client-secret
```

Update ingress to use auth:

```yaml
ingress:
  annotations:
    nginx.ingress.kubernetes.io/auth-url: "https://auth.kubetee.ai/oauth2/auth"
    nginx.ingress.kubernetes.io/auth-signin: "https://auth.kubetee.ai/oauth2/start"
    nginx.ingress.kubernetes.io/auth-response-headers: "X-Auth-Request-User,X-Auth-Request-Email"
```

**Option B: Custom Bittensor JWT Middleware**

Create a lightweight authentication service:

```python
# auth-service/main.py
from fastapi import FastAPI, Header, HTTPException
from bittensor import wallet
import jwt
from datetime import datetime, timedelta

app = FastAPI()

@app.post("/v1/auth/verify")
async def verify_bittensor_signature(
    x_hotkey: str = Header(...),
    x_signature: str = Header(...),
    x_timestamp: str = Header(...)
):
    """Verify Bittensor hotkey signature and issue JWT"""
    try:
        # Verify signature from Bittensor wallet
        wallet_instance = wallet.Wallet(hotkey=x_hotkey)
        if not wallet_instance.verify_signature(x_timestamp, x_signature):
            raise HTTPException(status_code=401, detail="Invalid signature")
        
        # Check timestamp to prevent replay attacks
        if abs(datetime.now().timestamp() - float(x_timestamp)) > 300:
            raise HTTPException(status_code=401, detail="Timestamp expired")
        
        # Generate JWT with hotkey identity
        token = jwt.encode({
            "hotkey": x_hotkey,
            "exp": datetime.utcnow() + timedelta(hours=1),
            "iat": datetime.utcnow(),
            "iss": "kubetee-auth"
        }, secret_key, algorithm="HS256")
        
        return {"access_token": token, "token_type": "bearer"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=str(e))
```

Deploy as a sidecar or separate service and configure ingress:

```yaml
ingress:
  annotations:
    nginx.ingress.kubernetes.io/auth-url: "http://bittensor-auth-service.nemo.svc.cluster.local/v1/auth/verify"
    nginx.ingress.kubernetes.io/auth-method: "POST"
    nginx.ingress.kubernetes.io/auth-response-headers: "Authorization"
```

**Option C: Linkerd Service Mesh Authorization Policies**

Leverage Linkerd's built-in authorization:

```yaml
apiVersion: policy.linkerd.io/v1beta3
kind: AuthorizationPolicy
metadata:
  name: nemo-service-auth
  namespace: nemo
spec:
  targetRef:
    group: core
    kind: Service
    name: nemo-entity-store
  requiredAuthenticationRefs:
  - name: jwt-auth
    kind: MeshTLSAuthentication
---
apiVersion: policy.linkerd.io/v1alpha1
kind: MeshTLSAuthentication
metadata:
  name: jwt-auth
  namespace: nemo
spec:
  identities:
  - "*.user-namespace-*.serviceaccount.identity.linkerd.cluster.local"
```

**Recommendation**: Implement **Option B** (Custom Bittensor JWT Middleware) as it aligns perfectly with the KubeTEE subnet's existing wallet-based authentication model, then layer **Option C** for service-to-service authorization.

---

### 3. Network Security

#### NVIDIA Requirement
> "The NeMo microservices are not intended to be internet-facing. Deploy them as the logic (middle) tier in a three-tier architecture."

#### Current Status: ✅ **WELL IMPLEMENTED**

The KubeTEE infrastructure already implements comprehensive network security:

**Existing Security Layers**:
1. **Linkerd mTLS**: All service-to-service traffic is encrypted
2. **Network Policies**: Kubernetes NetworkPolicy enforcement
3. **Namespace Isolation**: Per-tenant namespace boundaries
4. **Ingress Controller**: TLS termination at edge

**Current Architecture**:

```
[Internet] 
    ↓ TLS (Let's Encrypt)
[Ingress Controller] 
    ↓ AuthN/AuthZ Proxy
[NeMo Microservices] ← mTLS → [NIM Models] ← mTLS → [Databases]
    ↓ mTLS
[Internal Services]
```

#### Network Policy Enhancement

**Default Deny All Policy**:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-all
  namespace: nemo
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
```

**NeMo Entity Store Network Policy**:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: nemo-entity-store-policy
  namespace: nemo
spec:
  podSelector:
    matchLabels:
      app: nemo-entity-store
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: nemo
    - podSelector:
        matchLabels:
          app: ingress-nginx
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          name: nemo
    - podSelector:
        matchLabels:
          app: postgresql
    ports:
    - protocol: TCP
      port: 5432
  - to:  # DNS resolution
    - namespaceSelector:
        matchLabels:
          name: kube-system
    - podSelector:
        matchLabels:
          k8s-app: kube-dns
    ports:
    - protocol: UDP
      port: 53
```

**NeMo Customizer Network Policy** (needs GPU node access):

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: nemo-customizer-policy
  namespace: nemo
spec:
  podSelector:
    matchLabels:
      app: nemo-customizer
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          name: nemo
    ports:
    - protocol: TCP
      port: 8000
  egress:
  - to:  # PostgreSQL
    - podSelector:
        matchLabels:
          app: customizerdb
    ports:
    - protocol: TCP
      port: 5432
  - to:  # NeMo Data Store
    - podSelector:
        matchLabels:
          app: nemo-data-store
    ports:
    - protocol: TCP
      port: 3000
  - to:  # NGC Container Registry
    - namespaceSelector: {}
    ports:
    - protocol: TCP
      port: 443
  - to:  # DNS
    - namespaceSelector:
        matchLabels:
          name: kube-system
    ports:
    - protocol: UDP
      port: 53
```

**Cross-Namespace Access for User Namespaces**:

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: allow-from-user-namespaces
  namespace: nemo
spec:
  podSelector:
    matchLabels:
      app: nemo-nim-proxy
  policyTypes:
  - Ingress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          tenant: "user"  # User namespaces labeled with tenant=user
    ports:
    - protocol: TCP
      port: 8000
```

**Linkerd Server Authorization for Service Mesh**:

```yaml
apiVersion: policy.linkerd.io/v1beta1
kind: Server
metadata:
  name: nemo-entity-store-server
  namespace: nemo
spec:
  podSelector:
    matchLabels:
      app: nemo-entity-store
  port: 8000
  proxyProtocol: HTTP
---
apiVersion: policy.linkerd.io/v1beta1
kind: ServerAuthorization
metadata:
  name: nemo-internal-only
  namespace: nemo
spec:
  server:
    name: nemo-entity-store-server
  client:
    meshTLS:
      identities:
      - "*.nemo.serviceaccount.identity.linkerd.cluster.local"
      # Allow ingress controller
      - "ingress-nginx.ingress-nginx.serviceaccount.identity.linkerd.cluster.local"
```

#### Port Security Audit

**Default Network Ports Used** (from NVIDIA documentation):

| Port | Service | Exposure | Recommendation |
|------|---------|----------|----------------|
| 443/TCP | NeMo Admission Service | External via Ingress | ✅ Keep with TLS |
| 2746/TCP | Argo Workflows | Internal Only | ✅ Block external |
| 3000/TCP | NeMo Data Store | Internal Only | ✅ Block external |
| 7331/TCP | NeMo Evaluator | Internal Only | ✅ Block external |
| 7331/TCP | NeMo Guardrails | Internal Only | ✅ Block external |
| 8000/TCP | NIM API | Internal Only | ⚠️ Expose via NIM Proxy only |
| 8000/TCP | NeMo Customizer | Internal Only | ✅ Block external |
| 8000/TCP | NeMo Entity Store | External via Ingress | ⚠️ Requires auth proxy |
| 8443/TCP | NeMo Operator metrics | Internal Only | ✅ Block external |
| 5432/TCP | PostgreSQL Databases | Internal Only | ✅ Block external |
| 9091/TCP | Milvus metrics | Internal Only | ✅ Block external |
| 19530/TCP | Milvus API | Internal Only | ✅ Block external |

**Recommendation**: The current ingress configuration exposes necessary endpoints. Add the network policies above to enforce defense-in-depth.

---

### 4. Data Protection

#### NVIDIA Requirement
> "The NeMo microservices, by design, can access all content in the NeMo Data Store microservice, including LoRA adapters, training data, evaluation data, and evaluation results."

#### Current Status: ⚠️ **NEEDS ENHANCEMENT**

**Existing Infrastructure Security**:
- ✅ Rancher Longhorn encrypted storage (3 replicas)
- ✅ External object storage with TLS (iDrive e2)
- ✅ Database encryption at rest (PostgreSQL)
- ✅ Secrets management capability

**Data Store Access Control Issues**:
> "The NeMo Data Store microservice does not provide object-class-specific access controls. All items reside within a single access control boundary."

This is a critical security consideration for multi-tenant deployment.

#### Recommended Data Protection Strategy

**1. Namespace-Level Data Store Isolation**

Deploy separate NeMo Data Store instances per tenant namespace:

```yaml
# Per-tenant data store configuration
data-store:
  fullnameOverride: nemo-data-store-tenant-{{ .Values.tenantId }}
  namespace: user-namespace-{{ .Values.tenantId }}
  
  postgresql:
    auth:
      database: datastore_tenant_{{ .Values.tenantId }}
      username: datastore_{{ .Values.tenantId }}
      password: # Generated per tenant
  
  storage:
    s3:
      bucketName: "kubetee-tenant-{{ .Values.tenantId }}"
      # IAM policy restricts to tenant bucket only
```

**2. Object Storage IAM Policies**

Create per-tenant IAM policies:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::kubetee-tenant-${TENANT_ID}/*"
    },
    {
      "Effect": "Deny",
      "Action": "s3:*",
      "NotResource": "arn:aws:s3:::kubetee-tenant-${TENANT_ID}/*"
    }
  ]
}
```

**3. Kubernetes Secrets Encryption**

Ensure secrets are encrypted at rest (already supported by RKE2 FIPS):

```yaml
# /etc/rancher/rke2/config.yaml
secrets-encryption: true
```

Verify with:
```bash
kubectl get secrets -A -o json | \
  kubectl annotate --dry-run=client -f - \
  io.kubernetes.crd.encryption=encrypted
```

**4. Database-Level Encryption**

PostgreSQL with encryption:

```yaml
postgresql:
  primary:
    extraEnvVars:
    - name: POSTGRESQL_ENABLE_TLS
      value: "yes"
    - name: POSTGRESQL_TLS_CERT_FILE
      value: "/opt/bitnami/postgresql/certs/tls.crt"
    - name: POSTGRESQL_TLS_KEY_FILE
      value: "/opt/bitnami/postgresql/certs/tls.key"
    extraVolumes:
    - name: postgresql-tls
      secret:
        secretName: postgresql-tls-secret
    extraVolumeMounts:
    - name: postgresql-tls
      mountPath: /opt/bitnami/postgresql/certs
      readOnly: true
```

**5. Fine-Tuning Data Isolation**

Critical consideration for multi-tenant training:

```yaml
nemo-customizer:
  finetuning:
    # Ensure training jobs run in tenant namespace
    namespace: user-namespace-{{ .Values.tenantId }}
    
    # Use dedicated service account
    serviceAccount:
      name: customizer-tenant-{{ .Values.tenantId }}
    
    # Restrict node access via node affinity
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
        - matchExpressions:
          - key: tenant
            operator: In
            values:
            - {{ .Values.tenantId }}
    
    # Use Kata Containers for isolation
    runtimeClassName: kata-containers
```

**6. TEE Integration for Sensitive Data**

For highly sensitive training data in PROD environment:

```yaml
apiVersion: confidentialcontainers.org/v1beta1
kind: PeerPod
metadata:
  name: confidential-training-{{ .Values.tenantId }}
  namespace: user-namespace-{{ .Values.tenantId }}
spec:
  image: nvcr.io/nvidia/nemo:24.09
  teeConfig:
    type: tdx  # Intel TDX
    attestation: true
    verifier: https://attestation.kubetee.ai
  resources:
    limits:
      nvidia.com/gpu: 1
      memory: 32Gi
```

**7. Audit Logging for Data Access**

Enable comprehensive audit logging:

```yaml
# Kubernetes audit policy
apiVersion: audit.k8s.io/v1
kind: Policy
rules:
- level: RequestResponse
  namespaces: ["nemo", "user-namespace-*"]
  verbs: ["get", "list", "create", "update", "patch", "delete"]
  resources:
  - group: ""
    resources: ["secrets", "configmaps"]
  - group: "apps"
    resources: ["deployments", "statefulsets"]
```

Send to ElasticSearch (already in KubeTEE infrastructure):

```yaml
# Fluent Bit configuration
[OUTPUT]
    Name  es
    Match kube.audit.*
    Host elasticsearch.logging.svc.cluster.local
    Port 9200
    Logstash_Format On
    Logstash_Prefix k8s-audit
    Type _doc
    Include_Tag_Key On
    Tag_Key @tag
```

**Recommendation**: 
1. Deploy **namespace-isolated Data Stores** for each tenant in PROD
2. Use **shared Data Store** in STAGING for development
3. Implement **object storage IAM policies** for bucket-level isolation
4. Enable **Kata Containers** for all fine-tuning workloads
5. Use **Confidential Containers with TEE** for sensitive PROD workloads

---

### 5. Confidential Computing Integration

#### KubeTEE Advantage: Hardware-Based Security

The KubeTEE subnet provides unique security advantages through Confidential Computing that go beyond NVIDIA's base requirements:

**Intel TDX/SGX Integration**:
- Hardware-encrypted memory
- Attestation-based workload verification
- Protected from privileged access (including hypervisor)

**NVIDIA Hopper/Blackwell PCIe Protected Mode**:
- GPU memory encryption
- Secure multi-tenancy on GPUs
- Protect model weights and training data in GPU memory

#### Implementation Strategy

**1. Kata Containers Runtime for NeMo Workloads**

Configure all NeMo microservices to use Kata Containers:

```yaml
# values-nemo-kubetee.yaml
global:
  runtimeClassName: kata-containers

nemo-customizer:
  finetuning:
    training:
      runtimeClassName: kata-containers
      
nemo-evaluator:
  runtimeClassName: kata-containers
  
nemo-guardrails:
  runtimeClassName: kata-containers
```

**2. Confidential Containers Operator**

Deploy workloads with attestation:

```yaml
apiVersion: confidentialcontainers.org/v1beta1
kind: CcRuntime
metadata:
  name: cc-runtime-nemo
  namespace: nemo
spec:
  ccnpConfig:
    podSelector:
      matchLabels:
        confidential: "true"
    attestation:
      enabled: true
      verifier: "kata-attestation-service"
      policy: |
        measurement = "trusted-nemo-image-hash"
        enforce_tee = true
```

**3. TEE Node Selection**

Ensure NeMo pods are scheduled on TEE-enabled nodes:

```yaml
nodeAffinity:
  requiredDuringSchedulingIgnoredDuringExecution:
    nodeSelectorTerms:
    - matchExpressions:
      - key: feature.node.kubernetes.io/cpu-tdx.enabled
        operator: In
        values:
        - "true"
      - key: nvidia.com/gpu.confidential
        operator: In
        values:
        - "true"
```

**4. Attestation Validation**

Validators verify TEE attestation via Kata cronjobs:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: tee-attestation-validator
  namespace: validation
spec:
  schedule: "*/15 * * * *"  # Every 15 minutes
  jobTemplate:
    spec:
      template:
        spec:
          runtimeClassName: kata-containers
          containers:
          - name: validator
            image: kubetee/tee-validator:latest
            command:
            - /bin/sh
            - -c
            - |
              # Verify Intel TDX attestation
              tdx-verify --namespace nemo --pod nemo-customizer-*
              
              # Verify NVIDIA GPU TEE mode
              nvidia-smi -q | grep "Confidential Compute Mode: Enabled"
              
              # Collect Prometheus metrics
              curl http://prometheus.monitoring.svc.cluster.local:9090/api/v1/query \
                -d 'query=up{namespace="nemo"}'
```

**5. Encrypted Communication in TEE**

Linkerd mTLS works seamlessly with Kata Containers, providing:
- TLS 1.3 encryption between all pods
- Identity bound to Kubernetes ServiceAccount
- Certificate rotation every 24 hours
- Private keys stored in memory only (tmpfs)

**6. Protected Model Inference**

For sensitive model serving:

```yaml
apiVersion: apps.nvidia.com/v1alpha1
kind: NIMService
metadata:
  name: protected-llm
  namespace: nemo
spec:
  image: nvcr.io/nvidia/nemo/llama-3.3-nemotron-49b:latest
  replicas: 1
  
  # TEE configuration
  runtime: kata-containers
  confidential: true
  
  # GPU TEE mode
  resources:
    limits:
      nvidia.com/gpu: 1
  
  # Node selection
  nodeSelector:
    nvidia.com/gpu.confidential: "true"
    feature.node.kubernetes.io/cpu-tdx.enabled: "true"
```

**Benefits for Multi-Tenant AIaaS**:

1. **Data Privacy**: Training data never exposed in cleartext, even to infrastructure operators
2. **Model IP Protection**: Model weights encrypted in memory during training and inference
3. **Compliance**: Meets GDPR, HIPAA, and other regulatory requirements for sensitive data
4. **Zero Trust**: Hardware-verified execution, not just software promises
5. **Audit Trail**: Attestation logs provide cryptographic proof of secure execution

---

### 6. Multi-Tenancy Isolation

#### Architecture Overview

KubeTEE implements multi-tenancy through:
- **Rancher Projects**: Logical grouping of namespaces
- **Kubernetes Namespaces**: Per-user/miner isolation
- **Linkerd Service Mesh**: mTLS and authorization policies
- **Network Policies**: Traffic restrictions

#### Tenant Isolation Configuration

**1. Namespace Template for New Users**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: user-{{ .Values.userId }}
  labels:
    tenant: "user"
    project: "{{ .Values.projectId }}"
    linkerd.io/inject: enabled
  annotations:
    config.linkerd.io/default-inbound-policy: "deny"
    scheduler.alpha.kubernetes.io/node-selector: "tenant={{ .Values.userId }}"
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: tenant-quota
  namespace: user-{{ .Values.userId }}
spec:
  hard:
    requests.cpu: "64"
    requests.memory: "256Gi"
    requests.nvidia.com/gpu: "8"
    persistentvolumeclaims: "10"
    services: "50"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: tenant-limits
  namespace: user-{{ .Values.userId }}
spec:
  limits:
  - max:
      cpu: "32"
      memory: "128Gi"
      nvidia.com/gpu: "4"
    type: Container
```

**2. Shared NeMo Services Access**

Users need controlled access to shared NeMo services:

```yaml
apiVersion: policy.linkerd.io/v1beta1
kind: Server
metadata:
  name: nemo-shared-services
  namespace: nemo
spec:
  podSelector:
    matchLabels:
      tier: shared
  port: 8000
---
apiVersion: policy.linkerd.io/v1beta1
kind: ServerAuthorization
metadata:
  name: allow-authenticated-users
  namespace: nemo
spec:
  server:
    name: nemo-shared-services
  client:
    meshTLS:
      serviceAccounts:
      # Allow from any user namespace's default service account
      - name: default
        namespace: user-*
```

**3. Cross-Namespace Communication Restrictions**

```yaml
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: deny-cross-tenant
  namespace: user-{{ .Values.userId }}
spec:
  podSelector: {}
  policyTypes:
  - Ingress
  - Egress
  ingress:
  - from:
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: user-{{ .Values.userId }}
  egress:
  - to:
    - namespaceSelector:
        matchLabels:
          tier: shared  # Only to shared services
  - to:  # DNS
    - namespaceSelector:
        matchLabels:
          kubernetes.io/metadata.name: kube-system
    ports:
    - protocol: UDP
      port: 53
  - to: {}  # Allow external egress (internet)
    ports:
    - protocol: TCP
      port: 443
```

**4. Tenant-Specific Secrets Isolation**

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: tenant-sa
  namespace: user-{{ .Values.userId }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: tenant-secrets-reader
  namespace: user-{{ .Values.userId }}
rules:
- apiGroups: [""]
  resources: ["secrets"]
  verbs: ["get", "list"]
  resourceNames: ["tenant-*"]  # Only secrets starting with tenant-
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: tenant-secrets-binding
  namespace: user-{{ .Values.userId }}
subjects:
- kind: ServiceAccount
  name: tenant-sa
  namespace: user-{{ .Values.userId }}
roleRef:
  kind: Role
  name: tenant-secrets-reader
  apiGroup: rbac.authorization.k8s.io
```

**5. Rancher Project Configuration**

```yaml
apiVersion: management.cattle.io/v3
kind: Project
metadata:
  name: project-{{ .Values.userId }}
  namespace: cluster-{{ .Values.clusterId }}
spec:
  clusterName: cluster-{{ .Values.clusterId }}
  displayName: "User {{ .Values.userId }} Project"
  description: "Isolated project for tenant {{ .Values.userId }}"
  resourceQuota:
    limit:
      limitsCpu: "64000m"
      limitsMemory: "256Gi"
  namespaceDefaultResourceQuota:
    limit:
      limitsCpu: "32000m"
      limitsMemory: "128Gi"
  containerDefaultResourceLimit:
    limitsCpu: "16000m"
    limitsMemory: "64Gi"
```

---

## Current Configuration Analysis

### Helm Chart Security Configuration Review

#### 1. Image Pull Secrets

**Current Configuration** (`values-nemo-kubetee.yaml`):

```yaml
ngcAPIKey: YOUR-NGC-API-KEY  # ⚠️ Hardcoded in values file
existingImagePullSecret: nvcrimagepullsecret

imagePullSecrets:
  - name: nvcrimagepullsecret
    registry: nvcr.io
    username: $oauthtoken
    password: YOUR-NGC-API-KEY  # ⚠️ Hardcoded
```

**Issue**: API key exposed in values file

**Recommendation**: Use existing secret reference only:

```yaml
# Remove these lines:
# ngcAPIKey: YOUR-NGC-API-KEY
# imagePullSecrets: ...

# Keep only:
existingImagePullSecret: nvcrimagepullsecret

# Create secret separately:
# kubectl create secret docker-registry nvcrimagepullsecret \
#   --docker-server=nvcr.io \
#   --docker-username='$oauthtoken' \
#   --docker-password=$NGC_API_KEY \
#   --namespace=nemo
```

#### 2. TLS/Ingress Configuration

**Current Configuration**:

```yaml
ingress:
  enabled: false  # ⚠️ Disabled at individual service level
  
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: 50g
    cert-manager.io/cluster-issuer: "letsencrypt-prod"  # ✅ Good
    cert-manager.io/subject-organizations: "Kubetee AI LTD"
  
  className: ""  # ⚠️ Not specified
  
  tls:
    - secretName: nemo-tls
      hosts:
        - nemo.kubetee.ai
        - nim.kubetee.ai
        - data-store.kubetee.ai
```

**Issues**:
- Individual service ingresses disabled
- Main ingress doesn't specify className
- Missing security headers

**Recommendation**:

```yaml
ingress:
  enabled: true
  className: "nginx"
  
  annotations:
    # Existing
    nginx.ingress.kubernetes.io/proxy-body-size: 50g
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
    cert-manager.io/subject-organizations: "Kubetee AI LTD"
    
    # Add security headers
    nginx.ingress.kubernetes.io/force-ssl-redirect: "true"
    nginx.ingress.kubernetes.io/ssl-protocols: "TLSv1.3"
    nginx.ingress.kubernetes.io/ssl-ciphers: "ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256"
    
    # HSTS
    nginx.ingress.kubernetes.io/configuration-snippet: |
      more_set_headers "Strict-Transport-Security: max-age=31536000; includeSubDomains; preload";
      more_set_headers "X-Frame-Options: DENY";
      more_set_headers "X-Content-Type-Options: nosniff";
      more_set_headers "X-XSS-Protection: 1; mode=block";
      more_set_headers "Referrer-Policy: strict-origin-when-cross-origin";
    
    # Rate limiting (as discussed earlier)
    nginx.ingress.kubernetes.io/limit-rps: "100"
    nginx.ingress.kubernetes.io/limit-connections: "50"
```

#### 3. Security Contexts

**Current Configuration**:

```yaml
global:
  security:
    allowInsecureImages: true  # ⚠️ Security risk
    
data-store:
  containerSecurityContext: {}  # ⚠️ Not configured
  podSecurityContext:
    fsGroup: 1000
    fsGroupChangePolicy: OnRootMismatch
```

**Issue**: Insecure images allowed, containers may run as root

**Recommendation**:

```yaml
global:
  security:
    allowInsecureImages: false  # ✅ Require signed images
    
data-store:
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 1000
    runAsGroup: 1000
    fsGroup: 1000
    fsGroupChangePolicy: OnRootMismatch
    seccompProfile:
      type: RuntimeDefault
  
  containerSecurityContext:
    allowPrivilegeEscalation: false
    readOnlyRootFilesystem: true
    runAsNonRoot: true
    runAsUser: 1000
    capabilities:
      drop:
      - ALL
```

Apply to all microservices:

```yaml
nemo-customizer:
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 1000
    seccompProfile:
      type: RuntimeDefault
  containerSecurityContext:
    allowPrivilegeEscalation: false
    capabilities:
      drop:
      - ALL
      add:
      - NET_BIND_SERVICE  # Only if needed for port <1024

nemo-evaluator:
  podSecurityContext:
    runAsNonRoot: true
    runAsUser: 1000
    seccompProfile:
      type: RuntimeDefault
  containerSecurityContext:
    allowPrivilegeEscalation: false
    capabilities:
      drop:
      - ALL
```

#### 4. Database Security

**Current Configuration**:

```yaml
data-store:
  postgresql:
    enabled: true
    auth:
      password: datastore  # ⚠️ Weak password
      
nemo-customizer:
  postgresql:
    auth:
      enablePostgresUser: true  # ⚠️ Admin user enabled
      password: # Not specified
```

**Issue**: Weak/default passwords, admin user enabled

**Recommendation**:

```yaml
data-store:
  postgresql:
    enabled: true
    auth:
      existingSecret: datastore-postgresql-secret
      secretKeys:
        adminPasswordKey: postgres-password
        userPasswordKey: password
      # Do not hardcode passwords in values
    
    primary:
      extraEnvVars:
      - name: POSTGRESQL_ENABLE_TLS
        value: "yes"
      extraVolumes:
      - name: postgresql-tls
        secret:
          secretName: datastore-postgresql-tls
      extraVolumeMounts:
      - name: postgresql-tls
        mountPath: /opt/bitnami/postgresql/certs

nemo-customizer:
  postgresql:
    auth:
      enablePostgresUser: false  # ✅ Disable admin user
      existingSecret: customizer-postgresql-secret
```

Create secrets with strong passwords:

```bash
# Generate strong password
PG_PASSWORD=$(openssl rand -base64 32)

kubectl create secret generic datastore-postgresql-secret \
  --from-literal=postgres-password=$PG_PASSWORD \
  --from-literal=password=$PG_PASSWORD \
  --namespace=nemo

# Create TLS certificates
kubectl create secret generic datastore-postgresql-tls \
  --from-file=tls.crt=./postgresql.crt \
  --from-file=tls.key=./postgresql.key \
  --from-file=ca.crt=./ca.crt \
  --namespace=nemo
```

#### 5. Object Storage Configuration

**Current Configuration**:

```yaml
data-store:
  externalGitea:
    storage:
      s3:
        endpoint: "c8j7.par5.idrivee2-11.com"
        accessKey: "MvNGzmLuvoga36Kk6UbF"  # ⚠️ Exposed credentials
        accessSecret: "zocpC6PF4QwFOViGCLCekdQRDckVCE6qYEYfVHoo"  # ⚠️ Exposed
        bucketName: "hc-datasets"
        ssl: true
        existingSecret: ""  # ⚠️ Not using existing secret
```

**Issue**: S3 credentials hardcoded in values file

**Recommendation**:

```yaml
data-store:
  externalGitea:
    storage:
      s3:
        endpoint: "c8j7.par5.idrivee2-11.com"
        bucketName: "hc-datasets"
        ssl: true
        existingSecret: "s3-storage-secret"  # ✅ Use existing secret
        # Remove accessKey and accessSecret from values
```

Create secret separately:

```bash
kubectl create secret generic s3-storage-secret \
  --from-literal=accessKey=$S3_ACCESS_KEY \
  --from-literal=accessSecret=$S3_SECRET_KEY \
  --namespace=nemo
```

For multi-tenant isolation, create per-tenant secrets:

```bash
kubectl create secret generic s3-storage-secret-tenant-$TENANT_ID \
  --from-literal=accessKey=$TENANT_S3_ACCESS_KEY \
  --from-literal=accessSecret=$TENANT_S3_SECRET_KEY \
  --namespace=user-$TENANT_ID
```

#### 6. RBAC Configuration

**Current Configuration**:

Properly configured for most services with appropriate ClusterRole/Role bindings.

**Good practices observed**:
- ✅ Separate ServiceAccounts per microservice
- ✅ Minimal RBAC permissions
- ✅ Namespace-scoped roles where possible

**Recommendation**: Maintain current RBAC, add additional restrictions:

```yaml
# Prevent privilege escalation in user namespaces
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: prevent-privilege-escalation
rules:
- apiGroups: [""]
  resources: ["pods"]
  verbs: ["create", "update", "patch"]
  resourceNames: []
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: prevent-privilege-escalation-binding
subjects:
- kind: Group
  name: system:serviceaccounts:user-*
  apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: prevent-privilege-escalation
  apiGroup: rbac.authorization.k8s.io
```

---

## Security Gaps & Recommendations

### Critical (Fix Immediately)

| # | Gap | Impact | Recommendation | Priority |
|---|-----|--------|----------------|----------|
| 1 | No rate limiting | DoS attacks, resource exhaustion | Implement ingress-level rate limiting | 🔴 Critical |
| 2 | No application authentication | Unauthorized API access | Deploy Bittensor JWT auth proxy | 🔴 Critical |
| 3 | Secrets hardcoded in values | Credential exposure | Use Kubernetes secrets / Vault | 🔴 Critical |
| 4 | allowInsecureImages: true | Unsigned image execution | Set to false, require signed images | 🔴 Critical |
| 5 | Data Store lacks tenant isolation | Cross-tenant data access | Deploy per-tenant Data Stores | 🔴 Critical |

### High (Fix Soon)

| # | Gap | Impact | Recommendation | Priority |
|---|-----|--------|----------------|----------|
| 6 | Missing network policies | Lateral movement possible | Implement default-deny NetworkPolicies | 🟠 High |
| 7 | Weak database passwords | Database compromise | Generate strong random passwords | 🟠 High |
| 8 | Missing security contexts | Container breakout risk | Apply restrictive securityContexts | 🟠 High |
| 9 | No egress filtering | Data exfiltration possible | Implement egress NetworkPolicies | 🟠 High |
| 10 | TLS 1.2 allowed | Protocol downgrade attacks | Enforce TLS 1.3 only | 🟠 High |

### Medium (Plan for Implementation)

| # | Gap | Impact | Recommendation | Priority |
|---|-----|--------|----------------|----------|
| 11 | No pod disruption budgets | Availability during updates | Configure PodDisruptionBudgets | 🟡 Medium |
| 12 | Missing resource limits | Resource starvation | Set CPU/memory limits | 🟡 Medium |
| 13 | No audit logging for apps | Limited forensics capability | Enable application audit logs | 🟡 Medium |
| 14 | Missing backup/DR for DBs | Data loss risk | Implement Velero backups | 🟡 Medium |
| 15 | No image scanning | Vulnerable images deployed | Integrate Trivy/Grype scanning | 🟡 Medium |

### Low (Nice to Have)

| # | Gap | Impact | Recommendation | Priority |
|---|-----|--------|----------------|----------|
| 16 | No pod security policies | Non-compliant pods possible | Implement Pod Security Standards | 🟢 Low |
| 17 | Missing service mesh policies | Uncontrolled service communication | Define Linkerd ServerAuthorizations | 🟢 Low |
| 18 | No chaos engineering | Unknown failure modes | Implement chaos testing | 🟢 Low |
| 19 | Limited observability | Difficult troubleshooting | Enhanced metrics/tracing | 🟢 Low |
| 20 | No automated security scans | Drift from security baseline | Implement continuous scanning | 🟢 Low |

---

## Implementation Roadmap

### Phase 1: Critical Security Hardening (Week 1-2)

**Week 1**:
- [ ] Remove all hardcoded secrets from `values-nemo-kubetee.yaml`
- [ ] Create Kubernetes secrets for NGC API key, database passwords, S3 credentials
- [ ] Deploy Bittensor JWT authentication proxy
- [ ] Implement ingress-level rate limiting
- [ ] Set `allowInsecureImages: false`

**Week 2**:
- [ ] Deploy default-deny NetworkPolicies for all namespaces
- [ ] Implement service-specific NetworkPolicies for NeMo services
- [ ] Configure restrictive security contexts for all pods
- [ ] Enforce TLS 1.3 at ingress
- [ ] Enable HSTS and security headers

**Validation**:
```bash
# Test authentication
curl https://nemo.kubetee.ai/v1/namespaces -H "Authorization: Bearer invalid-token"
# Should return 401 Unauthorized

# Test rate limiting
for i in {1..150}; do curl https://nemo.kubetee.ai/v1/namespaces; done
# Should return 429 Too Many Requests

# Verify TLS 1.3
openssl s_client -connect nemo.kubetee.ai:443 -tls1_2
# Should fail

# Check security contexts
kubectl get pods -n nemo -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.securityContext.runAsNonRoot}{"\n"}{end}'
# All should show 'true'
```

### Phase 2: Multi-Tenancy Isolation (Week 3-4)

**Week 3**:
- [ ] Design per-tenant namespace template
- [ ] Implement namespace resource quotas and limits
- [ ] Configure Linkerd ServerAuthorizations for cross-namespace communication
- [ ] Deploy sample tenant environment and validate isolation

**Week 4**:
- [ ] Deploy per-tenant Data Store instances for PROD environment
- [ ] Implement object storage IAM policies per tenant
- [ ] Configure database-level encryption for PostgreSQL
- [ ] Set up per-tenant audit logging

**Validation**:
```bash
# Test cross-tenant isolation
kubectl exec -n user-tenant1 test-pod -- curl http://service.user-tenant2.svc.cluster.local
# Should fail (timeout or connection refused)

# Verify resource quotas
kubectl describe resourcequota -n user-tenant1
# Should show limits are enforced

# Check Linkerd authorization
linkerd viz -n user-tenant1 tap deploy/test-app --to ns/user-tenant2
# Should show denied requests
```

### Phase 3: TEE Integration (Week 5-6)

**Week 5**:
- [ ] Configure Kata Containers runtime for NeMo services
- [x] Deploy Confidential Containers operator
- [x] Implement node selectors for TEE-enabled nodes
- [ ] Configure NVIDIA GPU confidential computing mode

**Week 6**:
- [ ] Deploy TEE attestation validation cronjobs
- [ ] Integrate Intel TDX verification
- [ ] Set up automated attestation reporting to Prometheus
- [ ] Test end-to-end TEE-protected fine-tuning workflow

**Validation**:
```bash
# Verify Kata Containers runtime
kubectl get pods -n nemo -o jsonpath='{range .items[*]}{.metadata.name}{"\t"}{.spec.runtimeClassName}{"\n"}{end}'
# Should show 'kata-containers'

# Check TEE attestation
kubectl logs -n validation $(kubectl get pods -n validation -l app=tee-validator -o name) | grep "Attestation: Success"

# Verify GPU confidential mode
kubectl exec -n nemo $(kubectl get pods -n nemo -l app=nemo-customizer -o name) -- nvidia-smi -q | grep "Confidential Compute"
# Should show "Enabled"
```

### Phase 4: Observability & Audit (Week 7-8)

**Week 7**:
- [ ] Enable Kubernetes audit logging
- [ ] Configure FluentBit to send logs to ElasticSearch
- [ ] Set up Grafana dashboards for security metrics
- [ ] Implement Prometheus alerts for security events

**Week 8**:
- [ ] Deploy Falco for runtime security monitoring
- [ ] Configure automated vulnerability scanning with Trivy
- [ ] Set up compliance reports (CIS benchmarks)
- [ ] Document security audit procedures

**Validation**:
```bash
# Check audit logs
curl -X GET "elasticsearch.logging.svc.cluster.local:9200/k8s-audit-*/_search?q=namespace:nemo"
# Should return audit events

# Verify Falco is running
kubectl get pods -n falco
# Should show running pods

# Test Trivy scanning
trivy image nvcr.io/nvidia/nemo:latest
# Should show vulnerability report
```

### Phase 5: Documentation & Training (Week 9-10)

**Week 9**:
- [ ] Document security architecture and policies
- [ ] Create runbooks for incident response
- [ ] Write user guides for secure deployment
- [ ] Prepare security training materials

**Week 10**:
- [ ] Conduct security training for operators
- [ ] Perform tabletop exercise for incident response
- [ ] Review and update security policies
- [ ] Final security audit and penetration testing

---

## Compliance & Audit

### Regulatory Compliance

**FIPS-140-2** (Already Compliant via RKE2):
- ✅ Cryptographic modules certified
- ✅ Secrets encryption at rest
- ✅ TLS 1.3 for data in transit

**GDPR Considerations**:
- ✅ Data encryption (in transit and at rest)
- ✅ Access controls (RBAC, network policies)
- ✅ Audit logging (ElasticSearch)
- ⚠️ Need to implement: Data deletion workflows, consent management

**HIPAA Considerations** (for healthcare deployments):
- ✅ Access controls
- ✅ Encryption
- ✅ Audit trails
- ⚠️ Need to implement: Business Associate Agreements, PHI data classification

**SOC 2 Type II**:
- ✅ Logical access controls
- ✅ Encryption
- ✅ Monitoring and logging
- ⚠️ Need to implement: Formal change management, regular access reviews

### Security Audit Checklist

#### Infrastructure Security

- [ ] All nodes are RKE2 FIPS-140-2 certified
- [ ] Kata Containers enabled for workload isolation
- [ ] Intel TDX/SGX enabled on all compute nodes
- [ ] NVIDIA GPU confidential computing mode enabled
- [ ] Linkerd service mesh deployed and configured
- [ ] Network policies in place for all namespaces
- [ ] TLS 1.3 enforced for all external connections
- [ ] Let's Encrypt certificates auto-renewed

#### Application Security

- [ ] No secrets hardcoded in values files
- [ ] All secrets stored in Kubernetes Secrets or Vault
- [ ] Bittensor JWT authentication enabled
- [ ] Rate limiting configured on all public endpoints
- [ ] Security contexts applied to all pods
- [ ] No pods running as root
- [ ] Image signature verification enabled
- [ ] Database passwords rotated regularly

#### Data Security

- [ ] PostgreSQL TLS encryption enabled
- [ ] Object storage communication over HTTPS
- [ ] Per-tenant data store isolation in PROD
- [ ] Backup encryption enabled (Longhorn)
- [ ] Data retention policies documented
- [ ] Data deletion workflows implemented

#### Monitoring & Audit

- [ ] Kubernetes audit logging enabled
- [ ] Audit logs sent to ElasticSearch
- [ ] Prometheus metrics collecting security events
- [ ] Grafana dashboards for security monitoring
- [ ] Alerting configured for security incidents
- [ ] Log retention meets compliance requirements (typically 1-7 years)

#### Compliance

- [ ] TEE attestation logs retained
- [ ] Access logs available for audit
- [ ] Incident response plan documented
- [ ] Security training completed by all operators
- [ ] Third-party security audit completed (annually)
- [ ] Penetration testing performed (annually)

### Continuous Monitoring

**Security Metrics to Track**:

1. **Authentication Failures**: Track failed authentication attempts
   ```promql
   rate(http_requests_total{status="401"}[5m])
   ```

2. **Rate Limit Violations**: Monitor rate limiting effectiveness
   ```promql
   rate(nginx_ingress_controller_requests{status="429"}[5m])
   ```

3. **Unauthorized Access Attempts**: Track 403 responses
   ```promql
   rate(http_requests_total{status="403"}[5m])
   ```

4. **TEE Attestation Failures**: Monitor confidential computing violations
   ```promql
   tee_attestation_failures_total
   ```

5. **Network Policy Violations**: Track blocked connections
   ```promql
   rate(network_policy_dropped_packets_total[5m])
   ```

6. **Certificate Expiration**: Alert before certificates expire
   ```promql
   (cert_manager_certificate_expiration_timestamp_seconds - time()) < (7 * 24 * 3600)
   ```

**Alerting Rules**:

```yaml
groups:
- name: security_alerts
  rules:
  - alert: HighAuthFailureRate
    expr: rate(http_requests_total{status="401"}[5m]) > 10
    for: 5m
    annotations:
      summary: "High authentication failure rate detected"
      
  - alert: TEEAttestationFailure
    expr: tee_attestation_failures_total > 0
    for: 1m
    annotations:
      summary: "TEE attestation failed for workload"
      severity: critical
      
  - alert: UnauthorizedCrossTenantAccess
    expr: rate(network_policy_dropped_packets_total{direction="ingress"}[5m]) > 50
    for: 5m
    annotations:
      summary: "Possible cross-tenant access attempt detected"
```

---

## Conclusion

This security analysis demonstrates that while the NeMo Microservices Helm Chart provides a solid foundation, deploying it within the KubeTEE Subnet infrastructure offers **significant security advantages**:

### Key Strengths

1. **Enterprise-Grade Infrastructure**: FIPS-140-2 certified RKE2 Kubernetes provides a secure foundation
2. **Confidential Computing**: Intel TDX/SGX and NVIDIA GPU TEE offer hardware-based security beyond software controls
3. **Service Mesh Security**: Linkerd mTLS automatically encrypts all service-to-service communication
4. **Multi-Tenant Isolation**: Namespace-based isolation with Rancher RBAC management

### Critical Action Items

To meet NVIDIA's security requirements and industry best practices:

1. **Implement Rate Limiting** (NVIDIA requirement)
2. **Deploy Authentication Proxy** (NVIDIA requirement)
3. **Remove Hardcoded Secrets** (Critical vulnerability)
4. **Enable Tenant Isolation** (Multi-tenancy security)
5. **Configure Network Policies** (Defense in depth)

### Unique KubeTEE Advantages

The KubeTEE Subnet infrastructure provides security capabilities that go **beyond** NVIDIA's base requirements:

- ✅ Hardware-encrypted memory (Intel TDX)
- ✅ GPU memory encryption (NVIDIA Confidential Computing)
- ✅ Attestation-based trust (Confidential Containers)
- ✅ Zero-trust service mesh (Linkerd)
- ✅ Encrypted storage with replication (Longhorn)
- ✅ Comprehensive audit trails (ElasticSearch)

By implementing the recommendations in this document, the KubeTEE Subnet will provide a **production-ready, enterprise-grade, compliant AI-as-a-Service platform** with security exceeding industry standards.

---

**Document Version**: 1.0  
**Last Updated**: October 7, 2025  
**Next Review Date**: January 7, 2026  
**Owner**: KubeTEE Security Team  
**Approvers**: Architecture Review Board

---

## References

- [NVIDIA NeMo Microservices Security Guidelines](https://docs.nvidia.com/nemo/microservices/latest/set-up/security.html)
- [RKE2 Security Hardening Guide](https://docs.rke2.io/security/hardening_guide)
- [NIST SP 800-190: Application Container Security Guide](https://csrc.nist.gov/publications/detail/sp/800-190/final)
- [CIS Kubernetes Benchmark](https://www.cisecurity.org/benchmark/kubernetes)
- [Linkerd Security Documentation](https://linkerd.io/2/features/automatic-mtls/)
- [Confidential Containers Documentation](https://confidentialcontainers.org/)
- [OWASP Kubernetes Security Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Kubernetes_Security_Cheat_Sheet.html)

