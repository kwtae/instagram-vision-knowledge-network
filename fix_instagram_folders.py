import os
import glob
import shutil
import re
import requests
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger("fixer")

TARGET_DIR = "./watched_files/instagram"
CATEGORIES = "건축, 공간디자인, 실내건축, 주거공간, 상업공간, 공공건축, 전시공간, 파사드, 도면, 평면도, 투시도, 조감도, 건축모형, 모형, 건축가, 가구, 의자, 소파, 테이블, 책상, 수납장, 선반, 조명, 침대, 소품, 오브제, 하드웨어, 부속품, 목공, 금속공예, 가구제작, 디자인, 시각디자인, 영상디자인, 제품디자인, 타이포그래피, 브랜딩, 로고, UX, UI, 패키지디자인, 패션, 드로잉, 사진, 포토그래피, 인물사진, 스튜디오, 영화, 영상, 음악, 전시, 미술품, 표현, 책, 매거진, 인터뷰, 에세이, 리뷰, 비평, 논설, 칼럼, 기획, 전략, 사업공고, 조언, 작업, 그리드, 색감, 다이어그램, 질감, 텍스처, 타이포배치, 미니멀리즘, 음식, 플레이팅, ai, 미분류, 복합"
VALID_CATEGORIES = [c.strip() for c in CATEGORIES.split(',')]

def classify_text(text: str) -> list:
    if not text or len(text.strip()) < 10:
        return ["미분류"]
        
    try:
        url = "http://localhost:11434/api/generate"
        payload = {
            "model": "gpt-oss:20b",
            "prompt": f"You are an architectural assistant. Read this text and categorize it into maximum 4 comma separated tags choosing ONLY from this list: [{CATEGORIES}]. Only output the tags, nothing else.\nText: {text}",
            "stream": False
        }
        res = requests.post(url, json=payload, timeout=60)
        res.raise_for_status()
        result = res.json().get("response", "").strip()
        tags = [tag.strip() for tag in result.split(',') if tag.strip() in VALID_CATEGORIES]
        return tags if tags else ["미분류"]
    except Exception as e:
        logger.error(f"Classification failed: {e}")
        return ["미분류"]

def main():
    if not os.path.exists(TARGET_DIR):
        print("Directory not found")
        return
        
    files = glob.glob(os.path.join(TARGET_DIR, "ig_*"))
    
    # Group by shortcode
    groups = {}
    for f in files:
        if os.path.isdir(f):
            continue
        basename = os.path.basename(f)
        parts = basename.split('_')
        if len(parts) >= 2:
            shortcode = parts[1]
            if shortcode not in groups:
                groups[shortcode] = []
            groups[shortcode].append(f)
            
    logger.info(f"Found {len(groups)} total posts to organize.")
    
    for shortcode, file_list in groups.items():
        txt_files = [f for f in file_list if f.endswith('.txt')]
        image_files = [f for f in file_list if f.endswith(('.png', '.jpg'))]
        
        # 1. Parse text classification
        tags = ["미분류"]
        if txt_files:
            try:
                with open(txt_files[0], "r", encoding="utf-8") as f:
                    content = f.read()
                tags = classify_text(content)
            except:
                pass
                
        primary_tag = tags[0]
        
        # 2. Make tag directory
        tag_dir = os.path.join(TARGET_DIR, primary_tag)
        os.makedirs(tag_dir, exist_ok=True)
        
        # 3. Move files
        for f in file_list:
            if os.path.exists(f):
                shutil.move(f, os.path.join(tag_dir, os.path.basename(f)))
                
        # 4. Create shortcut
        url_str = f"https://www.instagram.com/p/{shortcode}/"
        shortcut_path = os.path.join(tag_dir, f"ig_{shortcode}_link.url")
        if not os.path.exists(shortcut_path):
            with open(shortcut_path, "w", encoding="utf-8") as f:
                f.write(f"[InternetShortcut]\nURL={url_str}\nIconIndex=0\n")
                
        logger.info(f"[{shortcode}] -> {primary_tag} (Moved {len(file_list)} files)")

if __name__ == '__main__':
    main()
