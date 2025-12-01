# Add this code after your imports in both files
import nltk
import ssl

# Fix SSL certificate issues if they occur
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:
    ssl._create_default_https_context = _create_unverified_https_context

# Download required NLTK data
def download_nltk_data():
    required_data = [
        'punkt',           # Tokenizer
        'stopwords',       # Stop words
        'wordnet',         # WordNet lemmatizer
        'punkt_tab',       # Updated punkt tokenizer
        'averaged_perceptron_tagger'  # POS tagger (might be needed)
    ]
    
    for data in required_data:
        try:
            nltk.download(data, quiet=True)
        except Exception as e:
            print(f"Could not download {data}: {e}")

# Call this function before using any NLTK features
download_nltk_data()