from db_manager import db
import json

count = db.collection.count()
print('Total Analyzed & Tagged Items in DB:', count)

docs = db.collection.get(limit=5)
print('\n[ Recent Items Samples ]')
docs_list = docs.get('documents', [])
for i in range(min(5, len(docs_list))):
    meta = docs['metadatas'][i]
    print(f'- File: {meta.get("filepath", "Unknown")}')
    print(f'  Tags: {meta.get("tags", "Unknown")}')
    print(f'  Preview: {docs_list[i][:100]}...')
