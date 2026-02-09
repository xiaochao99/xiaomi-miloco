# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""
Image motion detection utility.
Provides functionality to detect motion between images using DHash algorithm.
"""

import io
import logging
from typing import Optional

import imagehash
from PIL import Image

logger = logging.getLogger(name=__name__)

HASH_SIZE = 16
THRESHOLD = 5


class CheckImgMotionByDHash:
    """Image motion detection using DHash algorithm"""

    @staticmethod
    def _calculate_dhash(image_src) -> Optional[imagehash.ImageHash]:
        """Calculate DHash value of image using imagehash library"""
        try:
            if isinstance(image_src, bytes):
                img = Image.open(io.BytesIO(image_src))
            else:
                img = Image.open(image_src)
            return imagehash.dhash(img, hash_size=HASH_SIZE)
        except Exception as e:  # pylint: disable=broad-exception-caught
            logger.error("Error calculating DHash: %s", e)
            return None

    @staticmethod
    def is_image_changed(image1_src, image2_src) -> tuple[bool, int]:
        """
        Check if two images have changed
        """
        hash1 = CheckImgMotionByDHash._calculate_dhash(image1_src)
        hash2 = CheckImgMotionByDHash._calculate_dhash(image2_src)
        if hash1 is None or hash2 is None:
            return (False, -1)  # Processing failed
        # Calculate Hamming distance, imagehash library supports direct hash subtraction
        distance = hash1 - hash2
        changed = distance > THRESHOLD
        return (changed, distance)


def check_camera_motion(image1_src, image2_src) -> bool:
    """
    Check if camera image has changed
    """
    motion, _ = CheckImgMotionByDHash.is_image_changed(image1_src, image2_src)
    return motion
