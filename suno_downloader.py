from playwright.sync_api import sync_playwright
import os
import re
import requests
from bs4 import BeautifulSoup
from mutagen.id3 import ID3, USLT, APIC, ID3NoHeaderError

# Ensure the Logs folder exists.
os.makedirs("Logs", exist_ok=True)

# Global variables for timeouts (in milliseconds) – will be set in main().
NAV_TIMEOUT = 60000       # default: 60 seconds (will be updated)
SELECTOR_TIMEOUT = 20000  # default: 20 seconds (will be updated)

# Global log file (inside Logs folder relative to script location) and a dictionary for failure details.
LOG_FILE = os.path.join("Logs", "suno_operation_log.txt")
failures = {}  # Stores detailed failure messages per URL.

# Ensure the 'Logs' directory exists
if not os.path.exists('Logs'):
    os.makedirs('Logs')

# Global flag for overwriting files (set by the user at the start).
OVERWRITE_FILES = False

def log_operation(message):
    """Appends a message to the operation log file and prints it."""
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(message + "\n")
    print(message)

def initialize_files(skip_file, failed_file):
    """
    Ensures that the skip and failed files exist.
    If they do not exist, they are created with an initial header.
    """
    if not os.path.exists(skip_file):
        with open(skip_file, "w", encoding="utf-8") as f:
            f.write("Suno URLs SKIPPED:\n")
        log_operation(f"Created skip file: {skip_file}")
    if not os.path.exists(failed_file):
        with open(failed_file, "w", encoding="utf-8") as f:
            f.write("Suno URLs FAILED:\n")
        log_operation(f"Created failed file: {failed_file}")

