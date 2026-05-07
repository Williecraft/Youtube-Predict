"""
Find all working YouTube explore category URLs.
"""
import sys
sys.path.insert(0, ".")
from src.utils.http_client import YouTubeClient, extract_js_var, dig

client = YouTubeClient()

def count_videos(obj, depth=0):
    if depth > 30 or not isinstance(obj, (dict, list)):
        return 0
    if isinstance(obj, dict):
        if "videoId" in obj and "title" in obj:
            return 1
        return sum(count_videos(v, depth+1) for v in obj.values())
    return sum(count_videos(i, depth+1) for i in obj)

def find_tab_ids(data):
    tabs = dig(data, "contents", "twoColumnBrowseResultsRenderer", "tabs") or []
    return [
        (tab.get("tabRenderer") or tab.get("expandableTabRenderer") or {}).get("tabIdentifier", "")
        for tab in tabs
    ]

# Try all candidate explore URLs with gl=TW
CANDIDATES = [
    ("music",    "https://www.youtube.com/feed/music"),
    ("music2",   "https://www.youtube.com/music"),
    ("gaming",   "https://www.youtube.com/gaming"),
    ("news",     "https://www.youtube.com/news"),
    ("sports",   "https://www.youtube.com/sports"),
    ("live",     "https://www.youtube.com/live"),
    ("podcasts", "https://www.youtube.com/podcasts"),
    ("courses",  "https://www.youtube.com/courses"),
    ("learning", "https://www.youtube.com/feed/learning"),
    ("movies",   "https://www.youtube.com/movies"),
    ("films",    "https://www.youtube.com/channel/UCopNcN46UbXVtpKMrmU4Abg"),  # gaming channel
]

print(f"{'label':12} {'status':8} {'videos':8}  url")
for label, url in CANDIDATES:
    r = client.get(url, params={"gl": "TW", "hl": "zh-TW"})
    if r is None:
        print(f"{label:12} {'None':8}")
        continue
    d = extract_js_var(r.text, "ytInitialData")
    n = count_videos(d)
    final_url = r.url
    print(f"{label:12} {r.status_code:<8} {n:<8}  {final_url}")
