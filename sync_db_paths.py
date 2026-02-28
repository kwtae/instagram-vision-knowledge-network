import os
import logging
from db_manager import db

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("sync_paths")

def sync_paths():
    logger.info("Starting ChromaDB path synchronization...")
    
    # Get all entries from the DB
    # include metadatas and documents
    results = db.collection.get(include=["metadatas", "documents"])
    ids = results.get("ids", [])
    metas = results.get("metadatas", [])
    
    if not ids:
        logger.info("No entries found in database.")
        return

    updated_count = 0
    missing_count = 0
    already_correct = 0
    
    for i in range(len(ids)):
        doc_id = ids[i]
        meta = metas[i]
        old_path = meta.get("filepath", "")
        
        if not old_path:
            logger.warning(f"No filepath for ID: {doc_id}")
            continue
            
        # Check if file exists at the recorded path
        if os.path.exists(old_path):
            already_correct += 1
            continue
            
        # If not, try to find it in subdirectories of watched_files/instagram
        filename = os.path.basename(old_path)
        base_dir = "./watched_files/instagram"
        
        found_new_path = None
        
        # Search in all subdirectories
        for root, dirs, files in os.walk(base_dir):
            if filename in files:
                found_new_path = os.path.join(root, filename)
                break
        
        if found_new_path:
            # Normalize to use forward slashes or consistent backslashes
            found_new_path = found_new_path.replace("\\", "/")
            if not found_new_path.startswith("./"):
                found_new_path = "./" + found_new_path
            
            # Update metadata
            meta["filepath"] = found_new_path
            
            # Update the collection
            db.collection.update(
                ids=[doc_id],
                metadatas=[meta]
            )
            updated_count += 1
            # logger.info(f"Updated path for {doc_id}: {old_path} -> {found_new_path}")
        else:
            missing_count += 1
            logger.warning(f"File NOT found anywhere for ID: {doc_id} (Original: {old_path})")

    logger.info(f"Sync complete.")
    logger.info(f"Already correct: {already_correct}")
    logger.info(f"Updated: {updated_count}")
    logger.info(f"Missing: {missing_count}")

if __name__ == "__main__":
    sync_paths()
