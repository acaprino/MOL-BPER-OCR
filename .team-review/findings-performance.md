# Performance Review — image-payload / encoding path (`extraction/`)

Follow-up dimension recommended by the Phase 4c completeness critic (the one gap with zero coverage). Scope: `imaging.py`, the image sends in `pipeline.py`, the encoding/base64 path in `vlm_client.py`, plus the raw edge-agent entry. Done inline (narrow scope), evidence-based — sizes measured on the real test screenshots.

## Measured baseline (real screenshots, current PNG path)

| Screen | raw size | after `normalize_image` | content crop | PNG (current) | JPEG q90 | base64 sent (PNG → JPEG) |
|---|---|---|---|---|---|---|
| screen 1 | 847×678 | 847×678 (**not resized**) | 678×583 | 86 KB | 45 KB | 114 KB → 60 KB (1.9×) |
| screen 2 | 850×679 | 850×679 (**not resized**) | 680×584 | 87 KB | 47 KB | 116 KB → 62 KB (1.9×) |
| screen 4 | 846×677 | 846×677 (**not resized**) | 677×582 | 138 KB | 75 KB | 185 KB → 99 KB (1.9×) |

Header (anchor) crops are ~21-34 KB PNG. `PNG optimize=True` saves only ~3% — not worth it.

## Two corrections to the critic's gap note (05-risks P1/P3)

Honest reporting first, because two claims in the gap note don't survive measurement:

1. **"Multi-MB per call" — false for the current dataset.** The test screenshots are ~847px wide, so `normalize_image` (which caps the long side at 1800px, `imaging.py:12-16`) never resizes them; payloads are 86-185 KB, not multi-MB. The multi-MB figure only applies to a hypothetical high-DPI capture that actually reaches 1800px.
2. **"Directly inflates the token bill" — false.** Both OpenAI GPT-4o and Gemini price image input by **dimensions** (512px/768px tiles), not by byte size. PNG-vs-JPEG changes upload payload, bandwidth, latency, and request-size headroom — **not token count or USD token cost.** Any performance fix here must be sold on latency/bandwidth, not on the cost telemetry the POC tracks.

## Findings

### PERF-01 — Raw edge-agent path sends un-normalized, full-resolution captures (token-cost lever) — Medium
`extract_from_image` (`pipeline.py:104`) deliberately skips `normalize_image` (edge-agent pre-processes, CLAUDE.md constraint #12), but nothing clamps incoming dimensions. Because image **tokens are dimension-driven**, a 3840×2160 monitor capture sent raw is tiled into many more 512/768px tiles than a 1800px-capped image → materially higher token cost per call *and* a multi-MB base64 payload — on the anchor, main, and every retry. This is the genuine cost finding on this path (the CSV-review's ARCH-12/ME-14 flagged the same seam for robustness; here it is quantified as a token-cost driver). A cheap long-side clamp at the seam (or asserting the edge-agent already caps it) bounds both cost and payload without touching the CLI path.
Confidence: 85

### PERF-02 — Lossless PNG encoding is ~1.9× the JPEG payload — Low (bandwidth/latency only; accuracy risk on fix)
`img_to_png_bytes` (`imaging.py:31-34`) always encodes lossless PNG; `call_vlm` base64s it (`vlm_client.py:132`) on every call (anchor + main + up to 2 retries = up to 4 image uploads/screen). Measured ~1.9× larger than JPEG q90. **Impact is upload bandwidth + latency + staying under provider request-size limits — not token cost** (see correction #2). For the current 847px images the absolute saving is modest (~50-120 KB/call, far from any limit); it matters more for high-DPI captures (interacts with PERF-01).
**Do not blind-switch to JPEG.** The prompts demand character-exact fidelity (`prompts.py:9-11`), and JPEG artifacts on small text carry a real (if small at q90) OCR-accuracy risk. Recommendation: make the encoding **configurable** (env `VLM_IMAGE_FORMAT`, default PNG to preserve current accuracy; allow JPEG q90-92 for bandwidth-constrained / high-volume runs), and A/B the accuracy delta on the ground-truth set before changing the default. Not a slam-dunk — an opt-in lever with a measurement gate.
Confidence: 90 (payload delta), 60 (that JPEG is worth adopting by default)

### PERF-03 — Overlapping retry crops re-tokenize the same pixels — Low / informational
`RETRY_AREAS` overlap each other and the main `CONTENT_CROP` (HEADER `0.00-0.35` vs BODY `0.25-0.75` vs FOOTER `0.65-1.00`, `config.py:63-67`), so a screen that retries BODY+FOOTER re-sends and re-tokenizes overlapping bands already paid for on the main pass. This — not encoding — is where per-screen image-token cost actually grows. Inherent to the multi-pass design; the levers are tighter retry crops or fewer retries (which trade against accuracy). Documented so the correct mental model is on record: **image token cost scales with how many crops of what dimensions you send, not with the encoding format.**
Confidence: 85

### PERF-04 — `normalize_image` is shrink-only and unconditional — Low / mostly a non-issue
Confirmed shrink-only (`imaging.py:15`, `if scale < 1.0`): sub-1800px captures pass through at native resolution (all three test images). The critic's P3 framed this as an accuracy gap, but **upscaling adds no information and providers re-tile anyway**, so not upscaling is correct — this is close to a non-finding. Minor real note: contrast(1.05) + UnsharpMask(percent=120) are applied unconditionally (`imaging.py:17-18`), mildly over-processing already-sharp screenshots; negligible on cost, a possible small accuracy factor worth an A/B but out of scope for performance.
Confidence: 80

## Bottom line

No high-severity performance defect. The one worth acting on is **PERF-01** (clamp/verify dimensions on the raw edge-agent path — the only real token-cost lever, and it also bounds payload). **PERF-02** (PNG→JPEG) is a legitimate latency/bandwidth lever but must be opt-in behind a measurement gate, not a default flip, given the OCR-fidelity requirement — and it does **not** reduce the token cost the POC measures. PERF-03/04 are informational, and they correct the mental model: on this pipeline, image cost is driven by crop dimensions and count, not encoding.
