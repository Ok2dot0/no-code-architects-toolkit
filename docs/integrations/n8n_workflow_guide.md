**n8n Workflow Guide**

This guide shows how to call the toolkit's media endpoints from an `n8n` workflow using the `HTTP Request` node. It contains example node settings and sample JSON payloads for common flows: composing media with custom audio track assignment, concatenating videos with a transition SFX assigned to its own audio track, probing an asset, and merging multiple audio tracks into a single loudness-normalized main track.

**Prerequisites**
- **API URL:** `http://localhost:8080` (adjust for your deployment).
- **API Key:** Add your `x-api-key` value to requests.
- **n8n setup:** Use the `HTTP Request` node for API calls and the `Set` or `Function` node to build JSON bodies.
- **MinIO (optional):** If using local MinIO, ensure the app can access uploaded assets.

**Common HTTP Request Node Settings**
- **Method:** `POST` (for compose/concatenate/merge) or `GET` (for probe).
- **URL:** Full endpoint, e.g. `http://localhost:8080/v1/ffmpeg/compose`.
- **Authentication / Headers:** Add header `x-api-key: <YOUR_API_KEY>` and `Content-Type: application/json`.
- **Body Parameters:** Select `JSON` in the node and paste the sample JSON payload.

**Example 1 — Compose media and assign audio to a specific audio track**
- **Endpoint:** `POST /v1/ffmpeg/compose`
- **Purpose:** Add external audio as a specific audio track in the output file. Useful to create separate tracks that you later merge.

Sample JSON body:
```
{
  "inputs": [
    { "url": "https://www.w3schools.com/html/mov_bbb.mp4", "type": "video" },
    { "url": "https://www.example.com/my_whoosh.mp3", "type": "audio", "audio_track_id": 1 }
  ],
  "output_format": "mp4",
  "job_id": "compose-sample"
}
```

- **n8n node:** Use `HTTP Request` node with method `POST`, URL `http://localhost:8080/v1/ffmpeg/compose`, set the JSON body above, and add header `x-api-key`.

**Example 2 — Concatenate videos and set transition SFX on its own audio track**
- **Endpoint:** `POST /v1/video/concatenate`
- **Purpose:** Join multiple videos with transitions. Use `transition_sfx_track_id` to place the whoosh/transition sound effect onto a specific audio track in the output.

Sample JSON body:
```
{
  "videos": [
    { "url": "https://example.com/clip1.mp4" },
    { "url": "https://example.com/clip2.mp4" }
  ],
  "transition_type": "whip_pan",
  "transition_sfx": "assets/audio/whip_pan_whoosh.mp3",
  "transition_sfx_track_id": 1,
  "job_id": "concat-sample"
}
```

- **Notes:** The service will attempt to include the transition SFX as a separate audio track when `transition_sfx_track_id` is provided. If you used `compose` to create inputs with explicit `audio_track_id` values earlier, the final concatenated output can contain multiple audio tracks.

**Example 3 — Probe an asset to inspect audio tracks**
- **Endpoint:** `POST /v1/audio/probe`
- **Purpose:** Confirm how many audio tracks are present and get stream details before merging.

Sample JSON body:
```
{
  "url": "http://minio:9000/nca-toolkit-local/concat-sample_output.mp4"
}
```

**Example 4 — Merge all audio tracks into the main track with loudness normalization**
- **Endpoint:** `POST /v1/audio/merge_tracks`
- **Purpose:** Combine multiple audio tracks (main + SFX + others) into a single track, applying EBU R128 loudness normalization and optional per-track gain adjustments.

Sample JSON body:
```
{
  "url": "http://minio:9000/nca-toolkit-local/concat-sample_output.mp4",
  "target_lufs": -16,
  "true_peak": -1.0,
  "loudness_range": 7.0,
  "gain_adjustments": {
    "0": 0.0,
    "1": -3.0
  },
  "job_id": "merge-sample"
}
```

- **`gain_adjustments` keys**: track indexes (as strings) to dB adjustments applied before mixing.
- **Workflow tip:** After `concatenate`, call `probe` to confirm track indexes, then call `merge_tracks` with `gain_adjustments` tuned to taste.

**Putting it together — Example n8n workflow sequence**
- Step 1: `HTTP Request` to `/v1/ffmpeg/compose` (create separate audio tracks if needed).
- Step 2: `HTTP Request` to `/v1/video/concatenate` with `transition_sfx_track_id` set.
- Step 3: `HTTP Request` to `/v1/audio/probe` on the concatenated output to get stream indexes.
- Step 4: `HTTP Request` to `/v1/audio/merge_tracks` with `gain_adjustments` based on probe results.
- Step 5: Optional `HTTP Request` to an upload node or to notify downstream systems with the merged asset URL.

**Practical n8n node configuration hints**
- If you need to reuse the `x-api-key`, store it in n8n as a credential and reference it in the node headers.
- For `HTTP Request` node, choose `JSON` as the body format and paste the JSON payload. Use expressions (e.g., `{{$json["previousNodeName"]["body"]["output_url"]}}`) to chain outputs into subsequent nodes.
- When calling local URLs from n8n running in Docker, use the internal service name or adjust network settings (e.g., `http://host.docker.internal:8080` or the API container hostname) depending on your deployment.

**Troubleshooting**
- If the transition SFX does not appear as a separate audio track: ensure `transition_sfx_track_id` is provided and that the asset path is reachable inside the container (use absolute/minio URL if necessary).
- If `merge_tracks` output is unexpectedly loud/quiet: run `probe` to verify track indexes and adjust `gain_adjustments` accordingly.
- If public sample URLs fail from inside Docker, host a test asset in MinIO or use a reachable public sample.

**References**
- `POST /v1/ffmpeg/compose` — compose media with per-input `audio_track_id`.
- `POST /v1/video/concatenate` — concatenate videos; supports `transition_sfx_track_id`.
- `POST /v1/audio/probe` — inspect audio tracks of an asset.
- `POST /v1/audio/merge_tracks` — merge tracks and apply loudness normalization.

If you want, I can also add an example `n8n` workflow export (JSON) to this guide that you can import directly into your n8n instance. Want me to add that now?
