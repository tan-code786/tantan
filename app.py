import os
import json
import time
import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

# --- CONFIGURATION (Hidden from public) ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SELLERS_ENV = os.environ.get("SELLERS")
STATE_FILE = "state.json"

def send_telegram_alert(new_product_name, seller_url):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    message = f"🚨 NEW INVENTORY ALERT!\nProduct: {new_product_name}\nLink: {seller_url}"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Failed to send Telegram message: {e}")

def get_current_products(seller_url, page):
    try:
        # Navigate to the seller page
        page.goto(seller_url, wait_until="domcontentloaded")
        
        # WAIT 3 SECONDS: Give the website's JavaScript time to load the products
        page.wait_for_timeout(3000) 
        
        # Get the fully rendered HTML (exactly as a human sees it)
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        page_title = soup.title.string if soup.title else 'No Title'
        print(f"Loaded page: {page_title}")
        
        products_on_page = set()
        
        # Using the exact HTML class you found in the DevTools!
        product_elements = soup.find_all(class_='text-[14px] leading-[120%] font-semibold text-textBlack mb-[10px] line-clamp-2 h-[34px]')
        
        for element in product_elements:
            title = element.get_text(strip=True)
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

    # Start the invisible Playwright browser
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
        page = context.new_page()

        for seller in sellers:
            print(f"Checking target: {seller}")
            current_products = get_current_products(seller, page)
            
            if current_products is None:
                new_state[seller] = known_state.get(seller, [])
                continue

            new_state[seller] = list(current_products)

            if not is_first_run and seller in known_state:
                known_products = set(known_state[seller])
                new_items = current_products - known_products
                
                for item in new_items:
                    print(f"Detected new product: {item}")
                    send_telegram_alert(item, seller)

        browser.close()

    with open(STATE_FILE, "w") as f:
        json.dump(new_state, f)
    print("State updated successfully.")

if __name__ == "__main__":
    main()
