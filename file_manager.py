import os
import io
import logging
import asyncio
import base64
import queue
import threading
import requests
import fitz  # PyMuPDF
import pytesseract
import json
import re
import imagehash
from PIL import Image, ImageEnhance
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from db_manager import db

logger = logging.getLogger("mcp_vision_server.file_manager")

file_queue = queue.Queue()

HASH_FILE = "image_hashes.json"
seen_hashes = set()
if os.path.exists(HASH_FILE):
    try:
        with open(HASH_FILE, "r", encoding="utf-8") as f:
            seen_hashes = set(json.load(f))
    except Exception:
        pass

TAGS_CACHE_FILE = "post_tags.json"
post_tags_cache = {}
if os.path.exists(TAGS_CACHE_FILE):
    try:
        with open(TAGS_CACHE_FILE, "r", encoding="utf-8") as f:
            post_tags_cache = json.load(f)
    except Exception:
        pass

TEXT_CACHE_FILE = "post_text_cache.json"
post_text_cache = {}
if os.path.exists(TEXT_CACHE_FILE):
    try:
        with open(TEXT_CACHE_FILE, "r", encoding="utf-8") as f:
            post_text_cache = json.load(f)
    except Exception:
        pass

# 전략 4: 계층형 태깅 시스템 (Hierarchy Tagging)
HIERARCHY_MAP = {
    "의자": ["가구"],
    "소파": ["가구"],
    "테이블": ["가구"],
    "책상": ["가구"],
    "수납장": ["가구"],
    "선반": ["가구"],
    "침대": ["가구"],
    "조명": ["소품"],
    "평면도": ["도면"],
    "투시도": ["도면", "표현"],
    "조감도": ["도면", "표현"],
    "건축모형": ["모형"],
    "실내건축": ["공간디자인"],
    "파사드": ["외부건축", "건축"],
    "인물사진": ["사진", "포토그래피"]
}

VALID_CATEGORIES = [c.strip() for c in "건축, 공간디자인, 실내건축, 주거공간, 상업공간, 공공건축, 전시공간, 파사드, 외부건축, 도면, 평면도, 투시도, 조감도, 건축모형, 모형, 건축가, 가구, 의자, 소파, 테이블, 책상, 수납장, 선반, 조명, 침대, 소품, 오브제, 하드웨어, 부속품, 목공, 금속공예, 가구제작, 디자인, 시각디자인, 영상디자인, 제품디자인, 타이포그래피, 브랜딩, 로고, UX, UI, 패키지디자인, 패션, 드로잉, 사진, 포토그래피, 인물사진, 스튜디오, 영화, 영상, 음악, 전시, 미술품, 표현, 책, 매거진, 인터뷰, 에세이, 리뷰, 비평, 논설, 칼럼, 기획, 전략, 사업공고, 조언, 작업, 그리드, 색감, 다이어그램, 질감, 텍스처, 타이포배치, 미니멀리즘, 음식, 플레이팅, ai, 미분류, 복합".split(',')]

def apply_hierarchy(tags: list[str]) -> list[str]:
    extended = set(tags)
    for t in tags:
        if t in HIERARCHY_MAP:
            extended.update(HIERARCHY_MAP[t])
    return list(extended)

def clean_spam_text(text: str) -> str:
    lines = text.split('\n')
    clean_lines = []
    
    for line in lines:
        words = line.split()
        if not words:
            continue
            
        hashtags = [w for w in words if w.startswith('#')]
        
        if len(hashtags) > 3 and len(hashtags) > len(words) * 0.5:
            continue
            
        cleaned_line = re.sub(r'@[a-zA-Z0-9_.]+', '', line).strip()
        
        if cleaned_line and not (len(cleaned_line) < 15 and "view" in cleaned_line.lower()):
            clean_lines.append(cleaned_line)
            
    return '\n'.join(clean_lines)

