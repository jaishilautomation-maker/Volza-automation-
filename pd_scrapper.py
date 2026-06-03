import time
import json
import os
import hashlib
import io
import random
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Google API Imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

# --- CONFIGURATION ---
SCOPES = ['https://www.googleapis.com/auth/drive']
TARGET_FILE_ID = '1EATFlMiGsOHQZhcNJY7nvgdGYjVBz3iU'

# --- 1. GOOGLE DRIVE AUTHENTICATION ---
def get_drive_service():
    creds = None
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())
    return build('drive', 'v3', credentials=creds)

service = get_drive_service()

# --- 2. DRIVE HELPERS ---
def load_from_drive():
    print(f"📡 Syncing with Google Drive (ID: {TARGET_FILE_ID})...")
    try:
        request = service.files().get_media(fileId=TARGET_FILE_ID)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        fh.seek(0)
        return json.loads(fh.read().decode('utf-8'))
    except Exception as e:
        print(f"❌ Error loading cloud file: {e}")
        return []

def save_to_drive(data):
    json_data = json.dumps(data, indent=4, ensure_ascii=False).encode('utf-8')
    fh = io.BytesIO(json_data)
    media = MediaIoBaseUpload(fh, mimetype='application/json', resumable=True)
    try:
        service.files().update(fileId=TARGET_FILE_ID, media_body=media).execute()
        return True
    except Exception as e:
        print(f"❌ Upload failed: {e}")
        return False

# --- 3. SCRAPER LOGIC ---
def get_row_hash(row_list):
    return hashlib.md5("".join(map(str, row_list)).encode('utf-8')).hexdigest()

def handle_popups(driver):
    """Checks for the 'Switch to Partial View' button and clicks it if found."""
    try:
        # Looking for the blue 'Switch to Partial View' button from your screenshot
        partial_view_btn = driver.find_elements(By.XPATH, "//button[contains(text(), 'Switch to Partial View')]")
        if partial_view_btn:
            print("⚠️ Pagination Limit hit! Switching to Partial View...")
            driver.execute_script("arguments[0].click();", partial_view_btn[0])
            time.sleep(3)
    except:
        pass

def scrape_pages(driver, master_data, seen_hashes):
    page = 1
    while True:
        try:
            handle_popups(driver)
            print(f"    ∟ Scanning Page {page}...")
            
            # Wait for table
            WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.TAG_NAME, "tr")))
            
            # Scroll down slowly to mimic human browsing
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
            time.sleep(random.uniform(2, 4))
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(random.uniform(2, 3))
            
            rows = driver.find_elements(By.TAG_NAME, "tr")
            new_rows_count = 0
            
            for r in rows:
                cells = r.find_elements(By.TAG_NAME, "td")
                # Detect if data is 'Locked' (Partial View mode)
                row_text = r.text
                if "Click here to view" in row_text:
                    print("🚨 WARNING: Data is LOCKED in Partial View. Names will be missing.")

                data = [c.text.replace('copy', '').strip() for c in cells if c.text.strip()]
                if data:
                    row_id = get_row_hash(data)
                    if row_id not in seen_hashes:
                        master_data.append(data)
                        seen_hashes.add(row_id)
                        new_rows_count += 1
            
            if new_rows_count > 0:
                save_to_drive(master_data)
                print(f"💾 Cloud Updated: +{new_rows_count} rows. Total: {len(master_data)}")
            else:
                print("📝 No new unique rows found on this page.")

            # Pagination Logic
            try:
                next_li = driver.find_element(By.XPATH, "//li[contains(@class, 'ant-pagination-next')]")
                if "ant-pagination-disabled" in next_li.get_attribute("class"):
                    print("🏁 Reached the end of available pages.")
                    break
                
                btn = next_li.find_element(By.TAG_NAME, "button")
                driver.execute_script("arguments[0].click();", btn)
                page += 1
                # Randomized delay to prevent being flagged as a bot
                time.sleep(random.uniform(5, 9))
            except:
                print("🛑 Could not find the 'Next' button. Ending session.")
                break

        except Exception as e:
            print(f"⚠️ Scraping interrupted: {e}")
            break

# --- 4. RUNNER ---
def main():
    master_data = load_from_drive()
    seen_hashes = {get_row_hash(row) for row in master_data}
    print(f"✅ Ready: Loaded {len(master_data)} existing rows.")

    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = uc.Chrome(options=options
                       ,version_main=148)
    
    try:
        driver.get("https://app.volza.com/workspace/search")
        print("\n🚀 SCRAPER READY")
        print("1. Log in.")
        print("2. IMPORTANT: Use filters to keep results under 2,000 if possible.")
        input("3. Once the table is visible, press [ENTER] here...")

        scrape_pages(driver, master_data, seen_hashes)
        print(f"\n✨ DONE. Final Count: {len(master_data)}")

    finally:
        driver.quit()

if __name__ == "__main__":
    main()