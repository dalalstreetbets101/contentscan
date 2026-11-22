import os
import re
import json
import urllib.request
import urllib.error
from datetime import datetime

# Load configurations from .env manually to avoid python-dotenv dependency
def load_env():
    env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                if "=" in line and not line.strip().startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

load_env()


GOOGLE_CREDENTIALS_JSON = os.getenv("GOOGLE_CREDENTIALS_JSON", "google_credentials.json")
GOOGLE_DOCS_FOLDER_ID = os.getenv("GOOGLE_DOCS_FOLDER_ID")
GOOGLE_SHEETS_SPREADSHEET_ID = os.getenv("GOOGLE_SHEETS_SPREADSHEET_ID")
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
NOTION_DATABASE_ID = os.getenv("NOTION_DATABASE_ID")

def parse_report(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Report file not found: {file_path}")
        
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Extract Date
    date_match = re.search(r'Date:\s*(.*)', content)
    report_date = date_match.group(1).strip() if date_match else datetime.today().strftime('%Y-%m-%d')
    
    # Extract Top Priority Post Title (handles headers with or without markdown styling)
    priority_section = re.search(r"(?:##\s*)?TODAY'S TOP 3 PRIORITY POSTS\s*(.*)", content, re.IGNORECASE | re.DOTALL)
    top_story_title = ""
    if priority_section:
        lines = [l.strip() for l in priority_section.group(1).strip().split('\n') if l.strip()]
        if lines:
            m = re.search(r'\d+\.\s+(?:\*\*)?(.*?)(?:\*\*)?(?:\s*\(|$)', lines[0])
            if m:
                top_story_title = m.group(1).strip()
            else:
                top_story_title = re.sub(r'^\d+\.\s*', '', lines[0]).replace('**', '').strip()
                
    # Find details of the top story in the report
    # We can split on any line starting with optionally "### " followed by a number, dot, and space
    blocks = re.split(r'\n(?=(?:###\s*)?\s*\d+\.\s+)', content)
    top_story_category = "General"
    top_story_virality = "90" # Default fallback
    
    for block in blocks:
        lines = block.split('\n')
        if not lines or not lines[0].strip():
            continue
        title_line = lines[0].strip()
        # Clean title (remove numbers, dots, and trailing hyphens)
        clean_title = re.sub(r'^(?:###\s*)?\s*\d+\.\s*', '', title_line).strip()
        clean_title = re.sub(r'\s*-\s*$', '', clean_title).strip()
        
        is_match = False
        headline_val = ""
        category_val = ""
        virality_val = ""
        
        for line in lines[1:]:
            line = line.strip()
            if line.startswith("Category:"):
                category_val = line.split(":", 1)[1].strip()
            elif line.startswith("Headline :") or line.startswith("Headline:"):
                headline_val = line.split(":", 1)[1].strip()
            elif line.startswith("Virality Score:"):
                virality_val = line.split(":", 1)[1].strip()
                
        # Match topic or headline
        if top_story_title and clean_title:
            t_title_lower = top_story_title.lower()
            c_title_lower = clean_title.lower()
            h_val_lower = headline_val.lower() if headline_val else ""
            
            if (c_title_lower in t_title_lower or 
                t_title_lower in c_title_lower or 
                (h_val_lower and h_val_lower in t_title_lower) or 
                (h_val_lower and t_title_lower in h_val_lower)):
                is_match = True
            
        if is_match:
            if category_val:
                top_story_category = category_val
            else:
                # Deduce category based on the section of the block
                content_before = content.split(block)[0]
                if "TOP 5 BREAKING NEWS" in content_before:
                    top_story_category = "Breaking News"
                elif "TOP 5 BUSINESS STORIES" in content_before:
                    top_story_category = "Business Stories"
                elif "TOP 5 EVERGREEN FACTS" in content_before:
                    top_story_category = "Evergreen Facts"
                
            if virality_val:
                top_story_virality = virality_val
            break
            
    return {
        "date": report_date,
        "top_story": top_story_title,
        "virality": top_story_virality,
        "category": top_story_category,
        "full_content": content
    }

def markdown_to_html(md_text):
    html = md_text.replace('\r\n', '\n')
    
    # Convert headings
    html = re.sub(r'^#\s+(.*)', r'<h1>\1</h1>', html, flags=re.MULTILINE)
    html = re.sub(r'^##\s+(.*)', r'<h2>\1</h2>', html, flags=re.MULTILINE)
    html = re.sub(r'^###\s+(.*)', r'<h3>\1</h3>', html, flags=re.MULTILINE)
    
    # Convert bold
    html = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', html)
    
    # Convert dividers
    html = re.sub(r'^---$', r'<hr/>', html, flags=re.MULTILINE)
    
    # Convert lists
    html = re.sub(r'^\d+\.\s+(.*)', r'<li>\1</li>', html, flags=re.MULTILINE)
    
    # Wrap in basic HTML structure
    return f"<html><head><meta charset='utf-8'></head><body>{html}</body></html>"

def upload_to_google_docs(credentials_file, folder_id, report_date, md_content):
    if not os.path.exists(credentials_file):
        print(f"Skipping Google Docs upload: credentials file '{credentials_file}' not found.")
        return None
        
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        from googleapiclient.http import MediaInMemoryUpload
        
        scopes = ['https://www.googleapis.com/auth/drive']
        creds = service_account.Credentials.from_service_account_file(credentials_file, scopes=scopes)
        drive_service = build('drive', 'v3', credentials=creds)
        
        html_content = markdown_to_html(md_content)
        
        file_metadata = {
            'name': f'DSB-Daily-{report_date}',
            'mimeType': 'application/vnd.google-apps.document'
        }
        if folder_id:
            file_metadata['parents'] = [folder_id]
            
        media = MediaInMemoryUpload(html_content.encode('utf-8'), mimetype='text/html', resumable=True)
        file = drive_service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        
        doc_id = file.get('id')
        print(f"Successfully uploaded to Google Docs. File ID: {doc_id}")
        return doc_id
    except Exception as e:
        print(f"Error uploading to Google Docs: {e}")
        return None

def append_to_google_sheets(credentials_file, spreadsheet_id, row_data):
    if not os.path.exists(credentials_file):
        print(f"Skipping Google Sheets append: credentials file '{credentials_file}' not found.")
        return
        
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        
        scopes = ['https://www.googleapis.com/auth/spreadsheets']
        creds = service_account.Credentials.from_service_account_file(credentials_file, scopes=scopes)
        sheets_service = build('sheets', 'v4', credentials=creds)
        
        body = {'values': [row_data]}
        result = sheets_service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range='A1',
            valueInputOption='USER_ENTERED',
            body=body
        ).execute()
        print(f"Successfully appended summary row to Sheets spreadsheet.")
    except Exception as e:
        print(f"Error appending to Google Sheets: {e}")