def read_urls_from_file(file_path):
    """Reads URLs from a file, ignoring empty lines."""
    if not os.path.exists(file_path):
        log_operation(f"❌ File not found: {file_path}")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def sanitize_filename(filename):
    """Replaces illegal filename characters with an underscore."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def record_failure(url, message):
    """Records a failure message for a given URL in the global dictionary and logs it."""
    if url not in failures:
        failures[url] = []
    failures[url].append(message)
    log_operation(f"[{url}] FAILURE: {message}")

def extract_gpt_prompt(html):
    """
    Attempts to extract the GPT prompt from the HTML source.
    Searches for a JSON fragment with "gpt_description_prompt" (removing the trailing phrase)
    and falls back to the 3rd <meta> tag with a content attribute.
    """
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        script_text = script.get_text()
        if "gpt_description_prompt" in script_text:
            match = re.search(r'"gpt_description_prompt"\s*:\s*\\"?([^\\"]+)\\"?', script_text)
            if match:
                prompt = match.group(1).strip()
                prompt = prompt.replace(" song. Listen and make your own with Suno.", "").strip()
                if prompt:
                    return prompt
    meta_tags = soup.find_all("meta", attrs={"content": True})
    if len(meta_tags) >= 3:
        fallback_prompt = meta_tags[2].get("content", "").strip()
        fallback_prompt = fallback_prompt.replace(" song. Listen and make your own with Suno.", "").strip()
        if fallback_prompt:
            return fallback_prompt
    return None

def extract_page_data(url):
    """
    Uses Playwright to load the page at the given URL and extract:
      - The page title (for filenames)
      - The lyrics text (using the CSS selector "section.w-full > div:nth-child(1)")
      - The full HTML content
      - The GPT prompt (via extract_gpt_prompt)
    Timeouts for navigation and selectors are set by the global variables.
    """
    global NAV_TIMEOUT, SELECTOR_TIMEOUT
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        log_operation(f"⏳ Navigating to {url}...")
        try:
            page.goto(url, timeout=NAV_TIMEOUT)
        except Exception as e:
            msg = f"Error navigating to {url}: {e}"
            log_operation(f"❌ {msg}")
            record_failure(url, msg)
            browser.close()
            return "Unknown_Song", None, None, None
        try:
            page.wait_for_selector("section.w-full > div:nth-child(1)", timeout=SELECTOR_TIMEOUT)
            lyrics = page.text_content("section.w-full > div:nth-child(1)").strip()
        except Exception as e:
            msg = f"Error extracting lyrics from {url}: {e}"
            log_operation(f"❌ {msg}")
            record_failure(url, msg)
            lyrics = None
        title = page.title() or "Unknown_Song"
        html_content = page.content()
        gpt_prompt = extract_gpt_prompt(html_content)
        if not gpt_prompt:
            record_failure(url, "GPT prompt not found")
        browser.close()
        return title, lyrics, gpt_prompt, html_content

def save_text_to_file(text, directory, filename):
    """
    Saves the given text to a file in the specified directory.
    If OVERWRITE_FILES is False and the file exists, appends a number.
    """
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, filename)
    if not OVERWRITE_FILES:
        base, ext = os.path.splitext(filename)
        counter = 1
        while os.path.exists(filepath):
            filepath = os.path.join(directory, f"{base} ({counter}){ext}")
            counter += 1
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    log_operation(f"✅ Saved to {filepath}")

def download_file(url, directory, filename, extension):
    """
    Downloads a file from the provided URL using Requests and saves it
    in the specified directory with the given filename and extension.
    If OVERWRITE_FILES is False and the file exists, appends a number.
    Returns the final file path on success, or None on failure.
    """
    if not url:
        msg = f"URL not provided for {filename}.{extension}"
        log_operation(f"⚠️ {msg}")
        return None
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, f"{filename}.{extension}")
    if not OVERWRITE_FILES:
        counter = 1
        while os.path.exists(filepath):
            filepath = os.path.join(directory, f"{filename} ({counter}).{extension}")
            counter += 1
    try:
        response = requests.get(url, stream=True, timeout=15)
        response.raise_for_status()
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        log_operation(f"✅ Downloaded file to {filepath}")
        return filepath
    except Exception as e:
        msg = f"Failed to download {url}: {e}"
        log_operation(f"❌ {msg}")
        record_failure("", msg)
        return None

def add_lyrics_to_mp3(mp3_filepath, lyrics):
    """
    Adds the provided lyrics to the MP3 file's ID3 tag (USLT frame).
    Overwrites any existing lyrics.
    """
    try:
        try:
            audio = ID3(mp3_filepath)
        except ID3NoHeaderError:
            audio = ID3()
        audio.delall("USLT")
        audio.add(USLT(encoding=3, desc=u"lyrics", text=lyrics))
        audio.save(mp3_filepath)
        log_operation(f"✅ Added lyrics to MP3 tag for {mp3_filepath}")
    except Exception as e:
        msg = f"Error adding lyrics to MP3 tag for {mp3_filepath}: {e}"
        log_operation(f"❌ {msg}")
        record_failure("", msg)

def add_image_to_mp3(mp3_filepath, image_filepath):
    """
    Embeds the image (from image_filepath) into the MP3 file's ID3 tag (APIC frame).
    Overwrites any existing album art.
    """
    try:
        try:
            audio = ID3(mp3_filepath)
        except ID3NoHeaderError:
            audio = ID3()
        with open(image_filepath, "rb") as img:
            img_data = img.read()
        audio.delall("APIC")
        audio.add(APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,
            desc="Cover",
            data=img_data
        ))
        audio.save(mp3_filepath)
        log_operation(f"✅ Embedded image into MP3 tag for {mp3_filepath}")
    except Exception as e:
        msg = f"Error embedding image into MP3 tag for {mp3_filepath}: {e}"
        log_operation(f"❌ {msg}")
        record_failure("", msg)

session = requests.Session()

def get_user_selection():
    """
    Prompts the user to select what to extract and save for each URL.
    Options:
      1. HTML
      2. MP4
      3. MP3
      4. Lyrics
      5. Prompt
      6. Image
      7. Add index (prefix filenames with a padded 5-digit number)
      8. All of 1-6 (extraction options only)
      9. All of 1-7 (extraction options plus indexing)
    """
    print("Select what to extract and save for each URL:")
    print("1. HTML")
    print("2. MP4")
    print("3. MP3")
    print("4. Lyrics")
    print("5. Prompt")
    print("6. Image")
    print("7. Add index (prefix filenames with a padded 5-digit number)")
    print("8. All of 1-6 (extraction options only)")
    print("9. All of 1-7 (extraction options plus indexing)")
    choices = input("Enter numbers separated by commas (e.g., 1,2,4,5,6): ")
    selections = [x.strip() for x in choices.split(",")]
    sel = {
        "html": False,
        "mp4": False,
        "mp3": False,
        "lyrics": False,
        "prompt": False,
        "image": False,
        "index": False
    }
    if "8" in selections:
        sel["html"] = sel["mp4"] = sel["mp3"] = sel["lyrics"] = sel["prompt"] = sel["image"] = True
    if "9" in selections:
        sel["html"] = sel["mp4"] = sel["mp3"] = sel["lyrics"] = sel["prompt"] = sel["image"] = True
        sel["index"] = True
    if "1" in selections: sel["html"] = True
    if "2" in selections: sel["mp4"] = True
    if "3" in selections: sel["mp3"] = True
    if "4" in selections: sel["lyrics"] = True
    if "5" in selections: sel["prompt"] = True
    if "6" in selections: sel["image"] = True
    if "7" in selections: sel["index"] = True
    return sel

def retry_failed_urls(failed_urls, options):
    """Retries processing for the URLs in failed_urls once."""
    if not failed_urls:
        log_operation("✅ No failed URLs to retry.")
        return
    log_operation("\n🔄 Retrying failed URLs...")
    still_failed = set()
    for url in failed_urls:
        log_operation(f"🔄 Retrying URL: {url}")
        title, lyrics, gpt_prompt, html_content = extract_page_data(url)
        sanitized_title = sanitize_filename(title)
        if options["html"]:
            if html_content:
                save_text_to_file(html_content, "HTML", f"{sanitized_title} - Parsed.html")
            else:
                msg = "HTML content not found on retry"
                log_operation(f"⚠️ {msg}")
                record_failure(url, msg)
                still_failed.add(url)
        if options["lyrics"]:
            if lyrics:
                save_text_to_file(lyrics, "Lyrics", f"{sanitized_title} - Lyrics.txt")
            else:
                msg = "Lyrics not found on retry"
                log_operation(f"⚠️ {msg}")
                record_failure(url, msg)
                still_failed.add(url)
        if options["prompt"]:
            if gpt_prompt:
                save_text_to_file(gpt_prompt, "Prompts", f"{sanitized_title} - Prompt.txt")
            else:
                msg = "GPT prompt not found on retry"
                log_operation(f"⚠️ {msg}")
                record_failure(url, msg)
                still_failed.add(url)
        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            msg = f"Error fetching full HTML for media extraction on retry: {e}"
            log_operation(f"❌ {msg}")
            record_failure(url, msg)
            still_failed.add(url)
            continue
        if options["mp4"]:
            video_meta = soup.find("meta", {"property": "og:video:url"})
            video_url = video_meta.get("content") if video_meta else None
            if video_url:
                if not download_file(video_url, "Videos", sanitized_title, "mp4"):
                    still_failed.add(url)
            else:
                msg = "Video URL not found on retry"
                log_operation(f"⚠️ {msg}")
                record_failure(url, msg)
                still_failed.add(url)
        if options["mp3"]:
            audio_meta = soup.find("meta", {"property": "og:audio"})
            audio_url = audio_meta.get("content") if audio_meta else None
            if audio_url:
                mp3_filepath = download_file(audio_url, "Audio", sanitized_title, "mp3")
                if not mp3_filepath:
                    still_failed.add(url)
                else:
                    if lyrics:
                        add_lyrics_to_mp3(mp3_filepath, lyrics)
            else:
                msg = "Audio URL not found on retry"
                log_operation(f"⚠️ {msg}")
                record_failure(url, msg)
                still_failed.add(url)
        if options["image"]:
            image_meta = soup.find("meta", {"name": "twitter:image"})
            if image_meta:
                img_url = image_meta.get("content")
                if "image_large_" not in img_url:
                    image_meta = soup.find("meta", {"property": "og:image"})
                    img_url = image_meta.get("content") if image_meta else None
            else:
                image_meta = soup.find("meta", {"property": "og:image"})
                img_url = image_meta.get("content") if image_meta else None
            if img_url:
                image_filepath = download_file(img_url, "Images", sanitized_title + " - Art", "jpeg")
                if not image_filepath:
                    still_failed.add(url)
            else:
                msg = "Image URL not found on retry"
                log_operation(f"⚠️ {msg}")
                record_failure(url, msg)
                still_failed.add(url)
    if still_failed:
        log_operation("\n❌ The following URLs still failed after retry:")
        for url in still_failed:
            log_operation(url)
        with open("suno_urls_FAILED.txt", "a", encoding="utf-8") as f:
            f.write("Final failure details for this run:\n")
            for url in still_failed:
                f.write(url + "\n")
    else:
        log_operation("\n✅ All previously failed URLs succeeded on retry.")

def main():
    # Files for URLs and tracking.
    urls_file = "suno_urls.txt"             # File with URLs (one per line)
    skip_file = "suno_urls_SKIPPED.txt"       # File to keep track of processed URLs
    failed_file = "suno_urls_FAILED.txt"      # File to store failure details
    
    # Ensure that the skip and failed files exist.
    initialize_files(skip_file, failed_file)
    
    # Prompt the user whether to overwrite files.
    overwrite_choice = input("Do you want to overwrite files if they already exist? (Y/N): ").strip().upper()
    global OVERWRITE_FILES
    if overwrite_choice == "Y":
        OVERWRITE_FILES = True
        log_operation("Files will be overwritten if they exist.")
    else:
        OVERWRITE_FILES = False
        log_operation("Files will not be overwritten; duplicates will have appended numbers.")
    
    # Read already processed URLs.
    downloaded_set = set()
    if os.path.exists(skip_file):
        with open(skip_file, "r", encoding="utf-8") as f:
            for line in f:
                downloaded_set.add(line.strip())
    
    options = get_user_selection()
    
    # Prompt for timeouts (in seconds), then convert to milliseconds.
    try:
        nav_timeout_input = input("Enter timeout1 in seconds for page navigation: (Default 60)")
        nav_timeout_seconds = float(nav_timeout_input)
    except Exception:
        nav_timeout_seconds = 60
    try:
        selector_timeout_input = input("Enter timeout2 in seconds for waiting for selectors: (Default 20)")
        selector_timeout_seconds = float(selector_timeout_input)
    except Exception:
        selector_timeout_seconds = 20
    global NAV_TIMEOUT, SELECTOR_TIMEOUT
    NAV_TIMEOUT = int(nav_timeout_seconds * 1000)
    SELECTOR_TIMEOUT = int(selector_timeout_seconds * 1000)
    log_operation(f"Timeout settings: Navigation = {NAV_TIMEOUT} ms, Selector = {SELECTOR_TIMEOUT} ms")
    
    if options["index"]:
        current_index = len(downloaded_set)
    else:
        current_index = None
    
    urls = read_urls_from_file(urls_file)
    if not urls:
        log_operation("❌ No URLs found in the file.")
        return

    failed_urls = set()
    
    for url in urls:
        if url in downloaded_set:
            log_operation(f"Skipping URL (already processed): {url}")
            continue

        log_operation(f"🔄 Processing URL: {url}")
        if options["index"]:
            current_index += 1
            index_prefix = f"{current_index:05d} - "
        else:
            index_prefix = ""
        
        title, lyrics, gpt_prompt, html_content = extract_page_data(url)
        sanitized_title = sanitize_filename(title)
        
        if options["html"]:
            if html_content:
                save_text_to_file(html_content, "HTML", f"{index_prefix}{sanitized_title} - Parsed.html")
            else:
                record_failure(url, "HTML content not found")
                failed_urls.add(url)
        
        if options["lyrics"]:
            if lyrics:
                save_text_to_file(lyrics, "Lyrics", f"{index_prefix}{sanitized_title} - Lyrics.txt")
            else:
                record_failure(url, "Lyrics not found")
                failed_urls.add(url)
        
        if options["prompt"]:
            if gpt_prompt:
                save_text_to_file(gpt_prompt, "Prompts", f"{index_prefix}{sanitized_title} - Prompt.txt")
            else:
                record_failure(url, "GPT prompt not found")
                failed_urls.add(url)
        
        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            record_failure(url, f"Error fetching full HTML for media extraction: {e}")
            failed_urls.add(url)
            continue
        
        # MP4 extraction block added here.
        if options["mp4"]:
            video_meta = soup.find("meta", {"property": "og:video:url"})
            video_url = video_meta.get("content") if video_meta else None
            if video_url:
                video_filepath = download_file(video_url, "Videos", f"{index_prefix}{sanitized_title}", "mp4")
                if not video_filepath:
                    record_failure(url, "Failed to download video")
                    failed_urls.add(url)
            else:
                record_failure(url, "Video URL not found")
                failed_urls.add(url)
        
        # MP3 extraction
        current_mp3_filepath = None
        if options["mp3"]:
            audio_meta = soup.find("meta", {"property": "og:audio"})
            audio_url = audio_meta.get("content") if audio_meta else None
            if audio_url:
                current_mp3_filepath = download_file(audio_url, "Audio", f"{index_prefix}{sanitized_title}", "mp3")
                if not current_mp3_filepath:
                    failed_urls.add(url)
                else:
                    if lyrics:
                        add_lyrics_to_mp3(current_mp3_filepath, lyrics)
            else:
                record_failure(url, "Audio URL not found")
                failed_urls.add(url)
        
        # Image extraction
        current_image_filepath = None
        if options["image"]:
            image_meta = soup.find("meta", {"name": "twitter:image"})
            if image_meta:
                img_url = image_meta.get("content")
                if "image_large_" not in img_url:
                    image_meta = soup.find("meta", {"property": "og:image"})
                    img_url = image_meta.get("content") if image_meta else None
            else:
                image_meta = soup.find("meta", {"property": "og:image"})
                img_url = image_meta.get("content") if image_meta else None
            if img_url:
                current_image_filepath = download_file(img_url, "Images", f"{index_prefix}{sanitized_title} - Art", "jpeg")
                if not current_image_filepath:
                    failed_urls.add(url)
            else:
                record_failure(url, "Image URL not found")
                failed_urls.add(url)
        
        # If both MP3 and image were downloaded successfully, embed the image into the MP3.
        if options["mp3"] and options["image"] and current_mp3_filepath and current_image_filepath:
            add_image_to_mp3(current_mp3_filepath, current_image_filepath)
        
        # If no failures for this URL, immediately update the skip file.
        if url not in failed_urls:
            with open(skip_file, "a", encoding="utf-8") as sf:
                sf.write(url + "\n")
            downloaded_set.add(url)
            log_operation(f"✅ Marked URL as processed: {url}")
    
    if failures:
        with open(failed_file, "a", encoding="utf-8") as f:
            f.write("Final failure details for this run:\n")
            for url, msgs in failures.items():
                f.write(f"URL: {url}\n")
                for msg in msgs:
                    f.write(f"  - {msg}\n")
                f.write("\n")
        log_operation(f"\n❌ Failure details have been appended to {failed_file}")
    else:
        log_operation("\n✅ No failures recorded.")
    
    retry_failed_urls(failed_urls, options)

if __name__ == "__main__":
    main()
