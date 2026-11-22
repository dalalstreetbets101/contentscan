import os
import json
import urllib.request
import xml.etree.ElementTree as ET
import re
from datetime import datetime

# Configure feeds
FEEDS = {
    "AI_Infra": "https://news.google.com/rss/search?q=Nvidia+OR+OpenAI+OR+Anthropic+OR+AI+infrastructure&hl=en-US&gl=US&ceid=US:en",
    "Elon_Companies": "https://news.google.com/rss/search?q=Tesla+OR+SpaceX+OR+Elon+Musk&hl=en-US&gl=US&ceid=US:en",
    "Big_Tech": "https://news.google.com/rss/search?q=Microsoft+OR+Google+OR+Apple+OR+Amazon+OR+Meta&hl=en-US&gl=US&ceid=US:en",
    "Indian_Corporate": "https://news.google.com/rss/search?q=Reliance+OR+Tata+OR+Adani+OR+Sensex+OR+Nifty+OR+Indian+corporate&hl=en-IN&gl=IN&ceid=IN:en",
    "Indian_Startups": "https://news.google.com/rss/search?q=startup+funding+India+OR+unicorn+India+OR+valuation+India+OR+Indian+founder&hl=en-IN&gl=IN&ceid=IN:en",
    "Indian_IPOs_Markets": "https://news.google.com/rss/search?q=SEBI+OR+Indian+IPO+OR+DRHP+OR+NSE+OR+BSE&hl=en-IN&gl=IN&ceid=IN:en",
    "Crypto_Markets": "https://news.google.com/rss/search?q=Bitcoin+OR+Crypto+OR+Billionaire+OR+Markets+OR+Economy&hl=en-US&gl=US&ceid=US:en",
    "TechCrunch": "https://techcrunch.com/feed/"
}

HISTORY_FILE = "history.json"
CANDIDATES_FILE = "candidates.json"

def clean_words(text):
    text = re.sub(r'[^\w\s]', '', text.lower())
    words = {w for w in text.split() if len(w) > 3}
    return words

def calculate_overlap(headline1, headline2):
    w1 = clean_words(headline1)
    w2 = clean_words(headline2)
    if not w1 or not w2:
        return 0.0
    intersection = w1.intersection(w2)
    union = w1.union(w2)
    return len(intersection) / len(union)

def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"Error reading history.json: {e}")
            return []
    return []

def save_candidates(candidates):
    try:
        with open(CANDIDATES_FILE, 'w', encoding='utf-8') as f:
            json.dump(candidates, f, indent=2, ensure_ascii=False)
        print(f"Saved {len(candidates)} candidates to {CANDIDATES_FILE}")
    except Exception as e:
        print(f"Error saving candidates: {e}")

def fetch_feed_items(name, url):
    items = []
    print(f"Fetching feed: {name}...")
    try:
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            xml_data = response.read()
        
        root = ET.fromstring(xml_data)
        for item in root.findall('.//item'):
            title = item.find('title')
            link = item.find('link')
            pub_date = item.find('pubDate')
            
            title_text = title.text if title is not None else ""
            link_text = link.text if link is not None else ""
            pub_text = pub_date.text if pub_date is not None else ""
            
            # Clean Google News titles (usually ends with " - Source Name")
            if " - " in title_text:
                title_text = " - ".join(title_text.split(" - ")[:-1])
                
            if title_text and link_text:
                items.append({
                    "headline": title_text.strip(),
                    "url": link_text.strip(),
                    "published": pub_text,
                    "feed": name
                })
    except Exception as e:
        print(f"Failed to fetch {name}: {e}")
    return items

def parse_date(date_str):
    import email.utils
    try:
        return email.utils.parsedate_to_datetime(date_str)
    except Exception:
        try:
            # Fallback for simpler formats
            return datetime.strptime(date_str, "%Y-%m-%d")
        except Exception:
            return datetime.min

