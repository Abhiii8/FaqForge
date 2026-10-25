import os
import re
import json
from typing import Dict, Any, List, Optional, Tuple

# Prevent OpenMP runtime library conflict on Windows
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import torch
from backend.nlp.ollama_client import OllamaClient
from backend.nlp.chunker import DocumentChunker
from backend.nlp.verifier import SourceVerifier
from backend.nlp.deduplicator import SemanticDeduplicator

class FAQGenerator:
    """
    Advanced Multi-Stage FAQ Generator.
    Primary Engine: Local Ollama (qwen2.5:3b or configured model).
    Fallback Engine: Local Transformers (Flan-T5) when Ollama is offline.
    Includes Topic Inventory, Source Verification, and Quality Coverage Reporting.
    """

    def __init__(self, ollama_host: Optional[str] = None, model_name: Optional[str] = None):
        self.ollama = OllamaClient(host=ollama_host, model=model_name)
        self.chunker = DocumentChunker(target_words=320, overlap_words=35)
        self.deduplicator = SemanticDeduplicator(question_threshold=0.65, answer_threshold=0.70)
        self.fallback_pipeline = None
        self.device = 0 if torch.cuda.is_available() else -1

    def _init_fallback_model(self):
        """Initializes local Flan-T5 pipeline if Ollama is unavailable."""
        if self.fallback_pipeline is None:
            print("[NLP] Initializing local neural fallback engine (Flan-T5)...")
            try:
                from transformers import pipeline
                try:
                    self.fallback_pipeline = pipeline(
                        "text2text-generation", 
                        model="google/flan-t5-base", 
                        device=self.device,
                        model_kwargs={"local_files_only": True}
                    )
                except Exception:
                    self.fallback_pipeline = pipeline(
                        "text2text-generation", 
                        model="google/flan-t5-base", 
                        device=self.device
                    )
                print("[NLP] Fallback engine ready.")
            except Exception as e:
                print(f"[NLP Fallback Load Error]: {e}")
                self.fallback_pipeline = "rule_based"

    def get_engine_status(self) -> Dict[str, Any]:
        """Returns the current state of local AI inference engines."""
        ollama_status = self.ollama.check_connection()
        local_models = self.ollama.list_models() if ollama_status["running"] else []
        model_ready = self.ollama.is_model_available() if ollama_status["running"] else False
        
        return {
            "ollama_running": ollama_status["running"],
            "ollama_version": ollama_status.get("version"),
            "configured_model": self.ollama.model,
            "model_ready": model_ready,
            "installed_models": local_models,
            "primary_engine": "Ollama" if (ollama_status["running"] and model_ready) else "Flan-T5 (Local Fallback)",
            "instructions": ollama_status.get("instructions", "")
        }

    # =========================================================================
    # STAGE A: DOCUMENT ANALYSIS & TOPIC INVENTORY
    # =========================================================================
    def analyze_document_topics(self, chunks: List[Dict[str, Any]], primary_subject: str) -> Dict[str, Any]:
        """
        Stage A: Builds a document-level topic inventory so questions cover
        all sections and logical concepts, not just the beginning.
        """
        topic_inventory = []
        for idx, chunk in enumerate(chunks):
            text = chunk["text"]
            section = chunk.get("source_section", "General")
            
            # Detect topic categories in chunk
            categories = []
            if any(w in text.lower() for w in ['definition', 'refers to', 'is a', 'means', 'what is']):
                categories.append("Definition")
            if any(w in text.lower() for w in ['step', 'procedure', 'how to', 'install', 'configure', 'execute', 'run']):
                categories.append("Procedural")
            if any(w in text.lower() for w in ['feature', 'capability', 'benefit', 'advantage', 'supports', 'component']):
                categories.append("Features & Capabilities")
            if any(w in text.lower() for w in ['history', 'created', 'founded', 'released', 'launched', 'invented']):
                categories.append("History & Origin")
            if any(w in text.lower() for w in ['requirement', 'prerequisite', 'eligibility', 'limitation', 'exception']):
                categories.append("Requirements & Limits")
            if any(w in text.lower() for w in ['difference', 'compare', 'versus', 'vs', 'division', 'classified']):
                categories.append("Comparison")

            if not categories:
                categories = ["Core Concepts"]

            topic_inventory.append({
                "chunk_id": chunk.get("chunk_id", idx + 1),
                "section": section,
                "categories": categories,
                "pages": chunk.get("source_pages", [1]),
                "sample_text": text[:120]
            })

        all_categories = list(dict.fromkeys([c for item in topic_inventory for c in item["categories"]]))
        return {
            "subject": primary_subject,
            "total_chunks": len(chunks),
            "topic_inventory": topic_inventory,
            "major_topics": all_categories
        }

    # =========================================================================
    # STAGE B & C: MULTI-STAGE QUESTION & GROUNDED ANSWER GENERATION
    # =========================================================================
    def generate_faqs(
        self, 
        doc_data: Dict[str, Any], 
        num_faqs: int = 5, 
        faq_length: str = "medium",
        source_document: str = "document",
        doc_nlp = None,
        question_focus: str = "all"
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """
        Executes the full multi-stage FAQ generation pipeline.
        Returns: (faqs: List[Dict], coverage_report: Dict)
        """
        # 1. Chunk document intelligently
        chunks = self.chunker.chunk_document(doc_data, source_document=source_document)
        if not chunks:
            raw_text = doc_data.get("text", "")
            chunks = self.chunker.chunk_text(raw_text, source_document=source_document)

        if not chunks:
            return [], self._empty_coverage_report(source_document)

        # 2. Extract Primary Subject
        subject = self._extract_subject(doc_nlp, doc_data)
        
        # 3. Stage A: Document Analysis & Topic Inventory
        analysis = self.analyze_document_topics(chunks, subject)
        
        # 4. Check whether Ollama is ready, or use verified local fallback
        ollama_status = self.ollama.check_connection()
        use_ollama = ollama_status["running"] and self.ollama.is_model_available()

        print(f"[NLP Pipeline] Generating up to {num_faqs} FAQs using engine: {'Ollama (' + self.ollama.model + ')' if use_ollama else 'Flan-T5 Fallback'}")

        raw_candidates = []
        if use_ollama:
            raw_candidates = self._generate_with_ollama(chunks, subject, num_faqs, faq_length, source_document, question_focus)
        
        # If Ollama failed or produced fewer than target FAQs, supplement with local neural engine
        if len(raw_candidates) < num_faqs:
            fallback_needed = num_faqs - len(raw_candidates)
            flan_candidates = self._generate_with_flan(chunks, subject, fallback_needed, faq_length, source_document)
            raw_candidates.extend(flan_candidates)

        # 5. Stage D: Verification & Quality Filtering
        verified_faqs = []
        rejected_count = 0
        needs_review_count = 0
        duplicates_removed = 0

        for cand in raw_candidates:
            # Check duplicate against existing accepted FAQs
            is_dup, dup_reason = self.deduplicator.is_duplicate(cand, verified_faqs)
            if is_dup:
                duplicates_removed += 1
                continue

            # Run Independent Source Verification (Phase 6)
            verif = SourceVerifier.verify_faq(
                question=cand["question"],
                answer=cand["answer"],
                source_passage=cand.get("context", "")
            )

            cand["verification_status"] = verif["status"]
            cand["needs_review"] = verif["needs_review"]
            cand["supporting_excerpt"] = verif.get("supporting_excerpt", cand.get("supporting_excerpt", ""))
            cand["overall_score"] = verif["confidence"]
            cand["verification_reason"] = verif["reason"]

            if verif["status"] == "rejected":
                rejected_count += 1
                # Only keep rejected if we have too few FAQs, but mark clearly as needing review
                if len(verified_faqs) < num_faqs:
                    cand["verification_status"] = "needs_review"
                    cand["needs_review"] = True
                    needs_review_count += 1
                    verified_faqs.append(cand)
            elif verif["status"] == "needs_review":
                needs_review_count += 1
                verified_faqs.append(cand)
            else:
                verified_faqs.append(cand)

            if len(verified_faqs) >= num_faqs:
                break

        # 6. Build Document Coverage Report (Phase 8)
        coverage_report = self._build_coverage_report(
            doc_data=doc_data,
            chunks=chunks,
            analysis=analysis,
            generated_count=len(raw_candidates),
            verified_faqs=verified_faqs,
            needs_review_count=needs_review_count,
            rejected_count=rejected_count,
            duplicates_removed=duplicates_removed,
            engine_used="Ollama (" + self.ollama.model + ")" if use_ollama else "Flan-T5 (Local)"
        )

        return verified_faqs, coverage_report

    # =========================================================================
    # OLLAMA INFERENCE GENERATION
    # =========================================================================
    def _generate_with_ollama(
        self, 
        chunks: List[Dict[str, Any]], 
        subject: str, 
        num_faqs: int, 
        faq_length: str,
        source_document: str,
        question_focus: str = "all"
    ) -> List[Dict[str, Any]]:
        """Generates structured FAQ pairs using local Ollama model."""
        candidates = []
        # Distribute question targets evenly across chunks
        chunks_to_query = chunks[:max(num_faqs * 2, len(chunks))]

        length_desc = "1 to 2 complete, informative sentences"
        if faq_length == "small":
            length_desc = "a single concise, direct sentence"
        elif faq_length == "detailed":
            length_desc = "a detailed, multi-sentence paragraph explaining all key aspects"

        focus_instruction = ""
        if question_focus == "factual":
            focus_instruction = "- Prioritize factual definitions, key terminology, and specifications.\n"
        elif question_focus == "how_to":
            focus_instruction = "- Prioritize actionable procedures, configuration, implementation, or 'how-to' steps.\n"
        elif question_focus == "comparative":
            focus_instruction = "- Prioritize comparisons, advantages, capabilities, and distinctions.\n"

        for chunk in chunks_to_query:
            if len(candidates) >= num_faqs:
                break

            chunk_text = chunk["text"]
            section = chunk.get("source_section", "General")
            pages = chunk.get("source_pages", [1])

            needed = num_faqs - len(candidates)
            target_for_chunk = min(4, max(1, needed))

            system_prompt = (
                "You are an expert AI technical writer and documentation specialist. "
                "Your task is to generate high-quality, professional FAQ pairs strictly grounded in the provided context. "
                "Output ONLY a valid JSON object matching this schema:\n"
                "{\n"
                "  \"faqs\": [\n"
                "    {\n"
                "      \"question\": \"Natural, self-contained question ending with '?' explicitly naming the subject\",\n"
                "      \"answer\": \"Factual answer directly supported by the context\",\n"
                "      \"category\": \"Topic category (e.g. Definition, Features, Procedure, Overview)\",\n"
                "      \"question_type\": \"conceptual, factual, procedural, explanation, or definition\"\n"
                "    }\n"
                "  ]\n"
                "}\n"
                "Rules:\n"
                "- Formulate clear, self-contained questions that explicitly name the subject (never use pronouns like 'it', 'he', 'she', or 'they').\n"
                "- Formulate answers that are directly grounded, factual, and faithfully match the source passage.\n"
                "- Do NOT hallucinate, assume, or extrapolate beyond the provided text.\n"
                f"{focus_instruction}"
                f"- Answer length should be {length_desc}."
            )

            user_prompt = (
                f"Context from section '{section}':\n\n{chunk_text}\n\n"
                f"Generate up to {target_for_chunk} diverse, high-quality FAQ pairs covering different aspects of this context:"
            )

            res = self.ollama.generate(
                prompt=user_prompt,
                system=system_prompt,
                json_format=True,
                temperature=0.2,
                context_window=4096
            )

            if res.get("success") and res.get("response"):
                try:
                    data = json.loads(res["response"])
                    raw_items = data.get("faqs", [])
                    if not raw_items and "question" in data:
                        raw_items = [data]
                    for item in raw_items:
                        if len(candidates) >= num_faqs:
                            break
                        q = item.get("question", "").strip()
                        a = item.get("answer", "").strip()
                        q = self._clean_question(q, subject)
                        if self._is_valid_question(q) and len(a.split()) >= 3:
                            candidates.append({
                                "id": len(candidates) + 1,
                                "question": q,
                                "answer": a,
                                "category": item.get("category", section),
                                "question_type": item.get("question_type", "factual"),
                                "source_document": source_document,
                                "source_pages": pages,
                                "source_section": section,
                                "supporting_excerpt": chunk_text[:350],
                                "context": chunk_text,
                                "question_score": 0.95,
                                "answer_score": 0.96,
                                "overall_score": 0.95
                            })
                except json.JSONDecodeError:
                    pass

        return candidates

    # =========================================================================
    # FLAN-T5 LOCAL FALLBACK GENERATION
    # =========================================================================
    def _generate_with_flan(
        self, 
        chunks: List[Dict[str, Any]], 
        subject: str, 
        num_faqs: int, 
        faq_length: str,
        source_document: str
    ) -> List[Dict[str, Any]]:
        """Verified local Flan-T5 neural generation engine."""
        self._init_fallback_model()
        if self.fallback_pipeline == "rule_based" or not self.fallback_pipeline:
            return []

        candidates = []
        for chunk in chunks:
            if len(candidates) >= num_faqs:
                break

            chunk_text = chunk["text"]
            chunk_sents = chunk.get("sentences", [chunk_text])
            section = chunk.get("source_section", "General")
            pages = chunk.get("source_pages", [1])

            # Semantic prompt selection - collect all applicable prompts for chunk
            check_str = chunk_text.lower()
            chunk_prompts = []
            if any(w in check_str for w in ['coined', 'founded', 'created', 'developed', 'invented', 'launched', 'established', 'released']):
                chunk_prompts.append(("Historical / Origin", f"Write an FAQ question asking who created or founded {subject}, or when it happened, based on the text.\nContext: {chunk_text}\nQuestion:"))
            if any(w in check_str for w in ['divided into', 'types of', 'categories of', 'classified into', 'difference between', 'definition', 'is a']):
                chunk_prompts.append(("Conceptual", f"Write an FAQ question asking what {subject} is or defining it, based on the text.\nContext: {chunk_text}\nQuestion:"))
            if any(w in check_str for w in ['subfields', 'branches', 'components', 'features', 'paradigms', 'supports', 'standard library', 'packages']):
                chunk_prompts.append(("Features", f"Write an FAQ question asking what the key features or capabilities of {subject} are, based on the text.\nContext: {chunk_text}\nQuestion:"))
            if any(w in check_str for w in ['used for', 'widely used', 'applications', 'purpose', 'designed to', 'help']):
                chunk_prompts.append(("Applications", f"Write an FAQ question asking what {subject} is used for, based on the text.\nContext: {chunk_text}\nQuestion:"))
            if not chunk_prompts:
                chunk_prompts.append(("Overview", f"Write a clear, formal FAQ question about {subject} answered by this context. Do not use pronouns like 'it' or 'they'.\nContext: {chunk_text}\nQuestion:"))

            for q_type, prompt in chunk_prompts:
                if len(candidates) >= num_faqs:
                    break
                try:
                    res = self.fallback_pipeline(prompt, max_length=64, num_beams=4, do_sample=False)
                    raw_q = res[0]['generated_text'].strip()
                    question = self._clean_question(raw_q, subject)

                    if self._is_valid_question(question):
                        a_prompt = f"Answer the question directly based on the context.\nContext: {chunk_text}\nQuestion: {question}\nAnswer:"
                        a_res = self.fallback_pipeline(a_prompt, max_length=128, num_beams=4, do_sample=False)
                        raw_a = a_res[0]['generated_text'].strip()

                        answer = self._format_flan_answer(raw_a, chunk_sents, subject, faq_length)

                        candidates.append({
                            "id": len(candidates) + 1,
                            "question": question,
                            "answer": answer,
                            "category": section,
                            "question_type": q_type,
                            "source_document": source_document,
                            "source_pages": pages,
                            "source_section": section,
                            "supporting_excerpt": chunk_text[:350],
                            "context": chunk_text,
                            "question_score": 0.94,
                            "answer_score": 0.96,
                            "overall_score": 0.95
                        })
                except Exception as e:
                    print(f"[Flan Gen Error]: {e}")

        return candidates

    # =========================================================================
    # REGENERATION (QUESTION OR ANSWER)
    # =========================================================================
    def regenerate_faq(self, context: str, target: str = "both", faq_length: str = "medium") -> Optional[Dict[str, Any]]:
        """
        Regenerates question, answer, or both from source context.
        Uses Ollama if online, falling back to Flan-T5.
        """
        ollama_status = self.ollama.check_connection()
        if ollama_status["running"] and self.ollama.is_model_available():
            prompt = (
                f"Context:\n{context}\n\n"
                "Generate a fresh, natural FAQ question and factual answer based on this context. "
                "Output JSON: {\"question\": \"...\", \"answer\": \"...\", \"category\": \"General\", \"question_type\": \"conceptual\"}"
            )
            res = self.ollama.generate(prompt=prompt, json_format=True, temperature=0.7)
            if res.get("success") and res.get("response"):
                try:
                    data = json.loads(res["response"])
                    q = self._clean_question(data.get("question", ""), "the subject")
                    a = data.get("answer", "").strip()
                    verif = SourceVerifier.verify_faq(q, a, context)
                    return {
                        "question": q,
                        "answer": a,
                        "category": data.get("category", "General"),
                        "question_type": data.get("question_type", "conceptual"),
                        "supporting_excerpt": verif.get("supporting_excerpt", context[:300]),
                        "verification_status": verif["status"],
                        "needs_review": verif["needs_review"],
                        "overall_score": verif["confidence"],
                        "context": context
                    }
                except Exception:
                    pass

        # Fallback regeneration
        self._init_fallback_model()
        if self.fallback_pipeline and self.fallback_pipeline != "rule_based":
            try:
                qg_res = self.fallback_pipeline(
                    f"Write a specific and natural FAQ question answered by the text.\nContext: {context}\nQuestion:",
                    max_length=64, do_sample=True, top_p=0.92, temperature=0.7
                )
                q = self._clean_question(qg_res[0]['generated_text'].strip(), "the subject")
                qa_res = self.fallback_pipeline(
                    f"Answer the question clearly based on the context.\nContext: {context}\nQuestion: {q}\nAnswer:",
                    max_length=128, do_sample=False, num_beams=4
                )
                raw_a = qa_res[0]['generated_text'].strip()
                sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', context) if len(s.strip()) > 3]
                ans = self._format_flan_answer(raw_a, sents, "the subject", faq_length)
                verif = SourceVerifier.verify_faq(q, ans, context)
                return {
                    "question": q,
                    "answer": ans,
                    "category": "General",
                    "question_type": q.split()[0].capitalize() if q else "Factual",
                    "supporting_excerpt": verif.get("supporting_excerpt", context[:300]),
                    "verification_status": verif["status"],
                    "needs_review": verif["needs_review"],
                    "overall_score": verif["confidence"],
                    "context": context
                }
            except Exception as e:
                print(f"[Regenerate Error]: {e}")
        return None

    # =========================================================================
    # HELPER UTILITIES & COVERAGE REPORT
    # =========================================================================
    def _extract_subject(self, doc_nlp, doc_data: Dict[str, Any]) -> str:
        """Finds the main subject of the document."""
        if doc_nlp:
            first_sent = next(doc_nlp.sents, None)
            if first_sent:
                for token in first_sent:
                    if token.dep_ in ['nsubj', 'nsubjpass'] and len(token.text) > 2 and token.pos_ in ['PROPN', 'NOUN']:
                        compound_tokens = [w.text for w in token.lefts if w.dep_ in ['compound', 'amod']] + [token.text]
                        subj = " ".join(compound_tokens).strip()
                        if len(subj) > 2 and subj.lower() not in ['this', 'that', 'these', 'those', 'it', 'there']:
                            return subj

        headings = doc_data.get("headings", [])
        if headings:
            clean_h = re.sub(r'^(chapter|section|\d+[\.\)]*)\s*', '', headings[0], flags=re.IGNORECASE).strip()
            if len(clean_h) > 2:
                return clean_h

        return "the subject"

    def _clean_question(self, raw_q: str, subject: str) -> str:
        q = raw_q.strip()
        q = re.sub(r'^(Question|FAQ|Q)\s*:\s*', '', q, flags=re.IGNORECASE)
        q = re.sub(r'^\d+[\.\)]\s*', '', q)
        q = re.sub(r'^(Write a|Generate a|Based on the text,?|According to the text,?)\s*', '', q, flags=re.IGNORECASE)
        q = re.sub(r'\b([A-Za-z]+)\s+\1\b', r'\1', q, flags=re.IGNORECASE)

        if q:
            q = q[0].upper() + q[1:]
        q = q.rstrip('.!')
        if not q.endswith('?'):
            q += '?'

        # Only replace dangling personal pronouns (it, he, she) when subject is omitted
        if subject and subject.lower() not in q.lower():
            q = re.sub(r'\b(it|he|she)\b', subject, q, flags=re.IGNORECASE)
        return q

    def _is_valid_question(self, q: str) -> bool:
        if len(q.split()) < 4 or len(q) < 14:
            return False
        valid_starts = (
            'What', 'Who', 'When', 'Where', 'Why', 'How', 'Which', 
            'Is', 'Are', 'Can', 'Does', 'Do', 'Did', 'Has', 'Have', 'Could', 'Should'
        )
        if not any(q.startswith(start) for start in valid_starts):
            return False
        bad_phrases = ['the following text', 'the context', 'according to', 'the passage', 'text:']
        return not any(p in q.lower() for p in bad_phrases)

    def _format_flan_answer(self, raw_answer: str, chunk_sentences: list, subject: str, faq_length: str) -> str:
        raw_answer = raw_answer.strip().rstrip('.')
        best_sent = None
        for s in chunk_sentences:
            if raw_answer.lower() in s.lower():
                best_sent = s.strip()
                break
        if not best_sent and chunk_sentences:
            best_sent = chunk_sentences[0].strip()

        clean_sent = re.sub(r'^(It is|It was|It supports|The platform)\b', subject, best_sent or raw_answer, flags=re.IGNORECASE)
        if clean_sent and not clean_sent.endswith(('.', '!', '?')):
            clean_sent += '.'

        if faq_length == "small":
            return clean_sent if len(clean_sent.split()) <= 15 else (raw_answer + ".")
        elif faq_length == "detailed":
            return " ".join([s.strip() for s in chunk_sentences[:3]])
        return clean_sent

    def _build_coverage_report(
        self,
        doc_data: Dict[str, Any],
        chunks: List[Dict[str, Any]],
        analysis: Dict[str, Any],
        generated_count: int,
        verified_faqs: List[Dict[str, Any]],
        needs_review_count: int,
        rejected_count: int,
        duplicates_removed: int,
        engine_used: str
    ) -> Dict[str, Any]:
        """Phase 8: Constructs full document coverage and audit report."""
        covered_sections = list(dict.fromkeys([f.get("source_section", "General") for f in verified_faqs]))
        all_sections = list(dict.fromkeys([c.get("source_section", "General") for c in chunks]))
        missing_sections = [s for s in all_sections if s not in covered_sections and s != "General"]

        total_pages = doc_data.get("total_pages", 1)
        covered_pages = set()
        for f in verified_faqs:
            for p in f.get("source_pages", []):
                covered_pages.add(p)

        verified_count = sum(1 for f in verified_faqs if f.get("verification_status") == "verified")

        return {
            "engine": engine_used,
            "pages_processed": total_pages,
            "pages_covered": sorted(list(covered_pages)) or [1],
            "sections_identified": len(all_sections),
            "total_questions_generated": generated_count,
            "verified_count": verified_count,
            "needs_review_count": needs_review_count,
            "rejected_count": rejected_count,
            "duplicates_removed": duplicates_removed,
            "major_topics_covered": analysis.get("major_topics", []),
            "unaddressed_sections": missing_sections[:4],
            "completeness_score": round((len(covered_pages) / max(1, total_pages)) * 100, 1)
        }

    def _empty_coverage_report(self, source_document: str) -> Dict[str, Any]:
        return {
            "engine": "None",
            "pages_processed": 0,
            "pages_covered": [],
            "sections_identified": 0,
            "total_questions_generated": 0,
            "verified_count": 0,
            "needs_review_count": 0,
            "rejected_count": 0,
            "duplicates_removed": 0,
            "major_topics_covered": [],
            "unaddressed_sections": [],
            "completeness_score": 0.0
        }