def build_dsb_notion_blocks(content):
    blocks = []
    lines = content.split("\n")
    
    # Header title banner
    blocks.append({
        "object": "block",
        "type": "paragraph",
        "paragraph": {
            "rich_text": [
                {"type": "text", "text": {"content": "DALAL STREET BETS — DAILY BRIEFING\n"}, "annotations": {"bold": True, "color": "orange"}},
                {"type": "text", "text": {"content": "Content Discovery & Viral Opportunity Report"}, "annotations": {"italic": True, "color": "gray"}}
            ]
        }
    })
    blocks.append({"object": "block", "type": "divider", "divider": {}})
    
    i = 0
    in_priority = False
    
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
            
        # Section Headings
        if "TOP 5 BREAKING NEWS" in line:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "🔥 TOP 5 BREAKING NEWS"}, "annotations": {"bold": True, "color": "red"}}]
                }
            })
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue
            
        if "TOP 5 BUSINESS STORIES" in line:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "💼 TOP 5 BUSINESS STORIES"}, "annotations": {"bold": True, "color": "blue"}}]
                }
            })
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue
            
        if "TOP 5 EVERGREEN FACTS" in line:
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "💡 TOP 5 EVERGREEN FACTS"}, "annotations": {"bold": True, "color": "green"}}]
                }
            })
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue
            
        if "TOP 3 PRIORITY POSTS" in line or "PRIORITY POSTS" in line:
            in_priority = True
            blocks.append({
                "object": "block",
                "type": "heading_2",
                "heading_2": {
                    "rich_text": [{"type": "text", "text": {"content": "⭐ TODAY'S TOP PRIORITY POSTS"}, "annotations": {"bold": True, "color": "yellow"}}]
                }
            })
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue
            
        if in_priority and re.match(r"^\d+\.\s*", line):
            text = re.sub(r"^\d+\.\s*", "", line).strip()
            blocks.append({
                "object": "block",
                "type": "numbered_list_item",
                "numbered_list_item": {
                    "rich_text": [{"type": "text", "text": {"content": text}, "annotations": {"bold": True}}]
                }
            })
            i += 1
            continue

        # Story Headline (e.g. "1. Headline -" or "1. Topic-")
        if re.match(r"^\d+\.\s+", line):
            clean_title = re.sub(r"^\d+\.\s+", "", line).strip()
            num_match = re.match(r"^(\d+)\.", line)
            num_prefix = f"{num_match.group(1)}. " if num_match else ""
            clean_title = re.sub(r"\s*-\s*$", "", clean_title).strip()
            
            blocks.append({
                "object": "block",
                "type": "heading_3",
                "heading_3": {
                    "rich_text": [
                        {"type": "text", "text": {"content": f"{num_prefix}{clean_title}"}, "annotations": {"bold": True}}
                    ]
                }
            })
            i += 1
            continue

        # Evergreen Headline : field
        if line.startswith("Headline :") or line.startswith("Headline:"):
            h_val = line.split(":", 1)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Headline: "}, "annotations": {"bold": True, "color": "blue"}},
                        {"type": "text", "text": {"content": h_val}, "annotations": {"bold": True}}
                    ]
                }
            })
            i += 1
            continue

        # Category
        if line.startswith("Category:"):
            cat_val = line.split("Category:", 1)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Category: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f" {cat_val.upper()} "}, "annotations": {"code": True, "color": "orange"}}
                    ]
                }
            })
            i += 1
            continue

        # Source
        if line.startswith("Source:"):
            src_val = line.split("Source:", 1)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Source: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": src_val}, "annotations": {"bold": True}}
                    ]
                }
            })
            i += 1
            continue

        # Why it matters
        if line.startswith("Why it matters:"):
            val = line.split("Why it matters:", 1)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "WHY IT MATTERS:\n"}, "annotations": {"bold": True, "color": "gray"}},
                        {"type": "text", "text": {"content": val}}
                    ]
                }
            })
            i += 1
            continue

        # 1 Line Summary
        if line.lower().startswith("1 line summary:"):
            val = re.split(r"1 line summary:", line, flags=re.IGNORECASE)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "1 LINE SUMMARY:\n"}, "annotations": {"bold": True, "color": "gray"}},
                        {"type": "text", "text": {"content": val}}
                    ]
                }
            })
            i += 1
            continue

        # Why people care (for evergreen facts)
        if line.lower().startswith("why people care:"):
            val = line.split(":", 1)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "WHY PEOPLE CARE:\n"}, "annotations": {"bold": True, "color": "gray"}},
                        {"type": "text", "text": {"content": val}}
                    ]
                }
            })
            i += 1
            continue

        # Caption Hook
        if line.startswith("Caption Hook:"):
            val = line.split("Caption Hook:", 1)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "CAPTION HOOK:\n"}, "annotations": {"bold": True, "color": "gray"}},
                        {"type": "text", "text": {"content": val}}
                    ]
                }
            })
            i += 1
            continue

        # Suggested Thumbnail
        if line.startswith("Suggested Thumbnail:"):
            val = line.split("Suggested Thumbnail:", 1)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Thumbnail: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f" {val.upper()} "}, "annotations": {"code": True, "color": "orange"}}
                    ]
                }
            })
            i += 1
            continue

        # Virality Score
        if line.startswith("Virality Score:"):
            val = line.split("Virality Score:", 1)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "Virality Score: "}, "annotations": {"bold": True}},
                        {"type": "text", "text": {"content": f"{val}/100"}, "annotations": {"bold": True, "color": "red"}}
                    ]
                }
            })
            i += 1
            continue

        # ENGAGEMENT TRIGGER
        if line.startswith("ENGAGEMENT TRIGGER:"):
            val = line.split("ENGAGEMENT TRIGGER:", 1)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "ENGAGEMENT TRIGGER:\n"}, "annotations": {"bold": True, "color": "orange"}},
                        {"type": "text", "text": {"content": val}}
                    ]
                }
            })
            i += 1
            continue

        # QUESTION
        if line.startswith("QUESTION:"):
            val = line.split("QUESTION:", 1)[1].strip()
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [
                        {"type": "text", "text": {"content": "QUESTION:\n"}, "annotations": {"bold": True, "color": "blue"}},
                        {"type": "text", "text": {"content": val}}
                    ]
                }
            })
            i += 1
            continue

        # Source URL
        if line.startswith("Source URL:"):
            url_val = line.split("Source URL:", 1)[1].strip()
            if not url_val and i + 1 < len(lines):
                next_l = lines[i+1].strip()
                if next_l.startswith("http"):
                    url_val = next_l
                    i += 1
            if url_val.startswith("http"):
                blocks.append({
                    "object": "block",
                    "type": "paragraph",
                    "paragraph": {
                        "rich_text": [
                            {"type": "text", "text": {"content": "🔗 "}},
                            {
                                "type": "text",
                                "text": {"content": "VERIFY & READ SOURCE", "link": {"url": url_val}},
                                "annotations": {"bold": True, "underline": True, "color": "blue"}
                            }
                        ]
                    }
                })
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # General horizontal divider
        if line == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        # Fallback paragraph
        if not line.startswith("DAILY CONTENT REPORT") and not line.startswith("Date:"):
            blocks.append({
                "object": "block",
                "type": "paragraph",
                "paragraph": {
                    "rich_text": [{"type": "text", "text": {"content": line}}]
                }
            })
        i += 1

    return blocks


