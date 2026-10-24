"""Local webcam source (USB or built-in camera on the worker machine), selected by OpenCV device index.

Only a small integer index is accepted (no device paths, URLs or shell strings). The worker opens the
device; browsers still receive worker-published JPEG previews, exactly like RTSP sources. This works
only when the worker runs on the computer the webcam is plugged into (not inside Docker).
"""
import os
import time

import cv2

from .adapters import Frame

MAX_INDEX = 9


def parse_webcam_index(value) -> int:
    """'0'..'9' -> int; anything else raises ValueError('webcam_index_invalid')."""
    text = str(value).strip()
    if not text.isdigit() or not 0 <= int(text) <= MAX_INDEX:
        raise ValueError("webcam_index_invalid")
    return int(text)


class WebcamAdapter:
    def __init__(self, index, timeout=5):
        self.index = parse_webcam_index(index)
        self.timeout = timeout
        self.cap = None
        self.sequence = 0

    def open(self):
        # DirectShow opens quickly and honours a 1-frame buffer on Windows; elsewhere let OpenCV choose.
        backend = cv2.CAP_DSHOW if os.name == "nt" else cv2.CAP_ANY
        self.cap = cv2.VideoCapture(self.index, backend)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)   # keep latency low when the worker reads slower than the camera
        self.sequence = 0
        return self.cap.isOpened()

    def read(self):
        self.cap.grab()                            # drop one possibly-buffered old frame
        ok, image = self.cap.read()
        if not ok or image is None:
            return None
        h, w = image.shape[:2]
        self.sequence += 1
        return Frame(image, time.time(), w, h, self.sequence)

    def close(self):
        if self.cap:
            self.cap.release()
            self.cap = None
