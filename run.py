import os
# Prevent OpenMP runtime library conflict on Windows
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

from backend.app import create_app

app = create_app()

if __name__ == '__main__':
    # Ensure necessary folders exist
    for folder in ['uploads', 'exports', 'database', 'models']:
        os.makedirs(folder, exist_ok=True)
        
    print("Starting FAQForge NLP server...")
    app.run(debug=True, host='0.0.0.0', port=5000)
