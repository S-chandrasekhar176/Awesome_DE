import httpx
from bs4 import BeautifulSoup

def test_google_finance():
    print("--- Google Finance ---")
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    r = httpx.get('https://www.google.com/finance/', headers=headers, follow_redirects=True)
    soup = BeautifulSoup(r.text, 'html.parser')
    for a in soup.find_all('a'):
        href = a.get('href') or ''
        if '/quote/' in href:
            text = a.get_text(strip=True)
            if '%' in text:
                print(f"{href} : {text[:80].encode('ascii', 'ignore').decode()}")

def test_nse():
    print("--- NSE ---")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
    }
    # For NSE, we typically need to get the main page first to get cookies
    try:
        with httpx.Client(headers=headers, timeout=10) as client:
            client.get("https://www.nseindia.com/")
            r = client.get("https://www.nseindia.com/api/corporate-announcements?index=equities")
            print("NSE API Corporate Announcements Status:", r.status_code)
            if r.status_code == 200:
                print(r.text[:200])
    except Exception as e:
        print("NSE Error:", e)

if __name__ == "__main__":
    test_google_finance()
    test_nse()
