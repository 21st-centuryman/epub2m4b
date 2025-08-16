from flask import Flask, render_template, request, send_from_directory
import os
import re
from ebooklib import epub, ITEM_DOCUMENT  # Explicit import to satisfy type checkers
import glob
import subprocess
from typing import List, Optional
import torchaudio as ta
import torch
from chatterbox.tts import ChatterboxTTS
import threading
import uuid

app = Flask(__name__)
# Configuration for upload folder (create an 'uploads' directory in your project root)
UPLOAD_FOLDER = "uploads"
CHAPTERS_FOLDER = "chapters"
AUDIO_FOLDER = "audio"
AUDIOBOOKS_FOLDER = "audiobooks"
WAV_FOLDER = "temp"
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
if not os.path.exists(CHAPTERS_FOLDER):
    os.makedirs(CHAPTERS_FOLDER)
if not os.path.exists(AUDIOBOOKS_FOLDER):
    os.makedirs(AUDIOBOOKS_FOLDER)
if not os.path.exists(AUDIO_FOLDER):
    os.makedirs(AUDIO_FOLDER)
if not os.path.exists(WAV_FOLDER):
    os.makedirs(WAV_FOLDER)

# Global progress tracking
progress = {}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload", methods=["POST"])
def upload_file():
    if "file" not in request.files:
        return "<p>No file uploaded.</p>", 400
    file = request.files["file"]
    if not file.filename:
        return "<p>No selected file.</p>", 400
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
    file.save(file_path)
    try:
        book = epub.read_epub(file_path)
        chapter_data = []
        for item in book.toc:
            if isinstance(item, epub.Link):
                chapter_data.append({"title": item.title, "href": item.href})
            elif isinstance(item, tuple):
                section, links = item
                for link in links:
                    chapter_data.append({"title": link.title, "href": link.href})
        if not chapter_data:
            for item in book.get_items_of_type(ITEM_DOCUMENT):
                href = item.file_name
                content = item.get_content().decode("utf-8")
                title_start = content.find("<title>") + 7
                title_end = content.find("</title>")
                title = (
                    content[title_start:title_end]
                    if title_start > 6 and title_end > title_start
                    else os.path.basename(href)
                )
                chapter_data.append({"title": title, "href": href})
        html = """
        <form id="select-form" hx-post="/generate_audiobook" hx-target="#result" hx-swap="beforeend" hx-indicator="#loading">
          <input type="hidden" name="filename" value="{filename}">
          <div>
            <p class="subtitle"> You have the option to rename the chapters below</p> 
            <p class="subtitle"> Otherwise the metadata (as seen next to the checkboxes) will be the chapter names of your audiobook. </p>
            <label>
              <input type="checkbox" id="toggle-rename" onchange="toggleRenameFields()"> Rename chapters
            </label>
          </div>
          </br>
          <div><strong>Select chapters to include in your audiobook:</strong></div></br>
          <div class="rename_chapters" >
          <ul class="chapters">
        """.format(filename=file.filename)
        for i, data in enumerate(chapter_data):
            html += (
                f"<div class='chapter-item'>"
                f'<div class="input-chapter" style="visibility: hidden;"><input type="text" name="rename_{i}" placeholder="{data["title"]}"></div>'
                f"<li class='chapter-title'>"
                f'<input type="checkbox" name="chapter" value="{data["href"]}">'
                f"<span> {data['title']}</span>"
                f"</li>"
                f"</div>"
            )
        html += "</ul></div>"
        html += """<br/>
        <p>Please enter a name for your m4b audiobook:</p><br/>
            <input type="text" name="output_name" style="text-align: center;" placeholder="MyAudioBook" required> <br/>
            <button type="submit" class="btn">Generate Audiobook</button>
        </form>
        """
        return html
    except Exception as e:
        os.remove(file_path)
        return f"<p>Error parsing EPUB: {str(e)}</p>", 500


@app.route("/create", methods=["POST"])
def create_chapters():
    filename = request.form.get("filename")
    if not filename:
        return "<p>No filename provided.</p>", 400
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(file_path):
        return "<p>File not found.</p>", 404
    selected_hrefs = request.form.getlist("chapter")
    if not selected_hrefs:
        os.remove(file_path)
        return "<p>No chapters selected.</p>", 400
    try:
        book = epub.read_epub(file_path)
        for href in selected_hrefs:
            item = book.get_item_with_href(href)
            if item:
                content = item.get_content().decode("utf-8")
                output_filename = os.path.basename(href)
                output_path = os.path.join(CHAPTERS_FOLDER, output_filename)
                with open(output_path, "w", encoding="utf-8") as f:
                    f.write(content)
        os.remove(file_path)
        return """
        <p>please enter a name for your m4b audiobook:</p>
        <form id="generate-form" hx-post="/mp32m4b" hx-target="#result" hx-swap="beforeend" hx-indicator="#loading">
            <input type="text" name="output_name" placeholder="e.g., myaudiobook" required>
            <button type="submit">generate m4b</button>
        </form>
        """
    except Exception as e:
        os.remove(file_path)
        return f"<p>Error extracting chapters: {str(e)}</p>", 500


