import os
import json
import requests
from bs4 import BeautifulSoup

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SELLERS_ENV = os.environ.get("SELLERS")
STATE_FILE = "state.json"

# This connects to the FlareSolverr container we added in main.yml
FLARESOLVERR_URL = "http://localhost:8191/v1"

def send_telegram_alert(new_product_name, seller_url):
    chat_ids = [chat_id.strip() for chat_id in TELEGRAM_CHAT_ID.split(',')]
    for chat_id in chat_ids:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        message = f"🚨 NEW INVENTORY ALERT!\nProduct: {new_product_name}\nLink: {seller_url}"
        payload = {"chat_id": chat_id, "text": message, "disable_web_page_preview": True}
        try:
            requests.post(url, json=payload)
        except Exception as e:
            print(f"Failed to send Telegram message to {chat_id}: {e}")

def get_current_products(seller_url):
    try:
        # Ask FlareSolverr to go fight Cloudflare for us
        payload = {
            "cmd": "request.get",
            "url": seller_url,
            "maxTimeout": 60000 # Give it up to 60 seconds to pass the challenge
        }
        headers = {"Content-Type": "application/json"}
        
        # Send the request to FlareSolverr
        response = requests.post(FLARESOLVERR_URL, headers=headers, json=payload, timeout=65)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("status") != "ok":
            print(f"  -> FlareSolverr failed: {data.get('message')}")
            return None
            
        # FlareSolverr successfully got the HTML!
        html = data.get("solution", {}).get("response", "")
        soup = BeautifulSoup(html, 'html.parser')
        
        page_title = soup.title.string if soup.title else 'No Title'
        print(f"  -> Loaded page: {page_title}")
        
        # Double check that Cloudflare isn't still blocking us
        if "Just a moment" in page_title or "Attention Required" in page_title:
            print("  -> Cloudflare is still blocking the page.")
            return None

        products_on_page = set()
        
        # SMART SELECTOR
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

    for seller in sellers:
        print(f"Checking target: {seller}")
        current_products = get_current_products(seller)
        
        if current_products is None:
            new_state[seller] = known_state.get(seller, [])
            continue

        new_state[seller] = list(current_products)
        print(f"  -> Found {len(current_products)} products.")

        if not is_first_run and seller in known_state:
            known_products = set(known_state[seller])
            new_items = set(current_products) - known_products
            
            for item in new_items:
                print(f"  🚨 Detected new product: {item}")
                send_telegram_alert(item, seller)

    with open(STATE_FILE, "w") as f:
        json.dump(new_state, f)
    print("State updated successfully.")

if __name__ == "__main__":
    main()
