# Audio Merge Tracks Endpoint

## 1. Overview

The `/v1/audio/merge_tracks` endpoint merges all audio tracks from a media file into a single track with loudness normalization. This is the final step in a multi-track audio workflow where you've assigned different audio sources to separate tracks and now want to combine them with proper volume balancing.

The endpoint uses FFmpeg's `loudnorm` filter for EBU R128 compliant loudness normalization, ensuring consistent perceived loudness across all your output files.

## 2. Endpoint

**URL Path:** `/v1/audio/merge_tracks`
**HTTP Method:** `POST`

## 3. Request

### Headers

- `x-api-key` (required): The API key for authentication.

### Body Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `file_url` | string (URI) | Yes | - | URL of the media file with multiple audio tracks |
| `target_lufs` | number | No | -14.0 | Target integrated loudness in LUFS (-70 to -5) |
| `true_peak` | number | No | -1.0 | Maximum true peak in dBTP (-9 to 0) |
| `loudness_range` | number | No | 11.0 | Target loudness range in LU (1 to 20) |
| `gain_adjustments` | array | No | - | Per-track gain adjustments before mixing |
| `webhook_url` | string (URI) | No | - | URL to send the response webhook |
| `id` | string | No | - | Unique identifier for the request |

### Gain Adjustments Array Format

Each item in `gain_adjustments` should have:
- `track_id` (integer, 0-15): The audio track index
- `gain_db` (number, -60 to 30): Gain adjustment in decibels

### Example Request

```json
{
  "file_url": "https://example.com/video_with_3_audio_tracks.mp4",
  "target_lufs": -14,
  "true_peak": -1,
  "loudness_range": 11,
  "gain_adjustments": [
    {"track_id": 0, "gain_db": 0},
    {"track_id": 1, "gain_db": -6},
    {"track_id": 2, "gain_db": 3}
  ],
  "webhook_url": "https://example.com/webhook",
  "id": "merge-request-123"
}
```

```bash
curl -X POST \
  https://api.example.com/v1/audio/merge_tracks \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "file_url": "https://example.com/video_with_3_audio_tracks.mp4",
    "target_lufs": -14,
    "gain_adjustments": [
      {"track_id": 0, "gain_db": 0},
      {"track_id": 1, "gain_db": -6}
    ]
  }'
```

## 4. Response

### Success Response

```json
{
  "endpoint": "/v1/audio/merge_tracks",
  "code": 200,
  "id": "merge-request-123",
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "response": "https://storage.example.com/merged_output.mp4",
  "message": "success",
  "run_time": 15.234
}
```

The `response` field contains the URL of the processed file with:
- Video stream copied (unchanged)
- Single merged audio track with loudness normalization applied

### Error Responses

- **400 Bad Request**: Invalid request payload or no audio tracks found
- **401 Unauthorized**: Invalid or missing API key
- **500 Internal Server Error**: Processing failed

## 5. Loudness Normalization Settings

### Target LUFS
The integrated loudness target. Common values:
- `-14 LUFS`: YouTube, Spotify, most streaming platforms
- `-16 LUFS`: Broadcast TV (EBU recommendation)
- `-24 LUFS`: Film/Cinema

### True Peak
Maximum allowed peak level to prevent clipping:
- `-1 dBTP`: Standard for streaming
- `-2 dBTP`: More conservative, recommended for lossy codecs

### Loudness Range (LRA)
Controls dynamic range compression:
- `7 LU`: More compressed, consistent volume
- `11 LU`: Default, balanced dynamics
- `15 LU`: More dynamic range preserved

## 6. Usage in n8n

### Basic Merge Request

```json
{
  "method": "POST",
  "url": "https://your-api.com/v1/audio/merge_tracks",
  "headers": {
    "x-api-key": "{{ $env.NCA_API_KEY }}",
    "Content-Type": "application/json"
  },
  "body": {
    "file_url": "{{ $json.video_url }}",
    "target_lufs": -14
  }
}
```

### Complete Post-Processing Workflow

