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
import re
from services.file_management import download_file
from config import LOCAL_STORAGE_PATH

def get_extension_from_format(format_name):
    # Mapping of common format names to file extensions
    format_to_extension = {
        'mp4': 'mp4',
        'mov': 'mov',
        'avi': 'avi',
        'mkv': 'mkv',
        'webm': 'webm',
        'gif': 'gif',
        'apng': 'apng',
        'jpg': 'jpg',
        'jpeg': 'jpg',
        'png': 'png',
        'image2': 'png',  # Assume png for image2 format
        'rawvideo': 'raw',
        'mp3': 'mp3',
        'wav': 'wav',
        'aac': 'aac',
        'flac': 'flac',
        'ogg': 'ogg'
    }
    return format_to_extension.get(format_name.lower(), 'mp4')  # Default to mp4 if unknown

def get_metadata(filename, metadata_requests, job_id):
    metadata = {}
    if metadata_requests.get('thumbnail'):
        thumbnail_filename = f"{os.path.splitext(filename)[0]}_thumbnail.jpg"
        thumbnail_command = [
            'ffmpeg',
            '-i', filename,
            '-vf', 'select=eq(n\,0)',
            '-vframes', '1',
            thumbnail_filename
        ]
        try:
            subprocess.run(thumbnail_command, check=True, capture_output=True, text=True)
            if os.path.exists(thumbnail_filename):
                metadata['thumbnail'] = thumbnail_filename  # Return local path instead of URL
        except subprocess.CalledProcessError as e:
            print(f"Thumbnail generation failed: {e.stderr}")

    if metadata_requests.get('filesize'):
        metadata['filesize'] = os.path.getsize(filename)

    if metadata_requests.get('encoder') or metadata_requests.get('duration') or metadata_requests.get('bitrate'):
        ffprobe_command = [
            'ffprobe',
            '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            '-show_streams',
            filename
        ]
        result = subprocess.run(ffprobe_command, capture_output=True, text=True)
        probe_data = json.loads(result.stdout)
        
        if metadata_requests.get('duration'):
            metadata['duration'] = float(probe_data['format']['duration'])
        if metadata_requests.get('bitrate'):
            metadata['bitrate'] = int(probe_data['format']['bit_rate'])
        
        if metadata_requests.get('encoder'):
            metadata['encoder'] = {}
            for stream in probe_data['streams']:
                if stream['codec_type'] == 'video':
                    metadata['encoder']['video'] = stream.get('codec_name', 'unknown')
                elif stream['codec_type'] == 'audio':
                    metadata['encoder']['audio'] = stream.get('codec_name', 'unknown')

    return metadata

