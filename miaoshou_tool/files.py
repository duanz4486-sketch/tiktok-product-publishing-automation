from __future__ import annotations

import cgi
import zipfile
from pathlib import Path
from typing import Any

from batch_tiktok_collect import VALID_IMAGE_EXTS, natural_key

from .config import SINGLE_IMAGE_LIMIT, VALID_VIDEO_EXTS


def clean_prefix(value: str) -> str:
    return value.strip().replace("\\", "/").strip("/")


def field_list(form: cgi.FieldStorage, name: str) -> list[cgi.FieldStorage]:
    if name not in form:
        return []
    value = form[name]
    return value if isinstance(value, list) else [value]


def upload_filename(form: cgi.FieldStorage, name: str, default: str) -> str:
    field = form[name] if name in form else None
    raw_name = getattr(field, "filename", "") if field is not None and not isinstance(field, list) else ""
    clean_name = Path(str(raw_name).replace("\\", "/")).name
    return clean_name or default


def save_uploaded_file(field: cgi.FieldStorage, target: Path) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("wb") as out:
        while True:
            chunk = field.file.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    return target


def save_upload(form: cgi.FieldStorage, name: str, target: Path) -> None:
    field = form[name] if name in form else None
    if field is None or isinstance(field, list) or not getattr(field, "filename", ""):
        raise ValueError(f"缺少上传文件: {name}")
    save_uploaded_file(field, target)


def safe_upload_relative_path(filename: object) -> Path | None:
    raw = str(filename or "").replace("\\", "/").strip("/")
    if not raw:
        return None
    path = Path(raw)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"上传文件路径不安全: {filename}")
    return path