def main():
    history = load_history()
    print(f"Loaded {len(history)} historical stories.")
    
    all_raw_items = []
    for name, url in FEEDS.items():
        all_raw_items.extend(fetch_feed_items(name, url))
        
    candidates = []
    seen_urls = set()
    seen_headlines = set()
    
    # Pre-populate seen urls and headlines from history
    history_urls = {h['url'].lower() for h in history}
    
    for item in all_raw_items:
        url = item['url']
        url_lower = url.lower()
        headline = item['headline']
        
        # Deduplication against session items
        if url_lower in seen_urls or headline.lower() in seen_headlines:
            continue
            
        # Deduplication against historical items (URL match)
        if url_lower in history_urls:
            continue
            
        # Deduplication against historical items (Similarity check)
        is_duplicate = False
        for hist_item in history:
            sim = calculate_overlap(headline, hist_item['headline'])
            if sim > 0.45: # Overlap of 45% or more words indicates high similarity
                is_duplicate = True
                break
                
        if is_duplicate:
            continue
            
        seen_urls.add(url_lower)
        seen_headlines.add(headline.lower())
        candidates.append(item)
        
    # Separate Indian and International candidates
    indian_feeds = {"Indian_Corporate", "Indian_Startups", "Indian_IPOs_Markets"}
    indian_cands = [c for c in candidates if c.get("feed") in indian_feeds]
    intl_cands = [c for c in candidates if c.get("feed") not in indian_feeds]
    
    # Sort both lists by publication date (latest first)
    indian_cands.sort(key=lambda x: parse_date(x['published']), reverse=True)
    intl_cands.sort(key=lambda x: parse_date(x['published']), reverse=True)
    
    # Balance: take up to 50 of each, and fill the remaining spots if one has less than 50
    num_indian = len(indian_cands)
    num_intl = len(intl_cands)
    
    target_indian = 50
    target_intl = 50
    
    if num_indian < 50:
        target_indian = num_indian
        target_intl = min(num_intl, 100 - target_indian)
    elif num_intl < 50:
        target_intl = num_intl
        target_indian = min(num_indian, 100 - target_intl)
        
    balanced_cands = indian_cands[:target_indian] + intl_cands[:target_intl]
    
    # Sort the combined list chronologically (latest first)
    balanced_cands.sort(key=lambda x: parse_date(x['published']), reverse=True)
    
    # Save the top 100 balanced candidates
    save_candidates(balanced_cands[:100])
    
    # Update local data.js script for file:// protocol support
    update_data_js()

def update_data_js():
    import os
    import json
    directory = os.path.dirname(os.path.abspath(__file__))
    data = {
        "status": "ready",
        "cron_time": "12:00 PM IST (Daily)",
        "env_status": {},
        "candidates": [],
        "history": [],
        "latest_report": "",
        "latest_report_name": ""
    }
    
    # Read Env Status
    env_keys = ["NOTION_TOKEN", "NOTION_DATABASE_ID", "GOOGLE_DOCS_FOLDER_ID", "GOOGLE_SHEETS_SPREADSHEET_ID"]
    env_file = os.path.join(directory, ".env")
    if os.path.exists(env_file):
        try:
            with open(env_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            for line in lines:
                if '=' in line and not line.strip().startswith('#'):
                    k, v = line.split('=', 1)
                    k = k.strip()
                    v = v.strip()
                    if k in env_keys:
                        data["env_status"][k] = {
                            "configured": len(v) > 0,
                            "masked": v[:4] + "..." + v[-4:] if len(v) > 8 else "****"
                        }
        except Exception:
            pass
            
    for k in env_keys:
        if k not in data["env_status"]:
            data["env_status"][k] = {"configured": False, "masked": ""}
            
    # Read candidates.json
    candidates_file = os.path.join(directory, "candidates.json")
    if os.path.exists(candidates_file):
        try:
            with open(candidates_file, 'r', encoding='utf-8') as f:
                data["candidates"] = json.load(f)
        except Exception:
            pass
            
    # Read history.json
    history_file = os.path.join(directory, "history.json")
    if os.path.exists(history_file):
        try:
            with open(history_file, 'r', encoding='utf-8') as f:
                data["history"] = json.load(f)
        except Exception:
            pass
            
    # Read latest report
    reports_dir = os.path.join(directory, "reports")
    if os.path.exists(reports_dir):
        try:
            files = [f for f in os.listdir(reports_dir) if f.startswith("report_") and f.endswith(".md")]
            if files:
                files.sort(reverse=True)
                latest_report_file = os.path.join(reports_dir, files[0])
                with open(latest_report_file, 'r', encoding='utf-8') as f:
                    data["latest_report"] = f.read()
                    data["latest_report_name"] = files[0]
        except Exception:
            pass
            
    data_js_path = os.path.join(directory, "data.js")
    try:
        with open(data_js_path, 'w', encoding='utf-8') as f:
            f.write(f"window.DSB_DATA = {json.dumps(data, indent=2, ensure_ascii=False)};\n")
        print(f"Successfully updated local data script: {data_js_path}")
    except Exception as e:
        print(f"Error updating data.js: {e}")

if __name__ == "__main__":
    main()