@app.route("/generate_audiobook", methods=["POST"])
def generate_audiobook():
    # Step 1: Extract form data
    filename = request.form.get("filename")
    output_name = request.form.get("output_name")
    if not filename:
        return "<p>No filename provided.</p>", 400
    if not output_name:
        return "<p>Please provide a name for the audiobook.</p>", 400
    file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    if not os.path.exists(file_path):
        return "<p>File not found.</p>", 404
    selected_hrefs = request.form.getlist("chapter")
    if not selected_hrefs:
        if os.path.exists(file_path):
            os.remove(file_path)
        return "<p>No chapters selected.</p>", 400
    try:
        # Step 2: Rebuild TOC items (must match order in /upload and epub2html)
        book = epub.read_epub(file_path)
        toc_items = []
        for item in book.toc:
            if isinstance(item, epub.Link):
                toc_items.append((item.title, item.href))
            elif isinstance(item, tuple):
                section, links = item
                for link in links:
                    toc_items.append((link.title, link.href))
        if not toc_items:
            for item in book.get_items_of_type(ITEM_DOCUMENT):
                href = item.file_name
                content = item.get_content().decode("utf-8")
                title_start = content.find("<title>") + 7
                title_end = content.find("</title>")
                title = (
                    content[title_start:title_end]
                    if title_start > 6 and title_end > title_start
                    else os.path.basename(href)
                )
                toc_items.append((title, href))
        selected_indexes = [
            idx for idx, (title, href) in enumerate(toc_items) if href in selected_hrefs
        ]
        if not selected_indexes:
            raise ValueError("No valid chapters selected.")
        all_replacement_names = [
            request.form.get(f"rename_{i}", "").strip() for i in range(len(toc_items))
        ]
        replacement_names = [all_replacement_names[i] for i in selected_indexes]

        # Set up progress tracking
        task_id = str(uuid.uuid4())
        progress[task_id] = {"messages": [], "output_name": output_name}

        # Start background thread
        thread = threading.Thread(
            target=generation_task,
            args=(file_path, selected_indexes, replacement_names, output_name, task_id),
        )
        thread.start()

        # Return polling div
        return f"""
        <div id="progress" hx-get="/progress/{task_id}" hx-trigger="every 2s" hx-swap="innerHTML">
            Starting generation...
        </div>
        """

    except ValueError as ve:
        if os.path.exists(file_path):
            os.remove(file_path)
        return f"<p>Error: {str(ve)}</p>", 400


@app.route("/progress/<task_id>")
def get_progress(task_id):
    if task_id not in progress:
        return "<p>Invalid task ID.</p>"
    data = progress[task_id]
    messages = data["messages"]
    if not messages:
        return "<p>Initializing...</p>"
    last_msg = messages[-1]
    if last_msg == "DONE":
        output_name = data["output_name"]
        # Clean up progress after completion
        del progress[task_id]
        return f"""
        <p>Successfully generated '{output_name}.m4b'.</p>
        <a href="/download/{output_name}.m4b" class="down-btn" download>Download Audiobook</a>
        """
    elif last_msg.startswith("Error:"):
        # Clean up on error
        del progress[task_id]
        return f"<p>{last_msg}</p>"
    else:
        return f"<p>{last_msg}</p>"


def generation_task(
    file_path, selected_indexes, replacement_names, output_name, task_id
):
    messages = progress[task_id]["messages"]
    try:
        messages.append("Extracting chapters...")
        epub2html(file_path, selected_indexes, replacement_names)
        messages.append("Chapters extracted. Starting audio generation...")
        html2mp3(messages)
        messages.append("Generating audiobook...")
        mp32m4b(output_name, messages)
        messages.append("DONE")
    except Exception as e:
        messages.append(f"Error: {str(e)}")
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.route("/download/<filename>")
def download_file(filename):
    return send_from_directory(AUDIOBOOKS_FOLDER, filename)


@app.route("/assets/<path:filename>")
def serve_assets(filename):
    return send_from_directory("assets", filename)


# -------------------------------
# Functions
# -------------------------------

