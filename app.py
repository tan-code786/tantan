import os
import requests
from bs4 import BeautifulSoup
import json

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

def get_current_products(seller_url):
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
    }
    try:
        response = requests.get(seller_url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # NOTE: Remember to update 'PRODUCT_TITLE_CLASS' to the real BuySellVouchers class!
        product_elements = soup.find_all(class_='text-[14px] leading-[120%] font-semibold text-textBlack mb-[10px] line-clamp-2 h-[34px]')
        
        products_on_page = set()
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

    # Check each seller one by one
    for seller in sellers:
        print(f"Checking target: {seller}")
        current_products = get_current_products(seller)
        
        if current_products is None:
            # If page fails to load, keep old memory so we don't mess up the data
            new_state[seller] = known_state.get(seller, [])
            continue

        # Save current products to the new memory
        new_state[seller] = list(current_products)

        # If it's not the first time running, compare and alert!
        if not is_first_run and seller in known_state:
            known_products = set(known_state[seller])
            new_items = current_products - known_products
            
            for item in new_items:
                print(f"Detected new product: {item}")
                send_telegram_alert(item, seller)

    # Save the updated memory back to the JSON file
    with open(STATE_FILE, "w") as f:
        json.dump(new_state, f)
    print("State updated successfully.")

if __name__ == "__main__":
    main()
