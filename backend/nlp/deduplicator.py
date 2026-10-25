import re
from typing import List, Dict, Any, Tuple
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

class SemanticDeduplicator:
    """
    High-accuracy duplicate detector checking normalized wording,
    question intent similarity, and answer semantic overlap.
    """

    def __init__(self, question_threshold: float = 0.65, answer_threshold: float = 0.70):
        self.question_threshold = question_threshold
        self.answer_threshold = answer_threshold

    def is_duplicate(self, candidate_faq: Dict[str, Any], existing_faqs: List[Dict[str, Any]]) -> Tuple[bool, str]:
        """
        Compares candidate FAQ against existing collection.
        Returns (is_duplicate: bool, reason: str).
        """
        if not existing_faqs:
            return False, ""

        q_cand = candidate_faq.get("question", "").strip()
        a_cand = candidate_faq.get("answer", "").strip()

        # 1. Exact or near-exact normalized check
        q_norm = self._normalize(q_cand)
        a_norm = self._normalize(a_cand)

        for idx, item in enumerate(existing_faqs):
            q_exist_norm = self._normalize(item.get("question", ""))
            a_exist_norm = self._normalize(item.get("answer", ""))

            # Direct question match
            if q_norm == q_exist_norm:
                return True, f"Identical question to FAQ #{idx + 1}"

            # Direct answer match
            if a_norm and a_norm == a_exist_norm:
                return True, f"Identical answer to FAQ #{idx + 1}"

        # 2. Vector Cosine Similarity
        all_qs = [f.get("question", "") for f in existing_faqs] + [q_cand]
        all_as = [f.get("answer", "") for f in existing_faqs] + [a_cand]

        try:
            vec_q = TfidfVectorizer(stop_words='english', ngram_range=(1, 2))
            q_mat = vec_q.fit_transform(all_qs)
            q_sims = cosine_similarity(q_mat[-1], q_mat[:-1])[0]

            max_q_sim = float(q_sims.max())
            max_q_idx = int(q_sims.argmax())

            if max_q_sim >= self.question_threshold:
                return True, f"Question has {round(max_q_sim * 100)}% semantic overlap with FAQ #{max_q_idx + 1}"

            vec_a = TfidfVectorizer(stop_words='english')
            a_mat = vec_a.fit_transform(all_as)
            a_sims = cosine_similarity(a_mat[-1], a_mat[:-1])[0]

            max_a_sim = float(a_sims.max())
            max_a_idx = int(a_sims.argmax())

            if max_a_sim >= self.answer_threshold:
                return True, f"Answer answers identical facts ({round(max_a_sim * 100)}% overlap) as FAQ #{max_a_idx + 1}"

        except Exception:
            pass

        return False, ""

    @staticmethod
    def _normalize(text: str) -> str:
        """Removes punctuation and normalizes case and whitespace."""
        cleaned = re.sub(r'[^\w\s]', '', text.lower())
        return " ".join(cleaned.split())
