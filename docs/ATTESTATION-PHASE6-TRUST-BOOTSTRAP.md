# Phase 6 trust bootstrap — design note (delivery status updated 2026-11-27)

**Status:** §3.1 (per-boot bound key) and §3.2 (registry anti-rollback) are
**delivered** — see their inline delivery notes. §3.3–§3.5 remain design
proposals. This note is not the live contract;
[ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) §3.4 is (v2 binding).

**Scope:** Phase 6 of the zero-operator-trust program — **per-boot in-guest TLS
key generation with the public key bound into the attestation evidence** — and
the trust story that follows from it. This note surveys the candidate upstream
approaches, records which properties we want, and proposes a composed design.
It supersedes no live behavior.

---

## 1. The bar

Phase 6 must bootstrap trust with **no new hidden trust anchor**:

1. Every trust decision is verifiable **offline** against hardware endorsement
   chains (AMD ARK→ASK→VCEK / Intel PCK chain) and **publicly auditable
   reference values** — a buyer re-running verification must not need to trust
   a KubeTEE-operated CA, key, or service at verification time.
2. The serving key is **generated in the guest at each boot**, never persisted,
   and its public half is bound into hardware-signed evidence
   (`REPORTDATA = H(pubkey ‖ nonce)`).
3. The wire format is **standardized** where an interoperable standard exists,
   so third-party verifiers can consume our evidence without KubeTEE-specific
   code.
4. The registry lifecycle is **anti-rollback**: revoking a record must
   retroactively invalidate it, even to a verifier served stale registry bytes.

Anything that introduces a long-lived signing key held outside a TEE (an
"admissions CA", "policy key", "coordinator root") fails bar 1 unless the
relying party verifies it themselves end-to-end and the alternative is worse.

## 2. Candidate survey (2026-11-27)

| Approach | Trust anchor | Key binding | Standardized? | Verdict |
|---|---|---|---|---|
| **Interoperable RA-TLS** (Gramine RA-TLS, RATS-TLS, Open Enclave Attested TLS; CCC Attestation SIG harmonization) | Hardware chain + reference values only — cert is self-signed and its signature is *irrelevant* | `REPORTDATA = SHA-384(pubkey ‖ nonce)`, evidence in a standard X.509 extension (`TEEAttestation`, DICE AA v1.1-tagged CBOR, IANA-registered tags) | Yes — the SIG merged the OIDs/evidence format across implementations | **Adopt the binding + encoding only.** The in-handshake delivery is the "early attestation" class hit by the EarlyAttestationBleed CVEs (§3.1) — deliver post-handshake instead |
| **Contrast** (Edgeless Systems) | User-verified Coordinator CA (CLI carries embedded reference values); manifest signed by a workload-owner key | Mesh certs carry attestation-derived X.509 extensions; `REPORTDATA = hash(pubkey ‖ nonce)` | No (project-specific) | **Borrow the manifest history design.** Note its early attestation carries `GHSA-m2qg-wrxv-h898` / `CVE-2026-100833` (9.6, policy no-match-accepts) and `CVE-2026-100835` (machine-ID); do not import its delivery or policy-generation paths |
| **Veraison + CoRIM/EAR** (Linux Foundation) | Provisioned endorsements/reference values (CoRIM/CoMID — standard, signed, supply-chain-shaped) | n/a (it is a verifier, not a channel) | Yes — IETF RATS (RFC 9334, EAR, AR4SI, CoRIM) | **Adopt the reference-value and result formats** |
| **Certifier Framework** (CCC) | **Domain policy key** — the Certifier Service holds the private half and signs Admissions Certificates | Attestation names the auth key; short-lived X.509 admissions cert thereafter | No (SDSI/SPKI policy language, project-specific) | **Pass** — centralizes trust in a KubeTEE-held key (fails bar 1); useful ideas (proof artifacts) already covered by our signed registry + offline verification |
| Status quo (X-KubeTEE-Proof + signed registry) | Hardware chain + Ed25519-signed registry | Per-request statement signed by a KBS-released key — **not yet per-boot generated** | No (KubeTEE-specific headers) | Baseline to harden |

