"""Validate image bytes before writing them to the private upload directory."""

from io import BytesIO
import os
from pathlib import Path
import uuid
import warnings

from PIL import Image, UnidentifiedImageError

MAX_FILE_BYTES = int(os.environ.get("MAX_UPLOAD_BYTES", "15728640"))
MAX_REQUEST_BYTES = MAX_FILE_BYTES * 2 + 65536
MAX_PIXELS = int(os.environ.get("MAX_IMAGE_PIXELS", "24000000"))
FORMATS = {".jpg": "JPEG", ".jpeg": "JPEG", ".png": "PNG", ".webp": "WEBP", ".bmp": "BMP"}


def save_image(field, directory: Path) -> Path:
    extension = Path(field.filename).suffix.lower()
    if extension not in FORMATS:
        raise ValueError("Formato nao suportado. Use PNG, JPG, WEBP ou BMP.")
    data = field.file.read(MAX_FILE_BYTES + 1)
    if not data or len(data) > MAX_FILE_BYTES:
        raise ValueError("Arquivo vazio ou acima do limite de upload.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != FORMATS[extension]:
                    raise ValueError("Conteudo da imagem nao corresponde a extensao.")
                if image.width * image.height > MAX_PIXELS:
                    raise ValueError("Resolucao acima do limite permitido.")
                if getattr(image, "n_frames", 1) != 1:
                    raise ValueError("Imagens animadas ou multipagina nao sao aceitas.")
                image.verify()
            with Image.open(BytesIO(data)) as image:
                image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ValueError("Imagem invalida, truncada ou acima do limite de pixels.") from exc
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{uuid.uuid4().hex}{extension}"
    with path.open("xb") as output:
        output.write(data)
    return path
