# Copyright (C) 2025 Xiaomi Corporation
# This software may be used and distributed according to the terms of the Xiaomi Miloco License Agreement.

"""Image processing utilities."""
from io import BytesIO
from typing import Tuple
from PIL import Image
from miloco_ai_engine.middleware.exceptions import InvalidArgException

class ImageProcess:
    """Image processing utilities."""

    @staticmethod
    def save_image(image_data: bytes, image_path: str):
        with open(image_path, "wb") as f:
            f.write(image_data)

    @staticmethod
    def read_image(image_path: str) -> bytes:
        with open(image_path, "rb") as f:
            return f.read()

    @staticmethod
    def resize_low_precision(
        image_data: bytes,
        target_size: Tuple[int, int],
        fmt: str = "JPEG",
        quality: int = 60,
        colors: int = 128,
    ) -> bytes:
        """
        Compress and resize input image bytes to specified dimensions with low precision.

        Parameters:
        - image_data: Input raw image bytes
        - target_size: (width, height) target dimensions in pixels
        - fmt: Output format, default JPEG, options: JPEG/PNG/WEBP
        - quality: Lossy format quality (1-95), lower value means higher compression
        - colors: Color palette size limit for lossless formats like PNG (typical: 64/128/256)
        """
        width, height = target_size
        with BytesIO(image_data) as bio:
            with Image.open(bio) as img:
                # Correct image orientation
                try:
                    img = Image.Image.transpose(img, Image.Transpose.EXIF)
                except Exception: # pylint: disable=broad-exception-caught
                    pass

                # Resize (LANCZOS high-quality downsampling)
                img = img.convert("RGBA") if img.mode == "P" else img
                resized = img.resize((width, height), Image.Resampling.LANCZOS)

                out = BytesIO()
                fmt_upper = fmt.upper()

                if fmt_upper == "JPEG":
                    # JPEG requires three channels
                    rgb = resized.convert("RGB")
                    rgb.save(
                        out,
                        format="JPEG",
                        quality=max(1, min(95, quality)),
                        optimize=True,
                        progressive=True,
                        subsampling="4:2:0",
                    )
                elif fmt_upper == "PNG":
                    # Quantize PNG to palette to reduce size
                    paletted = resized.convert("P",
                                               palette=Image.Palette.ADAPTIVE,
                                               colors=max(2, min(256, colors)))
                    paletted.save(out, format="PNG", optimize=True)
                elif fmt_upper == "WEBP":
                    # WebP supports both lossy and lossless, use lossy for smaller size
                    webp_src = resized.convert("RGB")
                    webp_src.save(
                        out,
                        format="WEBP",
                        quality=max(1, min(95, quality)),
                        method=6,
                        exact=False,
                    )
                else:
                    # Fallback to JPEG
                    rgb = resized.convert("RGB")
                    rgb.save(
                        out,
                        format="JPEG",
                        quality=max(1, min(95, quality)),
                        optimize=True,
                        progressive=True,
                        subsampling="4:2:0",
                    )

                return out.getvalue()

    @staticmethod
    def center_crop_to_size(
        image_data: bytes,
        target_size: Tuple[int, int],
        fmt: str = "JPEG",
        quality: int = 85,
        colors: int = 128,
    ) -> bytes:
        """
        Center crop to target aspect ratio, then resize to fixed dimensions and output bytes.

        - First crop from center to maximum content area matching target aspect ratio
        - Then use LANCZOS to resize to exact target dimensions
        - Save in specified format (JPEG/PNG/WEBP), parameters consistent with resize_low_precision
        """
        target_width, target_height = target_size
        target_ratio = target_width / float(target_height)

        with BytesIO(image_data) as bio:
            with Image.open(bio) as img:
                # Correct orientation
                try:
                    img = Image.Image.transpose(img, Image.Transpose.EXIF)
                except Exception: # pylint: disable=broad-exception-caught
                    pass

                src_width, src_height = img.width, img.height
                if src_width == 0 or src_height == 0:
                    raise InvalidArgException(
                        "Invalid image size: width/height is zero")

                src_ratio = src_width / float(src_height)

                # Calculate center crop box
                if src_ratio > target_ratio:
                    # Image is wider: align by height, crop left and right
                    new_width = int(round(src_height * target_ratio))
                    new_height = src_height
                else:
                    # Image is taller or equal: align by width, crop top and bottom
                    new_width = src_width
                    new_height = int(round(src_width / target_ratio))

                left = int(round((src_width - new_width) / 2))
                top = int(round((src_height - new_height) / 2))
                right = left + new_width
                bottom = top + new_height

                cropped = img.crop((left, top, right, bottom))

                # Resize to fixed dimensions
                resized = cropped.resize((target_width, target_height), Image.Resampling.LANCZOS)

                out = BytesIO()
                fmt_upper = fmt.upper()

                if fmt_upper == "JPEG":
                    rgb = resized.convert("RGB")
                    rgb.save(
                        out,
                        format="JPEG",
                        quality=max(1, min(95, quality)),
                        optimize=True,
                        progressive=True,
                        subsampling="4:2:0",
                    )
                elif fmt_upper == "PNG":
                    paletted = resized.convert(
                        "P", palette=Image.Palette.ADAPTIVE, colors=max(2, min(256, colors))
                    )
                    paletted.save(out, format="PNG", optimize=True)
                elif fmt_upper == "WEBP":
                    webp_src = resized.convert("RGB")
                    webp_src.save(
                        out,
                        format="WEBP",
                        quality=max(1, min(95, quality)),
                        method=6,
                        exact=False,
                    )
                else:
                    rgb = resized.convert("RGB")
                    rgb.save(
                        out,
                        format="JPEG",
                        quality=max(1, min(95, quality)),
                        optimize=True,
                        progressive=True,
                        subsampling="4:2:0",
                    )

                return out.getvalue()
