#!/usr/bin/env python3
"""Build the CoRIM (Concise Reference Integrity Manifest) twin of the signed
TDX measurement record, for Trustee RVPS ingestion.

Produces the standard `kubetee.tee-reference-values/1` CoRIM that a Verifier's
RVPS ingests so a custom appraisal policy can compare a TDX quote's launch
registers (MRTD / MRCONFIGID / RTMR0-3) against KubeTEE's approved reference
state. This is the CoRIM twin of the human/JSON record published at
`/.well-known/tee-measurements-sglang.tdx.json`.

Design constraints (all verified against the DEPLOYED Trustee v0.23.0 source,
`confidential-containers/trustee@564a3ba51eaedd4734e88e1883a905dd780ee45b`,
specifically `rvps/src/extractors/corim/` + `rvps/Cargo.toml`'s pinned
`veraison/corim-rs@8d297d0`):

* The RVPS CoRIM extractor maps EACH reference value to a URI built from
  `class.vendor` / `class.model` / `mkey` / `mval.name` / `mval.serial_number`
  joined by `/`, with `/digests` appended when `mval.digests` is used (and the
  value stored as a JSON list of hex digests). So this manifest sets
  vendor=`kubetee`, model=<role-model>, mkey=<register> to yield URIs of the
  form `kubetee/<role-model>/<register>/digests`.
* Those URIs are DELIBERATELY namespaced. The stock `default_cpu` attestation
  policy queries BARE ids (`mr_td`, `rtmr_1`, `rtmr_2`, `xfam`, ...), so this
  CoRIM is inert to live appraisal (it cannot accidentally affirm an arbitrary
  guest). A KubeTEE appraisal policy opts in explicitly by querying these
  namespaced URIs -- see `ATTESTATION-REFERENCE-MEASURES-SGLANG.md` for the
  Rego snippet.
* The extractor does NOT verify CoRIM signatures (Trustee v0.23.0 note), so the
  detached Ed25519 signature here is a PUBLICATION integrity artifact (same key
  + key_id as the JSON record), not a Trustee-enforced input. It is emitted as
  a sidecar for offline verification and supply-chain provenance.
* Encoding is canonical CBOR (RFC 8949 4.2.1 key sorting) with the integer-key
  maps corim-rs expects for CBOR (`is_human_readable == false`):
    - CoRIM            = CBOR tag 501 -> {0: id(tstr), 1: [CoMID]}
    - CoMID            = CBOR tag 506 -> <CBOR-in-BYTES of the CoMID map below>
    - CoMID map        = {1: tag-identity, 4: triples}
    - tag-identity     = {0: tag-id(tstr), 1: tag-version(uint)}
    - triples          = {0: [reference-triple]}
    - reference-triple = [environment-map, [measurement-map, ...]]
    - environment-map  = {0: class-map}
    - class-map        = {1: vendor(tstr), 2: model(tstr)}
    - measurement-map  = {0: mkey(tstr), 1: {2: [digest]}}
    - digest           = [alg(int), val(bytes)]   SHA-384 alg = 7
  The tag-506 CoMID MUST be a CBOR **byte string** (CBOR-in-bytes) because
  corim-rs's `ConciseMidTag` deserializes it that way; an inline-map CoMID is
  rejected `Semantic(None, "CoRIM tag must be a byte string")` (verified against
  the live v0.23.0 RVPS, 2026-11-25). This matches upstream
  `rvps/src/extractors/corim/unsigned-example-corim.cbor`.

Usage (the private key never enters argv or Git):
    python3 scripts/build-tee-reference-values-corim.py \
        --key /path/to/signing-key.pem --out-dir kubetee-website/public/.well-known

Outputs (byte-reproducible -- canonical CBOR + fixed inputs):
    tee-reference-values.cbor          the unsigned CoRIM (tag 501)
    tee-reference-values.cbor.sig      detached Ed25519 over the CBOR bytes
    tee-reference-values.cbor.sha256   hex digest of the CBOR bytes
    tee-reference-values.json          human-readable twin + derived RV URIs
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import subprocess
import sys
from pathlib import Path

try:
    import cbor2
    from cbor2 import CBORTag
except ImportError:  # pragma: no cover
    sys.exit("needs cbor2:  python3 -m pip install --user cbor2")

# --- the approved reference state (byte-exact from the signed JSON record) ---
# Captured 2026-11-25T01:26:30Z from the booted TDX guest (the Kimi-K3.1-Pro
# `nim-terminator` backend on the lu-luxembourg-133 node-pinned manifest) via
# the in-guest evidence route
# GET .../kubetee/evidence over strict mTLS. Cross-validated: (1) the quote's
# report_data == sha256(epoch statement)||0^32 MATCH; (2) the CCEL event log
# (22 records) replayed reproduces all four RTMRs EXACTLY. See the JSON record's
# `measurements._capture` for the full provenance.
REFERENCE_VALUES = {
    "mr_td": "382d7bb61e152a5cc6eb22922a4dc9d33025211e24ec199fe38d6233c39cd86bf633e3c4f6e62393cf7ce6da91069ca0",
    "rtmr_0": "14f01287aefb3ac196451163aa8cf68cc1635083b24eb317256288815a5b48bbe7cdf2e2395ebf0474b3e528d2004014",
    "rtmr_1": "97fa8ac275f656b876de7c68709608bfe6ace60b58a3b8fb6e990c15bd8711ce8807ed86956f39b62afb9a9daee80227",
    "rtmr_2": "77903a48ffcc66809d3f01a9853186ac08bc0081d06e4d05a0e0307450188e08d9f21b9c77e6747df0a90e65d7e3bff9",
    "rtmr_3": "000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000",
    "mr_config_id": "0484a58e5927efd31bf871c74bcc9f1768f4335bb92340176989b3c5b320f9341d772b9e3e9c4fe4d824613cc19e6e0b",
}

SHA384_ALG = 7  # corim-rs `HashAlgorithm::Sha384` -> to_u8() == 7
KEY_ID = "kubetee-measurements-2026-11-25"

# Environment class naming: yields RV URIs `kubetee/<MODEL>/<register>/digests`.
# The class identifies the MODEL (Kimi-K3.1-Pro), never a deployment/node suffix.
VENDOR = "kubetee"
MODEL = "sglang-kimi-k3-1-pro"
COMID_TAG_ID = "kubetee-sglang-kimi-k3-1-pro-tdx-reference-values"
COMID_TAG_VERSION = 1
CORIM_ID = "kubetee-tee-reference-values-sglang-tdx-20261125"

OPENSSL = "/opt/homebrew/bin/openssl"


def derived_uri(register: str) -> str:
    """Re-implements the Trustee v0.23.0 CoRIM extractor's URI derivation."""
    return f"{VENDOR}/{MODEL}/{register}/digests"


