from datetime import datetime
import os
import matplotlib.pyplot as plt
from wordcloud import WordCloud
import numpy as np
import pymupdf
import nltk
from nltk.stem import WordNetLemmatizer
from nltk.corpus import stopwords
from wordcloud import WordCloud
import json

import tkinter
import tkinter.messagebox
import customtkinter
from CTkColorPicker import *
from CTkMessagebox import CTkMessagebox
from customtkinter import filedialog
from CTkToolTip import *
from CTkListbox import *

# Function to extract text from a PDF file


def extract_text_from_pdf(pdf_path):
    document = pymupdf.open(pdf_path)
    text = ""
    for page in document:
        text += page.get_text()
    return text

# Function to preprocess the text: tokenization, lemmatization, and removing stopwords


def preprocess_text(text, lang, exclude_words):
    # Normalize the text to lowercase
    text = text.lower()

    # Replace multi-word phrases with single tokens
    for phrase in exclude_words:
        phrase = phrase.strip().lower()
        if ' ' in phrase:
            text = text.replace(phrase, '_'.join(phrase.split()))
    #print("Text after replacing phrases:", text) # Debug

    # Tokenize the text
    tokens = nltk.word_tokenize(text)
    #print("Tokens:", tokens) # Debug

    # Initialize lemmatizer
    lemmatizer = WordNetLemmatizer()

    # Get stopwords for the specified language
    stop_words = set(stopwords.words(lang))

    # Convert exclude_words to a set with underscores replacing spaces
    exclude_words_set = set(word.strip().lower() for word in exclude_words)

    # Lemmatize and remove stopwords and excluded words
    processed_tokens = [
        lemmatizer.lemmatize(word)
        for word in tokens
        if word.isalpha() and word not in stop_words and word not in exclude_words_set
    ]

    # Join the processed tokens into a single string
    processed_text = str(' '.join(processed_tokens).replace('_', ' '))
    print(preprocess_text)

    #print("Processed Tokens:", processed_tokens) # Debug

    return processed_text


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

# Function to generate and save word cloud


def generate_word_cloud(pdf_path=None, txt_path=None, lang='english', width=1920, height=1080, background='white', font=None, exclude_words=[], output_dir=None, color_file=None):
    # Extract text from the appropriate file
    if pdf_path:
        text = extract_text_from_pdf(pdf_path)
    else:
        with open(txt_path, 'r', encoding='utf-8') as file:
            text = file.read()

    # Preprocess the text
    processed_text = preprocess_text(text, lang, exclude_words)

    # Select color function
    color_func = color_func_from_file(color_file)

    # Generate the word cloud
    wordcloud = WordCloud(
        width=width,
        height=height,
        background_color='rgba(255, 255, 255, 0)' if background == 'transparent' else background,
        mode='RGBA' if background == 'transparent' else 'RGB',
        font_path=font if font else None,
        color_func=color_func
    ).generate(processed_text)

    # Generate timestamp
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Save to file with timestamp
    filename = f"{output_dir}/wordcloud_{timestamp}.png"
    wordcloud.to_file(filename)
    print(f"Word cloud saved as {filename}")

    # Display the word cloud
    plt.figure(figsize=(width / 100, height / 100))
    plt.imshow(wordcloud, interpolation='bilinear')
    plt.axis('off')  # Remove axes
    plt.gcf().canvas.manager.set_window_title('Generated Wordcloud')
    plt.show()

    return filename


# GUI
# Modes: "System" (standard), "Dark", "Light"
customtkinter.set_appearance_mode("System")
# Themes: "blue" (standard), "green", "dark-blue"
customtkinter.set_default_color_theme("green")

# Function to handle GUI button click


