"""Download a product image without following an unsafe network path."""

import ipaddress
import socket
import struct
import zlib
from urllib.parse import urljoin, urlparse

import requests

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_IMAGE_EDGE = 8000
MAX_REDIRECTS = 3


class ImageFetchError(Exception):
    def __init__(self, english, arabic):
        super().__init__(english)
        self.english = english
        self.arabic = arabic


def _public_address(value):
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def assert_public_http_url(url):
    parsed = urlparse(url)
    host = (parsed.hostname or "").strip().lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
        raise ImageFetchError("unsafe image URL", "رابط الصورة غير آمن")
    if host in {"localhost", "metadata.google.internal"} or host.endswith((".local", ".internal", ".localhost")):
        raise ImageFetchError("unsafe image URL", "رابط الصورة غير آمن")
    try:
        literal = ipaddress.ip_address(host)
        addresses = [str(literal)]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80))
        except socket.gaierror as exc:
            raise ImageFetchError("image URL could not be resolved", "تعذر الوصول إلى رابط الصورة") from exc
        addresses = list({item[4][0] for item in infos})
    if not addresses or any(not _public_address(item) for item in addresses):
        raise ImageFetchError("unsafe image URL", "رابط الصورة غير آمن")
    return parsed


def sniff_image(data):
    if not isinstance(data, (bytes, bytearray)) or len(data) < 16 or len(data) > MAX_IMAGE_BYTES:
        return None
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return "png" if _edge_ok(width, height) else None
    if data.startswith(b"\xff\xd8\xff"):
        size = _jpeg_size(data)
        return "jpg" if size and _edge_ok(*size) else None
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        size = _webp_size(data)
        return "webp" if size and _edge_ok(*size) else None
    return None


def _edge_ok(width, height):
    return 1 <= width <= MAX_IMAGE_EDGE and 1 <= height <= MAX_IMAGE_EDGE


def _jpeg_size(data):
    index = 2
    while index + 9 < len(data):
        if data[index] != 0xFF:
            index += 1
            continue
        marker = data[index + 1]
        if marker in {0xC0, 0xC1, 0xC2}:
            height, width = struct.unpack(">HH", data[index + 5:index + 9])
            return width, height
        if marker == 0xD8 or marker == 0xD9:
            index += 2
            continue
        if index + 4 > len(data):
            return None
        length = struct.unpack(">H", data[index + 2:index + 4])[0]
        if length < 2:
            return None
        index += 2 + length
    return None


def _webp_size(data):
    if len(data) < 30:
        return None
    chunk = data[12:16]
    if chunk == b"VP8X" and len(data) >= 30:
        width = 1 + int.from_bytes(data[24:27], "little")
        height = 1 + int.from_bytes(data[27:30], "little")
        return width, height
    if chunk == b"VP8 " and len(data) >= 30:
        width, height = struct.unpack("<HH", data[26:30])
        return width & 0x3FFF, height & 0x3FFF
    if chunk == b"VP8L" and len(data) >= 25:
        bits = int.from_bytes(data[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    return None


def download_product_image(url):
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        assert_public_http_url(current)
        try:
            response = requests.get(
                current,
                stream=True,
                timeout=(3, 8),
                allow_redirects=False,
                headers={"User-Agent": "RiwaqImport/1.0"},
            )
        except requests.Timeout as exc:
            raise ImageFetchError("image request timed out", "انتهت مهلة تنزيل الصورة") from exc
        except requests.RequestException as exc:
            raise ImageFetchError("image URL could not be downloaded", "تعذر تنزيل الصورة") from exc
        if response.status_code in {301, 302, 303, 307, 308}:
            location = response.headers.get("Location")
            response.close()
            if not location:
                raise ImageFetchError("image URL could not be downloaded", "تعذر تنزيل الصورة")
            current = urljoin(current, location)
            continue
        if response.status_code != 200:
            response.close()
            raise ImageFetchError("image URL could not be downloaded", "تعذر تنزيل الصورة")
        chunks = []
        total = 0
        try:
            for chunk in response.iter_content(65536):
                if not chunk:
                    continue
                total += len(chunk)
                if total > MAX_IMAGE_BYTES:
                    raise ImageFetchError("image is too large", "الصورة أكبر من الحد المسموح")
                chunks.append(chunk)
        finally:
            response.close()
        data = b"".join(chunks)
        kind = sniff_image(data)
        if not kind:
            raise ImageFetchError("unsupported or corrupted image", "صورة غير مدعومة أو تالفة")
        return data, kind
    raise ImageFetchError("image URL could not be downloaded", "تعذر تنزيل الصورة")


def tiny_png(width=2, height=2):
    """A valid PNG used by tests. Not part of the import path."""
    raw = b"".join(b"\x00" + b"\x00\x00\x00" * width for _ in range(height))

    def chunk(tag, payload):
        return struct.pack(">I", len(payload)) + tag + payload + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")