def build_corim() -> CBORTag:
    claims = []
    for register, hexval in REFERENCE_VALUES.items():
        digest_bytes = bytes.fromhex(hexval)
        if len(digest_bytes) != 48:
            raise SystemExit(f"{register}: expected 48-byte SHA-384, got {len(digest_bytes)}")
        claims.append({0: register, 1: {2: [[SHA384_ALG, digest_bytes]]}})

    # ONE reference-triple = one compound reference state for one target
    # environment (all six registers must match together -- RATS "compound
    # reference value", confidential-containers/trustee#350).
    environment = {0: {1: VENDOR, 2: MODEL}}  # class-map: vendor + model
    reference_triple = [environment, claims]
    triples = {0: [reference_triple]}  # reference-triples
    comid_map = {
        1: {0: COMID_TAG_ID, 1: COMID_TAG_VERSION},  # tag-identity
        4: triples,  # triples
    }
    # Trustee's corim-rs `ConciseMidTag` deserializes the payload of CBOR tag 506
    # as a CBOR **byte string** (CBOR-in-bytes), NOT an inline map. Verified
    # against the live Trustee v0.23.0 RVPS (2026-11-25): an inline-map CoMID is
    # rejected `Semantic(None, "CoRIM tag must be a byte string")`; a byte-string
    # CoMID is accepted. Matches upstream
    # `rvps/src/extractors/corim/unsigned-example-corim.cbor` (`<tag 506> -> bstr`).
    comid = CBORTag(506, cbor2.dumps(comid_map, canonical=True))
    corim = CBORTag(501, {0: CORIM_ID, 1: [comid]})  # id + tags
    return corim


def verify_extraction(raw: bytes) -> list[dict]:
    """Round-trip the CBOR and re-derive the RV URIs + hex values exactly as the
    Trustee extractor would, so a layout mistake cannot ship silently."""
    dec = cbor2.loads(raw)
    assert dec.tag == 501, f"outer tag {dec.tag} != 501"
    out = []
    for tag in dec.value[1]:
        assert tag.tag == 506, f"CoMID tag {tag.tag} != 506"
        # The CoMID is a CBOR byte string (corim-rs ConciseMidTag); decode it.
        comid = cbor2.loads(tag.value)
        assert set(comid.keys()) == {1, 4}, f"unexpected CoMID keys {comid.keys()}"
        assert comid[1][0] == COMID_TAG_ID and comid[1][1] == COMID_TAG_VERSION
        for env, ref_claims in comid[4][0]:
            base = []
            cls = env.get(0)
            if cls is not None:
                if 1 in cls:
                    base.append(cls[1])
                if 2 in cls:
                    base.append(cls[2])
            for claim in ref_claims:
                comps = list(base)
                mkey = claim.get(0)
                if isinstance(mkey, str):
                    comps.append(mkey)
                elif isinstance(mkey, int):
                    comps.append(f"claim{mkey}")
                mval = claim[1]
                if 11 in mval:
                    comps.append(mval[11])
                if 8 in mval:
                    comps.append(mval[8])
                if 2 in mval:
                    uri = "/".join(comps + ["digests"])
                    hexes = [d[1].hex() for d in mval[2]]
                    out.append({"uri": uri, "value": hexes})
    return out