def process_and_store_file(filepath: str) -> bool:
    ext = os.path.splitext(filepath)[1].lower()
    if ext not in [".pdf", ".jpg", ".jpeg", ".png", ".txt"]:
        return False
        
    try:
        stat = os.stat(filepath)
        metadata = {
            "size_bytes": int(stat.st_size),
            "timestamp": float(stat.st_mtime)
        }
    except Exception as e:
        logger.error(f"Failed to extract file stats {filepath}: {e}")
        return False

    if ext == ".pdf":
        logger.info(f"Processing PDF: {filepath}")
        metadata["type"] = "pdf"
        text = extract_pdf_text(filepath)
        arch_tags = classify_content_text(text)
        arch_tags = apply_hierarchy(arch_tags)
        tags = ["pdf", "document"] + arch_tags
        
        db.add_reference(filepath, text, tags, metadata)
        return True

    filename = os.path.basename(filepath)
    shortcode = None
    if filename.startswith("ig_"):
        parts = filename.split('_')
        if len(parts) >= 2:
            shortcode = parts[1]

    tags = []
    final_text = ""

    # Carousel Context Cache
    CAROUSEL_CACHE_FILE = "carousel_desc_cache.json"
    carousel_desc_cache = {}
    if os.path.exists(CAROUSEL_CACHE_FILE):
        try:
            with open(CAROUSEL_CACHE_FILE, "r", encoding="utf-8") as f:
                carousel_desc_cache = json.load(f)
        except:
            pass

    if ext == ".txt":
        logger.info(f"Processing Text file: {filepath}")
        metadata["type"] = "text"
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw_text = f.read()
        except:
            return False
            
        text = clean_spam_text(raw_text)
        class_tags = classify_content_text(text)
        class_tags = apply_hierarchy(class_tags)
        tags = ["text", "instagram_post"] + class_tags
        final_text = text
        
        if shortcode:
            if class_tags:
                post_tags_cache[shortcode] = class_tags
                with open(TAGS_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(post_tags_cache, f)
            # 전략 1: 텍스트 캐시 저장 (이후 이미지 분석 시 Hybrid Reasoning에 사용)
            post_text_cache[shortcode] = text
            with open(TEXT_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(post_text_cache, f)

    else:
        logger.info(f"Processing image: {filepath}")
        metadata["type"] = "image"
        try:
            with Image.open(filepath) as img:
                img_hash = str(imagehash.phash(img))
                if img_hash in seen_hashes:
                    img.close()
                    os.remove(filepath)
                    return False
                seen_hashes.add(img_hash)
                with open(HASH_FILE, "w", encoding="utf-8") as f:
                    json.dump(list(seen_hashes), f)
                metadata["width"] = img.width
                metadata["height"] = img.height
                metadata["resolution"] = f"{img.width}x{img.height}"
        except:
            pass
            
        ocr_text = extract_image_ocr(filepath)
        
        cached_tags = post_tags_cache.get(shortcode) if shortcode else None
        cached_text = post_text_cache.get(shortcode) if shortcode else ""
        carousel_cached_desc = carousel_desc_cache.get(shortcode, "[Linked Object] This is another slide from the same architectural post.") if shortcode else "Inner Carousel Slide"
        
        if cached_tags and re.search(r'_[1-9]\d*\.(png|jpg|jpeg)$', filepath.lower()):
            logger.info(f"경량화: Carousel 상속 적용 -> {filepath} : {cached_tags}")
            description, image_tags = carousel_cached_desc, cached_tags
        else:
            # 전략 1 & 2: 이미지 분석 시 OCR 텍스트와 본문 텍스트를 함께 전달 (Hybrid + Deep Scan)
            description, image_tags = extract_image_semantics(filepath, ocr_text, cached_text)
            image_tags = apply_hierarchy(image_tags)
            if shortcode and image_tags and "미분류" not in image_tags:
                post_tags_cache[shortcode] = image_tags
                # Cache the description for subsequent carousel slides
                carousel_desc_cache[shortcode] = description
                with open(TAGS_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(post_tags_cache, f)
                with open(CAROUSEL_CACHE_FILE, "w", encoding="utf-8") as f:
                    json.dump(carousel_desc_cache, f)
            
        tags = ["image"] + image_tags
        # 전략 5: 이 방대한 시각 묘사와 문맥 텍스트 자체가 Vector DB에 임베딩되어 시각적 특징 검색 퀄리티 극대화
        final_text = f"Vision Description:\n{description}\n\nOCR Text:\n{ocr_text}\n\nRelated Post Text:\n{cached_text}"
        
    primary_tag = tags[1] if len(tags) > 1 else (tags[0] if tags else "미분류")
    if "instagram_post" in primary_tag or primary_tag in ["text", "image"]:
        primary_tag = tags[2] if len(tags) > 2 else "미분류"
        
    base_dir = os.path.dirname(filepath)
    if os.path.basename(base_dir) == primary_tag or os.path.basename(base_dir) == "미분류":
        base_dir = os.path.dirname(base_dir)
        
    target_dir = os.path.join(base_dir, primary_tag)
    os.makedirs(target_dir, exist_ok=True)
    new_filepath = os.path.join(target_dir, filename)
    
    import shutil
    try:
        shutil.move(filepath, new_filepath)
    except:
        new_filepath = filepath

    if shortcode:
        url_str = f"https://www.instagram.com/p/{shortcode}/"
        shortcut_path = os.path.join(target_dir, f"ig_{shortcode}_link.url")
        if not os.path.exists(shortcut_path):
            with open(shortcut_path, "w", encoding="utf-8") as f:
                f.write(f"[InternetShortcut]\nURL={url_str}\nIconIndex=0\n")
    
    db.add_reference(new_filepath, final_text.strip(), tags, metadata)
    return True

def process_queued_files():
    while True:
        filepath = file_queue.get()
        if filepath is None:
            break
        try:
            process_and_store_file(filepath)
        except Exception as e:
            logger.error(f"Queue execution fault {filepath}: {e}")
        finally:
            file_queue.task_done()

queue_worker = threading.Thread(target=process_queued_files, daemon=True)
queue_worker.start()

def extract_pdf_text(filepath: str) -> str:
    text = ""
    try:
        doc = fitz.open(filepath)
        for page in doc:
            text += page.get_text()
        logger.info(f"PDF 텍스트 추출 완료: {filepath}")
    except Exception as e:
        logger.error(f"PDF 텍스트 추출 중 오류 발생 {filepath}: {e}")
    return text

def classify_content_text(text: str, max_retries: int = 2) -> list[str]:
    if not text or len(text.strip()) < 30:
        return []

    for attempt in range(max_retries):
        try:
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": "llava:7b",
                "prompt": f"You are an architectural assistant. Read this text and categorize it into maximum 4 comma separated tags choosing ONLY from this list: [{', '.join(VALID_CATEGORIES)}]. Only output the tags, nothing else.\nText: {text}",
                "stream": False
            }
            response = requests.post(url, json=payload, timeout=90)
            response.raise_for_status()

            result = response.json().get("response", "").strip()

            if "NONE" in result.upper() or not result:
                return []

            tags = [tag.strip() for tag in result.split(',') if tag.strip() in VALID_CATEGORIES]
            logger.info(f"Architectural text classified into taxonomy: {tags}")
            return tags
        except Exception as e:
            logger.warning(f"Architectural text classification failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return []

def extract_image_ocr(filepath: str) -> str:
    try:
        image = Image.open(filepath)
        
        # 전략 3: 도면 및 텍스트 레이아웃 특화 전처리 (고대비 및 흑백 변환)
        image = image.convert('L') # Grayscale 변환
        enhancer = ImageEnhance.Contrast(image)
        image = enhancer.enhance(2.0) # 대비(Contrast) 200% 증가로 선명도 극대화
        
        text = pytesseract.image_to_string(image, lang='kor+eng')
        logger.info(f"이미지 OCR 추출 완료 (High Contrast 프리필터 적용): {filepath}")
        return text.strip()
    except Exception as e:
        logger.error(f"이미지 OCR 처리 중 오류 발생 {filepath}: {e}")
        return ""

def extract_image_semantics(filepath: str, ocr_text: str = "", post_text: str = "", max_retries: int = 2) -> tuple[str, list[str]]:
    for attempt in range(max_retries):
        try:
            with Image.open(filepath) as img:
                img.thumbnail((768, 768))
                buffered = io.BytesIO()
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(buffered, format="JPEG", quality=85)
                encoded_string = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            prompt = (
                "### FORCE VISION PROTOCOL ###\n"
                "You are an expert architectural vision-language AI. Your visual sensors ARE ACTIVE. "
                "The image is PROVIDED in your CURRENT visual buffer. DO NOT claim you cannot see it. "
                "DIRECTLY ANALYZE the image based on the following context and criteria.\n\n"
                f"[Contextual Data]\nOCR Text: {ocr_text[:300]}\nInstagram Post Text: {post_text[:300]}\n\n"
                "[Analysis Criteria]\n"
                "1. Spatial DNA (Interior/Exterior/Plan, Commercial/Residential etc)\n"
                "2. Object Spec (Furniture, Lighting, Built-in etc)\n"
                "3. Materiality (Wood, Concrete, Metal, Texture)\n"
                "4. Representation (Photo, Render, Model)\n\n"
                f"Strictly select 1 to 5 TAGS from this list: [{', '.join(VALID_CATEGORIES)}]\n\n"
                "OUTPUT FORMAT:\n"
                "DESCRIPTION: [3-4 sentences of deep visual architecture analysis]\n"
                "TAGS: [tag1, tag2, tag3]"
            )
            
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": "llava:7b",
                "prompt": prompt,
                "images": [encoded_string],
                "stream": False
            }
            response = requests.post(url, json=payload, timeout=90)
            response.raise_for_status()
            result_text = response.json().get("response", "").strip()

            description = "No description generated."
            tags = []
            if "TAGS:" in result_text.upper():
                parts = re.split(r'TAGS:', result_text, flags=re.IGNORECASE)
                description = parts[0].replace("DESCRIPTION:", "").strip()
                tag_str = parts[1].strip()
                tags = [t.strip() for t in tag_str.split(',') if t.strip() in VALID_CATEGORIES]
            else:
                description = result_text.replace("DESCRIPTION:", "").strip()
                tags = [c for c in VALID_CATEGORIES if c in result_text]
                
            if not tags:
                tags = ["미분류"]
                
            logger.info(f"Fast single-pass Vision processing complete ({tags}): {os.path.basename(filepath)}.")
            import time
            time.sleep(0.5)
            return (f"Spatial DNA & Materiality:\n{description}", tags[:5])
        except Exception as e:
            logger.warning(f"Ollama vision analysis failed (attempt {attempt + 1}/{max_retries}) {filepath}: {e}")
            import time
            time.sleep(2)
            if attempt == max_retries - 1:
                return ("", [])

class VisionFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        
        filepath = event.src_path
        filename = os.path.basename(filepath)
        
        # Skip temporary or hidden files
        if filename.startswith('.') or filename.startswith('~'):
            return

        # Check if the file is inside our watched root
        root_dir = os.path.abspath("./watched_files")
        abs_filepath = os.path.abspath(filepath)
        
        if abs_filepath.startswith(root_dir):
            logger.info(f"File creation detected inside watched root. Enqueuing: {filepath}")
            file_queue.put(filepath)

class DirectoryMonitor:
    def __init__(self, watch_dir: str):
        self.watch_dir = watch_dir
        self.observer = Observer()
        self.handler = VisionFileHandler()
        
    def start(self):
        if not os.path.exists(self.watch_dir):
            os.makedirs(self.watch_dir)
            logger.info(f"모니터링 디렉토리 생성됨: {self.watch_dir}")
            
        self.observer.schedule(self.handler, self.watch_dir, recursive=True)
        self.observer.start()
        logger.info(f"백그라운드 파일 모니터링이 시작되었습니다: {self.watch_dir}")
        
    def stop(self):
        self.observer.stop()
        self.observer.join()
        logger.info("파일 모니터링이 중지되었습니다.")

def scan_directory_once(watch_dir: str) -> dict:
    results = {"pdfs": 0, "images": 0, "texts": 0}
    if not os.path.exists(watch_dir):
        return results
        
    all_files = []
    for root, _, files in os.walk(watch_dir):
        for filename in files:
            all_files.append(os.path.join(root, filename))
            
    all_files.sort(key=lambda x: 0 if x.endswith('.txt') else 1)
    
    for filepath in all_files:
        success = process_and_store_file(filepath)
        if success:
            ext = os.path.splitext(filepath)[1].lower()
            if ext == ".pdf":
                results["pdfs"] += 1
            elif ext in [".jpg", ".jpeg", ".png"]:
                results["images"] += 1
            elif ext == ".txt":
                results["texts"] += 1
                
    return results