def on_generate_button_click():
    pdf_path = pdf_path_entry.get()
    txt_path = txt_path_entry.get()
    lang = language_var.get()
    width = int(width_entry.get())
    height = int(height_entry.get())
    background = background_entry.get()
    font = font_path_entry.get()
    output_folder = output_folder_entry.get()

    colors = [color_list_box.get(idx) for idx in range(color_list_box.size())]
    color_file_path = save_colors_to_file(colors)

    # Get excluded words and strip spaces
    exclude_words = [word.strip().lower() for word in exclude_words_textbox.get(
        "1.0", "end-1c").split(',')]
    #print(exclude_words) # Debug

    if not pdf_path and not txt_path:
        CTkMessagebox(title="Error", message="Please provide a PDF or text file.",
                      icon="warning", font=customtkinter.CTkFont(size=16))
        return

    if not output_folder:  # Check if output folder is not specified
        CTkMessagebox(title="Error", message="Please specify the output folder.",
                      icon="warning", font=customtkinter.CTkFont(size=16))
        return

    try:
        filename = generate_word_cloud(
            pdf_path, txt_path, lang, width, height, background, font, exclude_words, output_folder, color_file_path)
        CTkMessagebox(
            title="Success", message=f"Word cloud saved as {filename}", icon="check", font=customtkinter.CTkFont(size=16))
    except Exception as e:
        CTkMessagebox(title="Error", message=str(e), icon="cancel",
                      font=customtkinter.CTkFont(size=16))


def selectfile_pdf():
    filename_pdf.set(filedialog.askopenfilename(
        filetypes=[("PDF files", "*.pdf")]))


def selectfile_txt():
    filename_txt.set(filedialog.askopenfilename(
        filetypes=[("Text files", "*.txt")]))


def selectfile_font():
    filename_font.set(filedialog.askopenfilename(
        filetypes=[("Font files", "*.ttf *.otf")]))


def language_combobox_callback(choice):
    # print("Combobox dropdown clicked:", choice)
    language_var.set(str(choice).lower())


def select_background_color():
    pick_color = AskColor(title="Choose background color")
    color = pick_color.get()  # get the color string
    if color:
        background_entry.delete(0, tkinter.END)
        background_entry.insert(0, color)


def select_output_folder():
    output_folder = filedialog.askdirectory()
    output_folder_var.set(output_folder)


def add_color():
    color_picker = AskColor(title="Choose color")
    color = color_picker.get()
    if color:
        color_list_box.insert(tkinter.END, color)


def remove_selected_color():
    selected_indices = color_list_box.curselection()
    if isinstance(selected_indices, int):  # Check if it's an integer
        selected_indices = (selected_indices,)  # Convert to a tuple
    if selected_indices:
        # Convert selected_indices from a tuple to a list and iterate backwards to avoid index shifting
        for index in reversed(selected_indices):
            color_list_box.delete(index)


def save_colors_to_file(colors):
    global colors_file_path

    os.makedirs('./colors', exist_ok=True)

    # If no colors specified or colors_file_path is None, return None
    if not colors:
        return None

    try:
        # Read colors from the current file
        with open(colors_file_path, 'r') as file:
            data = json.load(file)
            current_colors = data.get("colors", [])

        # Check if the colors inside the file are the same as the colors parameter
        if set(current_colors) == set(colors):
            return colors_file_path  # If the colors are the same, return the existing file path

    except Exception as e:
        # Handle file read error
        print(f"Error reading color file: {e}")
        return None

    # Save the colors to a new file
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    new_color_file_path = f'./colors/colors_{timestamp}.json'
    with open(new_color_file_path, 'w') as file:
        json.dump({"colors": list(colors)}, file, indent=4)

    print(colors_file_path)
    return new_color_file_path


def load_colors_from_file():
    global colors_file_path

    # Open a file dialog to select a color file
    file_path = filedialog.askopenfilename(
        title="Select Color File", filetypes=[("JSON files", "*.json")])
    if file_path:
        try:
            # Read colors from the selected file
            with open(file_path, 'r') as file:
                data = json.load(file)
                colors = data.get("colors", [])

            # Clear the current listbox
            color_list_box.delete(0, tkinter.END)

            # Insert the colors into the listbox
            for color in colors:
                color_list_box.insert(tkinter.END, color)

            # Update the colors file path
            colors_file_path = file_path

        except Exception as e:
            # Handle file read error
            print(f"Error reading color file: {e}")

        print(colors_file_path)


# Create the GUI
app = customtkinter.CTk()
app.title("Word Cloud Generator")
app.geometry("600x800")

# Configure the grid layout to be resizable
app.grid_columnconfigure(1, weight=1)
for i in range(15):
    app.grid_rowconfigure(i, weight=1)

normal_font = customtkinter.CTkFont(size=16)
standard_pady = (10, 10)
standard_padx_left = (30, 5)
standard_padx_right = (5, 30)

