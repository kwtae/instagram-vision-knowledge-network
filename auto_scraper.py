import asyncio
import time
import random
import logging
from instagram_scraper import scrape_saved_posts

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("mcp_vision_server.auto_scraper")

async def auto_scrape(batch_size=50, max_batches=10000):
    logger.info("Starting automated Instagram scraper.")
    logger.info(f"Configuration: {batch_size} items per batch.")
    
    max_retries = 10
    consecutive_zeros = 0
    
    for i in range(max_batches):
        logger.info(f"--- [ Executing Batch {i+1} ] ---")
        
        # 스크래핑 수행
        downloaded = await scrape_saved_posts(batch_size)
        
        if not downloaded or len(downloaded) == 0:
            if consecutive_zeros < max_retries:
                consecutive_zeros += 1
                logger.warning(f"No new items found. Retrying in 5 minutes (Attempt {consecutive_zeros}/{max_retries})...")
                await asyncio.sleep(300)
                continue
            else:
                logger.info("No items found after maximum retries. Terminating the scraper process.")
                break
        
        consecutive_zeros = 0
            
        logger.info(f"Batch {i+1} completed. Downloaded {len(downloaded)} assets.")
        
        if i < max_batches - 1:
            # Short sleep implementation: ~2 seconds
            sleep_sec = random.randint(1, 3)
            logger.info(f"Initiating short sleep for {sleep_sec} seconds...")
            await asyncio.sleep(sleep_sec)
            
    logger.info("Automated scraper process concluded.")

if __name__ == "__main__":
    try:
        asyncio.run(auto_scrape(batch_size=50))
    except KeyboardInterrupt:
        logger.info("Process terminated by user.")
