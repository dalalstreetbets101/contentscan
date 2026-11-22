import os
import sys
import json
import datetime
import urllib.request
import urllib.error
import re
import subprocess
import time

# Reconfigure stdout to use utf-8 to avoid encoding errors in the terminal
sys.stdout.reconfigure(encoding='utf-8')

DIRECTORY = os.path.dirname(os.path.abspath(__file__))

def load_env():
    env_vars = {}
    env_path = os.path.join(DIRECTORY, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

def clean_url(url):
    url = url.split("?")[0]
    return url.strip().lower()

def strip_code_fences(text):
    text = text.strip()
    text = re.sub(r"^```markdown\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()

def validate_generated_report(report_text, candidates_data):
    # Helper to check sentence & word counts for "Why it matters:"
    def check_why_it_matters(val):
        words = val.split()
        cleaned_val = re.sub(r'(?<!\w)([A-Z]\.)(?!\w)', '', val)
        cleaned_val = re.sub(r'\bcult\.fit\b', 'cultfit', cleaned_val, flags=re.IGNORECASE)
        sentences = re.split(r'[.!?]+', cleaned_val)
        sentences = [s for s in sentences if s.strip()]
        return len(words), len(sentences)

    errors = []
    penalty_score = 0
    counts = {"breaking": 0, "business": 0, "evergreen": 0, "total": 0}
    
    # Basic Checks
    if not report_text.strip().startswith("DAILY CONTENT REPORT"):
        errors.append("Report must start with 'DAILY CONTENT REPORT'")
        penalty_score += 10
        
    date_match = re.search(r"Date:\s*(\d{4}-\d{2}-\d{2})", report_text)
    if not date_match:
        errors.append("Date: YYYY-MM-DD is missing or improperly formatted")
        penalty_score += 10
        
    # Check major sections
    sections_needed = ["TOP 5 BREAKING NEWS", "TOP 5 BUSINESS STORIES", "TOP 5 EVERGREEN FACTS"]
    for sec in sections_needed:
        if sec not in report_text:
            errors.append(f"Missing required section: '{sec}'")
            penalty_score += 5000
            
    if not (re.search(r"TODAY'S TOP \d+ PRIORITY POSTS", report_text) or "TODAY'S TOP 3 PRIORITY POSTS" in report_text):
        errors.append("Missing required section: 'TODAY'S TOP 3 PRIORITY POSTS'")
        penalty_score += 2000
        
    parts = re.split(r"TOP 5 BREAKING NEWS|TOP 5 BUSINESS STORIES|TOP 5 EVERGREEN FACTS|TODAY'S TOP \d+ PRIORITY POSTS", report_text)
    if len(parts) < 5:
        # Heavily penalize truncated or unparseable output
        penalty_score += 30000
        return False, ["Unable to parse the report sections properly (severely truncated)"], penalty_score, counts
        
    breaking_part = parts[1].strip("-\n\r ")
    business_part = parts[2].strip("-\n\r ")
    evergreen_part = parts[3].strip("-\n\r ")
    priority_part = parts[4].strip("-\n\r ")
    
    # 1. BREAKING NEWS check
    breaking_items = re.split(r"\n\s*\d+\.\s+", "\n" + breaking_part)
    breaking_items = [it.strip() for it in breaking_items if it.strip()]
    counts["breaking"] = len(breaking_items)
    if len(breaking_items) != 5:
        errors.append(f"Breaking News count is {len(breaking_items)} instead of 5")
        penalty_score += abs(5 - len(breaking_items)) * 2000
        
    for idx, item in enumerate(breaking_items):
        lines = [l.strip() for l in item.split("\n") if l.strip()]
        if not lines:
            errors.append(f"Breaking News {idx+1} is empty")
            penalty_score += 1000
            continue
        headline = lines[0]
        if not headline.endswith(" -"):
            errors.append(f"Breaking News {idx+1} headline must end with space-hyphen (' -'), got: '{headline}'")
            penalty_score += 1
            
        fields = ["Category:", "Source:", "Why it matters:", "1 Line Summary:", "Caption Hook:", "Suggested Thumbnail:", "Virality Score:", "ENGAGEMENT TRIGGER:", "QUESTION:", "Source URL:"]
        for field in fields:
            if not any(l.startswith(field) for l in lines):
                errors.append(f"Breaking News {idx+1} missing field: '{field}'")
                penalty_score += 100 if field != "Source URL:" else 500
                
        why_line = next((l for l in lines if l.startswith("Why it matters:")), "")
        if why_line:
            val = why_line.split("Why it matters:", 1)[1].strip()
            w_count, s_count = check_why_it_matters(val)
            if w_count > 40:
                errors.append(f"Breaking News {idx+1} 'Why it matters' is {w_count} words (max 40): '{val}'")
                penalty_score += 1
            if s_count > 2:
                errors.append(f"Breaking News {idx+1} 'Why it matters' has {s_count} sentences (max 2): '{val}'")
                penalty_score += 1
                
        thumb_line = next((l for l in lines if l.startswith("Suggested Thumbnail:")), "")
        if thumb_line:
            val = thumb_line.split("Suggested Thumbnail:", 1)[1].strip()
            w_count = len(val.split())
            if w_count < 3 or w_count > 6:
                errors.append(f"Breaking News {idx+1} thumbnail must be 3-6 words, got {w_count}: '{val}'")
                penalty_score += 1

        q_line = next((l for l in lines if l.startswith("QUESTION:")), "")
        if q_line:
            val = q_line.split("QUESTION:", 1)[1].strip()
            w_count = len(val.split())
            if w_count > 15:
                errors.append(f"Breaking News {idx+1} 'QUESTION' is {w_count} words (max 15): '{val}'")
                penalty_score += 1
            if not val.endswith("?"):
                errors.append(f"Breaking News {idx+1} 'QUESTION' must end with a question mark '?': '{val}'")
                penalty_score += 1

    # 2. BUSINESS STORIES check
    business_items = re.split(r"\n\s*\d+\.\s+", "\n" + business_part)
    business_items = [it.strip() for it in business_items if it.strip()]
    counts["business"] = len(business_items)
    if len(business_items) != 5:
        errors.append(f"Business Stories count is {len(business_items)} instead of 5")
        penalty_score += abs(5 - len(business_items)) * 2000
        
    for idx, item in enumerate(business_items):
        lines = [l.strip() for l in item.split("\n") if l.strip()]
        if not lines:
            errors.append(f"Business Stories {idx+1} is empty")
            penalty_score += 1000
            continue
        headline = lines[0]
        if not headline.endswith("-") or headline.endswith(" -"):
            errors.append(f"Business Stories {idx+1} headline must end with hyphen without preceding space ('-'), got: '{headline}'")
            penalty_score += 1
            
        fields = ["Source:", "Why it matters:", "1 Line Summary:", "Caption Hook:", "Suggested Thumbnail:", "Virality Score:", "ENGAGEMENT TRIGGER:", "QUESTION:", "Source URL:"]
        for field in fields:
            if not any(l.startswith(field) for l in lines):
                errors.append(f"Business Stories {idx+1} missing field: '{field}'")
                penalty_score += 100 if field != "Source URL:" else 500
                
        why_line = next((l for l in lines if l.startswith("Why it matters:")), "")
        if why_line:
            val = why_line.split("Why it matters:", 1)[1].strip()
            w_count, s_count = check_why_it_matters(val)
            if w_count > 40:
                errors.append(f"Business Stories {idx+1} 'Why it matters' is {w_count} words (max 40): '{val}'")
                penalty_score += 1
            if s_count > 2:
                errors.append(f"Business Stories {idx+1} 'Why it matters' has {s_count} sentences (max 2): '{val}'")
                penalty_score += 1
                
        thumb_line = next((l for l in lines if l.startswith("Suggested Thumbnail:")), "")
        if thumb_line:
            val = thumb_line.split("Suggested Thumbnail:", 1)[1].strip()
            w_count = len(val.split())
            if w_count < 3 or w_count > 6:
                errors.append(f"Business Stories {idx+1} thumbnail must be 3-6 words, got {w_count}: '{val}'")
                penalty_score += 1

        q_line = next((l for l in lines if l.startswith("QUESTION:")), "")
        if q_line:
            val = q_line.split("QUESTION:", 1)[1].strip()
            w_count = len(val.split())
            if w_count > 15:
                errors.append(f"Business Stories {idx+1} 'QUESTION' is {w_count} words (max 15): '{val}'")
                penalty_score += 1
            if not val.endswith("?"):
                errors.append(f"Business Stories {idx+1} 'QUESTION' must end with a question mark '?': '{val}'")
                penalty_score += 1

    # 3. EVERGREEN FACTS check
    evergreen_items = re.split(r"\n\s*\d+\.\s+", "\n" + evergreen_part)
    evergreen_items = [it.strip() for it in evergreen_items if it.strip()]
    counts["evergreen"] = len(evergreen_items)
    if len(evergreen_items) != 5:
        errors.append(f"Evergreen Facts count is {len(evergreen_items)} instead of 5")
        penalty_score += abs(5 - len(evergreen_items)) * 2000
        
    for idx, item in enumerate(evergreen_items):
        lines = [l.strip() for l in item.split("\n") if l.strip()]
        if not lines:
            errors.append(f"Evergreen Facts {idx+1} is empty")
            penalty_score += 1000
            continue
        topic = lines[0]
        if not topic.endswith("-") or topic.endswith(" -"):
            errors.append(f"Evergreen Facts {idx+1} topic must end with hyphen without preceding space ('-'), got: '{topic}'")
            penalty_score += 1
            
        fields = ["Headline :", "Source:", "Why it matters:", "1 line Summary:", "Why people care:", "Caption Hook:", "Suggested Thumbnail:", "Virality Score:", "ENGAGEMENT TRIGGER:", "QUESTION:", "Source URL:"]
        for field in fields:
            if not any(l.startswith(field) for l in lines):
                errors.append(f"Evergreen Facts {idx+1} missing field: '{field}'")
                penalty_score += 100 if field != "Source URL:" else 500
                
        why_line = next((l for l in lines if l.startswith("Why it matters:")), "")
        if why_line:
            val = why_line.split("Why it matters:", 1)[1].strip()
            w_count, s_count = check_why_it_matters(val)
            if w_count > 40:
                errors.append(f"Evergreen Facts {idx+1} 'Why it matters' is {w_count} words (max 40): '{val}'")
                penalty_score += 1
            if s_count > 2:
                errors.append(f"Evergreen Facts {idx+1} 'Why it matters' has {s_count} sentences (max 2): '{val}'")
                penalty_score += 1
                
        thumb_line = next((l for l in lines if l.startswith("Suggested Thumbnail:")), "")
        if thumb_line:
            val = thumb_line.split("Suggested Thumbnail:", 1)[1].strip()
            w_count = len(val.split())
            if w_count < 3 or w_count > 6:
                errors.append(f"Evergreen Facts {idx+1} thumbnail must be 3-6 words, got {w_count}: '{val}'")
                penalty_score += 1

        q_line = next((l for l in lines if l.startswith("QUESTION:")), "")
        if q_line:
            val = q_line.split("QUESTION:", 1)[1].strip()
            w_count = len(val.split())
            if w_count > 15:
                errors.append(f"Evergreen Facts {idx+1} 'QUESTION' is {w_count} words (max 15): '{val}'")
                penalty_score += 1
            if not val.endswith("?"):
                errors.append(f"Evergreen Facts {idx+1} 'QUESTION' must end with a question mark '?': '{val}'")
                penalty_score += 1

    counts["total"] = counts["breaking"] + counts["business"] + counts["evergreen"]
    if counts["total"] < 15:
        penalty_score += (15 - counts["total"]) * 2000

    # 4. Spacing checks
    all_lines = report_text.split("\n")
    for idx, l in enumerate(all_lines[:-1]):
        if l.strip() and all_lines[idx+1].strip():
            labels = ["Category:", "Source:", "Why it matters:", "1 Line Summary:", "1 line Summary:", "Caption Hook:", "Suggested Thumbnail:", "Virality Score:", "Source URL:", "Why people care:", "Headline :", "ENGAGEMENT TRIGGER:", "QUESTION:"]
            if any(l.strip().startswith(lbl) for lbl in labels) or any(all_lines[idx+1].strip().startswith(lbl) for lbl in labels):
                errors.append(f"Line {idx+1} and {idx+2} have no blank line between them: '{l.strip()}' and '{all_lines[idx+1].strip()}'")
                penalty_score += 1

    # 5. Geographic Mix validation using URLs
    indian_feeds = {"Indian_Corporate", "Indian_Startups", "Indian_IPOs_Markets"}
    indian_count = 0
    intl_count = 0
    url_to_feed = {clean_url(c["url"]): c["feed"] for c in candidates_data}
    
    extracted_urls = re.findall(r"Source URL:\s*(https?://[^\s\n\r]+)", report_text)
    for url in extracted_urls:
        c_url = clean_url(url)
        matched_feed = None
        if c_url in url_to_feed:
            matched_feed = url_to_feed[c_url]
        else:
            for k, v in url_to_feed.items():
                if k in c_url or c_url in k:
                    matched_feed = v
                    break
        
        if matched_feed:
            if matched_feed in indian_feeds:
                indian_count += 1
            else:
                intl_count += 1

    if len(extracted_urls) == 15:
        if indian_count < 7 or indian_count > 8:
            errors.append(f"Geographic mix invalid: Found {indian_count} Indian and {intl_count} International stories based on URL mapping.")
            penalty_score += 10

    is_valid = (len(errors) == 0 and counts["total"] == 15)
    return is_valid, errors, penalty_score, counts

def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    report_file = os.path.join(DIRECTORY, "reports", f"report_{today}.md")
    
    # 1. Exit if a complete report already exists
    if os.path.exists(report_file):
        with open(report_file, "r", encoding="utf-8") as f:
            existing_text = f.read()
        existing_urls = len(re.findall(r"Source URL:\s*https?://", existing_text))
        if existing_urls >= 15:
            print(f"Complete report for {today} already exists (15/15 articles). Exiting.")
            return
        else:
            print(f"Existing report for {today} is INCOMPLETE ({existing_urls}/15 articles, {len(existing_text)} bytes). Re-compiling to fix...")

    # 2. Load API key (checks .env or environment variable)
    env = load_env()
    api_key = env.get("GEMINI_API_KEY") or os.environ.get("GEMINI_API_KEY")
    if not api_key or api_key == "YOUR_GEMINI_API_KEY_HERE":
        print("ERROR: GEMINI_API_KEY is not configured in .env file or environment variables.")
        return

    # 3. Read candidates
    candidates_file = os.path.join(DIRECTORY, "candidates.json")
    if not os.path.exists(candidates_file):
        print("ERROR: candidates.json not found. Make sure today's scan has run.")
        return
        
    with open(candidates_file, "r", encoding="utf-8") as f:
        candidates_data = json.load(f)

    # Separate candidates into Indian and International (take top 25 each with compact representation)
    indian_feeds = {"Indian_Corporate", "Indian_Startups", "Indian_IPOs_Markets"}
    indian_cands = []
    intl_cands = []
    for c in candidates_data:
        item = {"title": c.get("title"), "url": c.get("url"), "feed": c.get("feed")}
        if c.get("feed") in indian_feeds:
            if len(indian_cands) < 25:
                indian_cands.append(item)
        else:
            if len(intl_cands) < 25:
                intl_cands.append(item)

    # 4. Read history for deduplication
    history_file = os.path.join(DIRECTORY, "history.json")
    history_list = []
    if os.path.exists(history_file):
        with open(history_file, "r", encoding="utf-8") as f:
            history_list = json.load(f)
            
    recent_headlines = [h["headline"] for h in history_list[-80:]] if history_list else []

    # 5. Read AGENTS.md instructions
    agents_md_path = os.path.join(DIRECTORY, ".agents", "AGENTS.md")
    if not os.path.exists(agents_md_path):
        print("ERROR: AGENTS.md instructions not found.")
        return
        
    with open(agents_md_path, "r", encoding="utf-8") as f:
        instructions = f.read()

    # Formulate base prompt content
    prompt_base = f"""
{instructions}

---
CURRENT DATE FOR THE REPORT: {today}
---
RECENTLY COVERED TOPICS/HEADLINES (DO NOT DUPLICATE):
{json.dumps(recent_headlines, indent=2)}
---
TODAY'S SCAN CANDIDATES DATA:

INDIAN CANDIDATES LIST (Choose exactly 8 stories from this list):
{json.dumps(indian_cands, indent=2)}

INTERNATIONAL CANDIDATES LIST (Choose exactly 7 stories from this list):
{json.dumps(intl_cands, indent=2)}
---

CRITICAL REQUIREMENTS:
1. Generate the complete DAILY CONTENT REPORT strictly following the structure, rules, and spacing guidelines from AGENTS.md.
2. Select exactly 8 stories from the INDIAN CANDIDATES LIST and exactly 7 stories from the INTERNATIONAL CANDIDATES LIST.
3. You MUST generate ALL sections and ALL 15 stories completely without stopping early:
   - TOP 5 BREAKING NEWS: Items 1 to 5 (3 Indian stories, 2 International stories)
   - TOP 5 BUSINESS STORIES: Items 1 to 5 (3 Indian stories, 2 International stories)
   - TOP 5 EVERGREEN FACTS: Items 1 to 5 (2 Indian stories, 3 International stories)
   - TODAY'S TOP 3 PRIORITY POSTS: Items 1 to 3
4. For every single story, provide ALL required fields:
   - Category, Source, Why it matters, 1 Line Summary, Caption Hook, Suggested Thumbnail, Virality Score, ENGAGEMENT TRIGGER, QUESTION, Source URL
5. Headlines/Topics format:
   - Breaking News: '1. [Headline] -'
   - Business Stories: '1. [Headline]-'
   - Evergreen Facts: '1. [Topic]-' with 'Headline : [Headline]'
6. Spacing: Exactly ONE empty line between every field name and value pair.
7. Why it matters: max 2 sentences and max 40 words.
8. Suggested Thumbnail: 3-6 words, uppercase, punchy text.
9. Start directly with 'DAILY CONTENT REPORT'. Do NOT use markdown code fences.
"""

    # We try models in order of stability and compliance:
    # 1. gemini-3.1-flash-lite (fast, highly stable, 65k output)
    # 2. gemini-3.5-flash-lite (backup)
    # 3. gemini-2.5-flash (larger model)
    models_to_try = ["gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-2.5-flash"]
    
    best_text = None
    min_penalty = 999999999
    best_errors = []
    best_counts = {}
    validation_passed = False
    
    for model in models_to_try:
        print(f"Trying to compile report with model: {model}...")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        
        for attempt in range(1, 3):
            current_prompt = prompt_base
            payload = {
                "contents": [
                    {"parts": [{"text": current_prompt}]}
                ],
                "generationConfig": {
                    "temperature": 0.15,
                    "maxOutputTokens": 8192
                }
            }
            
            try:
                req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=180) as response:
                    res_data = json.loads(response.read().decode("utf-8"))
                    cand = res_data["candidates"][0]
                    finish_reason = cand.get("finishReason", "STOP")
                    raw_text = cand["content"]["parts"][0]["text"].strip()
                    generated_text = strip_code_fences(raw_text)
                    
                    # Validate and score
                    is_valid, errors, penalty, counts = validate_generated_report(generated_text, candidates_data)
                    
                    if finish_reason != "STOP":
                        print(f"WARNING: Output was cut off by API (finishReason: {finish_reason}).")
                        penalty += 50000
                        
                    print(f"Attempt {attempt} for {model}: {counts['total']}/15 stories (Breaking={counts['breaking']}, Business={counts['business']}, Evergreen={counts['evergreen']}), Penalty={penalty}, Errors={len(errors)}")
                    
                    if penalty < min_penalty:
                        min_penalty = penalty
                        best_text = generated_text
                        best_errors = errors
                        best_counts = counts
                        
                    if is_valid or (counts["total"] == 15 and penalty < 50):
                        validation_passed = True
                        print(f"SUCCESS: Complete, valid report compiled using {model} (attempt {attempt}).")
                        break
                        
            except urllib.error.HTTPError as e:
                print(f"Model {model} (attempt {attempt}) failed with HTTP status {e.code}")
                time.sleep(5)
            except Exception as e:
                print(f"Model {model} (attempt {attempt}) encountered error: {e}")
                time.sleep(5)
                
            if validation_passed:
                break
                
        if validation_passed:
            break
            
    if not best_text:
        print("ERROR: Failed to generate report with any model.")
        return
        
    print(f"Selected best report: {best_counts.get('total', 0)}/15 articles (Penalty score: {min_penalty})")

    # Write report file
    os.makedirs(os.path.dirname(report_file), exist_ok=True)
    with open(report_file, "w", encoding="utf-8") as f:
        f.write(best_text)
    print(f"Report successfully compiled and written to: {report_file}")

    # Parse and Sync today's report into history.json
    print("Syncing generated report into history.json...")
    try:
        sections = re.split(r"TOP 5 ", best_text)
        history_entries = []
        
        # Breaking News
        if len(sections) > 1:
            breaking_part = sections[1].split("---")[0]
            items = re.split(r"\n\s*\d+\.\s+", "\n" + breaking_part)
            for item in items:
                lines = [line.strip() for line in item.split("\n") if line.strip()]
                if not lines or "BREAKING NEWS" in lines[0] or "DAILY CONTENT" in lines[0]:
                    continue
                title = re.sub(r"\s*-\s*$", "", lines[0]).strip()
                url = next((line.split("Source URL:", 1)[1].strip() for line in lines if line.startswith("Source URL:")), "")
                if title and url:
                    history_entries.append({"headline": title, "url": url, "date": today})

        # Business Stories
        if len(sections) > 2:
            business_part = sections[2].split("---")[0]
            items = re.split(r"\n\s*\d+\.\s+", "\n" + business_part)
            for item in items:
                lines = [line.strip() for line in item.split("\n") if line.strip()]
                if not lines or "BUSINESS STORIES" in lines[0]:
                    continue
                title = re.sub(r"\s*-\s*$", "", lines[0]).strip()
                url = next((line.split("Source URL:", 1)[1].strip() for line in lines if line.startswith("Source URL:")), "")
                if title and url:
                    history_entries.append({"headline": title, "url": url, "date": today})

        # Evergreen Facts
        if len(sections) > 3:
            evergreen_part = sections[3].split("---")[0]
            items = re.split(r"\n\s*\d+\.\s+", "\n" + evergreen_part)
            for item in items:
                lines = [line.strip() for line in item.split("\n") if line.strip()]
                if not lines:
                    continue
                title = next((line.split(":", 1)[1].strip() for line in lines if line.startswith("Headline :") or line.startswith("Headline:")), "")
                url = next((line.split("Source URL:", 1)[1].strip() for line in lines if line.startswith("Source URL:")), "")
                if title and url:
                    history_entries.append({"headline": title, "url": url, "date": today})

        # Load history
        if os.path.exists(history_file):
            with open(history_file, "r", encoding="utf-8") as f:
                history = json.load(f)
        else:
            history = []
        
        # Deduplicate urls
        existing_urls = {h["url"].lower() for h in history}
        new_added = 0
        for entry in history_entries:
            if entry["url"].lower() not in existing_urls:
                history.append(entry)
                new_added += 1
                
        if new_added > 0:
            with open(history_file, "w", encoding="utf-8") as f:
                json.dump(history, f, indent=2, ensure_ascii=False)
            print(f"Successfully added {new_added} entries to history.json.")
        else:
            print("No new entries added to history.json (already exists).")
    except Exception as e:
        print(f"Warning: Failed to sync history.json automatically: {e}")

    # Distribute to dashboard & Notion
    print("Running distribution to update data.js and Notion...")
    try:
        dist_script = os.path.join(DIRECTORY, "distribute_report.py")
        subprocess.run([sys.executable, dist_script], check=True, cwd=DIRECTORY)
        print("Dashboard data.js successfully updated.")
    except Exception as e:
        print(f"ERROR: Failed to run distribute_report.py: {e}")

if __name__ == "__main__":
    main()