def upload_to_notion(token, database_id, data):
    if not token or not database_id:
        print("Skipping Notion upload: NOTION_TOKEN or NOTION_DATABASE_ID not configured.")
        return None
        
    url = "https://api.notion.com/v1/pages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Notion-Version": "2022-06-28",
        "Content-Type": "application/json"
    }
    
    # 1. Build rich DSB Command styled Notion blocks (all 15 stories, headers, badges)
    blocks = build_dsb_notion_blocks(data["full_content"])
    print(f"Generated {len(blocks)} formatted Notion blocks for the report.")
    
    # 2. Fetch database schema dynamically
    db_url = f"https://api.notion.com/v1/databases/{database_id}"
    db_req = urllib.request.Request(db_url, headers=headers, method="GET")
    title_property_name = "Report "
    has_category = False
    category_type = "rich_text"
    has_top_story = False
    has_date = False
    has_source_project = False
    sp_type = "select"
    has_virality = False
    
    print("Querying Notion database properties to match schema...")
    try:
        with urllib.request.urlopen(db_req, timeout=15) as db_response:
            db_schema = json.loads(db_response.read().decode("utf-8"))
            properties = db_schema.get("properties", {})
            for prop_name, prop_val in properties.items():
                p_type = prop_val.get("type")
                if p_type == "title":
                    title_property_name = prop_name
                elif prop_name.lower() == "category":
                    has_category = True
                    category_type = p_type
                elif prop_name.lower() == "virality":
                    has_virality = True
                elif prop_name.lower() == "source project":
                    has_source_project = True
                    sp_type = p_type
                elif prop_name.lower() == "top story":
                    has_top_story = True
                elif prop_name.lower() == "date":
                    has_date = True
            print(f"Detected Title Column: '{title_property_name}'")
    except Exception as e:
        print(f"Warning: Could not fetch database schema dynamically ({e}). Using default properties.")

    # 2.5 Check if report page for this date already exists
    if has_date:
        try:
            q_url = f"https://api.notion.com/v1/databases/{database_id}/query"
            q_payload = {
                "filter": {
                    "property": "Date",
                    "date": {
                        "equals": data["date"]
                    }
                }
            }
            q_req = urllib.request.Request(q_url, data=json.dumps(q_payload).encode("utf-8"), headers=headers, method="POST")
            with urllib.request.urlopen(q_req, timeout=15) as q_resp:
                q_data = json.loads(q_resp.read().decode("utf-8"))
                existing_pages = q_data.get("results", [])
                if existing_pages:
                    existing_id = existing_pages[0]["id"]
                    print(f"Page for {data['date']} exists (ID: {existing_id}). Replacing with complete, fully styled report...")
                    arc_url = f"https://api.notion.com/v1/pages/{existing_id}"
                    arc_req = urllib.request.Request(arc_url, data=json.dumps({"archived": True}).encode("utf-8"), headers=headers, method="PATCH")
                    try:
                        urllib.request.urlopen(arc_req, timeout=15)
                    except Exception:
                        pass
        except Exception as q_err:
            print(f"Notice: Could not query existing pages ({q_err}). Proceeding with upload.")

    # 3. Build dynamic metadata properties payload
    properties_payload = {
        title_property_name: {
            "title": [
                {
                    "text": {
                        "content": f"DSB Daily Report - {data['date']}"
                    }
                }
            ]
        }
    }
    
    if has_date:
        properties_payload["Date"] = {
            "date": {
                "start": data["date"]
            }
        }
        
    if has_top_story:
        properties_payload["Top Story"] = {
            "rich_text": [
                {
                    "text": {
                        "content": data["top_story"][:2000] if data["top_story"] else ""
                    }
                }
            ]
        }
        
    if has_virality:
        try:
            virality_num = int(data["virality"])
            properties_payload["Virality"] = {
                "number": virality_num
            }
        except Exception:
            pass
            
    if has_category:
        if category_type == "select":
            properties_payload["Category"] = {
                "select": {
                    "name": data["category"] if data["category"] else "General"
                }
            }
        elif category_type == "rich_text":
            properties_payload["Category"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": data["category"] if data["category"] else "General"
                        }
                    }
                ]
            }
            
    if has_source_project:
        if sp_type == "rich_text":
            properties_payload["Source Project"] = {
                "rich_text": [
                    {
                        "text": {
                            "content": "Antigravity"
                        }
                    }
                ]
            }
        else:
            properties_payload["Source Project"] = {
                "select": {
                    "name": "Antigravity"
                }
            }
            
    # First batch of up to 100 blocks
    first_chunk = blocks[:100]
    payload = {
        "parent": { "database_id": database_id },
        "properties": properties_payload,
        "children": first_chunk
    }
    
    # 4. Create Page with first chunk
    print(f"Uploading daily report page to Notion database (ID: {database_id})...")
    created_page_id = None
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            res_data = json.loads(response.read().decode("utf-8"))
            created_page_id = res_data.get("id")
            print(f"Successfully created Notion page! Page ID: {created_page_id}")
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"Notion API error (HTTP {e.code}): {err_body}")
        if e.code == 400:
            print("Retrying with simplified schema...")
            fallback_payload = {
                "parent": { "database_id": database_id },
                "properties": {
                    title_property_name: {
                        "title": [{"text": {"content": f"DSB Daily Report - {data['date']}"}}]
                    }
                },
                "children": first_chunk
            }
            try:
                fallback_req = urllib.request.Request(url, data=json.dumps(fallback_payload).encode("utf-8"), headers=headers, method="POST")
                with urllib.request.urlopen(fallback_req, timeout=30) as fb_response:
                    res_data = json.loads(fb_response.read().decode("utf-8"))
                    created_page_id = res_data.get("id")
                    print(f"Successfully uploaded to Notion using fallback! Page ID: {created_page_id}")
            except Exception as fb_err:
                print(f"Fallback failed: {fb_err}")
    except Exception as e:
        print(f"Failed to connect to Notion API: {e}")

    # 5. Append all remaining chunks of blocks (beyond 100 blocks)
    if created_page_id and len(blocks) > 100:
        append_url = f"https://api.notion.com/v1/blocks/{created_page_id}/children"
        for idx in range(100, len(blocks), 100):
            chunk = blocks[idx : idx + 100]
            print(f"Appending remaining blocks chunk {idx} to {idx + len(chunk)} ({len(chunk)} blocks)...")
            patch_payload = {"children": chunk}
            try:
                patch_req = urllib.request.Request(append_url, data=json.dumps(patch_payload).encode("utf-8"), headers=headers, method="PATCH")
                with urllib.request.urlopen(patch_req, timeout=30) as p_resp:
                    pass
            except Exception as p_err:
                print(f"Warning: Failed to append blocks chunk {idx}-{idx+len(chunk)}: {p_err}")
                
        print(f"All {len(blocks)} blocks successfully uploaded to Notion page!")
        
    return created_page_id


