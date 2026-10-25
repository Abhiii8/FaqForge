import os
from flask import Blueprint, request, jsonify, current_app, Response
from werkzeug.utils import secure_filename
from backend.models.database import db, Document, FAQ, Keyword, Entity
from backend.nlp.document_processor import DocumentProcessor
from backend.nlp.pipeline import NLPPipeline
from backend.utils.progress import progress_catcher

api_bp = Blueprint('api', __name__)
nlp_pipeline = NLPPipeline()

ALLOWED_EXTENSIONS = {'txt', 'pdf', 'docx'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# =========================================================================
# OLLAMA STATUS & CONFIGURATION ENDPOINTS
# =========================================================================

@api_bp.route('/ollama/status', methods=['GET'])
def get_ollama_status():
    """Returns real-time status of local Ollama engine and installed models."""
    status = nlp_pipeline.generator.get_engine_status()
    # Provide backward-compatible convenience fields for frontend clients
    status["status"] = "ready" if (status.get("ollama_running") and status.get("model_ready")) else "offline"
    status["running"] = status.get("ollama_running", False)
    status["model"] = status.get("configured_model", "qwen2.5:3b")
    return jsonify(status), 200

@api_bp.route('/ollama/config', methods=['POST'])
def configure_ollama():
    """Updates the active Ollama model name."""
    data = request.json or {}
    model_name = data.get("model", "").strip()
    if not model_name:
        return jsonify({"error": "Model name required"}), 400
    
    nlp_pipeline.generator.ollama.model = model_name
    return jsonify({
        "message": f"Configured model set to '{model_name}'",
        "active_model": model_name,
        "is_available": nlp_pipeline.generator.ollama.is_model_available(model_name)
    }), 200

@api_bp.route('/ollama/pull', methods=['POST'])
def pull_ollama_model():
    """Triggers downloading/pulling a model locally via Ollama API."""
    data = request.json or {}
    model_name = data.get("model", nlp_pipeline.generator.ollama.model).strip()
    
    # Check if Ollama is running
    conn = nlp_pipeline.generator.ollama.check_connection()
    if not conn["running"]:
        return jsonify({"error": conn.get("error", "Ollama is not running")}), 503
        
    try:
        # Non-streaming pull check
        generator = nlp_pipeline.generator.ollama.pull_model(model_name)
        last_status = "started"
        for chunk in generator:
            if chunk.get("status") == "error":
                return jsonify({"error": chunk.get("error")}), 500
            last_status = chunk.get("status", last_status)
            
        return jsonify({
            "message": f"Model '{model_name}' pulled successfully.",
            "status": last_status
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# =========================================================================
# DOCUMENT UPLOAD & PARSING
# =========================================================================

@api_bp.route('/upload', methods=['POST'])
def upload_file():
    """Uploads file or text, extracts structure, and creates document record."""
    if 'file' not in request.files and 'text' not in request.form:
        return jsonify({'error': 'No file or text provided'}), 400

    original_text = ""
    filename = "Manual Input"
    file_type = "txt"
    filepath = None

    if 'file' in request.files:
        file = request.files['file']
        if file.filename != '':
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                file_type = filename.rsplit('.', 1)[1].lower()
                filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                
                try:
                    doc_data = DocumentProcessor.extract_document(filepath)
                    original_text = doc_data["text"]
                except Exception as e:
                    return jsonify({'error': str(e)}), 400
            else:
                return jsonify({'error': 'Invalid file type. Allowed: .pdf, .docx, .txt'}), 400

    if 'text' in request.form and request.form['text'].strip():
        original_text = request.form['text'].strip()
        
    if not original_text.strip():
        return jsonify({'error': 'Document or text is empty or contains no extractable content.'}), 400

    doc = Document(filename=filename, file_type=file_type, original_text=original_text)
    db.session.add(doc)
    db.session.commit()

    return jsonify({'message': 'Upload successful', 'document': doc.to_dict()}), 201

# =========================================================================
# FAQ GENERATION & REGENERATION
# =========================================================================

@api_bp.route('/generate', methods=['POST'])
def generate_faqs():
    """Generates structured, verified FAQs using local multi-stage pipeline."""
    data = request.json or {}
    doc_id = data.get('document_id')
    num_faqs = int(data.get('num_faqs', 5))
    faq_length = data.get('faq_length', 'medium')
    question_focus = data.get('question_focus', 'all')
    
    if not doc_id:
        return jsonify({'error': 'document_id required'}), 400
        
    doc = Document.query.get(doc_id)
    if not doc:
        return jsonify({'error': 'Document not found'}), 404
        
    try:
        if progress_catcher:
            progress_catcher.set("Extracting document content and analyzing sections...")

        # Check if original file is in upload folder to preserve full page structure
        filepath = os.path.join(current_app.config['UPLOAD_FOLDER'], doc.filename)
        if os.path.exists(filepath) and doc.file_type in ['pdf', 'docx']:
            doc_data = DocumentProcessor.extract_document(filepath)
            if progress_catcher:
                progress_catcher.set("Generating questions with local Ollama Qwen2.5 3B...")
            nlp_results = nlp_pipeline.process_document_data(
                doc_data=doc_data,
                num_faqs=num_faqs,
                faq_length=faq_length,
                source_document=doc.filename,
                question_focus=question_focus
            )
        else:
            if progress_catcher:
                progress_catcher.set("Generating questions with local Ollama Qwen2.5 3B...")
            nlp_results = nlp_pipeline.process_text(
                text=doc.original_text,
                num_faqs=num_faqs,
                faq_length=faq_length,
                source_document=doc.filename,
                question_focus=question_focus
            )
        
        if progress_catcher:
            progress_catcher.set("Verifying factual grounding and deduplicating...")

        doc.processed_text = nlp_results['processed_text']
        
        # Save Keywords
        for kw in nlp_results.get('keywords', []):
            k_obj = Keyword(document_id=doc.id, keyword=kw['keyword'], score=kw['score'])
            db.session.add(k_obj)
            
        # Save Entities
        for ent in nlp_results.get('entities', []):
            e_obj = Entity(document_id=doc.id, entity=ent['entity'], entity_type=ent['entity_type'])
            db.session.add(e_obj)
            
        # Save Structured FAQs
        created_faqs = []
        for faq_data in nlp_results.get('faqs', []):
            pages_val = ",".join(map(str, faq_data.get('source_pages', [1])))
            faq = FAQ(
                document_id=doc.id,
                question=faq_data['question'],
                answer=faq_data['answer'],
                category=faq_data.get('category', 'General'),
                question_type=faq_data.get('question_type', 'factual'),
                question_score=faq_data.get('question_score', 0.95),
                answer_score=faq_data.get('answer_score', 0.95),
                overall_score=faq_data.get('overall_score', 0.95),
                context=faq_data.get('context', ''),
                source_document=faq_data.get('source_document', doc.filename),
                source_pages=pages_val,
                source_section=faq_data.get('source_section', 'General'),
                supporting_excerpt=faq_data.get('supporting_excerpt', ''),
                verification_status=faq_data.get('verification_status', 'verified'),
                needs_review=bool(faq_data.get('needs_review', False))
            )
            db.session.add(faq)
            created_faqs.append(faq)
            
        db.session.commit()
        
        return jsonify({
            'message': 'Generation complete',
            'faqs': [f.to_dict() for f in created_faqs],
            'coverage_report': nlp_results.get('coverage_report', {}),
            'engine_status': nlp_results.get('engine_status', {}),
            'analysis': {
                'keywords': nlp_results.get('keywords', []),
                'entities': nlp_results.get('entities', []),
                'pos_tags': nlp_results.get('pos_tags', [])
            }
        }), 200
        
    except Exception as e:
        db.session.rollback()
        import traceback
        traceback.print_exc()
        return jsonify({'error': str(e)}), 500

@api_bp.route('/faqs/<int:faq_id>/regenerate', methods=['POST'])
def regenerate_faq(faq_id):
    """Regenerates a single FAQ with source verification."""
    faq = FAQ.query.get_or_404(faq_id)
    data = request.json or {}
    faq_length = data.get('faq_length', 'medium')
    target = data.get('target', 'both') # 'question', 'answer', or 'both'
    
    try:
        new_faq_data = nlp_pipeline.generator.regenerate_faq(
            context=faq.context or faq.supporting_excerpt or faq.answer,
            target=target,
            faq_length=faq_length
        )
        if new_faq_data:
            if target in ['question', 'both']:
                faq.question = new_faq_data['question']
            if target in ['answer', 'both']:
                faq.answer = new_faq_data['answer']
                
            faq.category = new_faq_data.get('category', faq.category)
            faq.question_type = new_faq_data.get('question_type', faq.question_type)
            faq.supporting_excerpt = new_faq_data.get('supporting_excerpt', faq.supporting_excerpt)
            faq.verification_status = new_faq_data.get('verification_status', faq.verification_status)
            faq.needs_review = new_faq_data.get('needs_review', faq.needs_review)
            faq.overall_score = new_faq_data.get('overall_score', faq.overall_score)
            
            db.session.commit()
            return jsonify(faq.to_dict()), 200
        else:
            return jsonify({'error': 'Failed to regenerate FAQ'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# =========================================================================
# DOCUMENT & FAQ CRUD ENDPOINTS
# =========================================================================

@api_bp.route('/documents', methods=['GET'])
def get_documents():
    docs = Document.query.order_by(Document.created_at.desc()).all()
    return jsonify([d.to_dict() for d in docs]), 200

@api_bp.route('/documents/<int:doc_id>', methods=['GET'])
def get_document(doc_id):
    doc = Document.query.get_or_404(doc_id)
    return jsonify(doc.to_dict()), 200

@api_bp.route('/documents/<int:doc_id>/faqs', methods=['GET'])
def get_document_faqs(doc_id):
    faqs = FAQ.query.filter_by(document_id=doc_id).all()
    return jsonify([f.to_dict() for f in faqs]), 200

@api_bp.route('/faqs/<int:faq_id>', methods=['PUT'])
def update_faq(faq_id):
    faq = FAQ.query.get_or_404(faq_id)
    data = request.json or {}
    
    if 'question' in data: faq.question = data['question']
    if 'answer' in data: faq.answer = data['answer']
    if 'category' in data: faq.category = data['category']
    if 'needs_review' in data: faq.needs_review = bool(data['needs_review'])
    if 'verification_status' in data: faq.verification_status = data['verification_status']
    
    db.session.commit()
    return jsonify(faq.to_dict()), 200

@api_bp.route('/faqs/<int:faq_id>', methods=['DELETE'])
def delete_faq(faq_id):
    faq = FAQ.query.get_or_404(faq_id)
    db.session.delete(faq)
    db.session.commit()
    return jsonify({'message': 'Deleted successfully'}), 200

@api_bp.route('/progress', methods=['GET'])
def get_progress():
    line = progress_catcher.last_line if progress_catcher else ""
    return jsonify({'progress': line}), 200
