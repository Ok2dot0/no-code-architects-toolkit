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
import random
import logging
import tempfile
import numpy as np
import librosa
import scipy.signal
import ffmpeg
from flask import Blueprint, jsonify
from services.authentication import authenticate
from app_utils import validate_payload, queue_task_wrapper
from services.s3_toolkit import upload_to_s3

logger = logging.getLogger(__name__)
v1_audio_smart_cut_bp = Blueprint('v1_audio_smart_cut', __name__)


def find_best_hook(audio_file, duration_sec=15):
    """
    Analyze audio file to find the best starting point (hook) for short-form content.
    Uses onset detection, energy analysis, and spectral features.
    
    Args:
        audio_file: Path to the audio file
        duration_sec: Duration of the segment to analyze for scoring
        
    Returns:
        float: Best start time in seconds
    """
    try:
        y, sr = librosa.load(audio_file)
        
        # Compute onset strength envelope
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, aggregate=np.median)
        
        # Detect peaks in onset envelope
        peaks, _ = scipy.signal.find_peaks(
            onset_env, 
            height=np.median(onset_env) * 1.5,
            distance=sr // 512
        )
        
        # Convert peak frames to time
        peak_times = librosa.frames_to_time(peaks, sr=sr)
        
        best_score = -1
        best_time = 0.0
        
        for t in peak_times:
            start_sample = int(t * sr)
            # Ensure we have enough audio for the segment
            if start_sample + sr * duration_sec > len(y):
                continue
            score = score_hook_segment(y, sr, start_sample, duration_sec)
            if score > best_score:
                best_score = score
                best_time = t
                
        logger.info(f"Found best hook at {best_time:.2f}s with score {best_score:.4f}")
        return best_time
        
    except Exception as e:
        logger.error(f"Error finding hook: {e}")
        return 0.0


def score_hook_segment(y, sr, start_sample, duration_sec=15):
    """
    Score a segment of audio for hook potential.
    
    Scoring is based on:
    - Energy level (RMS volume)
    - Onset strength (transients/attacks)
    - Spectral centroid variance (timbral interest)
    
    Args:
        y: Audio time series
        sr: Sample rate
        start_sample: Starting sample index
        duration_sec: Duration of segment to analyze
        
    Returns:
        float: Composite score for the segment
    """
    segment = y[start_sample:start_sample + int(sr * duration_sec)]
    if len(segment) == 0:
        return 0
    
    # Energy score (normalized RMS)
    energy = np.sqrt(np.mean(segment ** 2))
    y_range = np.max(np.abs(y)) - np.min(np.abs(y))
    energy_score = energy / (y_range + 1e-6)
    
    # Onset/beat strength score
    onset_strength = librosa.onset.onset_strength(y=segment, sr=sr)
    onset_score = np.mean(onset_strength)
    
    # Spectral centroid variance (higher = more timbral variety)
    S = np.abs(librosa.stft(segment))
    centroid = librosa.feature.spectral_centroid(S=S)[0]
    spectral_score = np.std(centroid) / (np.mean(centroid) + 1e-6)
    
    # Weighted composite score
    total_score = (0.4 * energy_score + 0.3 * onset_score + 0.3 * spectral_score)
    
    return total_score


@v1_audio_smart_cut_bp.route('/v1/audio/smart-cut', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "random": {
            "type": "boolean",
            "description": "If true, select a random audio file from the local-files folder"
        },
        "filename": {
            "type": "string",
            "description": "Specific filename to use (required if random is false)"
        },
        "duration": {
            "type": "number",
            "description": "Duration in seconds for the output clip"
        },
        "seed": {
            "type": "integer",
            "description": "Random seed for reproducibility"
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["random", "duration"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def smart_cut_endpoint(job_id, data):
    """
    Automatically find the best hook in an audio file and cut a segment.
    
    This endpoint uses audio analysis to detect the most compelling starting
    point in a music file, then cuts a segment of the specified duration
    and uploads it to S3.
    """
    try:
        is_random = data.get('random')
        filename = data.get('filename')
        duration = data.get('duration')
        seed = data.get('seed')
        
        # Set random seed for reproducibility
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
            
        local_files_dir = '/app/local-files'
        
        # Select audio file
        if is_random:
            audio_extensions = ('.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac')
            files = [f for f in os.listdir(local_files_dir) 
                     if f.lower().endswith(audio_extensions)]
            if not files:
                return {"error": "No audio files found in local-files folder"}, "/v1/audio/smart-cut", 404
            selected_file = random.choice(files)
        else:
            if not filename:
                return {"error": "Filename is required when random is false"}, "/v1/audio/smart-cut", 400
            selected_file = filename
            
        file_path = os.path.join(local_files_dir, selected_file)
        if not os.path.exists(file_path):
            return {"error": f"File '{selected_file}' not found"}, "/v1/audio/smart-cut", 404
        
        logger.info(f"Job {job_id}: Processing file {selected_file}")
        
        # Find the best hook point
        start_time = find_best_hook(file_path, duration_sec=duration)
        
        # Generate output filename
        base_name = os.path.splitext(selected_file)[0]
        output_filename = f"smartcut_{job_id}_{base_name}.mp3"
        output_path = os.path.join(tempfile.gettempdir(), output_filename)
        
        # Cut the audio using ffmpeg
        try:
            (
                ffmpeg
                .input(file_path, ss=start_time, t=duration)
                .output(output_path, acodec='libmp3lame', audio_bitrate='192k')
                .overwrite_output()
                .run(quiet=True)
            )
        except ffmpeg.Error as e:
            logger.error(f"FFmpeg error: {e}")
            return {"error": f"Failed to cut audio: {str(e)}"}, "/v1/audio/smart-cut", 500
        
        # Upload to S3
        s3_url = os.environ.get('S3_ENDPOINT_URL')
        access_key = os.environ.get('S3_ACCESS_KEY')
        secret_key = os.environ.get('S3_SECRET_KEY')
        bucket_name = os.environ.get('S3_BUCKET_NAME')
        region = os.environ.get('S3_REGION', 'us-east-1')
        
        if not all([s3_url, access_key, secret_key, bucket_name]):
            # Cleanup temp file
            if os.path.exists(output_path):
                os.remove(output_path)
            return {"error": "S3 configuration missing"}, "/v1/audio/smart-cut", 500

        uploaded_url = upload_to_s3(output_path, s3_url, access_key, secret_key, bucket_name, region)
        
        # Cleanup temp file
        if os.path.exists(output_path):
            os.remove(output_path)
        
        logger.info(f"Job {job_id}: Successfully processed and uploaded to {uploaded_url}")
        
        return {
            "url": uploaded_url,
            "original_file": selected_file,
            "start_time": round(start_time, 2),
            "duration": duration,
            "seed": seed
        }, "/v1/audio/smart-cut", 200
        
    except Exception as e:
        logger.error(f"Job {job_id}: Error in smart_cut_endpoint - {str(e)}")
        return {"error": str(e)}, "/v1/audio/smart-cut", 500
