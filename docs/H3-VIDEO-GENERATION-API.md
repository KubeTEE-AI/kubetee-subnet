# MiniMax H3 on KubeTEE — Video Generation API Reference

**Model:** `minimax/h3` (MiniMax-H3, joint video+audio DiT — every output ships with a generated soundtrack)
**Endpoint:** `https://llm.kubetee.ai/v1/videos` (async jobs)
**Billing:** **$0.08 per requested second**, charged at submission

**The model's grammar is documented by MiniMax** — generation modes (text-to-video, first/last-frame image-to-video, reference generation), input requirements and limits, supported formats, and prompt-writing craft (camera directives like `[pan]`/`[zoom]`, reference labeling): **[platform.minimax.io/docs/guides/video-generation](https://platform.minimax.io/docs/guides/video-generation)**. The model is the same weights; that guide applies in full.

This page documents **only how our serving differs**.

---

## 1. Differences at a glance

| Official `api.minimax.io` | KubeTEE `llm.kubetee.ai` |
|---|---|
| `POST /v2/video_generation` — JSON body with `content[]` + `role` labels | `POST /v1/videos` — **multipart form fields** (see §2) |
| Poll `task_id`; download from `content.url` | Poll job `id` via `GET /v1/videos/{id}`; download via `GET /v1/videos/{id}/content` |
| Input by URL only | URL **or** base64 data URL **or** direct multipart upload |
| Output 768P / 2K | **768 short-edge only** — no 2K; other short edges are **rejected**, never silently coerced |
| Duration 4–15 s, integer values only | 4–15 s, **fractional allowed**; frame count snaps up to the 17n+5 grid (≤ +16 frames ≈ 0.67 s extra, **not billed**) |
| List / cancel / delete task endpoints | **Not offered** — `GET /v1/videos` (list) returns 404 by design; artifacts expire on a **1 h in-memory TTL** (the TTL is the deletion) |
| Synchronous single-shot generation | **Not offered through the gateway** — the serving stack's raw-MP4 `/v1/videos/sync` exists but is not routed; async create → poll → download only |
| H3-Context-IR prompt-enhancement tasks | Not offered |
| 2K regeneration from a 768P source | Not offered |
| — | Opt-in long-video extensions: 30 s (`long_video_mode=full`), 300 s ref2va continuation |

Also fixed by the serving configuration: **24 fps** output; the six named aspect ratios (`21:9`, `16:9`, `4:3`, `1:1`, `3:4`, `9:16`).

## 2. Mapping official examples to our fields

| Official `content[]` item | Our multipart field |
|---|---|
| `{"type": "text"}` | `prompt` |
| `{"type": "image_url", "role": "first_frame"}` / `"last_frame"` | `image_reference` — ordered list: element 0 = first frame, element 1 = last frame |
| `{"type": "image_url", "role": "reference_image"}` | `image_reference` list entries |
| `{"type": "video_url", "role": "reference_video"}` | `video_reference` list entries |
| Audio references | `audio_reference` list entries |
| `duration`, `resolution`, `ratio` | `seconds` (or `extra_params={"duration": …}`), `aspect_ratio`; `resolution` has no equivalent — fixed 768 |

Each field accepts `{"image_url": "https://…"}` / `{"video_url": …}` / `{"audio_url": …}` or a base64 data URL; a single raw file part can be sent as `input_reference` (single reference only, not combinable with the others). The task (`t2va`/`fl2va`/`ref2va`) is auto-detected from the inputs; override with `extra_params={"task": …}` — mismatches (e.g. `t2va` with references attached) are rejected. All reference limits (≤9 images / ≤3 videos / ≤3 audio / 12 total, per-asset size caps, dimension and duration windows) are enforced exactly as in the official guide, with explicit errors.

## 3. One worked example

```bash
curl -sS -X POST "https://llm.kubetee.ai/v1/videos" \
  -H "Authorization: Bearer $KEY" \
  -F 'model=minimax/h3' \
  -F 'prompt=A drone shot over foggy pine forest at dawn, [pan] slowly left.' \
  -F 'extra_params={"task":"t2va","duration":6.0,"aspect_ratio":"16:9"}'
```

Poll `GET /v1/videos/{id}` until `completed` (`queued` → `in_progress` → `completed` / `failed`), then download `GET /v1/videos/{id}/content` **within the hour**: artifacts live only in the serving pod's encrypted memory (nothing is written to host disk — a confidential-computing property of the deployment), and a 404 always means "unknown or expired ID".

## 4. Billing

$0.08 per **requested** second, charged at submission. The frame-grid snap-up (§1) delivers slightly more video than requested at no extra charge. Known caveat (being fixed): a job that passes gateway validation but fails backend-side validation after acceptance can still be billed; failures raised inside the gateway are never billed.

---

*Advanced paths (latent-mask editing of a source video/audio, 300 s continuations at scale) exist in the serving stack and can be enabled per key — talk to us if you need them.*
