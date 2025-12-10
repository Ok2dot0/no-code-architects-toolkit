# Copyright (c) 2025 Stephen G. Pope
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License along
# with this program; if not, write to the Free Software Foundation, Inc.,
# 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301 USA.



import math
import os
import re
import subprocess
import tempfile
from typing import List, Tuple, Optional

import ffmpeg

from services.file_management import download_file
from config import LOCAL_STORAGE_PATH

SUPPORTED_TRANSITION_TYPES = {
    "none": None,
    "fade": "fade",
    "fade_black": "fadeblack",
    "wipe_left": "wipeleft",
    "wipe_right": "wiperight",
    "smooth_left": "smoothleft",
    "smooth_right": "smoothright",
    "whip_pan": "slideleft",
    "circle_open": "circleopen",
    "circle_close": "circleclose",
    "pixelize": "pixelize",
}

DEFAULT_TRANSITION_TYPE = "none"
DEFAULT_TRANSITION_DURATION = 0.8  # seconds
MIN_TRANSITION_DURATION = 0.2
MAX_TRANSITION_DURATION = 5.0
AUDIO_SAMPLE_RATE = 48000
# Go up 4 levels: video -> v1 -> services -> app
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
WHIP_PAN_SFX_PATH = os.path.join(REPO_ROOT, "assets", "audio", "whip_pan_whoosh.mp3")
DEFAULT_WHIP_PAN_SFX_GAIN_DB = -6.0
MIN_WHIP_PAN_SFX_GAIN_DB = -60.0
MAX_WHIP_PAN_SFX_GAIN_DB = 6.0

# Transition SFX track ID constants (None means mix into main audio)
DEFAULT_TRANSITION_SFX_TRACK_ID = None
MIN_TRANSITION_SFX_TRACK_ID = 0
MAX_TRANSITION_SFX_TRACK_ID = 15

