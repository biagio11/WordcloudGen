import argparse
from datetime import datetime
import json
import os
import numpy as np
import matplotlib.pyplot as plt
import pymupdf
import fitz
import nltk
from nltk.stem import WordNetLemmatizer
from nltk.corpus import stopwords
from wordcloud import WordCloud

# Function to extract text from a PDF file


def extract_text_from_pdf(pdf_path):
    document = pymupdf.open(pdf_path)
    text = ""
    for page in document:
        text += page.get_text()
    return text


# Function to preprocess the text: tokenization, lemmatization, and removing stopwords
def preprocess_text(text, lang, exclude_words):
    nltk.download('punkt')
    nltk.download('wordnet')
    nltk.download('stopwords')

    # Replace multi-word phrases with single tokens
    for phrase in exclude_words:
        phrase = phrase.strip()
        if ' ' in phrase:
            text = text.replace(phrase, '_'.join(phrase.split()))

    # Tokenize the text
    tokens = nltk.word_tokenize(text)

    # Initialize lemmatizer
    lemmatizer = WordNetLemmatizer()

    # Get stopwords for the specified language
    stop_words = set(stopwords.words(lang))

    # Convert exclude_words to a set with underscores replacing spaces
    exclude_words_set = set(word.strip().lower() for word in exclude_words)

    # Lemmatize and remove stopwords and excluded words
    processed_tokens = [
        lemmatizer.lemmatize(word.lower())
        for word in tokens
        if word.isalpha() and word.lower() not in stop_words and word.lower() not in exclude_words_set
    ]

    return ' '.join(processed_tokens).replace('_', ' ')


def color_func_from_file(color_file):
    # Default colors
    default_colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728',
                      '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

    # Create the ./colors folder if it doesn't exist
    os.makedirs('./colors', exist_ok=True)

    # Path to the default colors file
    default_colors_file = './colors/default_colors.json'

    # If color_file is None, generate a default colors file
    if color_file is None:
        with open(default_colors_file, 'w') as f:
            json.dump({"colors": default_colors}, f, indent=4)
        print(f"Default colors file generated: {default_colors_file}")
        color_file = default_colors_file
    else:
        # If the specified color file doesn't exist, use the default colors
        if not os.path.exists(color_file):
            print(
                f"{color_file} not found. Using default colors from {default_colors_file}.")
            color_file = default_colors_file

    # Load colors from the specified file
    with open(color_file, 'r') as f:
        colors = json.load(f).get("colors", default_colors)

    return lambda *args, **kwargs: np.random.choice(colors)


def main():
    # Parse command-line arguments
    parser = argparse.ArgumentParser(
        description='Generate a word cloud from a PDF or text file.')
    parser.add_argument('--pdf', type=str, help='Path to the PDF file.')
    parser.add_argument('--txt', type=str, help='Path to the text file.')
    parser.add_argument('--lang', type=str, default='english',
                        help='Language for stopwords.')
    parser.add_argument('--width', type=int, default=1920,
                        help='Width of the word cloud image.')
    parser.add_argument('--height', type=int, default=1080,
                        help='Height of the word cloud image.')
    parser.add_argument('--background', type=str, default='white',
                        help='Background color of the word cloud (e.g., "white", "black", or "transparent").')
    parser.add_argument('--font', type=str, help='Path to the font file.')
    parser.add_argument('--exclude-words', type=str, nargs='*', default=[],
                        help='List of words to exclude from the word cloud.')
    parser.add_argument('--color_file', type=str,
                        help='Path to a JSON file containing colors.')

    args = parser.parse_args()

    # Ensure a PDF or text file is provided
    if not args.pdf and not args.txt:
        print("Error: Please provide a PDF or text file.")
        return

    # Extract text from the appropriate file
    if args.pdf:
        text = extract_text_from_pdf(args.pdf)
    else:
        with open(args.txt, 'r', encoding='utf-8') as file:
            text = file.read()

    # Preprocess the text
    processed_text = preprocess_text(text, args.lang, args.exclude_words)

    # Select color function
    color_func = color_func_from_file(color_file)

    # Generate the word cloud
    wordcloud = WordCloud(
        width=args.width,
        height=args.height,
        background_color='rgba(255, 255, 255, 0)' if args.background == 'transparent' else args.background,
        mode='RGBA' if args.background == 'transparent' else 'RGB',
        font_path=args.font,
        color_func=color_func
    ).generate(processed_text)

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Save to file with timestamp
    filename = f"./output/wordcloud_{timestamp}.png"
    wordcloud.to_file(filename)
    print(f"Word cloud saved as {filename}")

    # Display the word cloud
    plt.figure(figsize=(args.width / 100, args.height / 100))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')  # Remove axes
    plt.show()


if __name__ == '__main__':
    main()
