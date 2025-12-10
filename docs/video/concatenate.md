# Video Concatenation Endpoint

## 1. Overview

The `/v1/video/concatenate` endpoint is a part of the Video API and is responsible for combining multiple video files into a single video file. This endpoint fits into the overall API structure as a part of the version 1 (v1) routes, specifically under the `/v1/video` namespace.

## 2. Endpoint

**URL Path:** `/v1/video/concatenate`
**HTTP Method:** `POST`

## 3. Request

### Headers

- `x-api-key` (required): The API key for authentication.

### Body Parameters

The request body must be a JSON object with the following properties:

- `video_urls` (required, array of objects): An array of video URLs to be concatenated. Each object in the array must have a `video_url` property (string, URI format) containing the URL of the video file.
- `webhook_url` (optional, string, URI format): The URL to which the response should be sent as a webhook.
- `id` (optional, string): An identifier for the request.
- `transition_type` (optional, string): Controls the transition applied between clips. Supported values are `"none"`, `"fade"`, `"fade_black"`, `"wipe_left"`, `"wipe_right"`, `"smooth_left"`, `"smooth_right"`, `"whip_pan"`, `"circle_open"`, `"circle_close"`, and `"pixelize"`. Defaults to `"none"` for hard cuts.
- `transition_duration` (optional, number): Duration of the transition in seconds. Values must be between `0.2` and `5.0`. Defaults to `0.8` seconds.
- `transition_sequence` (optional, array of strings): Lets you specify a different transition for every clip boundary. Provide exactly _n-1_ entries (where _n_ is the number of videos). Accepts the same values as `transition_type` except `"none"`.
- `whip_pan_sfx_gain_db` (optional, number): Boost or attenuate the built-in whip-pan whoosh layer in decibels. Values between `-60` and `6` are accepted. Defaults to `-6` for a subtle overlay.
- `transition_sfx_track_id` (optional, integer, 0-15): When specified, transition sound effects (like the whip-pan whoosh) are placed on a separate audio track instead of being mixed into the main audio. This allows for post-processing control over the SFX volume in your workflow.

The `validate_payload` decorator in the routes file enforces the following JSON schema for the request body:

```json
{
    "type": "object",
    "properties": {
        "video_urls": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "video_url": {"type": "string", "format": "uri"}
                },
                "required": ["video_url"]
            },
            "minItems": 1
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"},
        "transition_type": {
          "type": "string",
          "enum": [
            "none", "fade", "fade_black", "wipe_left", "wipe_right",
            "smooth_left", "smooth_right", "whip_pan", "circle_open", "circle_close", "pixelize"
          ]
        },
        "transition_duration": {
          "type": "number",
          "minimum": 0.2,
          "maximum": 5.0
        },
        "transition_sequence": {
          "type": "array",
          "items": {
            "type": "string",
            "enum": [
              "fade", "fade_black", "wipe_left", "wipe_right",
              "smooth_left", "smooth_right", "whip_pan", "circle_open", "circle_close", "pixelize"
            ]
          },
          "minItems": 1
        }
    },
    "required": ["video_urls"],
    "additionalProperties": False
}
```

### Example Request

```json
{
    "video_urls": [
        {"video_url": "https://example.com/video1.mp4"},
        {"video_url": "https://example.com/video2.mp4"},
        {"video_url": "https://example.com/video3.mp4"}
    ],
    "webhook_url": "https://example.com/webhook",
      "id": "request-123",
      "transition_type": "whip_pan",
      "transition_duration": 1.2,
      "transition_sequence": ["whip_pan", "whip_pan"],
      "whip_pan_sfx_gain_db": -3
}
```

```bash
curl -X POST \
     -H "x-api-key: YOUR_API_KEY" \
     -H "Content-Type: application/json" \
     -d '{
        "video_urls": [
            {"video_url": "https://example.com/video1.mp4"},
            {"video_url": "https://example.com/video2.mp4"},
            {"video_url": "https://example.com/video3.mp4"}
        ],
        "webhook_url": "https://example.com/webhook",
        "id": "request-123",
        "transition_type": "fade_black",
        "transition_duration": 1.2,
        "transition_sequence": ["fade", "wipe_left"]
     }' \
     https://your-api-endpoint.com/v1/video/concatenate
```

## 4. Response

### Success Response

The success response follows the general response format defined in the `app.py` file. Here's an example:

```json
{
    "endpoint": "/v1/video/concatenate",
    "code": 200,
    "id": "request-123",
    "job_id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
    "response": "https://cloud-storage.example.com/combined-video.mp4",
    "message": "success",
    "pid": 12345,
    "queue_id": 6789,
    "run_time": 10.234,
    "queue_time": 2.345,
    "total_time": 12.579,
    "queue_length": 0,
    "build_number": "1.0.0"
}
```

The `response` field contains the URL of the combined video file uploaded to cloud storage.

### Error Responses

- **400 Bad Request**: Returned when the request body is missing or invalid.

  ```json
  {
    "code": 400,
    "message": "Invalid request payload"
  }
  ```

- **401 Unauthorized**: Returned when the `x-api-key` header is missing or invalid.

  ```json
  {
    "code": 401,
    "message": "Unauthorized"
  }
  ```

- **429 Too Many Requests**: Returned when the maximum queue length is reached.

  ```json
  {
    "code": 429,
    "id": "request-123",
    "job_id": "a1b2c3d4-e5f6-g7h8-i9j0-k1l2m3n4o5p6",
    "message": "MAX_QUEUE_LENGTH (100) reached",
    "pid": 12345,
    "queue_id": 6789,
    "queue_length": 100,
    "build_number": "1.0.0"
  }
  ```