This n8n workflow demonstrates the full multi-track audio pipeline:

#### Step 1: Compose Video with Separate Audio Tracks

```json
{
  "inputs": [
    {"file_url": "{{ $json.video_url }}", "audio_track_id": 0},
    {"file_url": "{{ $json.voiceover_url }}", "audio_track_id": 1},
    {"file_url": "{{ $json.music_url }}", "audio_track_id": 2}
  ],
  "outputs": [
    {
      "options": [
        {"option": "-map", "argument": "0:v:0"},
        {"option": "-c:v", "argument": "copy"},
        {"option": "-c:a", "argument": "aac"},
        {"option": "-shortest"}
      ]
    }
  ]
}
```

#### Step 2: Probe Audio Tracks (Optional)

```json
{
  "file_url": "{{ $json.composed_video_url }}"
}
```

#### Step 3: Merge Tracks with Gain Adjustments

```json
{
  "file_url": "{{ $json.composed_video_url }}",
  "target_lufs": -14,
  "true_peak": -1,
  "gain_adjustments": [
    {"track_id": 0, "gain_db": 0},
    {"track_id": 1, "gain_db": 3},
    {"track_id": 2, "gain_db": -9}
  ]
}
```

### Dynamic Gain Adjustment Based on Content Type

Use a Function node to calculate gain adjustments:

```javascript
// Calculate gains based on content type
const contentType = $json.content_type; // 'podcast', 'music_video', 'tutorial'

let voiceGain = 0;
let musicGain = 0;
let sfxGain = 0;

switch(contentType) {
  case 'podcast':
    voiceGain = 3;
    musicGain = -12;
    sfxGain = -6;
    break;
  case 'music_video':
    voiceGain = 0;
    musicGain = 0;
    sfxGain = -3;
    break;
  case 'tutorial':
    voiceGain = 6;
    musicGain = -15;
    sfxGain = -9;
    break;
}

return [{
  json: {
    file_url: $json.video_url,
    target_lufs: -14,
    gain_adjustments: [
      {track_id: 0, gain_db: voiceGain},
      {track_id: 1, gain_db: musicGain},
      {track_id: 2, gain_db: sfxGain}
    ]
  }
}];
```

## 7. Complete Workflow Example

Here's a typical n8n workflow for video post-processing with consistent loudness:

```
[Webhook Trigger]
       ↓
[HTTP Request: /v1/video/concatenate]
  - transition_sfx_track_id: 1
       ↓
[HTTP Request: /v1/ffmpeg/compose]
  - Add voiceover to track 2
  - Add background music to track 3
       ↓
[HTTP Request: /v1/audio/probe]
  - Get track information
       ↓
[Function: Calculate Gains]
  - Analyze track metadata
  - Set gain_adjustments
       ↓
[HTTP Request: /v1/audio/merge_tracks]
  - target_lufs: -14
  - Apply calculated gains
       ↓
[Webhook Response]
  - Return final video URL
```

## 8. Best Practices

1. **Consistent Target LUFS**: Use the same `target_lufs` across all your content for consistent perceived loudness.

2. **Pre-mix Gain Structure**: Set `gain_adjustments` to establish the relative balance between tracks before normalization:
   - Voiceover/Dialogue: 0 to +6 dB (most important)
   - Background Music: -9 to -15 dB (supportive)
   - Sound Effects: -3 to -9 dB (accents)

3. **True Peak Headroom**: Use `-1 dBTP` or lower to prevent clipping when the audio is encoded to lossy formats.

4. **Quality Preservation**: The endpoint preserves video quality by copying the video stream without re-encoding.

5. **Workflow Validation**: Use `/v1/audio/probe` before merging to verify track structure and catch issues early.

## 9. Technical Notes

- The endpoint uses FFmpeg's `loudnorm` filter with `linear=true` for high-quality normalization
- Audio is re-encoded to AAC at 192kbps
- Video stream is copied without re-encoding
- Output container format matches the input format
- Processing time depends on file duration and number of audio tracks
