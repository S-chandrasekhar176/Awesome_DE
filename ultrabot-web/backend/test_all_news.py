import asyncio
import os
import sys

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from news.news_engine import NewsEngine

async def main():
    config = {"news": {"enabled": True}}
    engine = NewsEngine(config)
    print("Running full scan across ALL sources...")
    items = await engine.run_full_scan()
    print(f"Fetched {len(items)} analysed news items.")
    
    # Let's count items per source
    from collections import Counter
    counts = Counter(item.get("source") for item in items)
    print("Items per source:", dict(counts))
    
    # Print 2 from each source to verify
    seen_sources = set()
    for item in items:
        source = item.get("source")
        # keep a counter in seen_sources dict to print up to 2
        if source not in seen_sources:
            seen_sources.add(source)
            print(f"\n--- Sample from {source} ---")
            print(f"Headline: {item.get('headline')}")
            print(f"Impact: {item.get('impact_level')} | Symbols: {item.get('symbols')}")
            
if __name__ == "__main__":
    asyncio.run(main())
