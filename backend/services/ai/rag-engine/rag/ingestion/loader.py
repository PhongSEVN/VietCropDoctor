"""
Multi-format document loader.

Supports: .txt, .md, .pdf, .json
Returns a list of Document objects ready for chunking.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from rag.core.exceptions import IngestionError
from rag.core.disease_map import CLASS_TO_CROP

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf", ".json"}

# Folders whose documents are NOT crop-specific — they cover many/all crops
# (e.g. a general handbook on plant diseases). Documents here are stored with
# crop = list of every known crop, so a crop filter for ANY single crop still
# matches them (Qdrant matches a keyword value against the elements of a list
# payload). Put multi-crop documents in one of these folders.
_ALL_CROP_FOLDERS = {"chung", "pdf", "tong-hop", "tổng hợp"}
_ALL_CROPS = sorted(set(CLASS_TO_CROP.values()))

# Filenames that should never be indexed as knowledge content.
#   - link.txt / links_to_crawl.txt: crawl-target URL queues (not citations)
#   - sources.json: source-attribution sidecar (read separately, see below)
_EXCLUDED_FILENAMES = {
    "link.txt", "links_to_crawl.txt", "links.txt",
    "sources.json",
}

# Sidecar file mapping each document filename to its human-readable source name.
# Example sources.json:
#   {
#     "text.txt": "Chi cục Trồng trọt & BVTV TP.HCM",
#     "ttr21_caphe_2012.pdf": "Bộ Nông nghiệp và PTNT",
#     "*": "Nguồn mặc định cho file không liệt kê"
#   }
_SOURCE_MAP_FILENAME = "sources.json"


def _read_source_map(folder: Path) -> dict[str, str]:
    """Read sources.json in *folder* → {filename: source_name}.

    A "*" key acts as a folder-wide default for files not listed explicitly.
    Returns {} when the file is missing or invalid (never raises).
    """
    f = folder / _SOURCE_MAP_FILENAME
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Invalid %s in %s: %s", _SOURCE_MAP_FILENAME, folder, exc)
        return {}
    if not isinstance(data, dict):
        logger.warning("%s in %s is not a JSON object — ignored.", _SOURCE_MAP_FILENAME, folder)
        return {}
    return {str(k): str(v) for k, v in data.items()}


@dataclass
class Document:
    """Raw document before chunking."""

    text: str
    source: str                         # relative or absolute file path string
    filename: str
    doc_type: str                       # txt | md | pdf | json
    extra_metadata: dict = field(default_factory=dict)


class DocumentLoader:
    """Load documents from files or directories.

    Usage::

        loader = DocumentLoader()
        docs = loader.load_directory(Path("rag/knowledge"))
        # or single file
        doc = loader.load_file(Path("rag/knowledge/lúa/text.txt"))
    """

    def load_file(self, path: Path) -> Optional[Document]:
        """Load a single file. Returns None if the format is unsupported."""
        if path.name.lower() in _EXCLUDED_FILENAMES:
            logger.debug("Skipping excluded file: %s", path.name)
            return None
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            logger.debug("Skipping unsupported file: %s", path.name)
            return None

        try:
            loader_fn = {
                ".txt": self._load_txt,
                ".md":  self._load_txt,   # markdown treated as plain text
                ".pdf": self._load_pdf,
                ".json": self._load_json,
            }[suffix]

            text = loader_fn(path)
            if not text.strip():
                logger.warning("Empty document: %s", path)
                return None

            return Document(
                text=text,
                source=str(path),
                filename=path.name,
                doc_type=suffix.lstrip("."),
            )
        except Exception as exc:
            raise IngestionError(
                f"Failed to load {path.name}: {exc}",
                details={"path": str(path)},
            ) from exc

    def load_directory(
        self,
        directory: Path,
        recursive: bool = True,
        pattern: str = "*",
    ) -> list[Document]:
        """Load all supported documents from a directory.

        Args:
            directory:  Root directory to scan.
            recursive:  Descend into subdirectories.
            pattern:    Glob pattern filter (default: all files).

        Returns:
            List of Document objects, one per file.
        """
        if not directory.exists():
            raise IngestionError(
                f"Knowledge directory not found: {directory}",
                details={"path": str(directory)},
            )

        glob_fn = directory.rglob if recursive else directory.glob
        files = [p for p in glob_fn(pattern) if p.is_file()]

        docs: list[Document] = []
        skipped = 0
        for file_path in sorted(files):
            try:
                doc = self.load_file(file_path)
            except IngestionError as exc:
                logger.warning("Skipping %s: %s", file_path.name, exc.message)
                skipped += 1
                continue
            if doc:
                # Inject parent directory names as metadata (crop / disease)
                parts = file_path.relative_to(directory).parts
                if len(parts) >= 2:
                    crop_folder = parts[0]
                    if crop_folder.lower() in _ALL_CROP_FOLDERS:
                        # Multi-crop / general document → applies to every crop
                        doc.extra_metadata["crop"] = _ALL_CROPS
                    else:
                        doc.extra_metadata["crop"] = crop_folder
                if len(parts) >= 3:
                    doc.extra_metadata["disease_name"] = parts[1]
                # Attach human-readable source name from sibling sources.json
                # (lookup by filename, fall back to the "*" folder-wide default)
                source_map = _read_source_map(file_path.parent)
                source_name = source_map.get(doc.filename) or source_map.get("*")
                if source_name:
                    doc.extra_metadata["source_name"] = source_name
                docs.append(doc)
            else:
                skipped += 1

        logger.info(
            "Loaded %d documents from %s (%d skipped)",
            len(docs), directory, skipped,
        )
        return docs

    # ── Private loaders ───────────────────────────────────────────────────

    def _load_txt(self, path: Path) -> str:
        return path.read_text(encoding="utf-8", errors="replace")

    def _load_pdf(self, path: Path) -> str:
        """Extract text from PDF using pypdf (lightweight, no Java needed)."""
        try:
            from pypdf import PdfReader  # lazy import
        except ImportError as exc:
            raise IngestionError(
                "pypdf is required for PDF loading. Run: pip install pypdf"
            ) from exc

        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n\n".join(pages)

    def _load_json(self, path: Path) -> str:
        """Flatten JSON to text. Handles list-of-strings or dict with a 'text' key."""
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, str):
            return data
        if isinstance(data, list):
            return "\n".join(str(item) for item in data)
        if isinstance(data, dict):
            if "text" in data:
                return str(data["text"])
            if "content" in data:
                return str(data["content"])
            # Fallback: join all string values
            return "\n".join(str(v) for v in data.values() if isinstance(v, str))
        return str(data)
