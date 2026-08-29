import os
import json
import requests
from bs4 import BeautifulSoup
import concurrent.futures

# --- CONFIGURATION ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
SELLERS_ENV = os.environ.get("SELLERS")
STATE_FILE = "state.json"

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
        payload = {
            "cmd": "request.get",
            "url": seller_url,
            "maxTimeout": 60000 
        }
        headers = {"Content-Type": "application/json"}
        
        response = requests.post(FLARESOLVERR_URL, headers=headers, json=payload, timeout=65)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get("status") != "ok":
            print(f"  -> FlareSolverr failed for {seller_url}: {data.get('message')}")
            return None
            
        html = data.get("solution", {}).get("response", "")
        soup = BeautifulSoup(html, 'html.parser')
        
        page_title = soup.title.string if soup.title else 'No Title'
        print(f"  -> Loaded: {page_title} | ({seller_url})")
        
        if "Just a moment" in page_title or "Attention Required" in page_title:
            print(f"  -> Cloudflare is still blocking {seller_url}.")
            return None

        products_on_page = set()
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

def process_seller(seller):
    """This function is run by the worker threads"""
    print(f"Checking target: {seller}")
    products = get_current_products(seller)
    return seller, products

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

    # MULTITHREADING: Run 3 sellers at the exact same time!
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        # Send all sellers to the worker pool
        futures = {executor.submit(process_seller, seller): seller for seller in sellers}
        
        # As soon as a seller finishes, process its results
        for future in concurrent.futures.as_completed(futures):
            seller = futures[future]
            try:
                current_products = future.result()
            except Exception as e:
                print(f"Thread error for {seller}: {e}")
                current_products = None
            
            if current_products is None:
                new_state[seller] = known_state.get(seller, [])
                continue

            new_state[seller] = list(current_products)
            print(f"  -> Found {len(current_products)} products for {seller}")

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
