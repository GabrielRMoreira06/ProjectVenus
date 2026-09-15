"""
ImageUtils.py

Conversions between PIL.Image (what GeminiWorker/ChatHistory work
with) and Qt's QImage/QPixmap (what actually renders on screen).
Shared by MessageComposer (pasting an image in) and PanelWindow
(showing a thumbnail of one that was sent) — previously each defined
its own copy of one direction of this conversion.
"""

from io import BytesIO

from PIL import Image
from PyQt6.QtCore import QByteArray, QBuffer
from PyQt6.QtGui import QImage, QPixmap


def qimage_to_pil(qimage: QImage) -> Image.Image:
    """Converts a QImage (e.g. from the clipboard) into a PIL.Image."""
    buffer = QByteArray()
    qbuffer = QBuffer(buffer)
    qbuffer.open(QBuffer.OpenModeFlag.WriteOnly)
    qimage.save(qbuffer, "PNG")
    qbuffer.close()

    return Image.open(BytesIO(bytes(buffer))).convert("RGB")


def pil_to_qpixmap(pil_image: Image.Image) -> QPixmap:
    """
    Converts a PIL.Image into a QPixmap for display. .copy() detaches
    the QImage from the raw bytes buffer, which may otherwise be
    garbage-collected once this function returns.
    """
    if pil_image.mode != "RGB":
        pil_image = pil_image.convert("RGB")

    data = pil_image.tobytes("raw", "RGB")
    qimage = QImage(
        data, pil_image.width, pil_image.height,
        pil_image.width * 3, QImage.Format.Format_RGB888,
    ).copy()

    return QPixmap.fromImage(qimage)
