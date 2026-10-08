# Nemotron-3-Nano-Omni Multimodal API — any-to-any input on `llm.kubetee.ai`

Endpoint reference for **Nemotron-3-Nano-Omni**
(`nvidia/nemotron-3-nano-omni-30b-a3b-reasoning`) — the any-to-any model:
text, image, video, and audio **in**, text **out**, with reasoning traces and
tool calling. One StatefulSet (1 replica) on a single H100 SXM5 80GB under Kata
TDX CC (Intel TDX + NVIDIA CC) on the `na-us-michigan-97` production cluster,
behind a per-model in-guest HAProxy that terminates mTLS on `:8443`; the
east-west Gateway does L4/SNI TLS Passthrough
([East-West Attested mTLS](./EAST-WEST-ATTESTED-MTLS.md)).

It **consumes** audio and video but only **emits text** (and tool calls) — not
a TTS, image, or video *generation* model. For generation endpoints see
[H3 Video Generation API](./H3-VIDEO-GENERATION-API.md) and the LiteLLM
surfaces table in the [README](../README.md#litellm-gateway--the-multi-service-front-door).

| | |
|---|---|
| Served model name | `nvidia/nemotron-3-nano-omni-30b-a3b-reasoning` (the single entry on `GET /v1/models`) |
| Architecture | Mamba2-Transformer hybrid MoE — Nemotron 3 Nano LLM (30B A3B) + **CRADIO v4-H** vision encoder + **Parakeet** speech encoder (31B A3B, ~3B active) |
| Context | **256k** model maximum ([model card](https://build.nvidia.com/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning/modelcard)); our serve runs `max_model_len 131072` → **128k effective** |
| Weights | BF16 (61.5 GB) / FP8 (32.8 GB) / NVFP4 (20.9 GB), released 2026-04-28 on HF + NGC |
| Serving container | NVIDIA NIM `nvcr.io/nim/nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:1.7.0-variant`, digest-pinned |
| Hardware | **1× H100 80GB** — the point of the 3B-active design: a multimodal understanding-and-reasoning serve on one card |
| LiteLLM route | `model: nvidia/nemotron-3-nano-omni` → `POST https://llm.kubetee.ai/v1/chat/completions` |
| SNI base URL | `https://nemotron-omni.na-us-michigan-97.inference.kubetee.ai` (house mTLS client pair required) |
| Live since | 2026-10-08 (deployment, contract smoke, and load battery same day) |

## Access paths

**1. LiteLLM gateway — `https://llm.kubetee.ai`** (Bearer auth): standard
OpenAI `POST /v1/chat/completions` with
`model: nvidia/nemotron-3-nano-omni`. Virtual keys, budgets, and spend
tracking are enforced on this route as on every gateway route. The gateway's
`hosted_vllm` provider normalizes one field on the way out — see
[Reasoning field](#reasoning-field-name-is-non-standard).

**2. East-west SNI —
`https://nemotron-omni.na-us-michigan-97.inference.kubetee.ai`** — for
authorized integrators holding the house mTLS client pair. Same API directly
against the NIM (no gateway normalization — use the raw contract below).
Probe-exempt (no client cert): `GET /v1/health/ready` and `/health/live`;
everything else requires the client certificate.

---

## How to use it (runnable quick-start)

All examples use the LiteLLM gateway (`https://llm.kubetee.ai`) with a virtual
key — the shortest path. Swap in the SNI base URL + `--cacert/--cert/--key` for
the direct path.

### Text chat

```bash
curl -s https://llm.kubetee.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-<virtual-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/nemotron-3-nano-omni",
    "messages": [{"role": "user", "content": "Explain TDX attestation in two sentences."}],
    "max_tokens": 512
  }'
```

### Image input (base64 data URI)

```bash
IMG=$(base64 < photo.png | tr -d '\n')
curl -s https://llm.kubetee.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-<virtual-key>" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"nvidia/nemotron-3-nano-omni\",
    \"messages\": [{\"role\": \"user\", \"content\": [
      {\"type\": \"text\", \"text\": \"Describe this image.\"},
      {\"type\": \"image_url\", \"image_url\": {\"url\": \"data:image/png;base64,$IMG\"}}
    ]}],
    \"max_tokens\": 256,
    \"chat_template_kwargs\": {\"enable_thinking\": false}
  }"
```

A live `https://` URL also works in `image_url.url` (fetched server-side):

```json
{"type": "image_url", "image_url": {"url": "https://example.com/cat.jpg"}}
```

### Audio input (raw base64 WAV — no data: URI prefix!)

```bash
AUDIO=$(base64 < clip.wav | tr -d '\n')
curl -s https://llm.kubetee.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-<virtual-key>" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"nvidia/nemotron-3-nano-omni\",
    \"messages\": [{\"role\": \"user\", \"content\": [
      {\"type\": \"text\", \"text\": \"Transcribe what you hear.\"},
      {\"type\": \"input_audio\", \"input_audio\": {\"data\": \"$AUDIO\", \"format\": \"wav\"}}
    ]}],
    \"max_tokens\": 512,
    \"chat_template_kwargs\": {\"enable_thinking\": false}
  }"
```

### Video input (data URI MP4)

```bash
VID=$(base64 < clip.mp4 | tr -d '\n')
curl -s https://llm.kubetee.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-<virtual-key>" \
  -H "Content-Type: application/json" \
  -d "{
    \"model\": \"nvidia/nemotron-3-nano-omni\",
    \"messages\": [{\"role\": \"user\", \"content\": [
      {\"type\": \"text\", \"text\": \"Summarize this video.\"},
      {\"type\": \"video_url\", \"video_url\": {\"url\": \"data:video/mp4;base64,$VID\"}}
    ]}],
    \"max_tokens\": 256,
    \"chat_template_kwargs\": {\"enable_thinking\": false}
  }"
```

> Big payload? Inline base64 breaks the shell past ~2 MB ("argument list too
> long"). Put the request JSON in a file and use `curl -d @payload.json`.

### Mixed modalities in one turn

Combine parts freely — image + audio + text, multiple images, multiple audio
clips, all in one `content` array (all verified).

### Streaming (SSE)

Add `"stream": true` — deltas arrive as `data:` events terminated by
`data: [DONE]`. With thinking on you get `reasoning` deltas first, then
`content` deltas; with `"enable_thinking": false`, `content` deltas only.

```bash
curl -sN https://llm.kubetee.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-<virtual-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/nemotron-3-nano-omni",
    "messages": [{"role": "user", "content": "Count from 1 to 10."}],
    "max_tokens": 128, "stream": true,
    "chat_template_kwargs": {"enable_thinking": false}
  }'
```

### Tool calling

```bash
curl -s https://llm.kubetee.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-<virtual-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/nemotron-3-nano-omni",
    "messages": [{"role": "user", "content": "What is the weather in Paris?"}],
    "max_tokens": 128,
    "chat_template_kwargs": {"enable_thinking": false},
    "tools": [{"type": "function", "function": {
      "name": "get_weather",
      "description": "Get current weather for a city",
      "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]}
    }}],
    "tool_choice": "auto"
  }'
```

The response contains `message.tool_calls`; send the result back as a
`role: "tool"` message to get the final natural-language answer.

### JSON-schema output (structured extraction)

```bash
curl -s https://llm.kubetee.ai/v1/chat/completions \
  -H "Authorization: Bearer sk-<virtual-key>" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "nvidia/nemotron-3-nano-omni",
    "messages": [{"role": "user", "content": "Extract: Ada was born in 1815 in London."}],
    "max_tokens": 128,
    "chat_template_kwargs": {"enable_thinking": false},
    "response_format": {"type": "json_schema", "json_schema": {
      "name": "person", "strict": true,
      "schema": {"type": "object", "properties": {"name": {"type": "string"}, "year": {"type": "integer"}}, "required": ["name", "year"], "additionalProperties": false}
    }}
  }'
```

Returns schema-conformant JSON (e.g. `{"name": "Ada", "year": 1815}`).

### Python (OpenAI SDK)

```python
from openai import OpenAI

client = OpenAI(base_url="https://llm.kubetee.ai/v1", api_key="sk-<virtual-key>")

resp = client.chat.completions.create(
    model="nvidia/nemotron-3-nano-omni",
    messages=[{"role": "user", "content": "Describe this image."}],
    max_tokens=256,
    extra_body={"chat_template_kwargs": {"enable_thinking": False}},
)
print(resp.choices[0].message.content)
# With thinking ON, the trace is resp.choices[0].message.reasoning_content
# (and provider_specific_fields["reasoning"]).
```

`extra_body` is how any extra parameters (`chat_template_kwargs`,
`response_format`, `tools`) pass through the SDK.

---

## Request contract (verified 2026-10-08)

`POST /v1/chat/completions` — OpenAI JSON. Multimodal input is a `content`
**array** of typed parts:

| Part | Shape | Notes |
|------|-------|-------|
| Text | `{"type":"text","text":"…"}` (or a plain string) | |
| Image | `{"type":"image_url","image_url":{"url":"data:image/png;base64,…"}}` | `data:` URI **or** a live `https://` URL — fetched server-side (some CDNs reject the fetcher's bot policy, e.g. Wikimedia returns 403; raw.githubusercontent works). PNG/JPEG RGB (the card's image formats) |
| Audio | `{"type":"input_audio","input_audio":{"data":"<b64>","format":"wav"}}` | ⚠️ `data` is **RAW base64** — **no** `data:audio/…;base64,` prefix (that prefix belongs on `image_url` / `video_url` URLs only). A URI-prefixed value fails `400 Incorrect padding`. Card formats: **wav/mp3**, up to **1 hour**, ≥8 kHz. The card's examples use `{"type":"audio_url","audio_url":{"url":"…"}}` instead — both shapes reach the same encoder |
| Video | `{"type":"video_url","video_url":{"url":"data:video/mp4;base64,…"}}` | Real H.264/AAC MP4 (ffmpeg-muxed) — uncompressed AVI and hand-rolled MP4 muxes are rejected (`Could not open video stream`). Card cap: **2 minutes** (sampled ~1 fps / 128 frames at 1080p; 2 fps / 256 frames at 720p). Practical ceiling is the 4 GiB in-guest `/dev/shm`; an 18 MB clip is fine. Pull the clip's audio track with `mm_processor_kwargs: {"use_audio_in_video": true}` |

Multi-image, multi-audio, and mixed-modality turns are all verified (two
images in one turn → *"2 images: 1st is red, 2nd is blue"*; two audio clips →
*"You received two short tones."*).

**Outputs** (model card): text only, with JSON structured output,
chain-of-thought reasoning, tool calling, and **word-level timestamps for
transcription**. Input language is **English only**.

For large payloads POST the JSON from a file (`curl -d @payload.json`) — a
base64 video inlined in argv hits "argument list too long" past ~2 MB.

### Reasoning field name is NON-STANDARD

The thinking trace comes back as **`message.reasoning`** (Nemotron/vLLM style)
— **not** `reasoning_content`.

- **Direct SNI callers must read `message.reasoning`.**
- **LiteLLM callers** get the industry-standard `reasoning_content` (the
  `hosted_vllm` transformer remaps it) plus the original preserved in
  `provider_specific_fields.reasoning`.

Toggle with `chat_template_kwargs: {"enable_thinking": true|false}` (extra body
parameter; LiteLLM passes it through). Reasoning is **on when the key is
omitted**. Splitting the trace into its own field depends on the server's
reasoning parser (`--reasoning-parser nemotron_v3`, baked into our NIM);
without a parser the trace stays inline in `content`.

### Budget the thinking trace — cap it, or turn it off

With `enable_thinking` on (the default), a small `max_tokens` is consumed by
the trace: `content: null`, `finish_reason: "length"`, and the caller sees "no
answer". Three ways out:

1. **Cap the trace** — the model card's Budget-Controlled Reasoning
   (`reasoning_budget` + `grace_period` inside `chat_template_kwargs`; their
   sum goes in `thinking_token_budget`):
   ```json
   "max_tokens": 20480,
   "thinking_token_budget": 17408,
   "chat_template_kwargs": {"enable_thinking": true, "reasoning_budget": 16384}
   ```
2. **Leave room** — the card recommends `max_tokens` **≥20480** for multimodal
   reasoning, up to 131072 for hard math/programming.
3. **Turn it off** — `chat_template_kwargs: {"enable_thinking": false}` for
   short deterministic answers (the fast path used by the modality probes).

### Recommended sampling (model card)

| Mode | `temperature` | `top_p` | `top_k` | `max_tokens` | `reasoning_budget` | `grace_period` |
|---|---|---|---|---|---|---|
| Thinking (long-doc / multimodal reasoning) | 0.6 | 0.95 | — | 20480 | 16384 | 1024 |
| Instruct (general + ASR transcription) | 0.2 | — | 1 | 1024 | — | — |

### Streaming (`stream: true`)

Standard OpenAI SSE, verified in both modes, terminated by `data: [DONE]`:

| `enable_thinking` | Deltas observed |
|---|---|
| `true` | `reasoning` deltas first, then `content` deltas |
| `false` | `content` deltas only |

### Structured output

`response_format: {"type":"json_schema","json_schema":{…,"strict":true}}` is
honored — a `{"name": string, "year": integer}` extraction returned
`{"name": "Ada", "year": 1815}` and parsed clean.

### Tool calling

`tools` + `tool_choice: "auto"` emits `tool_calls` (32/32 requests across the
load battery), and the `role: "tool"` result round-trip produces a
natural-language answer.

### Long context

The model card gives a **256k** maximum context; our serve runs
`max_model_len 131072`, so **128k is the effective limit on this endpoint**
(`max_tokens` caps only the completion, and prompt + completion together
cannot exceed `max_model_len`). Verified: a needle at ~10.5k prompt tokens
(~32k characters, 60% depth) retrieved correctly in 24 s.

---

## Performance — 1× H100 load envelope (2026-10-08)

All through `llm.kubetee.ai`, mixed modalities (text / image / audio / tools,
one quarter each), `enable_thinking: false`, **0% errors and 100% tool-call
emission at every level**:

| Concurrency | Wall | Throughput | Latency p50 / p99 / max | Aggregate decode |
|---|---|---|---|---|
| 32 | 5.5 s | 5.85 req/s | 4.99 s / 5.47 s / 5.47 s | 110.6 tok/s |
| 64 | 5.9 s | 10.80 req/s | 5.36 s / 5.89 s / 5.89 s | 202.3 tok/s |
| 128 | 4.6 s | 27.59 req/s | 3.84 s / 4.53 s / 4.58 s | 506.2 tok/s |
| 8 × 1024-token sustained decode | 13.4 s | — | 12.6 s | 375.9 tok/s aggregate (**~50 tok/s per stream**) |

Latency is **uniform under load** (p50 ≈ p99) and did not degrade up to 128
concurrent requests — it improved, because short completions batch more
efficiently on the ~3B-active MoE at higher concurrency. No saturation point
was found below 128 in-flight on the single card. This is measured evidence
for the README's [Serving Configurations](../README.md#serving-configurations--every-service-requires-fast-inference)
claim: the confidential boundary is a security property, not a performance tax.

**Coverage.** Every input modality (text / image / audio / video), multi-image,
multi-audio, and mixed turns, remote-URL fetch, streaming in both thinking
modes, JSON-schema output, tool calling + round-trip, and a ~10.5k-token
needle are smoke-verified; concurrency verified to 128 in-flight. **Not yet
stress-tested:** multi-hour soak and failover, the 128k ceiling under load, and
exotic codecs beyond WAV audio / H.264 MP4 video / PNG-JPEG images.

---

## Gotchas (hit while building this)

1. **`input_audio.data` is raw base64** — the `data:` URI prefix that works on
   `image_url` / `video_url` URLs makes audio fail with `400 Incorrect padding`.
2. **Reasoning lives in `message.reasoning`**, not `reasoning_content` — unless
   you call through LiteLLM, which remaps it.
3. **Thinking eats small token budgets** — cap it with `reasoning_budget` /
   `thinking_token_budget`, send `enable_thinking: false`, or give
   `max_tokens` ≥20480 (the card's multimodal-reasoning recommendation).
4. **Video is narrow and short** — ffmpeg-muxed H.264/AAC MP4 only, and the
   model card caps clips at **2 minutes** (~128 frames at 1080p).
5. **Remote media URLs are fetched server-side** and are subject to the remote
   host's bot policy (Wikimedia 403s the fetcher — that is not a NIM limit).
6. **First-boot NGC manifest flake** — one `ManifestDownloadError` on the very
   first container start, self-healed on the second start; the engine then
   builds and persists on the NIM cache volume.
7. **No raw PDFs** — the API takes images, not PDF documents; render each page
   to PNG and send it as `image_url` (the card ships a `pdf_vlm_chat.py`
   recipe for exactly this).
8. **Audio inside a video is opt-in** — control it with
   `mm_processor_kwargs: {"use_audio_in_video": true|false}`.

## Follow-ups / flags

- **Commercial use is granted** per the NVIDIA model card (2026-04-28: "This
  model is available for commercial use", governed by the **NVIDIA Open Model
  Agreement**; the hosted trial API is separately under the NVIDIA API Trial
  Terms). The remaining gate is narrower than it was: confirm decentralized
  **miner** serving and sublicensing fit the Open Model Agreement's
  redistribution terms (plus the NGC terms on the NIM container) before
  exposing this model to miners.
- **Second replica** on the other H100 is deferred (1 replica by directive,
  2026-10-08) — the load envelope above is single-card by design.