Support notes: RA-TLS implementations are uneven across TEEs — Gramine's
`ra-tls` is SGX-oriented; RATS-TLS (Intel) covers TDX and heterogeneous
handshakes; the interoperable format defines TDX and SEV-SNP evidence shapes
(bare-metal SNP reports kept raw for offline verification — matching our
existing discipline). Veraison's SEV-SNP scheme is **work in progress** (PSA,
CCA, TPM, DICE implemented), so we adopt its *formats*, not its verifier, for
SNP. Verify each support claim against the deployed release before use — per
`coco-upstream-standards.mdc`, source snippets and blogs are hypotheses.

## 3. Proposed composition

Phase 6 = **per-boot bound key (post-handshake) + Contrast-style registry
chain + CoRIM/EAR-shaped records + instance-identity pinning + fail-closed
verifier invariants**:

### 3.1 Per-boot key, hardware binding — delivered POST-handshake (the core)

At guest boot, the attesting component generates an ephemeral keypair in TEE
memory (never written to disk, never released by KBS), and mints evidence whose
AMD `report_data` (64 bytes at `0x0050..0x0090`) is
`SHA-384(tag ‖ framed(pkix) ‖ framed(nonce) ‖ framed(context)) ‖ 16 zero bytes` —
the `ReportDataForKeyWithContext` length-framed transcript (tag is the raw
ASCII `kubetee.attestation.v2/ReportDataForKeyWithContext`; each input is
`u64-be length ‖ bytes`; nonce mandatory on freshness-critical flows). Evidence
is served on our existing **post-handshake
application-layer** route (`/kubetee/evidence`, `X-KubeTEE-Proof` /
`X-KubeTEE-Nonce` response headers) — **not** inside the TLS handshake.

**Delivery note (2026-11-27): LIVE as `kubetee.attestation.v2`.** The binding
above is the deployed wire format (`bindings.report_data_statement` carries the
JCS statement; `key_possession` proves ECDSA P-256 possession of the bound key
over `report_data`). Normative contract + conformance:
[ATTESTATION-SPEC-v1.md §3.4](./ATTESTATION-SPEC-v1.md). The KBS-released
serving identity is still the TLS terminator (the residual — see §4); the v2
bound key is a dedicated per-boot evidence key, distinct from the TLS serving
key.

**Delivery is deliberately NOT the RA-TLS in-cert pattern.** The
EarlyAttestationBleed line of research (§6) shows early/in-handshake
attestation is the class that keeps failing critically (`CVE-2026-92701`,
`CVE-2026-92702`, `CVE-2026-100833`, all ≥9.0), and its architectural flaws
stand regardless of implementation: evidence is exposed to a client the server
has not authenticated (harvested for replay/relay), handshake-time evidence
covers boot claims only, re-attestation needs post-handshake anyway, and it
adds handshake latency/failure modes. Cocos AI migrated to post-handshake
attestation; the remaining early-attestation implementations are documented as
still vulnerable in `draft-intra-handshake-fail`. We keep the RA-TLS
**evidence encoding** (`TEEAttestation`-shaped, standard tags) as an optional
interchange format — binding and encoding are standard; delivery stays in the
application layer where our nonce/rate-limit tiers already live.

Consequences:
- The KBS-released identity key retires from the serving path. What we
  currently document as *"does not prove a new hardware keypair is generated
  for every boot"* (CLIENT-FACING-ATTESTATION.md "what this does not prove")
  becomes proven.
- Post-handshake delivery keeps runtime claims and re-attestation possible
  (`X-KubeTEE-Nonce` mint-per-request already demonstrates this).
- Binding hygiene: domain-separate the report-data derivation (the
  `ReportDataForKeyWithContext` length-framed transcript pattern —
  `SHA-384(tag ‖ framed(pubkey) ‖ framed(nonce) ‖ framed(context))`) so no two
  distinct (pubkey, nonce, context) triples share a preimage. For the
  connection-binding upgrade see §3.4 (RFC 9261 exported authenticators).

### 3.2 Registry anti-rollback (Contrast's manifest history)

Our signed registry gains a **transition-hash chain**: each published record
set is signed over `content_hash ‖ previous_transition_hash`, history
content-addressed by SHA-256. Verifiers that have ever seen revision *N*
reject anything served below it — closing the "serve an old registry to a
revoked record's verifier" hole that `any-active-record` alone leaves open.
(Contrast applies the same construction to its Coordinator manifest history
and rotates its mesh CA on every update so pre-update workloads can't talk to
updated ones — worth mirroring for east-west
([EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md)) key rotation.)

