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



from flask import Blueprint
from app_utils import *
import logging
from services.v1.video.concatenate import (
    process_video_concatenate,
    SUPPORTED_TRANSITION_TYPES,
    DEFAULT_TRANSITION_TYPE,
    DEFAULT_TRANSITION_DURATION,
    MIN_TRANSITION_DURATION,
    MAX_TRANSITION_DURATION,
    DEFAULT_WHIP_PAN_SFX_GAIN_DB,
    MIN_WHIP_PAN_SFX_GAIN_DB,
    MAX_WHIP_PAN_SFX_GAIN_DB,
    DEFAULT_TRANSITION_SFX_TRACK_ID,
    MIN_TRANSITION_SFX_TRACK_ID,
    MAX_TRANSITION_SFX_TRACK_ID,
)
from services.authentication import authenticate
from services.cloud_storage import upload_file

v1_video_concatenate_bp = Blueprint('v1_video_concatenate', __name__)
logger = logging.getLogger(__name__)

@v1_video_concatenate_bp.route('/v1/video/concatenate', methods=['POST'])
@authenticate
@validate_payload({
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
            "enum": list(SUPPORTED_TRANSITION_TYPES.keys())
        },
        "transition_duration": {
            "type": "number",
            "minimum": MIN_TRANSITION_DURATION,
            "maximum": MAX_TRANSITION_DURATION
        },
        "transition_sequence": {
            "type": "array",
            "items": {
                "type": "string",
                "enum": [
                    key for key in SUPPORTED_TRANSITION_TYPES.keys() if key != "none"
                ],
            },
            "minItems": 1
        },
        "whip_pan_sfx_gain_db": {
            "type": "number",
            "minimum": MIN_WHIP_PAN_SFX_GAIN_DB,
            "maximum": MAX_WHIP_PAN_SFX_GAIN_DB,
        },
        "transition_sfx_track_id": {
            "type": "integer",
            "minimum": MIN_TRANSITION_SFX_TRACK_ID,
            "maximum": MAX_TRANSITION_SFX_TRACK_ID,
            "description": "Audio track index (0-15) to place transition sound effects. If not specified, SFX is mixed into main audio."
        },
    },
    "required": ["video_urls"],
    "additionalProperties": False
})
@queue_task_wrapper(bypass_queue=False)
def combine_videos(job_id, data):
    media_urls = data['video_urls']
    webhook_url = data.get('webhook_url')
    id = data.get('id')
    transition_type = data.get('transition_type', DEFAULT_TRANSITION_TYPE)
    transition_duration = data.get('transition_duration', DEFAULT_TRANSITION_DURATION)
    transition_sequence = data.get('transition_sequence')
    whip_pan_sfx_gain_db = data.get('whip_pan_sfx_gain_db', DEFAULT_WHIP_PAN_SFX_GAIN_DB)
    transition_sfx_track_id = data.get('transition_sfx_track_id', DEFAULT_TRANSITION_SFX_TRACK_ID)

    if transition_sequence is not None:
        expected_transitions = max(len(media_urls) - 1, 0)
        if expected_transitions == 0:
            return (
                "transition_sequence requires at least two video_urls.",
                "/v1/video/concatenate",
                400,
            )
        if len(transition_sequence) != expected_transitions:
            return (
                (
                    "transition_sequence must include exactly "
                    f"{expected_transitions} entries (one per clip boundary)."
                ),
                "/v1/video/concatenate",
                400,
            )

    logger.info(
        f"Job {job_id}: Received combine-videos request for {len(media_urls)} videos "
        f"with transition '{transition_type}'"
    )

    try:
        output_file = process_video_concatenate(
            media_urls,
            job_id,
            transition_type=transition_type,
            transition_duration=transition_duration,
            transition_sequence=transition_sequence,
            whip_pan_sfx_gain_db=whip_pan_sfx_gain_db,
            transition_sfx_track_id=transition_sfx_track_id,
        )
        logger.info(f"Job {job_id}: Video combination process completed successfully")

        cloud_url = upload_file(output_file)
        logger.info(f"Job {job_id}: Combined video uploaded to cloud storage: {cloud_url}")

        return cloud_url, "/v1/video/concatenate", 200

    except Exception as e:
        logger.error(f"Job {job_id}: Error during video combination process - {str(e)}")
        return str(e), "/v1/video/concatenate", 500