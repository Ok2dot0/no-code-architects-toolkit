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
import logging
from flask import Blueprint
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.cloud_storage import upload_file
from services.v1.audio.merge_tracks import (
    process_audio_merge_tracks,
    DEFAULT_TARGET_LUFS,
    MIN_TARGET_LUFS,
    MAX_TARGET_LUFS,
    DEFAULT_TRUE_PEAK,
    MIN_TRUE_PEAK,
    MAX_TRUE_PEAK,
    DEFAULT_LRA,
    MIN_LRA,
    MAX_LRA,
    MIN_GAIN_ADJUSTMENT,
    MAX_GAIN_ADJUSTMENT,
)

v1_audio_merge_tracks_bp = Blueprint('v1_audio_merge_tracks', __name__)
logger = logging.getLogger(__name__)


@v1_audio_merge_tracks_bp.route('/v1/audio/merge_tracks', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "file_url": {
            "type": "string",
            "format": "uri",
            "description": "URL of the media file with multiple audio tracks to merge"
        },
        "target_lufs": {
            "type": "number",
            "minimum": MIN_TARGET_LUFS,
            "maximum": MAX_TARGET_LUFS,
            "description": f"Target integrated loudness in LUFS. Default: {DEFAULT_TARGET_LUFS}"
        },
        "true_peak": {
            "type": "number",
            "minimum": MIN_TRUE_PEAK,
            "maximum": MAX_TRUE_PEAK,
            "description": f"Maximum true peak in dBTP. Default: {DEFAULT_TRUE_PEAK}"
        },
        "loudness_range": {
            "type": "number",
            "minimum": MIN_LRA,
            "maximum": MAX_LRA,
            "description": f"Target loudness range in LU. Default: {DEFAULT_LRA}"
        },
        "gain_adjustments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "track_id": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 15,
                        "description": "Audio track index (0-based)"
                    },
                    "gain_db": {
                        "type": "number",
                        "minimum": MIN_GAIN_ADJUSTMENT,
                        "maximum": MAX_GAIN_ADJUSTMENT,
                        "description": "Gain adjustment in dB for this track"
                    }
                },
                "required": ["track_id", "gain_db"]
            },
            "description": "Optional per-track gain adjustments applied before mixing"
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["file_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def audio_merge_tracks(job_id, data):
    """
    Merge all audio tracks from a media file into a single track with loudness normalization.
    
    This endpoint takes a video/audio file with multiple audio tracks and:
    1. Applies optional per-track gain adjustments
    2. Mixes all audio tracks into a single track
    3. Applies EBU R128 loudness normalization
    4. Outputs the file with video (if present) and the merged audio track
    """
    file_url = data['file_url']
    target_lufs = data.get('target_lufs', DEFAULT_TARGET_LUFS)
    true_peak = data.get('true_peak', DEFAULT_TRUE_PEAK)
    loudness_range = data.get('loudness_range', DEFAULT_LRA)
    gain_adjustments = data.get('gain_adjustments')
    
    logger.info(
        f"Job {job_id}: Merging audio tracks with target LUFS={target_lufs}, "
        f"true_peak={true_peak}, LRA={loudness_range}"
    )
    
    try:
        output_path = process_audio_merge_tracks(
            file_url,
            job_id,
            target_lufs=target_lufs,
            true_peak=true_peak,
            loudness_range=loudness_range,
            gain_adjustments=gain_adjustments,
        )
        
        logger.info(f"Job {job_id}: Audio tracks merged successfully")
        
        # Upload to cloud storage
        cloud_url = upload_file(output_path)
        logger.info(f"Job {job_id}: Merged file uploaded to {cloud_url}")
        
        # Clean up local file
        if os.path.exists(output_path):
            os.remove(output_path)
        
        return cloud_url, "/v1/audio/merge_tracks", 200
        
    except Exception as e:
        logger.error(f"Job {job_id}: Error merging audio tracks - {str(e)}")
        return str(e), "/v1/audio/merge_tracks", 500
