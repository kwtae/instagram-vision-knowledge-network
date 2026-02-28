import sys
import json
import os
import io
import base64
from PIL import Image
from db_manager import db

def main():
    import sys
    sys.stdout.reconfigure(encoding='utf-8')
    try:
        distance_threshold = 0.5
        limit = 500
        
        for arg in sys.argv[1:]:
            if arg.startswith("limit="):
                limit = int(arg.split("=")[1])
                
        all_data = db.collection.get(limit=limit, include=["documents", "metadatas"])
        docs = all_data.get("documents", [])
        
        if not all_data or not all_data["ids"]:
            print(json.dumps({"success": True, "nodes": [], "links": []}, ensure_ascii=False))
            return
            
        ids = all_data["ids"]
        metadatas = all_data["metadatas"]
        
        output_nodes = []
        output_edges = []
        
        # 1. Add File Nodes
        for i, doc_id in enumerate(ids):
            meta = metadatas[i] or {}
            filepath = meta.get("filepath", "Unknown")
            filename = os.path.basename(filepath)
            
            label = filename if filename != "Unknown" else doc_id
            group = meta.get("type", "unknown")
            tags_str = meta.get("tags", "")
            tags_list = [t.strip() for t in tags_str.split(',') if t.strip()]
            primary_tag = tags_list[0] if tags_list else "미분류"
            
            raw_doc = all_data["documents"][i] if all_data.get("documents") else ""
            # Clean up the document to show only the main content
            clean_desc = raw_doc
            if "Content: " in raw_doc:
                clean_desc = raw_doc.split("Content: ", 1)[-1].replace("Vision Description:\n", "").strip()
            
            output_nodes.append({
                "id": doc_id,
                "name": label or doc_id,
                "group": group,
                "primaryTag": primary_tag,
                "tags": tags_str,
                "filepath": filepath,
                "description": clean_desc
            })

        # 2. Generate Category Hubs
        categories = sorted(list(set(node["primaryTag"] for node in output_nodes)))
        for cat in categories:
            cat_id = f"CAT_{cat}"
            output_nodes.append({
                "id": cat_id,
                "name": cat,
                "group": "category",
                "isCategory": True,
                "tags": cat
            })
            
        # 3. Connect Files to Category Hubs
        for node in output_nodes:
            if not node.get("isCategory"):
                output_edges.append({
                    "source": node["id"],
                    "target": f"CAT_{node['primaryTag']}",
                    "value": 1.0,
                    "isCategoryLink": True
                })

        # 4. Semantic Similarity Edges (Optional/Limited)
        if docs:
            results = db.collection.query(
                query_texts=docs,
                n_results=min(len(docs), 5) # Reduce from 10 to 5 for speed
            )
            for i, query_id in enumerate(ids):
                retrieved_ids = results["ids"][i]
                distances = results["distances"][i]
                for j, target_id in enumerate(retrieved_ids):
                    dist = distances[j]
                    if target_id != query_id and dist < distance_threshold:
                        if query_id < target_id:
                            src, dst = query_id, target_id
                        else:
                            src, dst = target_id, query_id
                        edge = {"source": src, "target": dst, "value": round(1.0 - dist, 3)}
                        if edge not in output_edges:
                            output_edges.append(edge)

        import random
        random.shuffle(output_nodes)
        random.shuffle(output_edges)

        print(json.dumps({"success": True, "nodes": output_nodes, "links": output_edges}, ensure_ascii=False))
        
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))

if __name__ == "__main__":
    main()