def extract_zip(zip_path: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    target_root = target.resolve()
    with zipfile.ZipFile(zip_path) as archive:
        for info in archive.infolist():
            name = info.filename.replace("\\", "/")
            if not name or name.startswith("/") or "/../" in f"/{name}":
                raise ValueError(f"ZIP 内有不安全路径: {info.filename}")
            output = (target / name).resolve()
            try:
                output.relative_to(target_root)
            except ValueError:
                raise ValueError(f"ZIP 内有不安全路径: {info.filename}")
            if info.is_dir():
                output.mkdir(parents=True, exist_ok=True)
                continue
            output.parent.mkdir(parents=True, exist_ok=True)
            with archive.open(info) as src, output.open("wb") as dst:
                dst.write(src.read())


def stage_batch_images(form: cgi.FieldStorage, upload_dir: Path, image_root: Path) -> tuple[str, list[tuple[Path, str]]]:
    zip_fields = [field for field in field_list(form, "image_zip") if getattr(field, "filename", "")]
    folder_fields = [field for field in field_list(form, "image_folder") if getattr(field, "filename", "")]

    if zip_fields:
        zip_path = upload_dir / "images.zip"
        original_name = upload_filename(form, "image_zip", "images.zip")
        save_uploaded_file(zip_fields[0], zip_path)
        extract_zip(zip_path, image_root)
        return original_name, [(zip_path, original_name)]

    if not folder_fields:
        raise ValueError("请上传图片 ZIP 或图片文件夹")

    saved = 0
    top_names: list[str] = []
    for field in folder_fields:
        rel = safe_upload_relative_path(getattr(field, "filename", ""))
        if rel is None:
            continue
        if rel.name.lower() == "thumbs.db" or rel.suffix.lower() not in VALID_IMAGE_EXTS:
            continue
        if len(rel.parts) > 1 and rel.parts[0] not in top_names:
            top_names.append(rel.parts[0])
        save_uploaded_file(field, image_root / rel)
        saved += 1

    if not saved:
        raise ValueError("图片文件夹里没有找到支持的图片文件")

    source_name = top_names[0] if len(top_names) == 1 else "folder-upload"
    return source_name, []


def uploaded_image_files(form: cgi.FieldStorage, upload_dir: Path) -> list[Path]:
    staged: list[tuple[str, Path]] = []
    direct_dir = upload_dir / "direct-images"
    zip_index = 0

    def stage_field(field: cgi.FieldStorage) -> None:
        nonlocal zip_index
        filename = Path(str(getattr(field, "filename", "")).replace("\\", "/")).name
        suffix = Path(filename).suffix.lower()
        if not filename:
            return
        if suffix == ".zip":
            zip_index += 1
            zip_path = upload_dir / f"single-images-{zip_index}.zip"
            save_uploaded_file(field, zip_path)
            unzip_dir = upload_dir / f"single-images-{zip_index}"
            extract_zip(zip_path, unzip_dir)
            for path in unzip_dir.rglob("*"):
                if path.is_file() and path.suffix.lower() in VALID_IMAGE_EXTS:
                    staged.append((path.name, path))
            return
        if suffix in VALID_IMAGE_EXTS:
            target = direct_dir / f"{len(staged) + 1:03d}-{filename}"
            staged.append((filename, save_uploaded_file(field, target)))

    for name in ("image_upload", "image_files", "image_zip"):
        for field in field_list(form, name):
            stage_field(field)

    staged = sorted(staged, key=lambda item: natural_key(item[0]))
    return [path for _, path in staged[:SINGLE_IMAGE_LIMIT]]


def uploaded_sku_image_files(form: cgi.FieldStorage, upload_dir: Path) -> dict[str, Path]:
    row_ids = [str(item.value or "").strip() for item in field_list(form, "sku_row_id")]
    result: dict[str, Path] = {}
    sku_dir = upload_dir / "sku-images"
    for index, row_id in enumerate(row_ids):
        row_id = row_id or str(index)
        field_name = f"sku_image_file_{row_id}"
        field = form[field_name] if field_name in form else None
        if field is None or isinstance(field, list):
            continue
        filename = Path(str(getattr(field, "filename", "")).replace("\\", "/")).name
        if not filename:
            continue
        if Path(filename).suffix.lower() not in VALID_IMAGE_EXTS:
            raise ValueError(f"规格图 {filename} 不是支持的图片格式")
        result[row_id] = save_uploaded_file(field, sku_dir / f"{index + 1:03d}-{filename}")
    return result


def uploaded_video_file(form: cgi.FieldStorage, upload_dir: Path) -> Path | None:
    field = form["main_video"] if "main_video" in form else None
    if field is None or isinstance(field, list):
        return None
    filename = Path(str(getattr(field, "filename", "")).replace("\\", "/")).name
    if not filename:
        return None
    if Path(filename).suffix.lower() not in VALID_VIDEO_EXTS:
        raise ValueError(f"主图视频 {filename} 不是支持的视频格式")
    return save_uploaded_file(field, upload_dir / "video" / filename)


def image_seq_dirs(folder: Path) -> set[int]:
    found: set[int] = set()
    for path in folder.iterdir():
        if path.is_dir() and path.name.isdigit():
            found.add(int(path.name))
    return found


def image_count_for_seq(image_root: Path, seq: int) -> int:
    folder = image_root / str(seq)
    if not folder.is_dir():
        return 0
    return sum(1 for path in folder.iterdir() if path.is_file() and path.suffix.lower() in VALID_IMAGE_EXTS)


def build_preflight_failures(items: list[dict[str, Any]], image_root: Path, image_seqs: set[int], include_image_only: bool) -> list[dict[str, Any]]:
    excel_seqs = [int(item["seq"]) for item in items]
    excel_seq_set = set(excel_seqs)
    failures = [
        {"seq": seq, "title": item["title"], "status": "failed", "image_count": 0, "error": "缺少图片文件夹"}
        for item in items
        for seq in [int(item["seq"])]
        if seq not in image_seqs
    ]
    if include_image_only:
        failures.extend(
            {
                "seq": seq,
                "title": "",
                "status": "failed",
                "image_count": image_count_for_seq(image_root, seq),
                "error": "缺少标题",
            }
            for seq in sorted(image_seqs - excel_seq_set)
        )
    return failures


def find_image_base(image_root: Path, seqs: list[int]) -> Path | None:
    needed = set(seqs)
    candidates = [image_root] + [p for p in image_root.rglob("*") if p.is_dir() and p.name != "__MACOSX"]
    best: tuple[int, Path] | None = None
    for folder in candidates:
        score = len(image_seq_dirs(folder) & needed)
        if score and (best is None or score > best[0]):
            best = (score, folder)
        if score == len(needed):
            return folder
    return best[1] if best else None


def resolve_image_layout(image_root: Path, batch: str, seqs: list[int], image_prefix: str = "") -> tuple[Path, str]:
    image_prefix = clean_prefix(image_prefix)
    dirs = [p for p in image_root.iterdir() if p.is_dir() and p.name != "__MACOSX"]
    base = find_image_base(image_root, seqs)
    if not base:
        names = "、".join(p.name for p in dirs[:8]) or "空"
        raise ValueError(f"ZIP 顶层应是一个图片目录，或直接是 1、2、3 这些序号文件夹；当前是：{names}")
    if image_prefix:
        prefix = image_prefix
    elif base == image_root:
        prefix = batch
    else:
        try:
            prefix = base.relative_to(image_root).parts[0]
        except ValueError:
            prefix = batch

    return base, prefix
