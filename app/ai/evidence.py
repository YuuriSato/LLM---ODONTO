from pathlib import Path
from typing import Callable

import numpy as np
from PIL import Image, ImageChops, ImageFilter, JpegImagePlugin

from app import local_forensics as local
from app.ai.config import SCHEMA_VERSION
from app.ai.detector import DisabledDetector, ExternalDetector
from app.ai.schemas import EvidenceRecord, LocalEvidence


def noise_blocks(path: Path) -> dict:
    image = local.open_rgb(path, max_side=768).convert("L")
    residual = np.asarray(ImageChops.difference(image, image.filter(ImageFilter.GaussianBlur(1.2))), dtype=np.float32)
    height, width = residual.shape
    step_y, step_x = max(1, height // 6), max(1, width // 6)
    blocks = []
    for y in range(0, height - step_y + 1, step_y):
        for x in range(0, width - step_x + 1, step_x):
            blocks.append({"x": x, "y": y, "width": step_x, "height": step_y,
                           "std": round(float(np.std(residual[y:y + step_y, x:x + step_x])), 3)})
    return {"analysis_width": width, "analysis_height": height, "blocks": blocks}


def fft_metrics(path: Path) -> dict:
    gray = local.image_to_gray_array(path).astype(np.float64)
    height, width = gray.shape
    window = np.outer(np.hanning(height), np.hanning(width))
    spectrum = np.fft.fftshift(np.fft.fft2((gray - gray.mean()) * window))
    power = np.abs(spectrum) ** 2
    yy, xx = np.meshgrid(np.fft.fftshift(np.fft.fftfreq(height)), np.fft.fftshift(np.fft.fftfreq(width)), indexing="ij")
    radius = np.sqrt(xx ** 2 + yy ** 2) / np.sqrt(0.5)
    bins = np.linspace(0, 1, 17)
    total = float(power.sum())
    radial = np.histogram(radius, bins=bins, weights=power)[0]
    return {
        "analysis_width": width, "analysis_height": height,
        "total_energy": total,
        "radial_bin_edges": bins.tolist(),
        "radial_energy_fraction": (radial / total).tolist() if total > 1e-12 else None,
        "low_energy_fraction": float(power[radius < 0.25].sum() / total) if total > 1e-12 else None,
        "mid_energy_fraction": float(power[(radius >= 0.25) & (radius < 0.5)].sum() / total) if total > 1e-12 else None,
        "high_energy_fraction": float(power[radius >= 0.5].sum() / total) if total > 1e-12 else None,
    }


def metadata_metrics(path: Path) -> dict:
    with Image.open(path) as image:
        exif = image.getexif()
        return {
            "format": image.format, "width": image.width, "height": image.height,
            "mode": image.mode, "exif_present": bool(exif), "exif_tag_count": len(exif),
            "orientation": exif.get(274), "software": str(exif[305]) if 305 in exif else None,
            "icc_present": bool(image.info.get("icc_profile")),
            "transport_conversion": "BMP_to_PNG_lossless" if image.format == "BMP" else None,
        }


def compression_metrics(path: Path) -> dict:
    with Image.open(path) as image:
        quantization = getattr(image, "quantization", None)
        return {
            "format": image.format, "file_bytes": path.stat().st_size,
            "bytes_per_pixel": path.stat().st_size / (image.width * image.height),
            "jpeg_quantization": {str(k): v for k, v in quantization.items()} if quantization else None,
            "jpeg_sampling": JpegImagePlugin.get_sampling(image) if image.format == "JPEG" else None,
            "jpeg_status": "disponivel" if image.format == "JPEG" else "nao_aplicavel",
        }


def collect_evidence(image: Path, analysis_id: str, reference: Path | None = None,
                     calibration: dict | None = None, detector: ExternalDetector | None = None) -> LocalEvidence:
    records: list[EvidenceRecord] = []
    observations: list[str] = []
    limitations = ["Metricas e limiares locais sao heuristicos; nao provam autoria por IA."]

    def measure(identifier: str, family: str, method: str, fn: Callable, parameters=None, notes=None):
        try:
            record = EvidenceRecord(id=identifier, family=family, status="disponivel", method=method,
                                    parameters=parameters or {}, values=fn(), limitations=notes or [])
        except Exception as exc:
            record = EvidenceRecord(id=identifier, family=family, status="falhou", method=method,
                                    parameters=parameters or {}, signal="desconhecido",
                                    limitations=[f"Extracao falhou ({type(exc).__name__})."])
        records.append(record)
        return record

    dimensions = measure("dimensoes", "qualidade", "dimensoes apos orientacao EXIF", lambda: local.image_dimension_metrics(image))
    ela = measure("ela", "compressao", "diferenca apos recompressao JPEG", lambda: local.ela_metrics(image),
                  {"max_side": 768, "jpeg_quality": 88}, ["ELA anormal nao prova IA; conversao de formato afeta o resultado."])
    sharpness = measure("nitidez", "textura", "variancia do Laplaciano global e blocos", lambda: local.sharpness_metrics(image), {"max_side": 768, "block_count": 6})
    noise = measure("ruido", "textura", "residuo absoluto de filtro gaussiano", lambda: local.noise_metrics(image), {"max_side": 768, "sigma": 1.2, "block_count": 6})
    measure("ruido_blocos", "textura", "desvio padrao do residuo por bloco", lambda: noise_blocks(image),
            {"max_side": 768, "sigma": 1.2, "block_count": 6}, ["Coordenadas na imagem de analise reduzida; mesma origem do ruido global."])
    measure("fft", "frequencia", "FFT 2D com janela Hann e remocao da media", lambda: fft_metrics(image),
            {"max_side": 768, "radial_bins": 16}, ["Descritivo, sem limiar validado de IA. Energia normalizada ausente em imagem constante."])
    measure("compressao", "compressao", "inspecao do arquivo e tabelas JPEG", lambda: compression_metrics(image),
            notes=["Compressao e ELA sao correlacionados; nao constituem duas confirmacoes."])
    measure("metadata", "metadata", "cabecalho e EXIF tecnico", lambda: metadata_metrics(image),
            notes=["Ausencia de EXIF nao e prova de IA. Dados pessoais de EXIF nao sao incluidos."])
    overlay = measure("sobreposicao", "sobreposicao", "mascaras de cor e regioes", lambda: local.overlay_metrics(image))

    quality = "desconhecida"
    if dimensions.status == sharpness.status == "disponivel":
        quality_result = local.quality_assessment({**dimensions.values, **sharpness.values})
        quality = quality_result["quality_status"]
        observations.extend(quality_result["quality_reasons"])
        records.append(EvidenceRecord(id="qualidade", family="qualidade", status="disponivel",
                                      method="heuristica local de qualidade", values=quality_result))
    else:
        limitations.append("Qualidade nao pode ser avaliada integralmente.")

    def signal(record, abnormal, text):
        if record.status == "disponivel":
            record.signal = "anomalia" if abnormal else "sem_anomalia"
            if abnormal:
                observations.append(text)

    signal(ela, ela.values.get("ela_block_cv", 0) >= 0.35 and ela.values.get("ela_p95", 0) >= 5,
           "Recompressao irregular entre regioes; pode refletir compressao ou edicao.")
    signal(sharpness, sharpness.values.get("sharpness_block_cv", 0) >= 1.15, "Nitidez inconsistente entre regioes.")
    signal(noise, noise.values.get("noise_block_cv", 0) >= 0.95, "Ruido inconsistente entre regioes.")
    signal(overlay, overlay.values.get("green_marker_ratio", 0) >= 0.00035 or overlay.values.get("marker_overlay_ratio", 0) >= 0.0008 or overlay.values.get("saturated_overlay_ratio", 0) >= 0.002,
           "Agrupamentos coloridos compativeis com sobreposicao; requerem confirmacao visual.")

    if reference is not None:
        comparison = measure("comparacao", "comparacao", "dHash e diferenca apos ajuste central", lambda: local.compare_with_original(image, reference),
                             {"max_side": 768}, ["Sem registro geometrico robusto; diferencas nao identificam a tecnologia de edicao."])
        values = comparison.values
        if comparison.status == "disponivel" and values["same_scene"]:
            signal(comparison, values["central_mean_diff"] >= 8 or values["dhash_distance"] > 10,
                   "Diferencas com referencia; angulo, compressao ou edicao podem contribuir.")
        else:
            comparison.signal = "desconhecido"
            comparison.limitations.append("Comparacao nao conclusiva: cenas distintas ou extracao indisponivel.")
    else:
        records.append(EvidenceRecord(id="comparacao", family="comparacao", status="ausente", method="comparacao com referencia",
                                      limitations=["Imagem de referencia nao fornecida."], signal="desconhecido"))

    try:
        detected = (detector or DisabledDetector()).analyze(image)
        if detected.status == "disponivel" and (detected.score is None or not detected.scale or not detected.provider or not detected.version):
            raise ValueError("Detector sem proveniencia ou escala.")
        records.append(EvidenceRecord(id="detector_ia", family="detector", status=detected.status,
                                      method="detector externo", values=detected.model_dump(mode="json"),
                                      limitations=detected.limitations,
                                      signal="anomalia" if detected.status == "disponivel" and detected.conclusion == "alto" else
                                      "sem_anomalia" if detected.status == "disponivel" and detected.conclusion == "baixo" else "desconhecido"))
    except Exception as exc:
        records.append(EvidenceRecord(id="detector_ia", family="detector", status="falhou", method="detector externo",
                                      signal="desconhecido", limitations=[f"Detector indisponivel ({type(exc).__name__})."]))

    digest = local.file_sha256(image)
    entry = (calibration or {}).get(digest)
    if entry:
        records.append(EvidenceRecord(id="calibracao", family="historico", status="disponivel", method="rotulo humano anterior por SHA256",
                                      values={"label": str(entry.get("label", ""))},
                                      limitations=["Rotulo historico nao substitui a analise nem comprova autenticidade."]))
    for record in records:
        limitations.extend(record.limitations)
    if not observations:
        observations.append("Nenhuma anomalia forte detectada pelos metodos disponiveis; isso nao comprova autenticidade.")
    return LocalEvidence(schema_version=SCHEMA_VERSION, analysis_id=analysis_id, image_sha256=digest,
                         reference_sha256=local.file_sha256(reference) if reference else None,
                         quality=quality, records=records, observations=observations, limitations=limitations)
