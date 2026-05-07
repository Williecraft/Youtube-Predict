import sys, json
sys.path.insert(0, ".")
from src.utils.http_client import YouTubeClient, dig

client = YouTubeClient()
init_data, _ = client.get_watch_page("jNQXAC9IVRw")

# Find videoSecondaryInfoRenderer
contents = dig(init_data, "contents", "twoColumnWatchNextResults", "results", "results", "contents") or []
for item in contents:
    if "videoSecondaryInfoRenderer" in item:
        secondary = item["videoSecondaryInfoRenderer"]
        print("videoSecondaryInfoRenderer keys:", list(secondary.keys()))
        owner = secondary.get("owner", {})
        print("owner keys:", list(owner.keys()))
        vr = owner.get("videoOwnerRenderer", {})
        print("videoOwnerRenderer keys:", list(vr.keys()))
        sub = vr.get("subscriberCountText", {})
        print("subscriberCountText:", json.dumps(sub, ensure_ascii=False))
        break
