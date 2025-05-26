import sys
import os
import fitz  # PyMuPDF
import tkinter as tk
from tkinter import ttk
from PIL import Image, ImageTk
import threading
import time
import pyttsx3  # For text-to-speech (TTS)

# Command-line argument parsing
import argparse
parser = argparse.ArgumentParser(description="Chanting PDF Viewer: Match chanting audio to a PDF document.")
parser.add_argument('document', nargs='?', help='Path to the PDF file')
args = parser.parse_args()

if not args.document:
    parser.print_help()
    sys.exit(1)

PDF_PATH = args.document

if not os.path.isfile(PDF_PATH):
    print(f"Error: File '{PDF_PATH}' not found.")
    sys.exit(1)

# Open PDF
try:
    doc = fitz.open(PDF_PATH)
except Exception as e:
    print(f"Error opening PDF: {e}")
    sys.exit(1)

# Initialize TTS engine
engine = pyttsx3.init()
voices = engine.getProperty('voices')

# Function to set speech rate (speed) dynamically
def set_speed(speed):
    engine.setProperty('rate', speed)

# Function to set the voice
def set_voice(voice_id):
    engine.setProperty('voice', voice_id)

# Function to check for Vietnamese voice
def get_default_voice():
    for voice in voices:
        if 'vi_VN' in voice.languages:
            return voice.id
    return voices[0].id  # Default to the first available voice if Vietnamese is not found

# Get the default Vietnamese voice (if available)
default_voice_id = get_default_voice()

# Create the GUI window
root = tk.Tk()
root.title("Chanting PDF Viewer")

# Create the canvas to show the PDF pages
canvas = tk.Canvas(root)
canvas.pack()

# Create a horizontal frame for the volume bar and indicator dot
status_frame = tk.Frame(root)
status_frame.pack(pady=10, fill='x')

# Volume bar and indicator dot
volume_bar = ttk.Progressbar(status_frame, orient="horizontal", length=350, mode="determinate", maximum=100)
volume_bar.pack(side="left", padx=(0, 10))

indicator_canvas = tk.Canvas(status_frame, width=40, height=40, highlightthickness=0, bg='white')
indicator_canvas.pack(side="left")
indicator_dot = indicator_canvas.create_oval(10, 10, 30, 30, fill='gold', outline='black', width=2)

# Frame for Start Reading button and speed slider
control_frame = tk.Frame(root)
control_frame.pack(pady=10, fill='x')

# Start Reading button
toggle_button = tk.Button(control_frame, text="Start Reading", command=lambda: toggle_reading())
toggle_button.pack(side="left", padx=(10, 0))

# Speed Slider (200ms per word default corresponds to ~300wpm)
def update_speed(value):
    # Ensure the speed is updated properly as an integer
    set_speed(round(float(value)))

speed_slider = ttk.Scale(control_frame, from_=50, to=500, orient="horizontal", command=lambda v: update_speed(v))
speed_slider.set(300)  # Default speed 300 words per minute (200ms per word)
speed_slider.pack(side="left", padx=(10, 0))

# Speed Label
speed_label = tk.Label(control_frame, text="Adjust Speed (50-500 words per minute)")
speed_label.pack(side="left", padx=(10, 0))

img_tk = None  # Keep a reference to avoid garbage collection

current_page = 0
reading_active = False  # Track whether reading is active
current_word_idx = 0  # Track the index of the word currently being read aloud

HEADER_RATIO = 0.10  # top 10%
FOOTER_RATIO = 0.02  # bottom 10%

# Render and show the current PDF page as an image
def show_page(page_num, highlight_word=None):
    global current_page, img_tk
    total_pages = len(doc)
    current_page = max(0, min(page_num, total_pages - 1))  # Ensure current_page is within bounds
    page = doc.load_page(current_page)
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2))  # 2x zoom for better quality
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    img_tk = ImageTk.PhotoImage(img)
    canvas.config(width=img.width, height=img.height)
    canvas.create_image(0, 0, anchor="nw", image=img_tk)
    root.title(f"Chanting PDF Viewer - Page {current_page + 1} of {total_pages}")
    canvas.delete("highlight")
    if highlight_word is not None:
        highlight_word_on_canvas(current_page, highlight_word)

# Highlight a word on the canvas by drawing a yellow rectangle over it
def highlight_word_on_canvas(page_num, word_index):
    canvas.delete("highlight")
    page = doc.load_page(page_num)
    words = page.get_text("words")
    if 0 <= word_index < len(words):
        x0, y0, x1, y1 = words[word_index][:4]
        x0, y0, x1, y1 = [v * 2 for v in (x0, y0, x1, y1)]
        MARGIN = 6  # pixels
        x0 -= MARGIN
        y0 -= MARGIN + 4
        x1 += MARGIN
        y1 += MARGIN - 4
        canvas.create_rectangle(x0, y0, x1, y1, fill='', outline='red', width=3, tags="highlight")  # Red highlight

# Create a combobox for selecting TTS voice
def create_voice_selector():
    voice_names = [voice.name for voice in voices]
    voice_combobox = ttk.Combobox(root, values=voice_names, state="readonly", width=20)
    
    # Find the voice name corresponding to the default voice ID
    default_voice_name = next(voice.name for voice in voices if voice.id == default_voice_id)
    voice_combobox.set(default_voice_name)  # Set default voice to Vietnamese or the first available
    voice_combobox.bind("<<ComboboxSelected>>", on_voice_select)
    voice_combobox.pack(pady=10)
    voice_label = tk.Label(root, text="Select Speech Voice")
    voice_label.pack()

