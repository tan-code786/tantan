import os
import json
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from playwright_stealth import Stealth # <--- V2.0 IMPORT FIX

# --- CONFIGURATION (Hidden from public) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SELLERS_ENV = os.environ.get("SELLERS")
STATE_FILE = "state.json"

def send_telegram_alert(new_product_name, seller_url):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    message = f"🚨 NEW INVENTORY ALERT!\nProduct: {new_product_name}\nLink: {seller_url}"
    
    # We added the disable feature here so Telegram stops attaching the picture!
    payload = {
        "chat_id": TELEGRAM_CHAT_ID, 
        "text": message,
        "disable_web_page_preview": True
    }
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def get_current_products(seller_url, page):
    try:
        page.goto(seller_url, wait_until="domcontentloaded")
        
        # We give the GitHub server up to 15 seconds to fetch the API data and render the products
        try:
            page.wait_for_selector('a[href*="products/view/"]', timeout=15000)
            page.wait_for_timeout(1000) # Small buffer
        except:
            print(f"  -> No products currently listed (or timeout) for {seller_url}")
        
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        page_title = soup.title.string if soup.title else 'No Title'
        print(f"  -> Loaded page: {page_title}")
        
        products_on_page = set()
        
        # SMART SELECTOR: Now looks for any link containing 'products/view/' to catch all variations
        product_links = soup.find_all('a', href=lambda href: href and 'products/view/' in href)
        
        for link in product_links:
            h3 = link.find('h3')
            if h3:
                title = h3.get_text(strip=True)
                if title:
                    products_on_page.add(title)
                
        return products_on_page
    except Exception as e:
        print(f"Error checking seller {seller_url}: {e}")
        return None

def main():
    print("Starting Tracker...")
    if not SELLERS_ENV:
        print("Error: No sellers found in secrets!")
        return

    sellers = [s.strip() for s in SELLERS_ENV.split(',') if s.strip()]
    
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            known_state = json.load(f)
        is_first_run = False
    else:
        known_state = {}
        is_first_run = True

    new_state = {}

    with sync_playwright() as p:
        # Launch browser with arguments that disable automated bot detection
        browser = p.chromium.launch(headless=True, args=["--disable-blink-features=AutomationControlled"])
        
        # Use a modern User-Agent and a standard 1080p screen size
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1920, "height": 1080}
        )
        
        page = context.new_page()
        
        # ACTIVATE STEALTH MODE: Patches the browser using the V2 API!
        Stealth().apply_stealth_sync(page) # <--- V2.0 COMMAND FIX

        for seller in sellers:
            print(f"Checking target: {seller}")
            current_products = get_current_products(seller, page)
            
            if current_products is None:
                new_state[seller] = known_state.get(seller, [])
                continue

            new_state[seller] = list(current_products)
            print(f"  -> Found {len(current_products)} products.")

            if not is_first_run and seller in known_state:
                known_products = set(known_state[seller])
                new_items = current_products - known_products
                
                for item in new_items:
                    print(f"  🚨 Detected new product: {item}")
                    send_telegram_alert(item, seller)

        browser.close()

    with open(STATE_FILE, "w") as f:
        json.dump(new_state, f)
    print("State updated successfully.")

if __name__ == "__main__":
    main()
