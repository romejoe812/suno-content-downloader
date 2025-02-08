How This Script Works
User Selection:
When you run the script, you’re prompted to enter which items to extract and save. You can choose from:

HTML
MP4 (video)
MP3 (audio)
Lyrics
Prompt
Image
Page Data Extraction (Playwright):
The script uses Playwright to load each URL, waits for the lyrics element using the CSS selector section.w-full > div:nth-child(1), and extracts the page title, lyrics, full HTML, and GPT prompt (using extract_gpt_prompt()).
The GPT prompt extraction removes the substring " song. Listen and make your own with Suno.".

Saving & Downloading:
Based on your selections:

HTML, Lyrics, and GPT Prompt are saved as text files in their respective folders.
For media files, the script uses Requests with BeautifulSoup to re-fetch the HTML and extract media URLs from meta tags. It then downloads the MP4 video, MP3 audio, and the image (ensuring it uses a URL containing "image_large_").
Failure Logging:
Any failure (missing data or download errors) is appended to the failed_items list. After processing all URLs, these failures are saved to Logs/failed.txt.

# suno-content-downloader
Download Suno Content. Audio, Video, Lyrics, Prompt, Image
