"""Video capabilities."""

from .text_to_video import adapter  # noqa: F401  (registers text_to_video / ltx2-t2v)
from .image_to_video import adapter as _image_to_video_adapter  # noqa: F401  (registers image_to_video / ltx2-i2v)