**Delivery note (2026-11-27): code complete and enforced; pending the first
chained publish.** The construction is implemented three times, byte-identical
and KAT-pinned across languages: publisher
(`kubetee-website/scripts/build-tee-measurements-registry.py`), reference
verifier (`kubetee-attestation-verifier/src/registry.rs`), and the gateway
matcher (`litellm/.../kubetee_attestation.py`). Anti-rollback is now **enforced**
in both the verifier's `verify()` entry point (chain + monotonic `--min-revision`
floor, fail-closed on a chain-less registry) and the gateway matcher
(`_load_registry`, downgrade-aware: a chain-less doc is tolerated until the
first chained revision is accepted, then rejected as rollback;
`KUBETEE_REGISTRY_MIN_REVISION` pins the floor across restarts). The one
remaining step is the **first chained publish** (version 2 with `chain`) using
the offline signing key — runbook:
`kubetee-website/scripts/PUBLISH-REGISTRY-CHAINED.md`. Until that lands, the
published registry is `version 1, chain ABSENT` and the enforce paths treat it
as the pre-Phase-6 doc.

### 3.3 Reference values and results as standards (Veraison-shaped)

- Publish reference measurements as **CoRIM/CoMID** alongside (not instead of)
  `tee-measurements-registry.json`, so supply-chain tooling can consume them.
  **Format-maturity caveat (2026-11):** `draft-ietf-rats-corim` is under a
  65-item static-review cycle ([#638](https://github.com/ietf-rats-wg/draft-ietf-rats-corim/issues/638)),
  with open normative gaps that hit exactly our planned use — `S-01`: seven
  `measurement-values-map` codepoints have **no comparison algorithm** (entries
  can never match), `S-06`: multiple ACS matches vs exactly-one assumption in
  Reference Value processing, `C-03`: authority semantics contradiction, `D-10`:
  float-equality with no encoding rule, plus 12 pseudocode defects
  (`P-01`…`P-12`). Twin-not-replacement is therefore deliberate: the JSON
  registry stays contract-of-record until those close and a published CoRIM
  matcher exists (see the Veraison gap below); our CoRIM twin must not be the
  only verifiable form.
- Express appraisal output in **EAR / AR4SI** trust-vector terms (the Trustee
  v0.23.0 `appraisal` object already carries EAR draft-04 claims — keep them
  as the appraisal layer and align the verifier's result envelope).

**WG-document map (ietf-rats-wg, 2026-11) — each KubeTEE artifact has a
standards-track home; adopt the mature ones now:**

| KubeTEE artifact | WG document | Status / note |
|---|---|---|
| Evidence envelope | **EAT — RFC 9711** + **CMW — RFC 9999** | Published RFCs — adopt now (alongside the JSON) |
| Per-boot key binding (§3.1, §3.4 M2) | [`draft-ietf-rats-pkix-key-attestation`](https://github.com/ietf-rats-wg/key-attestation) | WG std-track; ASN.1 + **Go reference verifier** + sample data — buyers can verify with a non-KubeTEE verifier |
| Freshness + registry head (§3.2 anti-rollback) | [`draft-ietf-rats-epoch-marker`](https://github.com/ietf-rats-wg/draft-ietf-rats-epoch-marker) | Epoch Bell = shared freshness without local clocks; pin the registry head hash in an epoch marker |
| Registry discovery/retrieval | [`draft-ietf-rats-coserv`](https://github.com/ietf-rats-wg/draft-ietf-rats-coserv) | `.well-known` + CBOR query + semver; semver ordering is weaker than our signed hash chain — compose, don't replace |
| Node location claims (per-region records) | [`geographicresult`](https://github.com/ietf-rats-wg/geographicresult) | Individual draft — AR4SI-shaped geographic results for sayGM buyers |
| Multi-verifier story (bar 1) | [`draft-ietf-rats-multi-verifier`](https://github.com/ietf-rats-wg/draft-ietf-rats-multi-verifier) | Align terminology for buyer-side independent verification |
| Flow naming (passport/background) | [`draft-ietf-rats-reference-interaction-models`](https://github.com/ietf-rats-wg/draft-ietf-rats-reference-interaction-models) | Name our flow per the taxonomy (fresh per-request evidence, RP-side appraisal) |

### 3.4 Relay/diversion resistance (empirically exploited — the EAT taxonomy)

Fresh evidence + a bound key authenticates *a guest*, not *this machine*. The
EarlyAttestationTschüss (EAT) analysis (§6) formally defines three failure
classes, each with published CVEs at 9.1: **cross-connection relay** (evidence
bound to no connection-unique shared secret — `CVE-2026-33697` class),
**diversion** (no binding between Evidence and the host's Silicon identity
key → messages diverted to a different host that mints valid evidence —
`CVE-2026-100835`), and **relay under evidence-key compromise**. Mitigations,
strongest first:

- **Silicon-LTK binding (EAT's model M2 — the real fix):** proof of possession
  of **both** the evidence key and the host's hardware identity key (the
  TPM/HSM-held LTK) in the exchange. EAT's ProVerif results: this defeats
  diversion where all single-key binders fail. Carry this into the east-west
  mesh handshake ([EAST-WEST-ATTESTED-MTLS.md](./EAST-WEST-ATTESTED-MTLS.md))
  and Phase 6's per-boot key exchange — the per-boot key alone (binder-8 class)
  does **not** survive the compound-authentication goal.
- **Connection binding via RFC 9261 exported authenticators** for the
  buyer-facing evidence (the SEAT "standard attestation" direction): bind the
  evidence to the *traffic secrets of that connection* (EAT binder 9, the only
  mechanism reaching their binding level 2). This upgrades the current
  `X-KubeTEE-Proof` keyset statement — which is an application-layer binder —
  to a TLS-connection binder. Note EAT's argument that level 3 is likely
  unattainable for in-handshake delivery; post-handshake over exported
  authenticators is the supported route.
- **Machine-identity pinning (PIID / AMD `CHIP_ID`) — workaround only, with an
  explicit trust caveat.** EAT §9.2 refutes Edgeless's "out of TCB" claim
  precisely because *the vendor* supplied the pinned machine IDs with no
  verifiable provenance. Our registry version is strictly more transparent
  (signed, hash-chained, per-node records with documented custody), but the
  same refutation applies unless buyers can **independently assess ownership,
  custody, and compromise status**: publishing IDs does not by itself remove
  KubeTEE from the TCB. Record the open questions EAT names — who supplies the
  IDs, how a relying party verifies they belong to the intended machines, and
  how they are retired on hardware replacement/decommission/compromise (our
  answer: registry revocation + the §3.2 transition chain) — in the contract's
  threat model section.

### 3.5 Verifier fail-closed invariants (regression-tested, CVE-shaped)

EarlyAttestationBleed's three CVEs are failure *shapes* our verifier's hot
paths share. Each gets an explicit reject-on-missing fixture in
`kubetee-attestation-verifier` (and the gateway matcher):
1. **Expectation absent** (CVE-2026-92701): `report_data` compared against an
   expected value that was never set → accepted. Fixture: missing keyset/nonce
   expectation MUST reject.
2. **Zero-length input skips the check** (CVE-2026-92702): empty
   `report_data`/expected value bypasses comparison (fail-open lower API).
   Fixture: zero-length on either side MUST reject.
3. **No-match-accepts** (CVE-2026-100833): authorization predicate returns
   allow when no policy entry applies. Fixture: registry matcher and
   `policy.rego` image gate MUST reject when zero records/rules match — never
   fall through.

## 4. What this does not prove (additions to the client-facing list)

- Per-boot key rotation proves key freshness per boot; a *live* guest can still
  be compromised after measurement — runtime policy and KBS release gates
  remain the containment story (unchanged).
- A relayed handshake from a genuine co-located guest passes unless instance
  identity is pinned (§3.4).
- CoRIM/EAR adoption is format-level; it does not import Veraison's (currently
  SNP-incomplete) appraisal as our verification path.
- **Machine-identity pinning reduces the attack surface from "any machine in
  the world" to "the pinned machines", but KubeTEE remains in the TCB for
  machine custody** unless the buyer independently assesses ownership,
  protection, and compromise status of those machines (EAT §9.2's refutation
  applies to any vendor-supplied allowlist, including ours). The registry makes
  the allowlist auditable; it does not make the underlying custody
  independently verifiable.
- Post-handshake evidence is **receiver-confidential only after the client
  authenticates** — unlike early attestation it is not exposed pre-auth, but
  the endpoint should document that evidence minted for an unauthenticated
  caller reveals boot-time claim *shapes* (the information-disclosure half of
  the EarlyAttestationBleed analysis); rate-limited tiers bound the harvest.

## 5. Rollout shape (proposal only — no dates)

1. Land the §3.5 fail-closed fixtures in `kubetee-attestation-verifier` and the
   gateway matcher first (no protocol change — hardens the current verifier
   against the CVE-shaped regressions).
2. Extend the backend/gateway evidence envelope with the RA-TLS `TEEAttestation`
   encoding (alongside the existing JSON — additive, both verifiable), still
   delivered post-handshake.
3. Land per-boot keygen + `REPORTDATA` binding in the shim/image line (GitHub
   Actions build per `gh-only-image-builds.mdc`).
4. Upgrade connection binding: RFC 9261 exported-authenticator evidence
   (binder-9 class) for the buyer-facing tier, and Silicon-LTK dual
   proof-of-possession (EAT model M2) for the east-west mesh handshake (§3.4).
5. Publish record v(next) with transition-hash chaining + CoRIM twin +
   instance-identity fields (PIID / AMD `CHIP_ID`) + machine-custody
   provenance; verifier learns the chain + machine checks (§3.4 caveat
   applies).
6. Update
   [ATTESTATION-SPEC-v1.md](./ATTESTATION-SPEC-v1.md) /
   [CLIENT-FACING-ATTESTATION.md](./CLIENT-FACING-ATTESTATION.md) as a
   versioned contract revision with the retired "what this does not prove"
   lines removed and §4's additions added.

## 6. Sources (surveyed 2026-11-27 — verify before citing in the contract)

- **EarlyAttestationBleed (the delivery-decision driver):** Sardar & Bu,
  [paper](https://www.researchgate.net/publication/414529199_EarlyAttestationBleed_Three_Critical-severity_Vulnerabilities_of_CVSS_90_in_Confidential_Computing);
  [IETF UFMRG announcement](https://mailarchive.ietf.org/arch/msg/ufmrg/ZQKdp07P4UeTushAC1q9eBBtp0s/)
  (2026-09-21);
  [`draft-intra-handshake-fail`](https://datatracker.ietf.org/doc/draft-intra-handshake-fail/)
  (quotes the paper's §7 architectural flaws);
  [LPC'26 aTLS BoF slides](https://lpc.events/event/20/contributions/2640/attachments/2049/4690/20261005_LPC_2026_BoF.pdf)
  and
  [IETF-127 hackathon slides](https://datatracker.ietf.org/meeting/127/materials/slides-127-hackathon-sessd-earlyattestationbleed-and-earlyattestationtschuss-00.pdf).
  Advisories: Cocos AI [GHSA-4px3-wj2x-xx47](https://github.com/ultravioletrs/cocos/security/advisories/GHSA-4px3-wj2x-xx47) /
  [GHSA-4r6g-mp48-j2rw](https://github.com/ultravioletrs/cocos/security/advisories/GHSA-4r6g-mp48-j2rw);
  Contrast [GHSA-m2qg-wrxv-h898](https://github.com/edgelesssys/contrast/security/advisories/GHSA-m2qg-wrxv-h898).
  CVEs: [CVE-2026-92701](https://www.cve.org/CVERecord?id=CVE-2026-92701),
  [CVE-2026-92702](https://www.cve.org/CVERecord?id=CVE-2026-92702),
  [CVE-2026-100833](https://www.cve.org/CVERecord?id=CVE-2026-100833),
  plus the companion `CVE-2026-33697` (weak binder → relay, 7.5) and
  `CVE-2026-100835` (machine-ID check missing, 9.1).
- **EarlyAttestationTschüss (EAT) — the binding/pinning decision driver:**
  Sardar & Bu, [paper](https://www.researchgate.net/publication/417343302_EarlyAttestationTschuss_EAT)
  (preprint v0.1, 2026-11-08 — 9 CVEs at 9.1 across Privasys/Cocos/CCC-ref/
  Contrast/Meta Private Processing; formal three-class taxonomy: cross-connection
  relay, diversion, relay-under-`privEK`-compromise; M2 Silicon-LTK
  mitigation; PIID/`CHIP_ID` allowlist workaround + the §9.2 vendor-in-TCB
  refutation; RFC 9261 exported authenticators as the post-handshake fix).
  Related: [`draft-intra-handshake-fail`](https://datatracker.ietf.org/doc/draft-intra-handshake-fail/)
  §1.6/§9 (Contrast `CVE-2026-33697`, `CVE-2026-100835`; the v1.16.0 pinning
  workaround keeps Edgeless in the TCB),
  [`draft-sardar-rats-sec-cons`](https://datatracker.ietf.org/doc/draft-sardar-rats-sec-cons),
  [IETF-127 hackathon slides](https://datatracker.ietf.org/meeting/127/materials/slides-127-hackathon-sessd-earlyattestationbleed-and-earlyattestationtschuss-00.pdf).
  **Contested status (cited honestly):** preprint; the `draft-fossati-tls-attestation`
  author reserved judgment pending ProVerif artifact release
  ([coverage](https://freenode.net/article/formal-analysis-early-attestation-broken-spec-author-says-prove-it)).
  The CVEs and the draft withdrawal are fact; the impossibility claims are
  under review.

- **IETF RATS WG documents (the standards-track homes in §3.3's map):**
  [`draft-ietf-rats-pkix-key-attestation`](https://github.com/ietf-rats-wg/key-attestation)
  (attested-key evidence encoding — ASN.1 + Go reference verifier + sample
  data),
  [`draft-ietf-rats-epoch-marker`](https://github.com/ietf-rats-wg/draft-ietf-rats-epoch-marker)
  (Epoch Bell shared freshness),
  [`draft-ietf-rats-coserv`](https://github.com/ietf-rats-wg/draft-ietf-rats-coserv)
  (endorsement/reference-value retrieval),
  [`geographicresult`](https://github.com/ietf-rats-wg/geographicresult)
  (geographic attestation results),
  [`draft-ietf-rats-multi-verifier`](https://github.com/ietf-rats-wg/draft-ietf-rats-multi-verifier),
  [`draft-ietf-rats-reference-interaction-models`](https://github.com/ietf-rats-wg/draft-ietf-rats-reference-interaction-models);
  published formats **RFC 9711 (EAT)** and **RFC 9999 (CMW)**.
- Interoperable RA-TLS: CCC Attestation SIG `interoperable-ra-tls` project;
  [Unifying Remote Attestation Protocol Implementations](https://confidentialcomputing.io/2023/03/06/unifying-remote-attestation-protocol-implementations/)
  (OIDs/evidence format aligned to DICE Attestation Architecture v1.1);
  [Gramine `ra-tls`](https://github.com/gramineproject/gramine/blob/master/tools/sgx/ra-tls/ra_tls.h);
  [RATS-TLS](https://github.com/intel/confidential-computing-zoo/blob/main/documents/readthedoc/docs/source/Solutions/rats-tls/index.md)
  (heterogeneous TDX↔SGX handshakes).
- Contrast: [service mesh / PKI](https://docs.edgeless.systems/contrast/architecture/components/service-mesh),
  [Coordinator + manifest history](https://docs.edgeless.systems/contrast/architecture/components/coordinator),
  [attestation](https://docs.edgeless.systems/contrast/architecture/attestation/overview),
  [manifest update / signed transitions](https://docs.edgeless.systems/contrast/howto/manifest-update),
  [relay-attack advisory](https://docs.edgeless.systems/contrast/security).
- Veraison: [services overview](https://www.veraison-project.org/book/services/overview.html),
  [provisioning (CoRIM/CoMID)](https://www.veraison-project.org/book/provisioning.html),
  [attestation results (EAR/AR4SI)](https://www.veraison-project.org/book/attestation_result.html).
- Certifier Framework (evaluated, passed):
  [repo](https://github.com/ccc-certifier-framework/certifier-framework-for-confidential-computing),
  [VMware overview](https://blogs.vmware.com/opensource/2022/12/08/confidential-computing-part-3-the-certifier-framework/).