def sign_detached(cbor_bytes: bytes, key: Path) -> bytes:
    """Ed25519 detached signature over the CBOR bytes. The private key is passed
    only via `-inkey <file>`; it is never placed in argv or output."""
    derived = subprocess.check_output(
        [OPENSSL, "pkey", "-in", str(key), "-pubout", "-outform", "DER"]
    )
    expected_pub = (key.parent / "signing-public.der").read_bytes()
    if derived != expected_pub:
        raise SystemExit("offline key does not match its intended public identity")
    in_path = key.parent / ".tee-ref-values.cbor.tmp"
    sig_path = key.parent / ".tee-ref-values.sig.tmp"
    try:
        # `pkeyutl -rawin` needs a seekable input file (not a pipe/stdin).
        in_path.write_bytes(cbor_bytes)
        subprocess.run(
            [OPENSSL, "pkeyutl", "-sign", "-rawin", "-inkey", str(key),
             "-in", str(in_path), "-out", str(sig_path)],
            check=True,
        )
        return sig_path.read_bytes()
    finally:
        in_path.unlink(missing_ok=True)
        sig_path.unlink(missing_ok=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", type=Path, required=True,
                    help="offline Ed25519 private key (PEM)")
    ap.add_argument("--out-dir", type=Path, required=True)
    a = ap.parse_args()
    key = a.key.expanduser().resolve(strict=True)
    a.out_dir.mkdir(parents=True, exist_ok=True)

    corim = build_corim()
    raw = cbor2.dumps(corim, canonical=True)

    derived = verify_extraction(raw)
    expected = {derived_uri(r): [v] for r, v in REFERENCE_VALUES.items()}
    got = {d["uri"]: d["value"] for d in derived}
    if got != expected:
        raise SystemExit(f"extractor round-trip mismatch:\n got={got}\n want={expected}")

    cbor_path = a.out_dir / "tee-reference-values.cbor"
    cbor_path.write_bytes(raw)
    (a.out_dir / "tee-reference-values.cbor.sha256").write_text(
        hashlib.sha256(raw).hexdigest() + "  tee-reference-values.cbor\n"
    )

    sig = sign_detached(raw, key)
    (a.out_dir / "tee-reference-values.cbor.sig").write_bytes(sig)

    twin = {
        "schema": "kubetee.tee-reference-values/1",
        "version": 1,
        "status": "active",
        "key_id": KEY_ID,
        "corim": {
            "encoding": "application/corim-cbor+diagnostic; canonical CBOR (RFC 8949)",
            "outer_tag": 501,
            "comid_tag": 506,
            "digest_alg": "sha384",
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
            "signature": {
                "alg": "ed25519",
                "key_id": KEY_ID,
                "sig": base64.b64encode(sig).decode(),
            },
            "signature_note": (
                "Detached Ed25519 over the raw CBOR bytes (sign offline with key_id "
                + KEY_ID
                + " via scripts/build-tee-reference-values-corim.py --key <offline-key.pem>; "
                "the private half never enters the cluster or Git). Trustee v0.23.0's RVPS "
                "CoRIM extractor does not verify CoRIM signatures, so this is a "
                "publication integrity artifact (same key/key_id as "
                "tee-measurements-sglang.tdx.json), not a Trustee-enforced input."
            ),
        },
        "target_environment": {"class": {"vendor": VENDOR, "model": MODEL}},
        "reference_values": [
            {"uri": derived_uri(r), "register": r, "value": v} for r, v in REFERENCE_VALUES.items()
        ],
        "rvps": {
            "ingest": (
                "RVPS RegisterReferenceValue with a JSON Message "
                '{"version":"0.1.0","type":"corim","payload":"<base64-STANDARD CBOR>"} '
                "(Trustee v0.23.0 rvps/src/lib.rs Message + extractors/corim)."
            ),
            "note": (
                "Namespaced URIs are inert to the stock default_cpu attestation "
                "policy (which queries bare mr_td/rtmr_1/rtmr_2/xfam). Only a "
                "policy that explicitly queries these kubetee/<model>/<register>/"
                "digests URIs appraises against them."
            ),
        },
    }
    (a.out_dir / "tee-reference-values.json").write_text(
        json.dumps(twin, indent=2) + "\n"
    )

    print("cbor        =", cbor_path, "sha256=", twin["corim"]["sha256"], "bytes=", len(raw))
    print("signature   =", a.out_dir / "tee-reference-values.cbor.sig", "len=", len(sig))
    for d in derived:
        print("rv          =", d["uri"], "->", d["value"])


if __name__ == "__main__":
    main()
