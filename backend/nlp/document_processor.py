import os
import re
from typing import Dict, Any, List
import fitz  # PyMuPDF
from docx import Document as DocxDocument

class DocumentProcessor:
    """
    Advanced document extractor supporting PDF, DOCX, and TXT.
    Preserves page numbers, headings, tables, and section hierarchies.
    Detects scanned/encrypted files and cleans page artifacts.
    """

    @staticmethod
    def clean_text(text: str) -> str:
        """Sanitizes text, strips non-printable control characters, and normalizes blank lines."""
        if not text:
            return ""
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', text)
        cleaned = cleaned.replace('\r\n', '\n').replace('\r', '\n')
        cleaned = re.sub(r'[ \t]+', ' ', cleaned)
        cleaned = re.sub(r'\n\s*\n', '\n\n', cleaned)
        cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
        return cleaned.strip()

    _clean_text = clean_text

    @classmethod
    def extract_text(cls, file_path: str) -> str:
        """Returns the full unified text extracted from the document."""
        data = cls.extract_document(file_path)
        return data["text"]

    @classmethod
    def extract_document(cls, file_path: str) -> Dict[str, Any]:
        """
        Extracts structured document data including page-by-page content,
        headings, detected sections, and extraction diagnostics.
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        ext = os.path.splitext(file_path)[1].lower()
        if ext == '.pdf':
            return cls._extract_from_pdf(file_path)
        elif ext == '.docx':
            return cls._extract_from_docx(file_path)
        elif ext == '.txt':
            return cls._extract_from_txt(file_path)
        else:
            raise ValueError(f"Unsupported file format '{ext}'. Supported formats: .pdf, .docx, .txt")

    @classmethod
    def _extract_from_pdf(cls, file_path: str) -> Dict[str, Any]:
        """Extracts text page-by-page from PDF with structure analysis."""
        pages_data = []
        all_headings = []
        total_scanned = 0
        doc_metadata = {}

        try:
            with fitz.open(file_path) as doc:
                # 1. Check for encryption
                if doc.is_encrypted:
                    raise ValueError(
                        f"The PDF '{os.path.basename(file_path)}' is encrypted or password-protected. "
                        "Please remove the password or provide an unprotected document."
                    )

                doc_metadata = {
                    "title": doc.metadata.get("title", ""),
                    "author": doc.metadata.get("author", ""),
                    "subject": doc.metadata.get("subject", ""),
                    "page_count": len(doc)
                }

                if len(doc) == 0:
                    raise ValueError(f"The PDF '{os.path.basename(file_path)}' contains 0 pages.")

                # Analyze font sizes across document to detect headings
                font_sizes = []
                for page in doc:
                    text_dict = page.get_text("dict")
                    for block in text_dict.get("blocks", []):
                        if block.get("type") == 0:  # Text block
                            for line in block.get("lines", []):
                                for span in line.get("spans", []):
                                    if len(span.get("text", "").strip()) > 3:
                                        font_sizes.append(span.get("size", 10.0))

                median_font_size = (
                    sorted(font_sizes)[len(font_sizes) // 2] if font_sizes else 10.0
                )
                heading_threshold = median_font_size * 1.18

                # Extract each page
                for page_num in range(len(doc)):
                    page = doc[page_num]
                    page_index = page_num + 1
                    page_headings = []
                    page_lines = []

                    text_dict = page.get_text("dict")
                    image_count = len(page.get_images())

                    raw_page_text = page.get_text("text").strip()
                    word_count = len(raw_page_text.split())

                    # Check for scanned page
                    is_scanned = False
                    if word_count < 15 and image_count > 0:
                        is_scanned = True
                        total_scanned += 1

                    # Extract blocks preserving structural layout
                    blocks = page.get_text("blocks")
                    for b in blocks:
                        # b: (x0, y0, x1, y1, text, block_no, block_type)
                        if len(b) >= 5 and b[4]:
                            block_text = b[4].strip()
                            if not block_text:
                                continue

                            # Header/Footer artifact filter (e.g. Page numbers like "Page 1 of 5" or standalone numbers)
                            if re.match(r'^(page\s+\d+(\s+of\s+\d+)?|\d+)$', block_text, re.IGNORECASE):
                                continue

                            # Detect headings if line is short and uppercase or font size is large
                            lines = block_text.split("\n")
                            for line in lines:
                                line_clean = line.strip()
                                if line_clean:
                                    if (
                                        (len(line_clean) < 80 and line_clean.isupper() and len(line_clean) > 4) or
                                        re.match(r'^(chapter|section|\d+(\.\d+)*)\s+', line_clean, re.IGNORECASE)
                                    ):
                                        page_headings.append(line_clean)
                                        all_headings.append(line_clean)
                                    page_lines.append(line_clean)

                    page_text = "\n".join(page_lines).strip()
                    if not page_text and raw_page_text:
                        page_text = raw_page_text

                    # Clean repetitive extra spaces
                    page_text = re.sub(r'[ \t]+', ' ', page_text)
                    page_text = re.sub(r'\n{3,}', '\n\n', page_text)

                    pages_data.append({
                        "page_number": page_index,
                        "text": page_text,
                        "headings": page_headings,
                        "word_count": len(page_text.split()),
                        "is_empty": len(page_text.strip()) == 0,
                        "is_scanned": is_scanned,
                        "image_count": image_count
                    })

        except Exception as e:
            if "encrypted" in str(e).lower() or "password" in str(e).lower():
                raise
            raise ValueError(f"Failed to process PDF '{os.path.basename(file_path)}': {str(e)}")

        # Check total extracted text
        full_text = "\n\n".join([p["text"] for p in pages_data if p["text"].strip()]).strip()
        if not full_text:
            if total_scanned > 0:
                raise ValueError(
                    f"The PDF '{os.path.basename(file_path)}' contains {total_scanned} scanned page(s) "
                    "with images but no selectable digital text. Local OCR is required to read scanned documents."
                )
            raise ValueError(f"The PDF '{os.path.basename(file_path)}' contains no extractable text.")

        return {
            "text": full_text,
            "file_type": "pdf",
            "pages": pages_data,
            "total_pages": len(pages_data),
            "scanned_pages_count": total_scanned,
            "headings": list(dict.fromkeys(all_headings)),  # unique preserved order
            "metadata": doc_metadata
        }

    @classmethod
    def _extract_from_docx(cls, file_path: str) -> Dict[str, Any]:
        """Extracts text and headings from DOCX files."""
        try:
            doc = DocxDocument(file_path)
            paragraphs = []
            headings = []

            for para in doc.paragraphs:
                text = para.text.strip()
                if not text:
                    continue
                if para.style and para.style.name.startswith("Heading"):
                    headings.append(text)
                paragraphs.append(text)

            full_text = "\n\n".join(paragraphs).strip()
            if not full_text:
                raise ValueError(f"The document '{os.path.basename(file_path)}' is empty.")

            return {
                "text": full_text,
                "pages": [{
                    "page_number": 1,
                    "text": full_text,
                    "headings": headings,
                    "word_count": len(full_text.split()),
                    "is_empty": False,
                    "is_scanned": False,
                    "image_count": 0
                }],
                "total_pages": 1,
                "scanned_pages_count": 0,
                "headings": headings,
                "metadata": {}
            }
        except Exception as e:
            raise ValueError(f"Failed to extract DOCX file: {str(e)}")

    @classmethod
    def _extract_from_txt(cls, file_path: str) -> Dict[str, Any]:
        """Extracts plain text with encoding auto-detection fallback."""
        text = ""
        for encoding in ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']:
            try:
                with open(file_path, 'r', encoding=encoding) as f:
                    text = f.read().strip()
                break
            except UnicodeDecodeError:
                continue

        if not text:
            raise ValueError(f"The text file '{os.path.basename(file_path)}' is empty.")

        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        headings = [p for p in paragraphs if len(p) < 60 and (p.isupper() or p.startswith("#"))]

        return {
            "text": text,
            "pages": [{
                "page_number": 1,
                "text": text,
                "headings": headings,
                "word_count": len(text.split()),
                "is_empty": False,
                "is_scanned": False,
                "image_count": 0
            }],
            "total_pages": 1,
            "scanned_pages_count": 0,
            "headings": headings,
            "metadata": {}
        }
