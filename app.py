import os
import json
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
        # 1. Navigate to the seller page
        page.goto(seller_url, wait_until="domcontentloaded")
        
        # 2. SUPERPOWER: Wait specifically for a product link to appear on screen!
        # If the seller is completely out of stock, it waits 5 seconds, gives up, and safely returns 0 items.
        try:
            page.wait_for_selector('a[href*="/en/products/view/"]', timeout=5000)
            # Add a tiny 1-second buffer just in case multiple products are loading in one by one
            page.wait_for_timeout(1000)
        except:
            print(f"  -> No products currently listed (or timeout) for {seller_url}")
        
        # 3. Grab the fully loaded HTML 
        html = page.content()
        soup = BeautifulSoup(html, 'html.parser')
        
        page_title = soup.title.string if soup.title else 'No Title'
        print(f"  -> Loaded page: {page_title}")
        
        products_on_page = set()
        
        # 4. SMART SELECTOR: Find all links that contain "/en/products/view/"
        product_links = soup.find_all('a', href=lambda href: href and '/en/products/view/' in href)
        
        for link in product_links:
            # The product name is always inside an <h3> tag within this link
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

    # Split the secret by commas to get a list of all your sellers
    sellers = [s.strip() for s in SELLERS_ENV.split(',') if s.strip()]
    
    # Load memory of all sellers
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
        # We give it a standard Windows/Chrome user-agent to look like a real human
        context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36")
        page = context.new_page()

        for seller in sellers:
            print(f"Checking target: {seller}")
            current_products = get_current_products(seller, page)
            
            if current_products is None:
                # If page fails to load completely, keep old memory so we don't mess up the data
                new_state[seller] = known_state.get(seller, [])
                continue

            # Save current products to the new memory
            new_state[seller] = list(current_products)
            print(f"  -> Found {len(current_products)} products.")

            # Check for new items (only if it's not the very first time the script is running)
            if not is_first_run and seller in known_state:
                known_products = set(known_state[seller])
                new_items = current_products - known_products
                
                for item in new_items:
                    print(f"  🚨 Detected new product: {item}")
                    send_telegram_alert(item, seller)

        browser.close()

    # Save the updated memory back to the JSON file for the next 5-minute check
    with open(STATE_FILE, "w") as f:
        json.dump(new_state, f)
    print("State updated successfully.")

if __name__ == "__main__":
    main()
