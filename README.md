# Wordcloud Generation (WordcloudGen)

#### by biagio11

This is a simple Python project to generate word clouds from a PDF or text file using Python. The project leverages various libraries such as `pymupdf` for PDF processing, `nltk` for text preprocessing, and `wordcloud` for generating the word cloud image. The GUI version uses `customtkinter` and other related packages.

## Project Overview

The project script performs the following tasks:

1. Extracts text from a PDF or a text file.
2. Preprocesses the text by tokenizing, lemmatizing, and removing stopwords.
3. Generates a word cloud image using the processed text.
4. Saves the word cloud image with a timestamp.
5. Provides a GUI for easy interaction and word cloud generation.

The project is structured into 4 main folders i.e. `input`, `output`, `fonts`, `colors`. Don't delete this folders if you are using the command line.

## Installation

### Step 1: Install Miniconda

Miniconda is a minimal installer for conda, a package manager, and an environment management system. To install Miniconda, follow these steps:

1. Download the Miniconda installer for your operating system from the [official Miniconda page](https://docs.conda.io/en/latest/miniconda.html).
2. Run the installer and follow the instructions to complete the installation.

### Step 2: Set Up the Conda Environment

1. Open the Miniconda command line.

2. Navigate to the project folder using:
   
   ```bash
   cd C:/your/project/path
   ```

3. Create the conda environment using the `environment.yml` file:
   
   ```bash
   conda env create -f environment.yml
   ```

4. Activate the conda environment:
   
   ```bash
   conda activate wordcloud-env
   ```

***NOTE***: after the first installation you can skip the **3rd** point.

### Step 3: Download NLTK Data

The script requires certain NLTK data to function correctly.
Run the script `setup-nltk.py` to download the necessary NLTK data:

```bash
python setup_nltk.py
```

## Usage

1. Open the Miniconda command line.

2. Navigate to the project folder using:
   
   ```bash
   cd C:/your/project/path
   ```

3. Activate the conda environment:
   
   ```bash
   conda activate wordcloud-env
   ```
   
   ### Option 1: Run the Wordcloud Generation Script
   
   Run the script with the desired arguments. For example:
   
   ```bash
   python wordcloud_gen.py --pdf path/to/document.pdf --lang english --exclude word1 word2 word3 --color_file path/to/colors.json --width 1920 --height 1080 --background white --font path/to/font.ttf
   ```
   
   Alternatively, starting from a text file:
   
   ```bash
   python wordcloud_gen.py --txt path/to/document.txt --lang english --exclude word1 word2 word3 --color_file path/to/colors.json --width 1920 --height 1080 --background white --font path/to/font.ttf
   ```
   
   ### Option 2: Alternative approach: GUI
   
   Simply use the GUI via the command line.
   Run the Wordcloud Generation Script
   
   ```bash
   python wordcloud_gen_GUI.py
   ```

If already built use the `wordcloud_gen.exe` executable.

**Note**:

A known error when running `wordcloud_gen_GUI.py` is related to `pymupdf` library. To fix the issue try run the following command:

```bash
pip install --upgrade --force-reinstall pymupdf
```

## Build Settings

If you would like to build the project into a standalone usable `.exe` file do the following:

1. Show the paths for each required package with other dependencies using:
   
   ```bash
   pip show packagename
   ```
   
   You should check the paths for `customtkinter`, `CTkColorPicker`, `CTkMessagebox`, `CTkToolTip`, `CTkListbox`, `wordcloud`. Keep these paths as they will be used later.

2. Install `pyinstaller`:
   
   ```bash
   pip install pyinstaller
   ```

3. Build the application (if you used Miniconda):
   
   ```bash
   pyinstaller --noconfirm --onedir --windowed --add-data "C:/Users/user/miniconda3/envs/wordcloud-env/Lib/site-packages/customtkinter;customtkinter/" --add-data ... wordcloud_gen_GUI.py
   ```

4. Add the `--add-data` flag for each package (`customtkinter`, `CTkColorPicker`, `CTkMessagebox`, `CTkToolTip`,`CTkListbox`, `wordcloud`) using:
   
   ```bash
   --add-data "C:/package/path/packagename;packagename/"
   ```

5. Run the command and wait for the build. After the building process, navigate to the `dist` folder. Inside the folder named `wordcloud_gen_GUI`, you will find the executable named `wordcloud_gen_GUI.exe`.

6. For easy access, drag and drop the input, output, and font folders outside the main folder (the one where the `.exe` file is placed).

## Conclusion

By following these steps, you should be able to generate a word cloud from a PDF or text file with your preferred settings.

This project demonstrates basic text processing and visualization techniques using Python.

## Contribution

Your contributions are appreciated! :smile:
If you find this project helpful or like it, don't forget to star it :star:

Feel free to contribute to this project by providing feedback, suggesting improvements, opening [issues](https://github.com/biagio11/WordcloudGen/issues) or [pull requests](https://github.com/biagio11/WordcloudGen/pulls).
For major changes, please open an issue first to discuss what you would like to change.

Check out the **Contributors** section to see who has contributed to this project!

## License

![CC BY-NC-SA 4.0](https://mirrors.creativecommons.org/presskit/icons/cc.svg?ref=chooser-v1) ![CC BY-NC-SA 4.0](https://mirrors.creativecommons.org/presskit/icons/by.svg?ref=chooser-v1) ![CC BY-NC-SA 4.0](https://mirrors.creativecommons.org/presskit/icons/nc.svg?ref=chooser-v1) ![CC BY-NC-SA 4.0](https://mirrors.creativecommons.org/presskit/icons/sa.svg?ref=chooser-v1)

WordcloudGen by **biagio11** is licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/?ref=chooser-v1)

## Contributors

- [biagio11](https://github.com/biagio11)