# Info
text_info = "To generate a WordCloud please select a PDF OR a text file, select the document language, set the width and the height, choose a background and a font, you might even choose to exclude some words, then press Generate!"
customtkinter.CTkLabel(app, text=text_info, width=40, height=28, fg_color='transparent', font=normal_font,
                       wraplength=500).grid(row=0, column=0, padx=10, pady=(20, 25), columnspan=3, sticky="ew")

# PDF Path
filename_pdf = customtkinter.StringVar(value="")
pdf_label = customtkinter.CTkLabel(app, text="PDF Path:", font=normal_font)
pdf_label.grid(row=1, column=0, padx=standard_padx_left, pady=0, sticky="w")
CTkToolTip(pdf_label, "Select or enter a PDF file path")
pdf_path_entry = customtkinter.CTkEntry(
    app, width=300, textvariable=filename_pdf, placeholder_text="Select or enter a PDF file path", font=normal_font)
pdf_path_entry.grid(row=1, column=1, padx=10, pady=0, sticky="ew")
customtkinter.CTkButton(app, text="Choose file", command=selectfile_pdf,
                        font=normal_font).grid(row=1, column=2, padx=standard_padx_right, pady=0, sticky="ew")

# OR
customtkinter.CTkLabel(app, text='OR', fg_color='transparent', font=customtkinter.CTkFont(
    size=18, weight="bold")).grid(row=2, column=1, padx=10, pady=0, sticky="ew")

# Text Path
filename_txt = customtkinter.StringVar(value="")
txt_label = customtkinter.CTkLabel(app, text="Text Path:", font=normal_font)
txt_label.grid(row=3, column=0, padx=standard_padx_left, pady=0, sticky="w")
CTkToolTip(txt_label, "Select or enter a text file path")
txt_path_entry = customtkinter.CTkEntry(
    app, width=300, textvariable=filename_txt, placeholder_text="Select or enter a text file path", font=normal_font)
txt_path_entry.grid(row=3, column=1, padx=10, pady=0, sticky="ew")
customtkinter.CTkButton(app, text="Choose file", command=selectfile_txt,
                        font=normal_font).grid(row=3, column=2, padx=standard_padx_right, pady=0, sticky="ew")

# Language
language_label = customtkinter.CTkLabel(
    app, text="Corpus language:", font=normal_font)
language_label.grid(row=4, column=0, padx=standard_padx_left,
                    pady=standard_pady, sticky="w")
CTkToolTip(language_label, "Select the language of the text corpus")
language_var = customtkinter.StringVar(value="english")
customtkinter.CTkComboBox(app, values=["english", "italian", "german", "slovene", "spanish", "french"],
                          command=language_combobox_callback, variable=language_var, width=400, font=normal_font).grid(row=4, column=1, padx=(15, 10), pady=(30, 10), columnspan=1, sticky="ew")

# Create a frame to contain the width and height elements
wh_frame = customtkinter.CTkFrame(app, fg_color='transparent')
wh_frame.grid(row=5, column=1, columnspan=2,
              padx=standard_padx_right, pady=standard_pady, sticky="ew")

# Adjust column weights for the frame
wh_frame.grid_columnconfigure(0, weight=1)
wh_frame.grid_columnconfigure(1, weight=1)
wh_frame.grid_columnconfigure(2, weight=1)
wh_frame.grid_columnconfigure(3, weight=1)

wh_label = customtkinter.CTkLabel(app, text="Width ⨯ Height", font=normal_font)
wh_label.grid(row=5, column=0, padx=standard_padx_left,
              pady=standard_pady, sticky="w")
CTkToolTip(wh_label, "Enter width ⨯ height of the word cloud in pixels")

# Width
width_entry = customtkinter.CTkEntry(wh_frame, font=normal_font, width=100)
width_entry.insert(0, '1920')
width_entry.grid(row=0, column=1, padx=(0, 20), pady=0, sticky="ew")

# Height
height_entry = customtkinter.CTkEntry(wh_frame, font=normal_font, width=100)
height_entry.insert(0, '1080')
height_entry.grid(row=0, column=3, padx=20, pady=0, sticky="ew")


# Background Color
background_label = customtkinter.CTkLabel(
    app, text="Background Color:", font=normal_font)
background_label.grid(row=7, column=0, padx=standard_padx_left,
                      pady=standard_pady, sticky="w")
