import logging
import time
from file_manager import scan_directory_once

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_vision_server.run_scan")

def start():
    logger.info("Starting local file sync into ChromaDB...")
    start_t = time.time()
    res = scan_directory_once("./watched_files")
    end_t = time.time()
    logger.info(f"Finished parsing in {end_t - start_t:.2f} seconds. Results: {res}")

if __name__ == "__main__":
    start()