- **500 Internal Server Error**: Returned when an unexpected error occurs during the video concatenation process.

  ```json
  {
    "code": 500,
    "message": "An error occurred during video concatenation"
  }
  ```

## 5. Error Handling

The endpoint handles the following common errors:

- **Missing or invalid request body**: If the request body is missing or does not conform to the expected JSON schema, a 400 Bad Request error is returned.
- **Missing or invalid API key**: If the `x-api-key` header is missing or invalid, a 401 Unauthorized error is returned.
- **Queue length exceeded**: If the maximum queue length is reached (determined by the `MAX_QUEUE_LENGTH` environment variable), a 429 Too Many Requests error is returned.
- **Unexpected errors during video concatenation**: If an unexpected error occurs during the video concatenation process, a 500 Internal Server Error is returned with the error message.

The main application context (`app.py`) also includes error handling for the task queue. If the queue length exceeds the `MAX_QUEUE_LENGTH` limit, the request is rejected with a 429 Too Many Requests error.

## 6. Usage Notes

- The video files to be concatenated must be accessible via the provided URLs.
- The order of the video files in the `video_urls` array determines the order in which they will be concatenated.
- Omitting `transition_type` keeps the previous hard-cut behavior. Specify one of the supported values together with an optional `transition_duration` to blend clips.
- When using `transition_sfx_track_id`, the output video will have multiple audio tracks that can be merged later using `/v1/audio/merge_tracks`.

## 7. Multi-Track Audio for Post-Processing (n8n)

The `transition_sfx_track_id` parameter enables a post-processing workflow where transition sound effects are kept separate from the main audio, allowing you to control their volume after measuring loudness.

### Example: Whip Pan with SFX on Separate Track

```json
{
  "video_urls": [
    {"video_url": "{{ $('Previous Node').item.json.clip1_url }}"},
    {"video_url": "{{ $('Previous Node').item.json.clip2_url }}"},
    {"video_url": "{{ $('Previous Node').item.json.clip3_url }}"}
  ],
  "transition_type": "whip_pan",
  "transition_duration": 0.5,
  "whip_pan_sfx_gain_db": 0,
  "transition_sfx_track_id": 1,
  "webhook_url": "{{ $env.WEBHOOK_URL }}",
  "id": "{{ $json.job_id }}"
}
```

This creates an output with:
- **Track 0**: Main audio (crossfaded between clips)
- **Track 1**: Whoosh sound effects from transitions

### n8n Workflow for Loudness-Matched Audio

1. **Concatenate videos** with `transition_sfx_track_id: 1`
2. **Probe audio tracks** using `/v1/audio/probe` to get track information
3. **Merge tracks** using `/v1/audio/merge_tracks` with gain adjustments:

```json
{
  "file_url": "{{ $json.concatenated_video_url }}",
  "target_lufs": -14,
  "gain_adjustments": [
    {"track_id": 0, "gain_db": 0},
    {"track_id": 1, "gain_db": -3}
  ]
}
```
- The `whip_pan` transition layers an `xfade=slideleft` move with a timed gaussian blur + blend curve so the cut blooms into a motion-blurred whip.
- Each whip-pan transition also mixes in the bundled `assets/audio/whip_pan_whoosh.mp3` file. Control its loudness with `whip_pan_sfx_gain_db` if you need a more aggressive or more subtle hit.
- Supply `transition_sequence` when you want per-boundary transitions. The array must contain exactly one transition name for every boundary between clips.
- If the `webhook_url` parameter is provided, the response will be sent as a webhook to the specified URL.
- The `id` parameter can be used to identify the request in the response.

## 7. Common Issues

- Providing invalid or inaccessible video URLs.
- Exceeding the maximum queue length, which can lead to requests being rejected with a 429 Too Many Requests error.
- Encountering unexpected errors during the video concatenation process, which can result in a 500 Internal Server Error.

## 8. Best Practices

- Validate the video URLs before sending the request to ensure they are accessible and in the correct format.
- Monitor the queue length and adjust the `MAX_QUEUE_LENGTH` value accordingly to prevent requests from being rejected due to a full queue.
- Implement retry mechanisms for handling temporary errors or failures during the video concatenation process.
- Provide meaningful and descriptive `id` values to easily identify requests in the response.
- When orchestrating jobs from n8n (or any low-code flow), set `transition_type` to `"whip_pan"` and send a `transition_sequence` that repeats `"whip_pan"` for every boundary to ensure consistent styling.

## 9. n8n Workflow Snippet

The screenshots above come from an n8n workflow that gathers signed URLs and calls this endpoint. To force whip pan transitions everywhere and optionally tweak the whoosh volume, update the `Code` node that builds the request payload to something like:

```javascript
const items = $input.all();
const video_urls = items.map((item) => ({ video_url: item.json.url }));
const whipPlan = Array(Math.max(video_urls.length - 1, 0)).fill("whip_pan");
const whipDuration = 0.8; // tweak this if you need longer/shorter pans

return [{
  json: {
    output: JSON.stringify({
      video_urls,
      id: "2323",
      transition_type: "whip_pan",
      transition_duration: whipDuration,
      transition_sequence: whipPlan,
      whip_pan_sfx_gain_db: -4
    })
  }
}];
```

Feed the resulting JSON into the HTTP node, keep the `x-api-key` header, and the API will apply the whip-pan visual transition plus the whoosh overlay for every boundary.