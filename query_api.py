import sys
import json
import os
from db_manager import db

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        limit = 50
        offset = 0
        tag_filter = None
        query_text = None
        
        for arg in sys.argv[1:]:
            if arg.startswith("limit="):
                limit = int(arg.split("=")[1])
            elif arg.startswith("offset="):
                offset = int(arg.split("=")[1])
            elif arg.startswith("tag="):
                tag_filter = arg.split("=")[1]
            elif arg.startswith("q="):
                query_text = arg.split("=")[1]
                
        # 1. Semantic Search Mode
        if query_text:
            search_results = db.collection.query(
                query_texts=[query_text],
                n_results=limit,
                where={"type": "image"}
            )
            
            ids = search_results.get("ids", [[]])[0]
            docs = search_results.get("documents", [[]])[0]
            metas = search_results.get("metadatas", [[]])[0]
            distances = search_results.get("distances", [[]])[0]
            
            output = []
            for i in range(len(ids)):
                item_meta = metas[i] if metas else {}
                output.append({
                    "id": ids[i],
                    "filepath": item_meta.get("filepath", ""),
                    "url": item_meta.get("url", ""),
                    "description": docs[i] if docs else "",
                    "tags": item_meta.get("tags", ""),
                    "type": item_meta.get("type", "unknown"),
                    "timestamp": item_meta.get("timestamp", 0),
                    "search_score": round(1.0 - distances[i], 3) if distances else 0
                })
        
        # 2. Metadata Filter Mode
        else:
            where_clause = {"type": "image"}
            results = db.collection.get(where=where_clause, limit=limit if not tag_filter else 2000, offset=offset)
                
            docs = results.get("documents", [])
            metas = results.get("metadatas", [])
            ids = results.get("ids", [])
            
            output = []
            for i in range(len(ids)):
                item_meta = metas[i] if metas else {}
                item_tags = item_meta.get("tags", "")
                
                # Manual filtering for tags if tag_filter is present
                if tag_filter:
                    # Check if tag exists in the comma-separated string
                    tags_list = [t.strip() for t in item_tags.split(',')]
                    if tag_filter not in tags_list:
                        continue
                        
                output.append({
                    "id": ids[i],
                    "filepath": item_meta.get("filepath", ""),
                    "url": item_meta.get("url", ""),
                    "description": docs[i] if docs else "",
                    "tags": item_tags,
                    "type": item_meta.get("type", "unknown"),
                    "timestamp": item_meta.get("timestamp", 0)
                })
            
            # Apply limit if we filtered in python
            if tag_filter:
                output = output[offset:offset+limit]
        
        import random
        random.shuffle(output)
            
        print(json.dumps({"success": True, "count": len(output), "data": output}, ensure_ascii=False))
        
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
