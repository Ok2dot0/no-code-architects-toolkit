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


def process_audio_probe(file_url: str, job_id: str) -> Dict[str, Any]:
    """
    Probe a media file and return detailed information about all audio tracks.
    
    Args:
        file_url: URL of the media file to probe
        job_id: Unique job identifier
    
    Returns:
        Dictionary containing:
        - audio_tracks: List of audio track information
        - format: Container format information
        - duration: Total duration in seconds
    """
    input_path = download_file(file_url, LOCAL_STORAGE_PATH)
    
    try:
        # Run ffprobe to get detailed stream information
        ffprobe_command = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            input_path
        ]
        
        result = subprocess.run(ffprobe_command, capture_output=True, text=True, check=True)
        probe_data = json.loads(result.stdout)
        
        # Extract audio track information
        audio_tracks = []
        audio_stream_index = 0
        
        for stream in probe_data.get('streams', []):
            if stream.get('codec_type') == 'audio':
                track_info = {
                    'track_id': audio_stream_index,
                    'stream_index': stream.get('index'),
                    'codec': stream.get('codec_name'),
                    'codec_long_name': stream.get('codec_long_name'),
                    'sample_rate': int(stream.get('sample_rate', 0)) if stream.get('sample_rate') else None,
                    'channels': stream.get('channels'),
                    'channel_layout': stream.get('channel_layout'),
                    'bit_rate': int(stream.get('bit_rate', 0)) if stream.get('bit_rate') else None,
                    'duration': float(stream.get('duration', 0)) if stream.get('duration') else None,
                    'language': stream.get('tags', {}).get('language'),
                    'title': stream.get('tags', {}).get('title'),
                }
                
                # Add bits per sample for lossless formats
                if stream.get('bits_per_sample'):
                    track_info['bits_per_sample'] = stream.get('bits_per_sample')
                
                # Add bits per raw sample if available
                if stream.get('bits_per_raw_sample'):
                    track_info['bits_per_raw_sample'] = int(stream.get('bits_per_raw_sample'))
                
                audio_tracks.append(track_info)
                audio_stream_index += 1
        
        # Extract format information
        format_info = probe_data.get('format', {})
        
        response = {
            'audio_tracks': audio_tracks,
            'track_count': len(audio_tracks),
            'format': {
                'name': format_info.get('format_name'),
                'long_name': format_info.get('format_long_name'),
            },
            'duration': float(format_info.get('duration', 0)) if format_info.get('duration') else None,
            'bit_rate': int(format_info.get('bit_rate', 0)) if format_info.get('bit_rate') else None,
            'size': int(format_info.get('size', 0)) if format_info.get('size') else None,
        }
        
        return response
        
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFprobe command failed: {e.stderr}")
    finally:
        # Clean up downloaded file
        if os.path.exists(input_path):
            os.remove(input_path)
