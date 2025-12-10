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

import logging
from flask import Blueprint
from app_utils import validate_payload, queue_task_wrapper
from services.authentication import authenticate
from services.v1.audio.probe import process_audio_probe

v1_audio_probe_bp = Blueprint('v1_audio_probe', __name__)
logger = logging.getLogger(__name__)


@v1_audio_probe_bp.route('/v1/audio/probe', methods=['POST'])
@authenticate
@validate_payload({
    "type": "object",
    "properties": {
        "file_url": {
            "type": "string",
            "format": "uri",
            "description": "URL of the media file to probe for audio track information"
        },
        "webhook_url": {"type": "string", "format": "uri"},
        "id": {"type": "string"}
    },
    "required": ["file_url"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def audio_probe(job_id, data):
    """
    Probe a media file and return detailed information about all audio tracks.
    
    Returns information including:
    - Number of audio tracks
    - Codec, sample rate, channels, bitrate for each track
    - Language and title metadata if available
    """
    file_url = data['file_url']
    
    logger.info(f"Job {job_id}: Probing audio tracks for {file_url}")
    
    try:
        result = process_audio_probe(file_url, job_id)
        logger.info(f"Job {job_id}: Found {result['track_count']} audio track(s)")
        return result, "/v1/audio/probe", 200
        
    except Exception as e:
        logger.error(f"Job {job_id}: Error probing audio tracks - {str(e)}")
        return str(e), "/v1/audio/probe", 500