regex_replacements = [
    (re.compile(r"<html\b[^>]*>|</html>"), ""),
    (re.compile(r"<body\b[^>]*>|</body>"), ""),
    (re.compile(r"<p\b[^>]*>", re.IGNORECASE), "<p>"),
    (re.compile(r"<h([1-6])\b[^>]*>", re.IGNORECASE), r"<h\1>"),
    (re.compile(r"<img\b[^>]*>|</img>"), ""),
    (re.compile(r"<span\b[^>]*>|</span>"), ""),
    (re.compile(r"<a\b[^>]*>|</a>"), ""),
    (re.compile(r"<div\b[^>]*>|</div>"), ""),
    (re.compile(r"<head\b[^>]>.?</head>", re.IGNORECASE | re.DOTALL), ""),
    (re.compile(r"<\?xml\b[^>]*>", re.IGNORECASE), ""),
    (re.compile(r"<!DOCTYPE\b[^>]*>", re.IGNORECASE), ""),
    (re.compile(r"<i\b[^>]*>|</i>", re.IGNORECASE), ""),
    (re.compile(r"<sup\b[^>]*>|</sup>", re.IGNORECASE), ""),
    (re.compile(r"<small\b[^>]*>|</small>", re.IGNORECASE), ""),
]


def apply_regex_replacements(html: str) -> str:
    """Apply all regex replacements to the HTML content."""
    for pattern, replacement in regex_replacements:
        html = pattern.sub(replacement, html)
    return html


