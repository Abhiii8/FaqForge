from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Document(db.Model):
    __tablename__ = 'documents'
    
    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    file_type = db.Column(db.String(50), nullable=False)
    original_text = db.Column(db.Text, nullable=False)
    processed_text = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    keywords = db.relationship('Keyword', backref='document', lazy=True, cascade="all, delete-orphan")
    entities = db.relationship('Entity', backref='document', lazy=True, cascade="all, delete-orphan")
    faqs = db.relationship('FAQ', backref='document', lazy=True, cascade="all, delete-orphan")

    def to_dict(self):
        return {
            'id': self.id,
            'filename': self.filename,
            'file_type': self.file_type,
            'created_at': self.created_at.isoformat(),
            'faq_count': len(self.faqs)
        }

class Keyword(db.Model):
    __tablename__ = 'keywords'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    keyword = db.Column(db.String(100), nullable=False)
    score = db.Column(db.Float, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'keyword': self.keyword,
            'score': self.score
        }

class Entity(db.Model):
    __tablename__ = 'entities'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    entity = db.Column(db.String(255), nullable=False)
    entity_type = db.Column(db.String(100), nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'entity': self.entity,
            'entity_type': self.entity_type
        }

class FAQ(db.Model):
    __tablename__ = 'faqs'
    
    id = db.Column(db.Integer, primary_key=True)
    document_id = db.Column(db.Integer, db.ForeignKey('documents.id'), nullable=False)
    question = db.Column(db.Text, nullable=False)
    answer = db.Column(db.Text, nullable=False)
    question_type = db.Column(db.String(50), nullable=True)
    category = db.Column(db.String(100), nullable=True, default="General")
    question_score = db.Column(db.Float, nullable=True)
    answer_score = db.Column(db.Float, nullable=True)
    overall_score = db.Column(db.Float, nullable=True)
    context = db.Column(db.Text, nullable=True)
    
    # Structured source citation and verification fields
    source_document = db.Column(db.String(255), nullable=True, default="")
    source_pages = db.Column(db.String(100), nullable=True, default="1")
    source_section = db.Column(db.String(255), nullable=True, default="General")
    supporting_excerpt = db.Column(db.Text, nullable=True, default="")
    verification_status = db.Column(db.String(50), nullable=True, default="verified")
    needs_review = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        # Format source_pages into list of ints if possible
        pages_list = [1]
        if self.source_pages:
            try:
                pages_list = [int(p.strip()) for p in str(self.source_pages).split(",") if p.strip().isdigit()]
            except Exception:
                pages_list = [1]
                
        return {
            'id': self.id,
            'document_id': self.document_id,
            'question': self.question,
            'answer': self.answer,
            'category': self.category or "General",
            'question_type': self.question_type or "Factual",
            'question_score': self.question_score or 0.95,
            'answer_score': self.answer_score or 0.95,
            'overall_score': self.overall_score or 0.95,
            'context': self.context or "",
            'source_document': self.source_document or "",
            'source_pages': pages_list or [1],
            'source_section': self.source_section or "General",
            'supporting_excerpt': self.supporting_excerpt or "",
            'verification_status': self.verification_status or "verified",
            'needs_review': bool(self.needs_review),
            'created_at': self.created_at.isoformat()
        }
