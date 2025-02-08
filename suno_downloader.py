from playwright.sync_api import sync_playwright
import os
import re
import requests
from bs4 import BeautifulSoup

def read_urls_from_file(file_path):
    """Reads URLs from a file, ignoring empty lines."""
    if not os.path.exists(file_path):
        print(f"❌ File not found: {file_path}")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]

def sanitize_filename(filename):
    """Sanitizes a string to be used as a filename by replacing illegal characters with an underscore."""
    return re.sub(r'[<>:"/\\|?*]', '_', filename)

def extract_gpt_prompt(html):
    """
    Attempts to extract the GPT prompt from the HTML source.
    First, it searches for a JSON fragment containing the key "gpt_description_prompt"
    (e.g., "gpt_description_prompt": "some value").
    If that search fails, it falls back to using the 3rd <meta> tag in the entire HTML.
    In either case, it then removes the unwanted substring:
       " song. Listen and make your own with Suno."
    """
    # Try to find the prompt in any <script> tag.
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script"):
        script_text = script.get_text()
        if "gpt_description_prompt" in script_text:
            # Use a regex to capture the value.
            match = re.search(r'gpt_description_prompt\\"\s*:\s*\\"?([^\\"]+)\\"?', script_text)
            if match:
                prompt = match.group(1).strip()
                prompt = prompt.replace(" song. Listen and make your own with Suno.", "").strip()
                return prompt
    # Fallback: use the 3rd <meta> tag (index 2) with a content attribute in the entire HTML.
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
      - The page title (for naming files)
      - The lyrics text (using the CSS selector "section.w-full > div:nth-child(1)")
      - The full HTML content of the page
      - The GPT prompt (via extract_gpt_prompt)
    """
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        print(f"⏳ Navigating to {url}...")
        try:
            page.goto(url, timeout=60000)  # Allow up to 60 seconds for navigation
        except Exception as e:
            print(f"❌ Error navigating to {url}: {e}")
            browser.close()
            return "Unknown_Song", None, None, None
        
        try:
            page.wait_for_selector("section.w-full > div:nth-child(1)", timeout=20000)
            lyrics = page.text_content("section.w-full > div:nth-child(1)").strip()
        except Exception as e:
            print(f"❌ Error extracting lyrics from {url}: {e}")
            lyrics = None

        title = page.title() or "Unknown_Song"
        html_content = page.content()
        gpt_prompt = extract_gpt_prompt(html_content)
        browser.close()
        return title, lyrics, gpt_prompt, html_content

def save_text_to_file(text, directory, filename):
    """Saves the given text to a file in the specified directory."""
    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(text)
    print(f"✅ Saved to {filepath}")

def download_file(url, directory, filename, extension):
    """
    Downloads a file from the provided URL using Requests and saves it
    in the specified directory with the given filename and extension.
    """
    if not url:
        print(f"⚠️ URL not provided for {filename}.{extension}")
        return False

    os.makedirs(directory, exist_ok=True)
    filepath = os.path.join(directory, f"{filename}.{extension}")
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
        print(f"✅ Downloaded file to {filepath}")
        return True
    except Exception as e:
        print(f"❌ Failed to download {url}: {e}")
        return False

# Use a persistent requests.Session() for media downloads.
session = requests.Session()

def get_user_selection():
    """
    Prompts the user to select what to extract and save.
    Options:
      1. HTML
      2. MP4
      3. MP3
      4. Lyrics
      5. Prompt
      6. Image
    Enter numbers separated by commas (e.g., "1,2,4,5,6").
    """
    print("Select what to extract and save for each URL:")
    print("1. HTML")
    print("2. MP4")
    print("3. MP3")
    print("4. Lyrics")
    print("5. Prompt")
    print("6. Image")
    choices = input("Enter numbers separated by commas (e.g., 1,2,4,5,6): ")
    selections = [x.strip() for x in choices.split(",")]
    return {
        "html": "1" in selections,
        "mp4": "2" in selections,
        "mp3": "3" in selections,
        "lyrics": "4" in selections,
        "prompt": "5" in selections,
        "image": "6" in selections
    }

def main():
    urls_file = "suno_urls.txt"  # Ensure this file exists in the same directory
    urls = read_urls_from_file(urls_file)
    if not urls:
        print("❌ No URLs found in the file.")
        return

    options = get_user_selection()
    
    for url in urls:
        print(f"🔄 Processing URL: {url}")
        title, lyrics, gpt_prompt, html_content = extract_page_data(url)
        sanitized_title = sanitize_filename(title)
        
        # Save HTML if selected.
        if options["html"]:
            if html_content:
                save_text_to_file(html_content, "HTML", f"{sanitized_title} - Parsed.html")
            else:
                print(f"⚠️ HTML content not found for: {url}")
        
        # Save Lyrics if selected.
        if options["lyrics"]:
            if lyrics:
                save_text_to_file(lyrics, "Lyrics", f"{sanitized_title} - Lyrics.txt")
            else:
                print(f"⚠️ Lyrics not found for: {url}")
        
        # Save GPT Prompt if selected.
        if options["prompt"]:
            if gpt_prompt:
                save_text_to_file(gpt_prompt, "GPT_Prompts", f"{sanitized_title} - GPT_Prompt.txt")
            else:
                print(f"⚠️ GPT prompt not found for: {url}")
        
        # For media files, re-fetch the full HTML using Requests and parse it with BeautifulSoup.
        try:
            response = session.get(url, timeout=15)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")
        except Exception as e:
            print(f"❌ Error fetching full HTML for media extraction from {url}: {e}")
            continue
        
        # Download MP4 if selected.
        if options["mp4"]:
            video_meta = soup.find("meta", {"property": "og:video:url"})
            video_url = video_meta.get("content") if video_meta else None
            if video_url:
                download_file(video_url, "Videos", sanitized_title, "mp4")
            else:
                print(f"⚠️ Video URL not found for: {url}")
        
        # Download MP3 if selected.
        if options["mp3"]:
            audio_meta = soup.find("meta", {"property": "og:audio"})
            audio_url = audio_meta.get("content") if audio_meta else None
            if audio_url:
                download_file(audio_url, "Audio", sanitized_title, "mp3")
            else:
                print(f"⚠️ Audio URL not found for: {url}")
        
        # Download Image if selected.
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
                download_file(img_url, "Images", sanitized_title + " - Art", "jpeg")
            else:
                print(f"⚠️ Image URL not found for: {url}")

if __name__ == "__main__":
    main()