def main():
    report_file = os.path.join("reports", f"report_{datetime.today().strftime('%Y-%m-%d')}.md")
    # Fallback to local run check if report file doesn't exist
    if not os.path.exists(report_file):
        # Scan folder for any report file
        reports_dir = "reports"
        if os.path.exists(reports_dir):
            files = [f for f in os.listdir(reports_dir) if f.startswith("report_") and f.endswith(".md")]
            if files:
                files.sort(reverse=True)
                report_file = os.path.join(reports_dir, files[0])
                
    if not os.path.exists(report_file):
        print(f"No report file found to distribute.")
        return
        
    print(f"Parsing report for distribution: {report_file}")
    data = parse_report(report_file)
    
    # 1. Google Docs Upload
    upload_to_google_docs(GOOGLE_CREDENTIALS_JSON, GOOGLE_DOCS_FOLDER_ID, data["date"], data["full_content"])
    
    # 2. Google Sheets Logging
    sheets_row = [data["date"], data["top_story"], data["virality"], data["category"]]
    append_to_google_sheets(GOOGLE_CREDENTIALS_JSON, GOOGLE_SHEETS_SPREADSHEET_ID, sheets_row)
    
    # 3. Notion Upload
    if NOTION_TOKEN and NOTION_DATABASE_ID:
        upload_to_notion(NOTION_TOKEN, NOTION_DATABASE_ID, data)
    
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
