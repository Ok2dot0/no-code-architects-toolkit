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

import os
import subprocess
import json
from typing import List, Dict, Any, Optional
from services.file_management import download_file
from config import LOCAL_STORAGE_PATH

# Default loudness normalization settings
DEFAULT_TARGET_LUFS = -14.0
MIN_TARGET_LUFS = -70.0
MAX_TARGET_LUFS = -5.0

DEFAULT_TRUE_PEAK = -1.0
MIN_TRUE_PEAK = -9.0
MAX_TRUE_PEAK = 0.0

DEFAULT_LRA = 11.0  # Loudness Range
MIN_LRA = 1.0
MAX_LRA = 20.0

MIN_GAIN_ADJUSTMENT = -60.0
MAX_GAIN_ADJUSTMENT = 30.0


def process_audio_merge_tracks(
    file_url: str,
    job_id: str,
    target_lufs: float = DEFAULT_TARGET_LUFS,
    true_peak: float = DEFAULT_TRUE_PEAK,
    loudness_range: float = DEFAULT_LRA,
    gain_adjustments: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """
    Merge all audio tracks from a media file into a single track with loudness normalization.
    
    Args:
        file_url: URL of the media file
        job_id: Unique job identifier
        target_lufs: Target integrated loudness in LUFS (default: -14)
        true_peak: Maximum true peak in dBTP (default: -1)
        loudness_range: Target loudness range in LU (default: 11)
        gain_adjustments: Optional list of per-track gain adjustments
                         Format: [{"track_id": 0, "gain_db": 3.0}, ...]
    
    Returns:
        Path to the output file with merged audio tracks
    """
    input_path = download_file(file_url, LOCAL_STORAGE_PATH)
    
    # Determine output extension from input
    _, ext = os.path.splitext(input_path)
    if not ext:
        ext = '.mp4'
    output_path = os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_merged{ext}")
    
    try:
        # First, probe the file to get audio track count
        probe_command = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_streams',
            '-select_streams', 'a',
            input_path
        ]
        
        probe_result = subprocess.run(probe_command, capture_output=True, text=True, check=True)
        probe_data = json.loads(probe_result.stdout)
        audio_streams = probe_data.get('streams', [])
        audio_count = len(audio_streams)
        
        if audio_count == 0:
            raise ValueError("No audio tracks found in the input file")
        
        # Build gain adjustment map
        gain_map = {}
        if gain_adjustments:
            for adj in gain_adjustments:
                track_id = adj.get('track_id')
                gain_db = adj.get('gain_db', 0)
                if track_id is not None:
                    # Clamp gain to valid range
                    gain_db = max(MIN_GAIN_ADJUSTMENT, min(MAX_GAIN_ADJUSTMENT, gain_db))
                    gain_map[track_id] = gain_db
        
        # Build the FFmpeg filter complex
        filter_parts = []
        mix_inputs = []
        
        for i in range(audio_count):
            # Get gain for this track (default to 0 dB if not specified)
            gain_db = gain_map.get(i, 0)
            
            if gain_db != 0:
                # Apply volume adjustment for this track
                # Convert dB to linear: 10^(dB/20)
                filter_parts.append(f"[0:a:{i}]volume={gain_db}dB[a{i}]")
                mix_inputs.append(f"[a{i}]")
            else:
                mix_inputs.append(f"[0:a:{i}]")
        
        # Mix all audio tracks together
        if audio_count == 1:
            # Single track - just normalize it
            if filter_parts:
                mix_output = "[a0]"
            else:
                mix_output = "[0:a:0]"
            
            # Apply loudness normalization
            filter_parts.append(
                f"{mix_output}loudnorm="
                f"I={target_lufs}:"
                f"TP={true_peak}:"
                f"LRA={loudness_range}:"
                f"measured_I=-23:"
                f"measured_TP=-1:"
                f"measured_LRA=11:"
                f"linear=true:"
                f"print_format=summary[aout]"
            )
        else:
            # Multiple tracks - mix then normalize
            mix_input_str = "".join(mix_inputs)
            filter_parts.append(
                f"{mix_input_str}amix=inputs={audio_count}:"
                f"duration=longest:"
                f"dropout_transition=0,"
                f"loudnorm="
                f"I={target_lufs}:"
                f"TP={true_peak}:"
                f"LRA={loudness_range}:"
                f"measured_I=-23:"
                f"measured_TP=-1:"
                f"measured_LRA=11:"
                f"linear=true:"
                f"print_format=summary[aout]"
            )
        
        filter_complex = ";".join(filter_parts)
        
        # Build FFmpeg command
        command = [
            'ffmpeg',
            '-y',
            '-i', input_path,
            '-filter_complex', filter_complex,
            '-map', '0:v?',  # Copy video if present (? makes it optional)
            '-map', '[aout]',
            '-c:v', 'copy',
            '-c:a', 'aac',
            '-b:a', '192k',
            output_path
        ]
        
        result = subprocess.run(command, capture_output=True, text=True)
        
        if result.returncode != 0:
            raise Exception(f"FFmpeg command failed: {result.stderr}")
        
        if not os.path.exists(output_path):
            raise FileNotFoundError(f"Output file {output_path} was not created")
        
        return output_path
        
    except subprocess.CalledProcessError as e:
        raise Exception(f"Command failed: {e.stderr}")
    finally:
        # Clean up input file
        if os.path.exists(input_path):
            os.remove(input_path)