def process_ffmpeg_compose(data, job_id):
    output_filenames = []
    
    # Build FFmpeg command
    command = ["ffmpeg"]
    
    # Add global options
    for option in data.get("global_options", []):
        command.append(option["option"])
        if "argument" in option and option["argument"] is not None:
            command.append(str(option["argument"]))
    
    # Add inputs
    input_paths = []
    download_cache = {}  # cache of url -> local_path
    audio_track_mappings = []  # Track audio_track_id assignments for later mapping
    for input_index, input_data in enumerate(data["inputs"]):
        if "options" in input_data:
            for option in input_data["options"]:
                command.append(option["option"])
                if "argument" in option and option["argument"] is not None:
                    command.append(str(option["argument"]))
        file_url = input_data["file_url"]
        if file_url in download_cache:
            input_path = download_cache[file_url]
        else:
            input_path = download_file(file_url, LOCAL_STORAGE_PATH)
            download_cache[file_url] = input_path
        input_paths.append(input_path)
        command.extend(["-i", input_path])
        
        # Track audio_track_id if specified
        if "audio_track_id" in input_data:
            audio_track_mappings.append({
                "input_index": input_index,
                "track_id": input_data["audio_track_id"]
            })
    
    # Add filters
    subtitles_paths = []  # Track downloaded subtitles/filter files
    user_filters = []
    if data.get("filters"):
        for filter_obj in data["filters"]:
            filter_str = filter_obj["filter"]
            def replace_url(match):
                prefix = match.group(1)
                filter_type = match.group(2)
                quote = match.group(3)
                url = match.group(4)
                closing_quote = match.group(5)
                trailing = match.group(6) or ''
                if not url or url.strip() == '':
                    print(f"[DEBUG] Skipping empty URL for filter: {match.group(0)}")
                    return match.group(0)
                print(f"[DEBUG] Parsed URL for filter: {url}")
                local_path = download_file(url, LOCAL_STORAGE_PATH)
                subtitles_paths.append(local_path)
                fixed_path = local_path.replace('\\', '/')
                return f"{prefix}{filter_type}={quote}{fixed_path}{closing_quote}{trailing}"
            # Regex: (.*?)(subtitles|ass)=(['"])(https?://[^'\"]+)(['"])(.*)
            pattern = r"(.*?)(subtitles|ass)=([\'\"])(https?://[^'\"]+)([\'\"])(.*)"
            filter_str = re.sub(pattern, replace_url, filter_str)
            user_filters.append(filter_str)
    
    # Build audio track mapping filters if audio_track_id is specified
    audio_track_filters = []
    audio_track_labels = []
    if audio_track_mappings:
        # Find the max track_id to determine total number of output audio tracks
        max_track_id = max(m["track_id"] for m in audio_track_mappings)
        
        # Create a dict mapping track_id -> list of input indices
        track_to_inputs = {}
        for mapping in audio_track_mappings:
            track_id = mapping["track_id"]
            input_idx = mapping["input_index"]
            if track_id not in track_to_inputs:
                track_to_inputs[track_id] = []
            track_to_inputs[track_id].append(input_idx)
        
        # Generate filter chains for each track
        for track_id in range(max_track_id + 1):
            if track_id in track_to_inputs:
                input_indices = track_to_inputs[track_id]
                if len(input_indices) == 1:
                    # Single input for this track - just label it
                    input_idx = input_indices[0]
                    audio_track_filters.append(f"[{input_idx}:a]anull[atrack{track_id}]")
                else:
                    # Multiple inputs for this track - mix them together
                    input_labels = "".join(f"[{idx}:a]" for idx in input_indices)
                    audio_track_filters.append(f"{input_labels}amix=inputs={len(input_indices)}:dropout_transition=0[atrack{track_id}]")
                audio_track_labels.append(f"[atrack{track_id}]")
            else:
                # No input for this track - create silence
                audio_track_filters.append(f"anullsrc=channel_layout=stereo:sample_rate=48000[atrack{track_id}]")
                audio_track_labels.append(f"[atrack{track_id}]")
    
    # Combine user filters with audio track filters
    all_filters = user_filters + audio_track_filters
    if all_filters:
        filter_complex = ";".join(all_filters)
        command.extend(["-filter_complex", filter_complex])
    
    # Add outputs
    for i, output in enumerate(data["outputs"]):
        format_name = None
        for option in output["options"]:
            if option["option"] == "-f":
                format_name = option.get("argument")
                break
        
        extension = get_extension_from_format(format_name) if format_name else 'mp4'
        output_filename = os.path.join(LOCAL_STORAGE_PATH, f"{job_id}_output_{i}.{extension}")
        output_filenames.append(output_filename)
        
        # Add audio track mappings if we generated them
        if audio_track_labels:
            for label in audio_track_labels:
                command.extend(["-map", label])
        
        for option in output["options"]:
            command.append(option["option"])
            if "argument" in option and option["argument"] is not None:
                command.append(str(option["argument"]))
        command.append(output_filename)
    
    # Execute FFmpeg command
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        raise Exception(f"FFmpeg command failed: {e.stderr}")
    
    # Clean up input files
    for input_path in input_paths:
        if os.path.exists(input_path):
            os.remove(input_path)
    # Clean up subtitles/filter files
    for subtitles_path in subtitles_paths:
        if os.path.exists(subtitles_path):
            os.remove(subtitles_path)
    # Get metadata if requested
    metadata = []
    if data.get("metadata"):
        for output_filename in output_filenames:
            metadata.append(get_metadata(output_filename, data["metadata"], job_id))
    
    return output_filenames, metadata
