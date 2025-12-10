# Audio Probe Endpoint

## 1. Overview

The `/v1/audio/probe` endpoint analyzes a media file and returns detailed information about all audio tracks it contains. This is useful for understanding the audio track structure of a video before processing it with other endpoints like `/v1/audio/merge_tracks` or `/v1/ffmpeg/compose`.

## 2. Endpoint

**URL Path:** `/v1/audio/probe`
**HTTP Method:** `POST`

## 3. Request

### Headers

- `x-api-key` (required): The API key for authentication.

### Body Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `file_url` | string (URI) | Yes | URL of the media file to probe |
| `webhook_url` | string (URI) | No | URL to send the response webhook |
| `id` | string | No | Unique identifier for the request |

### Example Request

```json
{
  "file_url": "https://example.com/video_with_multiple_tracks.mp4",
  "webhook_url": "https://example.com/webhook",
  "id": "probe-request-123"
}
```

```bash
curl -X POST \
  https://api.example.com/v1/audio/probe \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "file_url": "https://example.com/video_with_multiple_tracks.mp4"
  }'
```

## 4. Response

### Success Response

```json
{
  "endpoint": "/v1/audio/probe",
  "code": 200,
  "id": "probe-request-123",
  "job_id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "response": {
    "audio_tracks": [
      {
        "track_id": 0,
        "stream_index": 1,
        "codec": "aac",
        "codec_long_name": "AAC (Advanced Audio Coding)",
        "sample_rate": 48000,
        "channels": 2,
        "channel_layout": "stereo",
        "bit_rate": 128000,
        "duration": 120.5,
        "language": "eng",
        "title": "Main Audio"
      },
      {
        "track_id": 1,
        "stream_index": 2,
        "codec": "aac",
        "codec_long_name": "AAC (Advanced Audio Coding)",
        "sample_rate": 48000,
        "channels": 2,
        "channel_layout": "stereo",
        "bit_rate": 128000,
        "duration": 120.5,
        "language": null,
        "title": "Sound Effects"
      }
    ],
    "track_count": 2,
    "format": {
      "name": "mov,mp4,m4a,3gp,3g2,mj2",
      "long_name": "QuickTime / MOV"
    },
    "duration": 120.5,
    "bit_rate": 5000000,
    "size": 75312640
  },
  "message": "success",
  "run_time": 1.234
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `audio_tracks` | array | List of audio track information |
| `audio_tracks[].track_id` | integer | Zero-based audio track index (use this for `audio_track_id` in other endpoints) |
| `audio_tracks[].stream_index` | integer | FFmpeg stream index |
| `audio_tracks[].codec` | string | Audio codec name (e.g., "aac", "mp3", "opus") |
| `audio_tracks[].codec_long_name` | string | Full codec name |
| `audio_tracks[].sample_rate` | integer | Sample rate in Hz |
| `audio_tracks[].channels` | integer | Number of audio channels |
| `audio_tracks[].channel_layout` | string | Channel layout (e.g., "stereo", "5.1") |
| `audio_tracks[].bit_rate` | integer | Bitrate in bits per second |
| `audio_tracks[].duration` | number | Duration in seconds |
| `audio_tracks[].language` | string | Language tag if available |
| `audio_tracks[].title` | string | Track title if available |
| `track_count` | integer | Total number of audio tracks |
| `format` | object | Container format information |
| `duration` | number | Total file duration in seconds |
| `bit_rate` | integer | Overall bitrate |
| `size` | integer | File size in bytes |

### Error Responses

- **400 Bad Request**: Invalid request payload
- **401 Unauthorized**: Invalid or missing API key
- **500 Internal Server Error**: Failed to probe the file

## 5. Usage in n8n

### Basic Probe Request

```json
{
  "method": "POST",
  "url": "https://your-api.com/v1/audio/probe",
  "headers": {
    "x-api-key": "{{ $env.NCA_API_KEY }}",
    "Content-Type": "application/json"
  },
  "body": {
    "file_url": "{{ $json.video_url }}"
  }
}
```

### Workflow Example: Check Track Count Before Merging

Use an IF node after probing to decide if merging is needed:

```javascript
// In n8n Function node
const trackCount = $json.response.track_count;

if (trackCount > 1) {
  return [{
    json: {
      needsMerge: true,
      tracks: $json.response.audio_tracks,
      fileUrl: $json.file_url
    }
  }];
} else {
  return [{
    json: {
      needsMerge: false,
      fileUrl: $json.file_url
    }
  }];
}
```

### Get Track Information for Gain Adjustments

```javascript
// Generate gain_adjustments array based on track titles
const tracks = $json.response.audio_tracks;
const gainAdjustments = tracks.map(track => {
  let gain = 0;
  
  // Reduce SFX track volume
  if (track.title && track.title.toLowerCase().includes('sfx')) {
    gain = -6;
  }
  // Boost voiceover
  if (track.title && track.title.toLowerCase().includes('voice')) {
    gain = 3;
  }
  
  return {
    track_id: track.track_id,
    gain_db: gain
  };
});

return [{
  json: {
    gain_adjustments: gainAdjustments
  }
}];
```

## 6. Common Use Cases

1. **Pre-merge analysis**: Check how many audio tracks exist before calling `/v1/audio/merge_tracks`
2. **Track identification**: Find which track contains voiceover vs. music vs. SFX
3. **Quality verification**: Verify audio codec and bitrate meet requirements
4. **Duration checking**: Ensure audio duration matches video duration
5. **Workflow routing**: Route files with single tracks differently from multi-track files
