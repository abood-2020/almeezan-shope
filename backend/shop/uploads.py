from django.core.exceptions import ValidationError

IMAGE_TYPES = {
    "logo": {".png", ".jpg", ".jpeg", ".webp", ".svg"},
    "favicon": {".png", ".jpg", ".jpeg", ".webp", ".svg", ".ico"},
    "poster": {".png", ".jpg", ".jpeg", ".webp"},
    "og": {".png", ".jpg", ".jpeg", ".webp"},
}
IMAGE_LIMIT = 2 * 1024 * 1024
FAVICON_LIMIT = 512 * 1024
VIDEO_LIMIT = 25 * 1024 * 1024
UPLOAD_FIELDS = {
    "logo": "logo",
    "favicon": "favicon",
    "og_image": "og",
    "hero_poster": "poster",
    "hero_video": "video",
}


def _extension(upload):
    name = (upload.name or "").lower()
    dot = name.rfind(".")
    return name[dot:] if dot >= 0 else ""


def _head(upload, size=32):
    upload.seek(0)
    data = upload.read(size)
    upload.seek(0)
    return data


def validate_public_upload(upload, kind):
    if upload is None:
        return
    extension = _extension(upload)
    if kind == "video":
        if extension not in {".mp4", ".webm"} or upload.size > VIDEO_LIMIT:
            raise ValidationError({"hero_video": "Upload an mp4 or webm file up to 25 MB."})
        header = _head(upload, 16)
        if extension == ".webm" and not header.startswith(b"\x1a\x45\xdf\xa3"):
            raise ValidationError({"hero_video": "The file is not a valid webm video."})
        if extension == ".mp4" and b"ftyp" not in header:
            raise ValidationError({"hero_video": "The file is not a valid mp4 video."})
        return
    allowed = IMAGE_TYPES[kind]
    limit = FAVICON_LIMIT if kind == "favicon" else IMAGE_LIMIT
    field = {value: key for key, value in UPLOAD_FIELDS.items()}.get(kind, kind)
    if extension not in allowed or upload.size > limit:
        raise ValidationError({field: "Upload a supported image within the size limit."})
    header = _head(upload, 64)
    if extension in {".jpg", ".jpeg"} and not header.startswith(b"\xff\xd8"):
        raise ValidationError({field: "The file is not a valid JPEG image."})
    if extension == ".png" and not header.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValidationError({field: "The file is not a valid PNG image."})
    if extension == ".webp" and not (header.startswith(b"RIFF") and header[8:12] == b"WEBP"):
        raise ValidationError({field: "The file is not a valid WebP image."})
    if extension == ".ico" and not header.startswith(b"\x00\x00\x01\x00"):
        raise ValidationError({field: "The file is not a valid icon."})
    if extension == ".svg":
        upload.seek(0)
        text = upload.read(200_000).decode("utf-8", errors="ignore").lower()
        upload.seek(0)
        if "<svg" not in text or any(token in text for token in ("<script", "javascript:", "onload=", "onerror=", "foreignobject")):
            raise ValidationError({field: "This SVG file is not allowed."})
