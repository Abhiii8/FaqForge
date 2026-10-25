import os
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import torch
import spacy
from typing import Dict, Any, Optional
from sklearn.feature_extraction.text import TfidfVectorizer
from backend.nlp.generator import FAQGenerator

class NLPPipeline:
    """
    Unified NLP Pipeline managing document analysis, spaCy parsing,
    TF-IDF keywords, NER entities, and multi-stage FAQ generation.
    """
    def __init__(self):
        try:
            self.nlp = spacy.load("en_core_web_sm")
        except OSError:
            from spacy.cli import download
            download("en_core_web_sm")
            self.nlp = spacy.load("en_core_web_sm")
            
        self.generator = FAQGenerator()

    def process_text(
        self, 
        text: str, 
        num_faqs: int = 5, 
        faq_length: str = "medium",
        source_document: str = "Pasted Text",
        question_focus: str = "all"
    ) -> Dict[str, Any]:
        """Processes raw text input and produces FAQs with coverage report."""
        clean_text = text.strip()
        doc_data = {
            "text": clean_text,
            "pages": [{
                "page_number": 1,
                "text": clean_text,
                "headings": [],
                "word_count": len(clean_text.split()),
                "is_empty": False,
                "is_scanned": False
            }],
            "total_pages": 1,
            "headings": []
        }
        return self.process_document_data(
            doc_data=doc_data,
            num_faqs=num_faqs,
            faq_length=faq_length,
            source_document=source_document,
            question_focus=question_focus
        )

    def process_document_data(
        self, 
        doc_data: Dict[str, Any], 
        num_faqs: int = 5, 
        faq_length: str = "medium",
        source_document: str = "document",
        question_focus: str = "all"
    ) -> Dict[str, Any]:
        """Processes structured document data (from PDF, DOCX, or text)."""
        full_text = doc_data.get("text", "").strip()
        
        # spaCy linguistic analysis
        # Sample first 10,000 chars for entity/POS tagging to maintain high performance
        sample_for_nlp = full_text[:12000]
        doc = self.nlp(sample_for_nlp)

        tokens = [token.text for token in doc[:100]]
        lemmas = [token.lemma_ for token in doc[:100] if not token.is_punct and not token.is_space]
        pos_tags = [{"token": token.text, "pos": token.pos_} for token in doc[:60] if not token.is_space]
        entities = [{"entity": ent.text, "entity_type": ent.label_} for ent in doc.ents[:25]]

        # Keyword extraction using TF-IDF
        sentences = [sent.text.strip() for sent in doc.sents if len(sent.text.split()) > 3]
        keywords = []
        if len(sentences) > 0:
            try:
                vectorizer = TfidfVectorizer(stop_words='english', max_features=12)
                tfidf_matrix = vectorizer.fit_transform(sentences)
                feature_names = vectorizer.get_feature_names_out()
                scores = tfidf_matrix.sum(axis=0).A1
                sorted_items = sorted(zip(feature_names, scores), key=lambda x: x[1], reverse=True)
                keywords = [{"keyword": k, "score": round(float(s), 3)} for k, s in sorted_items]
            except Exception as e:
                print(f"[TF-IDF Keywords Error]: {e}")

        # Multi-stage FAQ generation and verification
        faqs, coverage_report = self.generator.generate_faqs(
            doc_data=doc_data,
            num_faqs=num_faqs,
            faq_length=faq_length,
            source_document=source_document,
            doc_nlp=doc,
            question_focus=question_focus
        )

        return {
            "processed_text": full_text[:5000],
            "tokens": tokens,
            "lemmas": lemmas,
            "pos_tags": pos_tags,
            "entities": entities,
            "keywords": keywords,
            "faqs": faqs,
            "coverage_report": coverage_report,
            "engine_status": self.generator.get_engine_status()
        }
