# Standard library imports
import json
import os

# Third-party imports
from googleapiclient.discovery import build
from tqdm import tqdm

# !!! УВАГА: ВСТАВТЕ СЮДИ ВАШ НОВИЙ КЛЮЧ !!!
youtube_v3_api_key = "YOUR_API_KEY" 

print("Welcome to the YouTube Comment Fetcher! \\o/ - Written by @slackeight (Modified)")

print("Step 1 is getting all the comments from the Google Takeout files... ", end="")

def fix_weird_text_stuff(text):
    weird_text_stuff = {
        "&quot;": "\"",
        "&#39;": "'",
        "&#x27;": "'",
        "&#x2F;": "/",
        "&amp;": "&",
        "1<br>": "\n",
        "<br>": "\n",
        "\u2014": "-"
    }
    for key, value in weird_text_stuff.items():
        text = text.replace(key, value)
    return text

# --- ПОШУК ФАЙЛІВ ---
comments_files = [] 
path = 'comments' 

if os.path.exists(path):
    files_in_folder = os.listdir(path)
    for f in files_in_folder:
        if f.lower().endswith('.csv') and "cache" not in f:
            comments_files.append(os.path.join(path, f))
else:
    print(f"Error: Folder '{path}' not found!")

print(f"Found {len(comments_files)} comment files in '{path}' folder.")

if not comments_files:
    error_message = """ERROR! Couldn't find the comments files."""
    raise FileNotFoundError(error_message)

comment_ids = []
for file in comments_files:
    try:
        with open(file, 'r', encoding='utf-8') as f:
            comment_ids.extend([line.split(',')[0] for line in f if line.strip()])
    except Exception as e:
        print(f"Warning: Error reading file {file}: {e}")
        continue

print("Done! Successfully loaded in the comments.\n")

print("Step 2 is building a YouTube API client... ", end="")

try:
    youtube = build('youtube', 'v3', developerKey = youtube_v3_api_key if youtube_v3_api_key != "YOUR_API_KEY" else os.getenv("YOUTUBE_V3_API_KEY"))
except Exception as e:
    raise Exception(f"ERROR! Couldn't build YouTube API client: {e}")

comment_data = {}
print("Done! Now getting comment data...\n\n")

cache_separator = "!SEPERATOR!"

# --- ЗАВАНТАЖЕННЯ КЕШУ ---
try:
    with open('comments_cache.csv', 'r', encoding='utf-8') as f:
        try:
            for line in f:
                parts = line.split(cache_separator)
                if len(parts) >= 5:
                    comment_data[parts[0]] = {
                        'comment': fix_weird_text_stuff(parts[1].strip()),
                        'like_count': parts[2].strip(),
                        'video_title': parts[3].strip(),
                        'video_url': parts[4].strip()
                    }
        except Exception as e:
            print(f"Error loading cache: {e}. Starting fresh/continuing.")
except FileNotFoundError:
    print("No cache file found, starting from scratch.")

# --- ОСНОВНИЙ ЦИКЛ ОБРОБКИ ---
with open('comments_cache.csv', 'a', encoding='utf-8') as cache_file:
    progress_bar = tqdm(total=len(comment_ids), desc="Processing comments", miniters=2)

    unprocessed_comment_ids = [i for i in comment_ids if i not in comment_data]
    progress_bar.update(len(comment_ids) - len(unprocessed_comment_ids))

    # ВАЖЛИВО: Цей цикл має бути з відступом, щоб бути всередині 'with open'!
    for comment_id in unprocessed_comment_ids:
        try:
            # 1. Запит коментаря
            response = youtube.commentThreads().list(
                part="snippet",
                id=comment_id
            ).execute()
            
            if response['items']:
                video_id = response['items'][0]['snippet']['videoId']
                
                # 2. Запит відео
                video_data = youtube.videos().list(
                    part="snippet",
                    id=video_id
                ).execute()
                
                video_title = video_data['items'][0]['snippet']['title']
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                content = response['items'][0]['snippet']['topLevelComment']['snippet']['textDisplay'].strip().replace("\n", " ")
                like_count = response['items'][0]['snippet']['topLevelComment']['snippet']['likeCount']
                
                # Зберігаємо в пам'ять
                comment_data[comment_id] = {
                    'comment': content,
                    'like_count': like_count,
                    'video_title': video_title,
                    'video_url': video_url
                }
                
                # Запис у кеш
                cache_line = f"{comment_id}{cache_separator}{content}{cache_separator}{like_count}{cache_separator}{video_title}{cache_separator}{video_url}\n"
                cache_file.write(cache_line)
                cache_file.flush()
            else:
                # Коментар не знайдено
                comment_data[comment_id] = {'comment': 'not found', 'like_count': 0, 'video_title': 'not found', 'video_url': 'not found'}
                cache_file.write(f"{comment_id}{cache_separator}not found{cache_separator}0{cache_separator}not found{cache_separator}not found\n")
                cache_file.flush()

        except Exception as e:
            error_msg = str(e)
            
            # --- ЗАХИСТ ВІД КВОТИ ---
            if "quotaExceeded" in error_msg or "403" in error_msg:
                print("\n\n🛑 ЛІМІТ ВИЧЕРПАНО (QUOTA EXCEEDED)!")
                print("Зберігаємо поточний результат у JSON і завершуємо роботу.")
                break # Вихід з циклу
            
            print(f"\nWarning: Error processing comment {comment_id}: {e}")
            continue
        
        finally:
            progress_bar.update(1)

    progress_bar.close()

print("Done processing! Generating JSON report...")

# --- ЗБЕРЕЖЕННЯ JSON ---
sorted_comments = sorted(
    [{"id": k, 
      "comment": v['comment'], 
      "like_count": int(v['like_count']) if str(v['like_count']).isdigit() else 0, 
      "video_title": v['video_title'], 
      "video_url": v['video_url']} 
     for k, v in comment_data.items()],
    key=lambda x: x['like_count'],
    reverse=True
)

with open('most_liked_comments.json', 'w', encoding='utf-8') as f:
    json_entries = [
        json.dumps({item['id']: {'comment': item['comment'], 'like_count': item['like_count'], 'video_title': item['video_title'], 'video_url': item['video_url']}}, 
                   indent=4, ensure_ascii=False)[1:-2]
        for item in sorted_comments
    ]
    f.write('{\n    ' + ',\n    '.join(json_entries) + '\n}')

print(f"Successfully saved {len(sorted_comments)} comments to 'most_liked_comments.json'")