def process_video_concatenate(
    media_urls,
    job_id,
    webhook_url=None,
    transition_type: str = DEFAULT_TRANSITION_TYPE,
    transition_duration: float = DEFAULT_TRANSITION_DURATION,
    transition_sequence: Optional[List[str]] = None,
    whip_pan_sfx_gain_db: float = DEFAULT_WHIP_PAN_SFX_GAIN_DB,
    transition_sfx_track_id: Optional[int] = DEFAULT_TRANSITION_SFX_TRACK_ID,
):
    """Combine multiple videos into one, optionally applying transitions between clips."""

    validated_transition = _normalize_transition_type(transition_type)
    normalized_duration = _normalize_transition_duration(transition_duration)
    normalized_whip_pan_gain = _normalize_whip_pan_sfx_gain_db(whip_pan_sfx_gain_db)
    normalized_sfx_track_id = _normalize_transition_sfx_track_id(transition_sfx_track_id)

    input_files: List[str] = []
    output_filename = f"{job_id}.mp4"
    output_path = os.path.join(LOCAL_STORAGE_PATH, output_filename)

    try:
        for i, media_item in enumerate(media_urls):
            url = media_item["video_url"]
            input_filename = download_file(url, os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_input_{i}"))
            input_files.append(input_filename)

        transition_plan = _build_transition_plan(
            len(input_files),
            validated_transition,
            transition_sequence,
        )

        if _should_apply_transitions(transition_plan):
            _concatenate_with_transitions(
                input_files,
                output_path,
                transition_plan,
                normalized_duration,
                normalized_whip_pan_gain,
                normalized_sfx_track_id,
            )
        else:
            _concatenate_with_concat_demuxer(input_files, output_path)

        for f in input_files:
            os.remove(f)

        if not os.path.exists(output_path):
            raise FileNotFoundError(f"Output file {output_path} does not exist after combination.")

        return output_path
    except Exception as e:
        print(f"Video combination failed: {str(e)}")
        raise


def _build_transition_plan(
    clip_count: int,
    default_transition: str,
    transition_sequence: Optional[List[str]],
) -> List[str]:
    """Create a per-boundary transition plan based on the request."""

    if clip_count <= 1:
        return []

    if not transition_sequence:
        return [default_transition] * (clip_count - 1)

    if len(transition_sequence) != clip_count - 1:
        raise ValueError(
            "transition_sequence must include one transition per clip boundary."
        )

    normalized_plan: List[str] = []
    for index, requested in enumerate(transition_sequence):
        key = _normalize_transition_type(requested)
        if key == "none":
            raise ValueError(
                "transition_sequence entries must specify an actual transition type."
            )
        normalized_plan.append(key)

    return normalized_plan


def _should_apply_transitions(transition_plan: List[str]) -> bool:
    return any(key != "none" for key in transition_plan)


def _concatenate_with_concat_demuxer(input_files: List[str], output_path: str) -> None:
    concat_file = tempfile.NamedTemporaryFile(
        mode="w",
        suffix="_concat_list.txt",
        dir=LOCAL_STORAGE_PATH,
        delete=False,
        encoding="utf-8",
    )

    try:
        with concat_file as handle:
            for input_file in input_files:
                handle.write(f"file '{os.path.abspath(input_file)}'\n")

        (
            ffmpeg.input(concat_file.name, format="concat", safe=0)
            .output(output_path, c="copy")
            .run(overwrite_output=True)
        )
    finally:
        if os.path.exists(concat_file.name):
            os.remove(concat_file.name)


def _concatenate_with_transitions(
    input_files: List[str],
    output_path: str,
    transition_plan: List[str],
    transition_duration: float,
    whip_pan_sfx_gain_db: float,
    transition_sfx_track_id: Optional[int] = None,
) -> None:
    media_streams = []

    for path in input_files:
        duration, has_audio = _probe_media(path)
        media_input = ffmpeg.input(path)
        audio_stream = media_input.audio if has_audio else _build_silence_audio(duration)
        media_streams.append(
            {
                "video": media_input.video,
                "audio": audio_stream,
                "duration": duration,
            }
        )

    current_video = media_streams[0]["video"]
    current_audio = media_streams[0]["audio"]
    cumulative_duration = media_streams[0]["duration"]
    trailing_clip_duration = media_streams[0]["duration"]
    
    # Collect SFX streams if they should go to a separate track
    sfx_streams = []
    total_duration_so_far = media_streams[0]["duration"]

    for idx in range(1, len(media_streams)):
        next_stream = media_streams[idx]
        transition_key = transition_plan[idx - 1]
        effective_duration = _effective_transition_duration(
            transition_duration,
            trailing_clip_duration,
            next_stream["duration"],
        )
        offset = max(cumulative_duration - effective_duration, 0)

        if transition_key == "whip_pan":
            current_video = _apply_whip_pan_transition(
                current_video,
                next_stream["video"],
                effective_duration,
                offset,
            )
            if transition_sfx_track_id is not None:
                # SFX goes to separate track - just crossfade main audio
                current_audio = ffmpeg.filter(
                    [current_audio, next_stream["audio"]],
                    "acrossfade",
                    d=effective_duration,
                )
                # Collect SFX stream for separate track
                sfx_stream = _build_whip_pan_sound_effect(offset, effective_duration, whip_pan_sfx_gain_db)
                if sfx_stream is not None:
                    sfx_streams.append({"stream": sfx_stream, "offset": offset})
            else:
                # Mix SFX into main audio (original behavior)
                current_audio = _apply_whip_pan_audio(
                    current_audio,
                    next_stream["audio"],
                    effective_duration,
                    offset,
                    whip_pan_sfx_gain_db,
                )
        else:
            transition_name = SUPPORTED_TRANSITION_TYPES[transition_key]
            if transition_name is None:
                raise ValueError("transition plan unexpectedly requested 'none'.")
            current_video = ffmpeg.filter(
                [current_video, next_stream["video"]],
                "xfade",
                transition=transition_name,
                duration=effective_duration,
                offset=offset,
            )
            current_audio = ffmpeg.filter(
                [current_audio, next_stream["audio"]],
                "acrossfade",
                d=effective_duration,
            )

        cumulative_duration = cumulative_duration + next_stream["duration"] - effective_duration
        trailing_clip_duration = next_stream["duration"]
        total_duration_so_far = cumulative_duration

    output_kwargs = {"vcodec": "libx264", "pix_fmt": "yuv420p", "movflags": "faststart"}

    stream = None
    if current_audio is not None:
        output_kwargs["acodec"] = "aac"
        
        if transition_sfx_track_id is not None and sfx_streams:
            # Build separate SFX track by mixing all SFX streams with silence base
            sfx_track = _build_sfx_track(sfx_streams, cumulative_duration, AUDIO_SAMPLE_RATE)
            
            # Use ffmpeg.merge_outputs to combine video+main audio with sfx audio
            # This creates two output specs that share the same filter graph
            video_audio_output = ffmpeg.output(
                current_video, current_audio, output_path,
                **output_kwargs
            )
            
            # Get the compiled command to see the filter graph
            cmd = video_audio_output.compile()
            
            # Find filter_complex and add SFX track to it
            filter_idx = None
            for i, arg in enumerate(cmd):
                if arg == "-filter_complex":
                    filter_idx = i
                    break
            
            if filter_idx is not None:
                # Compile SFX track to get its filter part
                sfx_output = ffmpeg.output(sfx_track, "/dev/null", format="null")
                sfx_cmd = sfx_output.compile()
                
                # Find SFX filter_complex
                sfx_filter_idx = None
                for i, arg in enumerate(sfx_cmd):
                    if arg == "-filter_complex":
                        sfx_filter_idx = i
                        break
                
                if sfx_filter_idx is not None:
                    main_filter = cmd[filter_idx + 1]
                    sfx_filter = sfx_cmd[sfx_filter_idx + 1]
                    
                    # Rename ALL labels in SFX filter to avoid conflicts
                    # Replace [s0], [s1], [s2], etc. with [sfx0], [sfx1], [sfx2], etc.
                    def rename_sfx_label(match):
                        return f"[sfx{match.group(1)}]"
                    sfx_filter_renamed = re.sub(r'\[s(\d+)\]', rename_sfx_label, sfx_filter)
                    
                    # Also rename input references [0:a], [1:a] etc. to use the anullsrc input
                    # The SFX filter should only use the anullsrc input which is already in its filter
                    
                    # Find the final output label (should now be [sfx0] or similar)
                    final_sfx_label_match = re.search(r'\[sfx\d+\]$', sfx_filter_renamed)
                    if final_sfx_label_match:
                        final_sfx_label = final_sfx_label_match.group(0)
                        # Rename the final output to just [sfx]
                        sfx_filter_renamed = sfx_filter_renamed[:-len(final_sfx_label)] + "[sfx]"
                    else:
                        # If no match, just append [sfx] at the end
                        sfx_filter_renamed = sfx_filter_renamed.rstrip(";") + "[sfx]"
                    
                    # Combine filters
                    combined_filter = f"{main_filter};{sfx_filter_renamed}"
                    
                    # Rebuild command with multi-track output
                    new_cmd = ["ffmpeg", "-y"]
                    
                    # Add all inputs (skip ffmpeg itself)
                    i = 1
                    while i < filter_idx:
                        new_cmd.append(cmd[i])
                        i += 1
                    
                    # Add combined filter
                    new_cmd.extend(["-filter_complex", combined_filter])
                    
                    # Find the actual output labels from the main filter
                    # Look for the last [sN] labels that would be video and audio outputs
                    main_labels = re.findall(r'\[s\d+\]', main_filter)
                    if len(main_labels) >= 2:
                        # Last two labels should be video and main audio
                        video_label = main_labels[-2] if len(main_labels) >= 2 else "[s0]"
                        audio_label = main_labels[-1]
                    else:
                        video_label = "[s0]"
                        audio_label = "[s1]" if len(main_labels) >= 1 else "[s0]"
                    
                    # Map outputs
                    new_cmd.extend(["-map", video_label])  # video
                    new_cmd.extend(["-map", audio_label])  # main audio
                    new_cmd.extend(["-map", "[sfx]"])  # sfx
                    
                    # Add output options
                    new_cmd.extend(["-vcodec", output_kwargs.get("vcodec", "libx264")])
                    new_cmd.extend(["-pix_fmt", output_kwargs.get("pix_fmt", "yuv420p")])
                    new_cmd.extend(["-movflags", output_kwargs.get("movflags", "faststart")])
                    new_cmd.extend(["-c:a", output_kwargs.get("acodec", "aac")])
                    new_cmd.append(output_path)
                    
                    result = subprocess.run(new_cmd, capture_output=True, text=True)
                    if result.returncode != 0:
                        raise RuntimeError(f"FFmpeg multi-track output failed: {result.stderr}")
                    return
            
            # Fallback if we couldn't build multi-track command
            stream = video_audio_output
        else:
            stream = ffmpeg.output(current_video, current_audio, output_path, **output_kwargs)
    else:
        stream = ffmpeg.output(current_video, output_path, **output_kwargs)

    stream.run(overwrite_output=True)


def _apply_whip_pan_transition(
    leading_video,
    trailing_video,
    transition_duration: float,
    offset: float,
):
    base = ffmpeg.filter(
        [leading_video, trailing_video],
        "xfade",
        transition="slideleft",
        duration=transition_duration,
        offset=offset,
    )

    split_node = base.filter_multi_output("split")
    sharp = split_node.stream("out0")
    blur_source = split_node.stream("out1")
    blurred = ffmpeg.filter(blur_source, "gblur", sigma=100, steps=1, sigmaV=0)
    blend_expr = _build_whip_pan_expression(offset, transition_duration)
    return ffmpeg.filter([sharp, blurred], "blend", all_expr=blend_expr)


def _apply_whip_pan_audio(
    leading_audio,
    trailing_audio,
    transition_duration: float,
    offset: float,
    gain_db: float,
):
    base_audio = ffmpeg.filter(
        [leading_audio, trailing_audio],
        "acrossfade",
        d=transition_duration,
    )

    effect_stream = _build_whip_pan_sound_effect(offset, transition_duration, gain_db)
    if effect_stream is None:
        return base_audio

    return ffmpeg.filter(
        [base_audio, effect_stream],
        "amix",
        inputs=2,
        dropout_transition=0,
    )


def _build_whip_pan_sound_effect(offset: float, duration: float, gain_db: float):
    if not os.path.exists(WHIP_PAN_SFX_PATH):
        return None

    effect = ffmpeg.input(WHIP_PAN_SFX_PATH).audio
    trimmed = effect.filter_(
        "atrim",
        start=0,
        duration=duration,
    ).filter_("asetpts", "PTS-STARTPTS")

    if gain_db != 0:
        linear_gain = math.pow(10.0, gain_db / 20.0)
        trimmed = trimmed.filter_("volume", linear_gain)

    delay_ms = max(int(round(offset * 1000)), 0)
    if delay_ms > 0:
        trimmed = trimmed.filter_("adelay", f"{delay_ms}|{delay_ms}")

    return trimmed


def _build_whip_pan_expression(offset: float, duration: float) -> str:
    offset_str = _format_decimal(offset)
    duration_str = _format_decimal(duration)
    end_str = _format_decimal(offset + duration)
    return (
        f"if(between(T,{offset_str},{end_str}),"
        f"A+(B-A)*sin((T-{offset_str})/{duration_str}*3.14159),"
        "A)"
    )


def _format_decimal(value: float) -> str:
    formatted = format(value, ".6f").rstrip("0").rstrip(".")
    return formatted if formatted else "0"


def _normalize_transition_type(requested_type: str) -> str:
    transition_key = (requested_type or DEFAULT_TRANSITION_TYPE).lower()
    if transition_key not in SUPPORTED_TRANSITION_TYPES:
        valid = ", ".join(sorted(SUPPORTED_TRANSITION_TYPES.keys()))
        raise ValueError(f"Unsupported transition_type '{requested_type}'. Choose one of: {valid}.")
    return transition_key


def _normalize_transition_duration(duration: float) -> float:
    try:
        value = float(duration)
    except (TypeError, ValueError) as exc:
        raise ValueError("transition_duration must be a number.") from exc

    if value < MIN_TRANSITION_DURATION:
        return MIN_TRANSITION_DURATION
    if value > MAX_TRANSITION_DURATION:
        return MAX_TRANSITION_DURATION
    return value


def _normalize_whip_pan_sfx_gain_db(gain_db: float) -> float:
    try:
        value = float(gain_db)
    except (TypeError, ValueError) as exc:
        raise ValueError("whip_pan_sfx_gain_db must be a number.") from exc

    if value < MIN_WHIP_PAN_SFX_GAIN_DB:
        return MIN_WHIP_PAN_SFX_GAIN_DB
    if value > MAX_WHIP_PAN_SFX_GAIN_DB:
        return MAX_WHIP_PAN_SFX_GAIN_DB
    return value


def _normalize_transition_sfx_track_id(track_id: Optional[int]) -> Optional[int]:
    """Normalize and validate the transition SFX track ID."""
    if track_id is None:
        return None
    try:
        value = int(track_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("transition_sfx_track_id must be an integer.") from exc

    if value < MIN_TRANSITION_SFX_TRACK_ID:
        return MIN_TRANSITION_SFX_TRACK_ID
    if value > MAX_TRANSITION_SFX_TRACK_ID:
        return MAX_TRANSITION_SFX_TRACK_ID
    return value


def _build_sfx_track(sfx_streams: List[dict], total_duration: float, sample_rate: int):
    """Build a single audio track from multiple SFX streams by mixing them together.
    
    Args:
        sfx_streams: List of dicts with 'stream' and 'offset' keys
        total_duration: Total duration of the output in seconds
        sample_rate: Audio sample rate
    
    Returns:
        Combined audio stream for the SFX track
    """
    if not sfx_streams:
        # Return silence if no SFX
        return _build_silence_audio(total_duration)
    
    # Start with silence base of the full duration
    base_silence = ffmpeg.input(
        "anullsrc",
        f="lavfi",
        channel_layout="stereo",
        sample_rate=sample_rate,
    ).audio.filter_("atrim", duration=total_duration).filter_("asetpts", "N/SR/TB")
    
    # Mix all SFX streams into the silence base
    # Note: The SFX streams already have their delays applied
    streams_to_mix = [base_silence]
    for sfx_info in sfx_streams:
        streams_to_mix.append(sfx_info["stream"])
    
    if len(streams_to_mix) == 1:
        return streams_to_mix[0]
    
    # Use amix to combine all streams
    return ffmpeg.filter(
        streams_to_mix,
        "amix",
        inputs=len(streams_to_mix),
        duration="first",  # Use duration of first stream (silence base)
        dropout_transition=0,
    )


def _effective_transition_duration(
    requested: float, previous_tail: float, next_clip: float
) -> float:
    max_allowed = min(previous_tail, next_clip)
    safe_cap = max(max_allowed - 0.05, MIN_TRANSITION_DURATION)
    effective = min(requested, safe_cap)
    if effective < MIN_TRANSITION_DURATION:
        raise ValueError("Transition duration is longer than one of the clips.")
    return effective


def _probe_media(path: str) -> Tuple[float, bool]:
    try:
        probe = ffmpeg.probe(path)
    except ffmpeg.Error as exc:
        raise RuntimeError(f"Unable to probe media file {path}: {exc}") from exc

    duration_str = probe.get("format", {}).get("duration")
    if duration_str is None:
        raise ValueError(f"Unable to determine duration for {path}.")

    duration = float(duration_str)
    has_audio = any(stream.get("codec_type") == "audio" for stream in probe.get("streams", []))
    return duration, has_audio


def _build_silence_audio(duration: float):
    silence = ffmpeg.input(
        "anullsrc",
        f="lavfi",
        channel_layout="stereo",
        sample_rate=AUDIO_SAMPLE_RATE,
    ).audio

    return silence.filter_("atrim", duration=duration).filter_("asetpts", "N/SR/TB")
