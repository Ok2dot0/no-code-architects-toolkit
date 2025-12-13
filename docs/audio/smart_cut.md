# Audio Smart Cut Endpoint

## 1. Overview

The `/v1/audio/smart-cut` endpoint automatically analyzes an audio file to detect the most compelling "hook" point and cuts a segment of specified duration starting from that point. This is ideal for creating short-form content (TikTok, Instagram Reels, YouTube Shorts) where you want the audio to start at an engaging moment.

The endpoint uses audio analysis techniques including:
- **Onset detection**: Identifies when new notes or percussive events start
- **Energy analysis**: Tracks loudness variations to find high-energy sections
- **Spectral analysis**: Measures timbral changes that often indicate exciting moments like drops or builds

## 2. Endpoint

**URL Path:** `/v1/audio/smart-cut`
**HTTP Method:** `POST`

## 3. Request

### Headers

- `x-api-key` (required): The API key for authentication.

### Body Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `random` | boolean | Yes | If `true`, selects a random audio file from the local-files folder. If `false`, the `filename` parameter is required. |
| `filename` | string | Conditional | The specific filename to use. Required when `random` is `false`. |
| `duration` | number | Yes | Duration in seconds for the output clip. |
| `seed` | integer | No | Random seed for reproducibility. When provided, the same seed will always select the same file (when random=true) and produce consistent results. |
| `webhook_url` | string (URI) | No | URL to send the response webhook |
| `id` | string | No | Unique identifier for the request |

### Example Request - Random Selection

```json
{
  "random": true,
  "duration": 15,
  "seed": 12345
}
```

### Example Request - Specific File

```json
{
  "random": false,
  "filename": "my_song.mp3",
  "duration": 30
}
```

### cURL Example

```bash
curl -X POST \
  https://api.example.com/v1/audio/smart-cut \
  -H 'x-api-key: YOUR_API_KEY' \
  -H 'Content-Type: application/json' \
  -d '{
    "random": true,
    "duration": 15,
    "seed": 42
  }'
```

## 4. Response

### Success Response

```json
{
  "url": "https://your-s3-endpoint.com/bucket/smartcut_abc123_song.mp3",
  "original_file": "song.mp3",
  "start_time": 45.23,
  "duration": 15,
  "seed": 42
}
```

### Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `url` | string | The S3 URL of the processed audio clip |
| `original_file` | string | The filename of the source audio file |
| `start_time` | number | The detected hook start time in seconds |
| `duration` | number | The duration of the output clip |
| `seed` | integer | The seed used (if provided) |

### Error Responses

**404 Not Found - No Audio Files**
```json
{
  "error": "No audio files found in local-files folder"
}
```

**404 Not Found - File Not Found**
```json
{
  "error": "File 'song.mp3' not found"
}
```

**400 Bad Request - Missing Filename**
```json
{
  "error": "Filename is required when random is false"
}
```

**500 Internal Server Error - S3 Configuration**
```json
{
  "error": "S3 configuration missing"
}
```

## 5. Setup Requirements

### Local Files Folder

Audio files must be placed in the `/app/local-files` folder inside the container. This folder should be mounted as a volume in your docker-compose configuration:

```yaml
services:
  ncat:
    volumes:
      - ./local-files:/app/local-files
```

### Supported Audio Formats

The endpoint supports the following audio formats:
- MP3 (`.mp3`)
- WAV (`.wav`)
- FLAC (`.flac`)
- M4A (`.m4a`)
- OGG (`.ogg`)
- AAC (`.aac`)

### S3 Configuration

The following environment variables must be set for S3 upload:

| Variable | Description |
|----------|-------------|
| `S3_ENDPOINT_URL` | S3-compatible endpoint URL |
| `S3_ACCESS_KEY` | S3 access key |
| `S3_SECRET_KEY` | S3 secret key |
| `S3_BUCKET_NAME` | Target bucket name |
| `S3_REGION` | S3 region (default: `us-east-1`) |

## 6. How Hook Detection Works

The algorithm scores potential starting points based on three factors:

1. **Energy Score (40%)**: Segments with higher RMS energy (loudness) score better. This helps find sections where the music is more intense.

2. **Onset Score (30%)**: Measures the strength of transients and attacks. Strong beats and clear rhythmic patterns score higher.

3. **Spectral Score (30%)**: Analyzes timbral variety by looking at spectral centroid variance. Sections with more interesting sound changes score better.

The algorithm:
1. Scans the entire audio file for onset peaks
2. Scores each potential starting point using the composite formula
3. Selects the highest-scoring position as the hook point
4. Cuts the audio from that point for the specified duration

## 7. Use Cases

- **Short-Form Video Creation**: Automatically find the catchiest part of a song for TikTok/Reels
- **Music Sampling**: Extract the most engaging segments from longer tracks
- **Podcast Highlights**: Find high-energy moments in podcast episodes
- **Batch Processing**: Use with `seed` parameter for reproducible results across multiple runs

## 8. Tips for Best Results

1. **Duration**: For short-form content, 15-30 seconds typically works best
2. **Seed**: Use the same seed value to get consistent results when re-processing
3. **File Quality**: Higher quality source files (320kbps MP3, FLAC) produce better analysis results
4. **Music vs Speech**: The algorithm is optimized for music; results may vary with speech-only content
