"""
tools/media.py - WeCom AI Bot media upload/download utilities

Provides:
- upload_media: upload temporary media (image/voice/video/file) → media_id
- download_media: download and decrypt a file from message URL → local file

Based on wecom-aibot-sdk WSClient.
"""

import logging
from pathlib import Path

from wecom_mcp.auth import get_client

logger = logging.getLogger(__name__)

MEDIA_TYPES = {"image", "voice", "video", "file"}


async def upload_media(
    file_path: str,
    media_type: str = "file",
) -> dict:
    """
    Upload a temporary media file via WebSocket channel (chunked upload).

    Args:
        file_path: Absolute path to the local file.
        media_type: Media type: image, voice, video, file.

    Returns:
        dict with type, media_id, created_at.
    """
    if media_type not in MEDIA_TYPES:
        raise ValueError(
            f"Invalid media_type: {media_type}. Must be one of {list(MEDIA_TYPES)}"
        )

    p = Path(file_path)
    if not p.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")

    client = await get_client()

    with open(p, "rb") as f:
        file_data = f.read()

    logger.info("Uploading media: type=%s, file=%s (%d bytes)", media_type, p.name, len(file_data))
    result = await client.upload_media(file_data, type=media_type, filename=p.name)

    media_id = result.get("media_id", "")
    logger.info("Media uploaded: media_id=%s", media_id[:16] if media_id else "N/A")
    return result


async def download_media(
    url: str,
    save_dir: str = ".",
    file_name: str = "",
    aes_key: str = "",
) -> dict:
    """
    Download and decrypt a media file (image/file from message).

    AI Bot message media URLs are AES-encrypted; the SDK handles decryption.

    Args:
        url: Encrypted media URL from the message frame.
        save_dir: Directory to save the file. Default: current directory.
        file_name: Desired filename. If empty, uses the name from the response.
        aes_key: AES key from the message frame (image.aeskey / file.aeskey).

    Returns:
        dict with file_path, file_size.
    """
    client = await get_client()

    logger.info("Downloading media from encrypted URL...")
    result = await client.download_file(url, aes_key if aes_key else None)

    buffer = result.get("buffer", b"")
    detected_name = result.get("filename", "")

    save_path = Path(save_dir)
    save_path.mkdir(parents=True, exist_ok=True)

    if not file_name:
        file_name = detected_name or f"downloaded_{len(buffer)}"

    out_path = save_path / file_name
    out_path.write_bytes(buffer)

    file_size = len(buffer)
    logger.info("Media downloaded: path=%s, size=%d", out_path, file_size)
    return {
        "file_path": str(out_path),
        "file_size": file_size,
    }
