import os
import glob
from file_manager import extract_image_semantics

print("Finding a random image to test...")
image_files = glob.glob('./watched_files/instagram/ig_*_0.png')
if image_files:
    target_img = image_files[0]
    base = target_img.replace('_0.png', '')
    txt_file = base + '.txt'
    
    post_text = ''
    if os.path.exists(txt_file):
        with open(txt_file, 'r', encoding='utf-8') as f:
            post_text = f.read().strip()
            
    print(f"Target Image: {target_img}")
    print(f"Context Text: {post_text[:200]}...")
    
    print("\n[Running Deep Scan...]")
    desc, tags = extract_image_semantics(target_img, ocr_text='', post_text=post_text)
    
    print("\n=== DEEP SCAN RESULT ===")
    print(f"Tags Array: {tags}")
    print(f"Generated Description:\n{desc}")
else:
    print("No images found.")