def epub2html(
    epub_file_path: str,
    selected_indexes: List[int],
    replacement_names: Optional[List[str]] = None,
) -> List[str]:
    # Read the EPUB
    try:
        book = epub.read_epub(epub_file_path)
    except Exception as e:
        raise ValueError(f"Error reading EPUB: {str(e)}")
    # Flatten the TOC to a list of (title, href) tuples with implicit indexing
    toc_items: List[tuple[str, str]] = []
    for item in book.toc:
        if isinstance(item, epub.Link):
            toc_items.append((item.title, item.href))
        elif isinstance(item, tuple):  # Handle nested TOC
            section, links = item
            for link in links:
                toc_items.append((link.title, link.href))
    # Fallback to document items if no TOC
    if not toc_items:
        for item in book.get_items_of_type(ITEM_DOCUMENT):
            href = item.file_name
            content = item.get_content().decode("utf-8")
            title_start = content.find("<title>") + 7
            title_end = content.find("</title>")
            title = (
                content[title_start:title_end]
                if title_start > 6 and title_end > title_start
                else os.path.basename(href)
            )
            toc_items.append((title, href))
    # Handle replacement_names: default to empty list if None
    if replacement_names is None:
        replacement_names = []
    # Pad replacement_names with empty strings if shorter than selected_indexes
    replacement_names += [""] * (len(selected_indexes) - len(replacement_names))
    # Extract and write selected chapters (with regex replacements applied)
    created_files: List[str] = []
    for idx, chapter_index in enumerate(selected_indexes):
        if chapter_index < 0 or chapter_index >= len(toc_items):
            continue  # Skip invalid indexes
        original_title, href = toc_items[chapter_index]
        item = book.get_item_with_href(href)
        if not item:
            continue
        content = item.get_content().decode("utf-8")  # Plain HTML extraction
        # Apply regex replacements to the content for this chapter
        content = apply_regex_replacements(content)
        # Use replacement name for filename only (if provided and not empty)
        new_title = original_title
        if idx < len(replacement_names) and replacement_names[idx]:
            new_title = replacement_names[idx]
        # Generate filename with zero-padded prefix (e.g., 000_Title.html)
        prefix = f"{idx:03d}"
        safe_title = (
            new_title.replace(" ", "_").replace("/", "_").replace("\\", "_")
        )  # Sanitize for filesystem
        out_filename = f"{prefix}{safe_title}.html"
        out_path = os.path.join(CHAPTERS_FOLDER, out_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(content)
        created_files.append(out_filename)
    if not created_files:
        raise ValueError("No valid chapters extracted.")
    return created_files


def html2mp3(progress_messages):
    device = (
        "cuda"
        if torch.cuda.is_available()
        else "mps"
        if torch.backends.mps.is_available()
        else next(_ for _ in ()).throw(
            RuntimeError("No supported device found (CUDA or MPS unavailable)")
        )
    )
    print(f"Using device: {device}")
    map_location = torch.device(device)
    torch_load_original = torch.load

    def patched_torch_load(*args, **kwargs):
        if "map_location" not in kwargs:
            kwargs["map_location"] = map_location
        return torch_load_original(*args, **kwargs)

    torch.load = patched_torch_load
    model = ChatterboxTTS.from_pretrained(device=device)
    AUDIO_PROMPT_PATH = "pope.wav"
    html_files = sorted(glob.glob("./chapters/*.html"))
    for html_path in html_files:
        name = os.path.splitext(os.path.basename(html_path))[0]
        progress_messages.append(f"Generating audio for chapter: {name}")
        os.makedirs(WAV_FOLDER, exist_ok=True)
        wav_files = []
        with open(html_path, "r", encoding="utf-8") as f:
            for idx, line in enumerate(f):
                stripped = line.lstrip()
                text = ""
                if stripped.startswith("<h1>"):
                    text = stripped[len("<h1>") :].split("</h1>")[0].strip() + "..."
                    exag = 0.7
                    cfg = 0.3
                elif stripped.startswith("<p>"):
                    text = stripped[len("<p>") :].split("</p>")[0].strip()
                    exag = 0.5
                    cfg = 0.5
                else:
                    # TODO add case for h2, h3, h4, h5, h6
                    continue  # skip lines that are not <h1> or <p>
                if text:
                    wav = model.generate(
                        text,
                        audio_prompt_path=AUDIO_PROMPT_PATH,
                        exaggeration=exag,
                        cfg_weight=cfg,
                    )
                    wav_path = f"{WAV_FOLDER}/{idx}.wav"
                    ta.save(wav_path, wav, model.sr)
                    wav_files.append(wav_path)
        wav_files = sorted(
            wav_files, key=lambda x: int(os.path.splitext(os.path.basename(x))[0])
        )
        with open("wav_list.txt", "w") as f_list:
            for wav in wav_files:
                f_list.write(f"file '{wav}'\n")
        # Delete the html file after processing
        try:
            os.remove(html_path)
        except Exception as e:
            print(f"Warning: could not delete {html_path}: {e}")
        subprocess.run(
            [
                "ffmpeg",
                "-f",
                "concat",
                "-safe",
                "0",
                "-i",
                "wav_list.txt",
                "-acodec",
                "libmp3lame",
                "-b:a",
                "192k",
                f"audio/{name}.mp3",
            ],
            check=True,  # Add to catch failures
        )
        for wav in wav_files:
            try:
                os.remove(wav)
            except Exception as e:
                print(f"Warning: could not delete {wav}: {e}")
    if os.path.exists(WAV_FOLDER):
        os.rmdir(WAV_FOLDER)


def mp32m4b(output_name, progress_messages):
    audio_folder = "audio"
    mp3_files = glob.glob(os.path.join(audio_folder, "*.mp3"))
    if not mp3_files:
        raise ValueError("No MP3 files found in 'audio' folder.")
    prefixes = set()
    for file_path in mp3_files:
        filename = os.path.basename(file_path)
        prefixes.add(filename[:3])  # Assuming 3-character prefix like '001'
    sorted_prefixes = sorted(prefixes, key=lambda x: int(x))
    list_path = "list.txt"
    with open(list_path, "w") as list_file:
        for prefix in sorted_prefixes:
            pattern = os.path.join(audio_folder, f"{prefix}*.mp3")
            matching_files = glob.glob(pattern)
            if matching_files:
                first_match = matching_files[0]
                rel_path = os.path.relpath(first_match, start=os.curdir)
                list_file.write(f"file '{rel_path}'\n")
    metadata_path = "metadata.txt"
    start_ms = 0
    with open(metadata_path, "w") as metadata_file:
        metadata_file.write(";FFMETADATA1\n")
        with open(list_path, "r") as file_list:
            for line in file_list:
                file_path = line.strip().split("'")[1]
                result = subprocess.run(
                    [
                        "ffprobe",
                        "-v",
                        "error",
                        "-show_entries",
                        "format=duration",
                        "-of",
                        "default=noprint_wrappers=1:nokey=1",
                        file_path,
                    ],
                    stdout=subprocess.PIPE,
                    text=True,
                )
                duration_ms = int(float(result.stdout.strip()) * 1000)
                end_ms = start_ms + duration_ms
                metadata_file.write("[CHAPTER]\n")
                metadata_file.write("TIMEBASE=1/1000\n")
                metadata_file.write(f"START={start_ms}\n")
                metadata_file.write(f"END={end_ms}\n")
                title = os.path.basename(file_path).replace(".mp3", "")[3:]
                metadata_file.write(f"title={title}\n\n")
                start_ms = end_ms
    output_path = os.path.join(AUDIOBOOKS_FOLDER, f"{output_name}.m4b")
    subprocess.run(
        [
            "ffmpeg",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            list_path,
            "-i",
            metadata_path,
            "-c:a",
            "aac",
            "-b:a",
            "320k",
            "-map_metadata",
            "1",
            "-map",
            "0",
            "-metadata:s:0",
            "stik=2",
            "-f",
            "mp4",
            output_path,
        ],
        check=True,
    )
    os.remove(list_path)
    os.remove(metadata_path)
    progress_messages.append("Audiobook generation complete.")


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True, port=5001)
