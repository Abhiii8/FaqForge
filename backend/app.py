import os
from flask import Flask
from flask_cors import CORS
from backend.models.database import db
from backend.utils.progress import init_catcher

# Initialize stderr catcher globally before other things load
init_catcher()

def create_app(test_config=None):
    app = Flask(__name__, 
                static_folder='../frontend', 
                static_url_path='/')
    
    # Configure Database
    db_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'database', 'faqforge.db')
    app.config['SQLALCHEMY_DATABASE_URI'] = f'sqlite:///{db_path}'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    # Configure Uploads & Exports
    app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'uploads')
    app.config['EXPORT_FOLDER'] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'exports')
    
    # Enable CORS
    CORS(app)
    
    # Initialize plugins
    db.init_app(app)
    
    with app.app_context():
        db.create_all()
        # Safe migration for existing SQLite database
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                existing_cols = [row[1] for row in conn.execute(text("PRAGMA table_info(faqs)")).fetchall()]
                col_defs = {
                    "category": "TEXT DEFAULT 'General'",
                    "source_document": "TEXT DEFAULT ''",
                    "source_pages": "TEXT DEFAULT '1'",
                    "source_section": "TEXT DEFAULT 'General'",
                    "supporting_excerpt": "TEXT DEFAULT ''",
                    "verification_status": "TEXT DEFAULT 'verified'",
                    "needs_review": "BOOLEAN DEFAULT 0"
                }
                for col_name, col_type in col_defs.items():
                    if col_name not in existing_cols:
                        conn.execute(text(f"ALTER TABLE faqs ADD COLUMN {col_name} {col_type}"))
                conn.commit()
        except Exception as e:
            print(f"[DB Migration Note]: {e}")

    # Register blueprints (routes)
    from backend.routes.api import api_bp
    from backend.routes.export import export_bp
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(export_bp, url_prefix='/api/export')
    
    # Serve static frontend files
    @app.route('/')
    @app.route('/landing')
    @app.route('/landing.html')
    def index():
        return app.send_static_file('landing.html')
        
    @app.route('/app')
    @app.route('/studio')
    @app.route('/index.html')
    def app_studio():
        return app.send_static_file('index.html')

    @app.route('/results.html')
    def results():
        return app.send_static_file('results.html')
        
    @app.route('/history.html')
    def history():
        return app.send_static_file('history.html')

    return app