CTkToolTip(background_label, "Select the background color or enter 'transparent'")
background_entry = customtkinter.CTkEntry(app, font=normal_font)
background_entry.insert(0, 'transparent')
background_entry.grid(row=7, column=1, padx=10,
                      pady=standard_pady, sticky="ew")
customtkinter.CTkButton(app, text="Choose color", command=select_background_color,
                        font=normal_font).grid(row=7, column=2, padx=standard_padx_right, pady=standard_pady, sticky="e")

# Font Path
filename_font = customtkinter.StringVar(value="")
font_label = customtkinter.CTkLabel(app, text="Font Path:", font=normal_font)
font_label.grid(row=8, column=0, padx=standard_padx_left,
                pady=standard_pady, sticky="w")
CTkToolTip(font_label, "Select or enter the path to a font file (TTF or OTF)")
font_path_entry = customtkinter.CTkEntry(
    app, width=300, textvariable=filename_font, placeholder_text="Select or enter a font file path", font=normal_font)
font_path_entry.grid(row=8, column=1, padx=10, pady=standard_pady, sticky="ew")
customtkinter.CTkButton(app, text="Choose file", command=selectfile_font, font=normal_font).grid(
    row=8, column=2, padx=standard_padx_right, pady=standard_pady, sticky="ew")

# Exclude Words
exclude_words_label = customtkinter.CTkLabel(
    app, text="Exclude Words:", font=normal_font)
exclude_words_label.grid(row=9, column=0, padx=standard_padx_left,
                         pady=standard_pady, sticky="w")
CTkToolTip(exclude_words_label,
           "Enter words to exclude from the word cloud, separated by commas")
exclude_words_textbox = customtkinter.CTkTextbox(
    app, width=300, height=75, font=normal_font, border_color=("dark gray", "dark gray"), wrap="word")
exclude_words_textbox.grid(row=9, column=1, padx=standard_padx_right,
                           pady=standard_pady, columnspan=2, sticky="ew")

# Color Selection
color_label = customtkinter.CTkLabel(app, text="Colors:", font=normal_font)
color_label.grid(row=10, column=0, padx=standard_padx_left,
                 pady=0, sticky="w")
CTkToolTip(color_label, "Select colors for the word cloud")


color_list_box = CTkListbox(
    app, font=normal_font)
color_list_box.grid(row=10, column=1, padx=10,
                    pady=0, sticky="ew")

# Create a frame to contain the color buttons
color_buttons_frame = customtkinter.CTkFrame(app, fg_color='transparent')
color_buttons_frame.grid(
    row=10, column=2, padx=standard_padx_right, pady=(0, 5), sticky="ew")

add_color_button = customtkinter.CTkButton(
    color_buttons_frame, text="Add", command=add_color, font=normal_font)
add_color_button.pack(fill="x", pady=(0, 5))

remove_color_button = customtkinter.CTkButton(
    color_buttons_frame, text="Remove", command=remove_selected_color, font=normal_font)
remove_color_button.pack(fill="x", pady=(0, 5))

# Define a variable to hold the colors file path
colors_file_path = None
load_color_button = customtkinter.CTkButton(
    color_buttons_frame, text="Load from File", command=load_colors_from_file, font=normal_font)
load_color_button.pack(fill="x", pady=(15, 0))


# Output Folder Path
output_folder_var = customtkinter.StringVar(value="")
output_folder_label = customtkinter.CTkLabel(
    app, text="Output Folder:", font=normal_font)
output_folder_label.grid(row=11, column=0, padx=standard_padx_left,
                         pady=standard_pady, sticky="w")
CTkToolTip(output_folder_label,
           "Enter or select the output folder path")
output_folder_entry = customtkinter.CTkEntry(
    app, width=300, textvariable=output_folder_var, placeholder_text="Enter or select the output folder path", font=normal_font)
output_folder_entry.grid(row=11, column=1, padx=10,
                         pady=standard_pady, sticky="ew")
customtkinter.CTkButton(app, text="Choose folder", command=select_output_folder,
                        font=normal_font).grid(row=11, column=2, padx=standard_padx_right, pady=standard_pady, sticky="ew")


# Generate Button
generate_button = customtkinter.CTkButton(app, text="Generate Word Cloud", font=customtkinter.CTkFont(
    size=18), border_spacing=10, command=on_generate_button_click)
generate_button.grid(row=12, column=0, columnspan=3,
                     padx=(30, 30), pady=(15, 15), sticky="ew")

app.mainloop()