# Function to handle voice selection change
def on_voice_select(event):
    selected_voice_name = event.widget.get()
    for voice in voices:
        if voice.name == selected_voice_name:
            set_voice(voice.id)
            break

# Function to read aloud the words from the PDF
def read_aloud(word):
    if word:
        engine.say(word)
        engine.runAndWait()

# Function to read the words aloud and highlight the word
def highlight_and_read():
    global current_word_idx  # Access the global variable to track the word index
    page = doc.load_page(current_page)
    words_info = page.get_text("words")
    page_height = page.rect.height
    body_words, body_indices = filter_body_words(words_info, page_height)

    # Ensure we are properly reading the last word
    if body_words and current_word_idx < len(body_words):
        # Highlight the next word before reading the current one
        if current_word_idx + 1 < len(body_words):
            highlight_word_on_canvas(current_page, body_indices[current_word_idx + 1])

        # Check if we are at the last word of the page
        if current_word_idx == len(body_words) - 1:
            # Read the current (last) word before moving to the next page
            word = body_words[current_word_idx]
            read_aloud(word)  # Read the word aloud
            current_word_idx += 1  # Move to the next word

            # Move to the next page after the last word is read
            next_page_num = current_page + 1
            if next_page_num < len(doc):
                show_page(next_page_num)  # Move to the next page
                current_word_idx = 0  # Reset word index for the new page
            return

        # Read the current word aloud
        word = body_words[current_word_idx]  # Get the current word from body_words
        read_aloud(word)  # Read the word aloud
        current_word_idx += 1  # Move to the next word

# Filter body words to exclude header and footer
def filter_body_words(words, page_height):
    body_words = []
    body_indices = []
    for idx, w in enumerate(words):
        x0, y0, x1, y1 = w[:4]
        if y1 < HEADER_RATIO * page_height:
            continue  # Skip header
        if y0 > (1 - FOOTER_RATIO) * page_height:
            continue  # Skip footer
        body_words.append(w[4])  # The word string
        body_indices.append(idx)  # Original index in words
    return body_words, body_indices

# Call the function with dynamic delay between each word
def update_reading():
    if reading_active:
        highlight_and_read()

    # Get the current speed (wpm) from the slider and calculate the delay
    wpm = speed_slider.get()  # Get words per minute from slider
    delay_ms = 60 * 1000 / wpm  # Convert wpm to milliseconds delay
    root.after(int(delay_ms), update_reading)  # Call after dynamic delay

# Start/Stop Reading
def toggle_reading():
    global reading_active, current_word_idx
    reading_active = not reading_active
    if reading_active:
        toggle_button.config(text="Stop Reading")
        current_word_idx = 0  # Reset to the first word on the page
        update_reading()  # Start reading when toggled to "Start Reading"
    else:
        toggle_button.config(text="Start Reading")
        engine.stop()  # Stop the TTS engine when toggled to "Stop Reading"

# Go to the specified page
def go_to_page():
    try:
        page_num = int(page_entry.get()) - 1  # Convert to 0-indexed
        if 0 <= page_num < len(doc):
            show_page(page_num)
        else:
            print("Invalid page number.")
    except ValueError:
        print("Please enter a valid page number.")

# Go to Page Entry and Button in one row below the volume bar
page_row = tk.Frame(root)
page_row.pack(pady=10)

page_label = tk.Label(page_row, text="Go to Page:")
page_label.pack(side="left", padx=5)

page_entry = tk.Entry(page_row, width=5)
page_entry.pack(side="left", padx=5)

go_button = tk.Button(page_row, text="Go", command=go_to_page)
go_button.pack(side="left", padx=5)

# Function to handle click on word to jump to that word and resume reading
def on_canvas_click(event):
    global current_word_idx
    page = doc.load_page(current_page)
    words_info = page.get_text("words")
    page_height = page.rect.height
    body_words, body_indices = filter_body_words(words_info, page_height)

    # Adjust canvas-to-PDF coordinate mapping with better click detection logic
    for i, word in enumerate(body_words):
        # Get the word's bounding box (x0, y0, x1, y1)
        x0, y0, x1, y1 = words_info[body_indices[i]][:4]
        
        # Scale word coordinates to match canvas scale (2x zoom in our case)
        x0, y0, x1, y1 = [v * 2 for v in (x0, y0, x1, y1)]

        # Check if the mouse click is within the bounds of the word
        # If the mouse click is inside the word's bounding box, register it
        if x0 <= event.x <= x1 and y0 <= event.y <= y1:
            current_word_idx = i
            highlight_word_on_canvas(current_page, body_indices[current_word_idx])  # Highlight the selected word
            read_aloud(word)  # Read the word aloud
            break


# Bind mouse click event to jump to clicked word
canvas.bind('<Button-1>', on_canvas_click)

# Bind keys for page navigation
def next_page(event=None):
    global current_page
    next_page_num = current_page + 1
    if next_page_num < len(doc):
        show_page(next_page_num)

def prev_page(event=None):
    global current_page
    prev_page_num = current_page - 1
    if prev_page_num >= 0:
        show_page(prev_page_num)

root.bind("<Next>", next_page)      # Page Down
root.bind("<Prior>", prev_page)     # Page Up
root.bind("<Right>", next_page)     # Right Arrow
root.bind("<Down>", next_page)      # Down Arrow
root.bind("<Left>", prev_page)      # Left Arrow
root.bind("<Up>", prev_page)        # Up Arrow

# Create the GUI components
create_voice_selector()

# Show the first page
show_page(0)

# Start the Tkinter event loop
root.mainloop()
