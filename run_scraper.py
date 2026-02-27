import asyncio
import logging
from instagram_scraper import scrape_saved_posts

logging.basicConfig(level=logging.INFO)

async def main():
    print("Starting Instagram scraper for 10 posts...")
    downloaded = await scrape_saved_posts(10)
    print(f"Finished. Downloaded {len(downloaded)} files (including screenshots and carousels).")

if __name__ == "__main__":
    asyncio.run(main())
