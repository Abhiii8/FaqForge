import re
from typing import List, Dict, Any, Optional

class DocumentChunker:
    """
    Intelligent semantic text chunker that preserves page numbers,
    section headings, and paragraph boundaries without breaking sentences.
    """

    def __init__(self, target_words: int = 350, overlap_words: int = 40):
        self.target_words = target_words
        self.overlap_words = overlap_words

    def chunk_document(
        self, 
        doc_data: Dict[str, Any], 
        source_document: str = "document"
    ) -> List[Dict[str, Any]]:
        """
        Takes structured document data from DocumentProcessor and partitions it
        into semantically rich, section-aware chunks with full page mapping.
        """
        pages = doc_data.get("pages", [])
        if not pages:
            # Fallback for plain text without page breakdown
            raw_text = doc_data.get("text", "")
            return self.chunk_text(raw_text, source_document=source_document)

        chunks = []
        current_section = doc_data.get("headings", ["Overview"])[0] if doc_data.get("headings") else "General"
        
        running_sentences = []
        running_pages = set()
        running_word_count = 0

        for page in pages:
            page_num = page.get("page_number", 1)
            page_headings = page.get("headings", [])
            page_text = page.get("text", "").strip()

            if not page_text:
                continue

            # Split page into paragraphs
            paragraphs = [p.strip() for p in re.split(r'\n\s*\n', page_text) if p.strip()]

            for para in paragraphs:
                # Check if this paragraph is or contains a new section heading
                for h in page_headings:
                    if h.lower() in para.lower():
                        current_section = h
                        break

                # Split paragraph into sentences cleanly
                sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', para) if len(s.strip()) > 3]
                if not sentences:
                    sentences = [para]

                for sentence in sentences:
                    sent_words = len(sentence.split())
                    running_sentences.append(sentence)
                    running_pages.add(page_num)
                    running_word_count += sent_words

                    # If reached target size, finalize chunk
                    if running_word_count >= self.target_words:
                        chunk_text = " ".join(running_sentences).strip()
                        chunks.append({
                            "chunk_id": len(chunks) + 1,
                            "text": chunk_text,
                            "sentences": list(running_sentences),
                            "word_count": running_word_count,
                            "source_document": source_document,
                            "source_pages": sorted(list(running_pages)),
                            "source_section": current_section
                        })

                        # Overlap: keep the last 1-2 sentences for continuity
                        overlap_sents = []
                        overlap_cnt = 0
                        for s in reversed(running_sentences):
                            s_cnt = len(s.split())
                            if overlap_cnt + s_cnt <= self.overlap_words:
                                overlap_sents.insert(0, s)
                                overlap_cnt += s_cnt
                            else:
                                break

                        running_sentences = overlap_sents
                        running_word_count = overlap_cnt
                        running_pages = {page_num}

        # Final trailing chunk
        if running_sentences:
            chunk_text = " ".join(running_sentences).strip()
            chunks.append({
                "chunk_id": len(chunks) + 1,
                "text": chunk_text,
                "sentences": list(running_sentences),
                "word_count": running_word_count,
                "source_document": source_document,
                "source_pages": sorted(list(running_pages)),
                "source_section": current_section
            })

        return chunks

    def chunk_text(self, text: str, source_document: str = "Pasted Text") -> List[Dict[str, Any]]:
        """Splits raw text into clean semantic chunks with sentence integrity."""
        paragraphs = [p.strip() for p in re.split(r'\n\s*\n', text) if p.strip()]
        chunks = []
        running_sents = []
        running_words = 0

        for para in paragraphs:
            # Check for simple markdown/plain headers
            section = "General"
            if len(para) < 60 and (para.startswith("#") or para.isupper()):
                section = para.lstrip("# ").strip()

            sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', para) if len(s.strip()) > 3]
            if not sentences:
                sentences = [para]

            for sent in sentences:
                w_count = len(sent.split())
                running_sents.append(sent)
                running_words += w_count

                if running_words >= self.target_words:
                    chunks.append({
                        "chunk_id": len(chunks) + 1,
                        "text": " ".join(running_sents).strip(),
                        "sentences": list(running_sents),
                        "word_count": running_words,
                        "source_document": source_document,
                        "source_pages": [1],
                        "source_section": section
                    })
                    running_sents = running_sents[-1:] if len(running_sents) > 1 else []
                    running_words = len(running_sents[0].split()) if running_sents else 0

        if running_sents:
            chunks.append({
                "chunk_id": len(chunks) + 1,
                "text": " ".join(running_sents).strip(),
                "sentences": list(running_sents),
                "word_count": running_words,
                "source_document": source_document,
                "source_pages": [1],
                "source_section": "General"
            })

        return chunks
