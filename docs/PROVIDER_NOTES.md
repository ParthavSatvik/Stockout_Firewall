> Historical design notes. Current implementation/status is in the root-level reports. Do not treat this earlier document as fresh verification.

# Provider notes (from official docs, read 2026-10-16)

Everything here comes from a read of the vendor documentation pages during the Cowork session.
No call was made to any provider (no keys, and outbound access to package registries was blocked).
Items marked **VERIFY** were not stated on the page that was readable and must be confirmed against
the live docs or a real key before they are relied on.

## Sarvam AI — https://docs.sarvam.ai

### Speech-to-text (REST)
- `POST /speech-to-text` — REST is documented for audio under ~30 s. Longer audio: Batch API (up to 2 h) or WebSocket streaming.
- Base URL not stated on the page read. **VERIFY**: expected `https://api.sarvam.ai`.
- Auth header: `api-subscription-key: <key>`.
- Multipart fields: `file` (required), `model` (`saaras:v4` default, or `saaras:v3`), `mode` (only for `saaras:v3`: `transcribe | translate | verbatim | translit | codemix`), `language_code` (BCP-47, or `unknown` to auto-detect), `with_timestamps`, `input_audio_codec` (PCM only), `keyterms` (JSON array, ≤50 terms, ≤64 chars, `saaras:v4` only).
- Language codes include `kn-IN`, `hi-IN`, `en-IN`, `ta-IN`, `te-IN`, `ml-IN`, `mr-IN`, `gu-IN`, `bn-IN`, `pa-IN`, `od-IN` and others (24 values incl. `unknown`).
- Response: `request_id`, `transcript`, `language_code`, `language_probability` (only when language is auto-detected), optional `timestamps`.
- Formats: WAV, MP3, AAC, AIFF, OGG, OPUS, FLAC, MP4/M4A, AMR, WMA, WebM, PCM (16 kHz only). 16 kHz recommended; multi-channel merged to mono.
- Index page also lists `Saarika v2.5` (recognition). Which model suits code-mixed Kannada/Hindi/English kirana speech is **VERIFY** — try `saaras:v3` with `mode=codemix` and `saaras:v4` with a real key and compare.

### Chat completions
- Bearer auth (`Authorization: Bearer <key>`) per the API reference page. Base URL/path not stated. **VERIFY**: expected `https://api.sarvam.ai/v1/chat/completions`.
- Conflict between pages: the API reference lists only `sarvam-m`; the docs index calls `Sarvam-M` and `Sarvam-30B` deprecated and names `Sarvam-105B` as flagship. **Make the model name an env var (`SARVAM_LLM_MODEL`) and check the model list with a real key.**
- Request body is messages-based (`messages`, `model`, `temperature`, `max_tokens`, `reasoning_effort`, `seed`, `stop`, …).
- Pricing is in INR on the pricing page; rates, free credits and rate limits were not readable. Billing is org-level with a shared credit balance. Handle 429 and 503 with retry/backoff. **VERIFY** pricing, free credits, rate limits and data-use terms before enabling.

## Paytm Payment Gateway — https://www.paytmpayments.com/docs

### Initiate Transaction
- Staging: `POST https://securestage.paytmpayments.com/theia/api/v1/initiateTransaction?mid={mid}&orderId={orderId}`
- Production: `https://secure.paytmpayments.com/theia/api/v1/initiateTransaction?...` (seen only in commented sample code).
- Body: `{ "body": { requestType: "Payment", mid, websiteName, orderId, callbackUrl, txnAmount: {value: "1.00", currency: "INR"}, userInfo: {custId} }, "head": { signature, [version, channelId, requestTimestamp] } }`.
- `head.signature` is a checksum over the `body` object serialised to a JSON string (Node `JSON.stringify`, PHP `json_encode(..., JSON_UNESCAPED_SLASHES)`, Python `json.dumps`). Serialisation must be byte-identical to what is sent.
- Response returns `txnToken`, used by the JS checkout. **VERIFY** the exact `resultInfo.resultStatus` values from the full API reference.

### Checksum
- Docs say the checksum uses SHA-256 and AES-128. The detailed algorithm page was **not readable** in this session. Use Paytm's official checksum library or re-read the "Checksum Logic" page; do not hand-roll from memory without checking it against Paytm's test vectors.

### Transaction status / webhooks
- The Transaction Status API (`/v3/order/status`) and webhook/callback docs were **not readable**. **VERIFY** the URL, request signature, and `TXN_SUCCESS / TXN_FAILURE / PENDING` semantics. Always confirm payment status server-side; never trust the browser redirect.
- Real merchant onboarding, escrow, split settlement and payouts are out of scope for the prototype (see master prompt).

## Google Maps Routes API v2 — https://developers.google.com/maps/documentation/routes

- Methods: `ComputeRoutes`, `ComputeRouteMatrix`. REST paths are under `https://routes.googleapis.com/` (**VERIFY** exact paths: `/directions/v2:computeRoutes`, `/distanceMatrix/v2:computeRouteMatrix`).
- A response field mask is mandatory (`X-Goog-FieldMask` header). API key header `X-Goog-Api-Key` (**VERIFY**).
- Matrix request: `origins[]`, `destinations[]`, `travelMode`, `routingPreference` (`routingPreference` only for `DRIVE` / `TWO_WHEELER`).
- Matrix response elements: `originIndex`, `destinationIndex`, `status`, `condition`, `distanceMeters`, `duration`. Include `status` in the field mask or errors look like OK.
- Pricing/quota not read. **VERIFY** before enabling. Without a key, use the estimated-distance fallback and label it as an estimate (not a road route).
