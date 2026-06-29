"""KnowledgeLoader — loads and indexes knowledge base documents."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


class KnowledgeLoader:
    """
    Loads knowledge base documents for agent context injection.

    Supports:
    - Plain text files (.txt, .md)
    - JSON files (.json)
    - PDF files (.pdf) — requires pdfplumber (optional)
    - Future: website crawling, SKKNI documents
    """

    SUPPORTED_EXTENSIONS = {".txt", ".md", ".json"}

    def __init__(self, knowledge_dir: str = "knowledge"):
        self.knowledge_dir = knowledge_dir
        self._index: dict[str, str] = {}
        if os.path.exists(knowledge_dir):
            self._index_directory()

    def _index_directory(self):
        """Walk knowledge dir and index all supported files."""
        for root, _, files in os.walk(self.knowledge_dir):
            for fname in files:
                ext = os.path.splitext(fname)[1].lower()
                if ext in self.SUPPORTED_EXTENSIONS:
                    fpath = os.path.join(root, fname)
                    key = os.path.relpath(fpath, self.knowledge_dir).replace("\\", "/")
                    self._index[key] = fpath
        logger.info(f"Knowledge base indexed: {len(self._index)} documents")

    def load(self, key: str) -> str:
        """Load a document by its relative path key."""
        if key not in self._index:
            raise FileNotFoundError(f"Knowledge document not found: {key}")
        return self._read_file(self._index[key])

    def search(self, query: str, top_k: int = 3) -> list[dict[str, str]]:
        """
        Simple keyword search across indexed documents.
        Returns list of {key, snippet} dicts.
        (Future: replace with vector/semantic search)
        """
        results = []
        query_lower = query.lower()
        for key, fpath in self._index.items():
            try:
                content = self._read_file(fpath)
                if query_lower in content.lower():
                    # Extract a short snippet around the first match
                    idx = content.lower().index(query_lower)
                    start = max(0, idx - 100)
                    end = min(len(content), idx + 300)
                    snippet = content[start:end].strip()
                    results.append({"key": key, "snippet": snippet})
                    if len(results) >= top_k:
                        break
            except Exception:
                continue
        return results

    def list_documents(self) -> list[str]:
        """Return all indexed document keys."""
        return list(self._index.keys())

    def _read_file(self, fpath: str) -> str:
        """Read a file and return its content as string."""
        ext = os.path.splitext(fpath)[1].lower()
        with open(fpath, "r", encoding="utf-8") as f:
            if ext == ".json":
                data = json.load(f)
                return json.dumps(data, ensure_ascii=False, indent=2)
            return f.read()

    def add_document(self, key: str, content: str):
        """Add a document to the knowledge base programmatically."""
        os.makedirs(self.knowledge_dir, exist_ok=True)
        fpath = os.path.join(self.knowledge_dir, key)
        os.makedirs(os.path.dirname(fpath), exist_ok=True)
        with open(fpath, "w", encoding="utf-8") as f:
            f.write(content)
        self._index[key] = fpath
        logger.info(f"Knowledge document added: {key}")
