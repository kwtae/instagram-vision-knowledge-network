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
from PIL import Image
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

def clean_spam_text(text: str) -> str:
    """Removes excessive hashtag lists, mentions, and skips empty logs to lightweight processing."""
    lines = text.split('\n')
    clean_lines = []
    
    for line in lines:
        words = line.split()
        if not words:
            continue
            
        hashtags = [w for w in words if w.startswith('#')]
        
        # If a line consists mostly of hashtags (>3 total && >50% of the line size), drop it
        if len(hashtags) > 3 and len(hashtags) > len(words) * 0.5:
            continue
            
        # Remove @mentions but keep the rest of the line
        cleaned_line = re.sub(r'@[a-zA-Z0-9_.]+', '', line).strip()
        
        if cleaned_line and not (len(cleaned_line) < 15 and "view" in cleaned_line.lower()):
            clean_lines.append(cleaned_line)
            
    return '\n'.join(clean_lines)

def process_and_store_file(filepath: str) -> bool:
    """Extracts metadata and delegates OCR/Vision processing for persistence."""
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
        text = extract_pdf_text(filepath) # Keep this line to define 'text'
        arch_tags = classify_content_text(text) # Classify PDF text too
        tags = ["pdf", "document"] + arch_tags
        
        db.add_reference(filepath, text, tags, metadata)
        return True
    elif ext == ".txt":
        logger.info(f"Processing Text file: {filepath}")
        metadata["type"] = "text"
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                raw_text = f.read()
        except Exception as e:
            logger.error(f"Text file read fault {filepath}: {e}")
            return False
            
        # Clean spam data
        text = clean_spam_text(raw_text)
        if len(text.strip()) < 30:
            logger.info(f"텍스트가 너무 짧거나 스팸으로 판정되어 무시됩니다: {filepath}")
            return False
            
        # Analyze text for content taxonomy
        class_tags = classify_content_text(text)
        tags = ["text", "instagram_post"] + class_tags
        db.add_reference(filepath, text, tags, metadata)
        return True
    else:
        logger.info(f"Processing image: {filepath}")
        metadata["type"] = "image"
        try:
            with Image.open(filepath) as img:
                img_hash = str(imagehash.phash(img))
                if img_hash in seen_hashes:
                    logger.info(f"Duplicate image detected (Hash: {img_hash}), deleting redundant file: {filepath}")
                    img.close()
                    os.remove(filepath)
                    return False
                
                seen_hashes.add(img_hash)
                with open(HASH_FILE, "w", encoding="utf-8") as f:
                    json.dump(list(seen_hashes), f)
                
                metadata["width"] = img.width
                metadata["height"] = img.height
                metadata["resolution"] = f"{img.width}x{img.height}"
        except Exception as e:
            logger.warning(f"Image context parsing failed initially: {e}")
            pass
            
        ocr_text = extract_image_ocr(filepath)
        description, tags = extract_image_semantics(filepath)
        
        # Merge AI-generated vision description with OCR text for rich semantic indexing
        final_text = f"Vision Description:\n{description}\n\nOCR Text:\n{ocr_text}"
        
        db.add_reference(filepath, final_text.strip(), tags, metadata)
        return True

def process_queued_files():
    """Background worker loop managing the asynchronous ingestion queue."""
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

# Boot background queue worker
queue_worker = threading.Thread(target=process_queued_files, daemon=True)
queue_worker.start()

def extract_pdf_text(filepath: str) -> str:
    """PDF 파일에서 텍스트를 추출합니다."""
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
    """Uses LLM to classify architectural text against a specific taxonomy."""
    if not text or len(text.strip()) < 30:
        return []

    categories = "건축, 공간디자인, 실내건축, 주거공간, 상업공간, 공공건축, 전시공간, 파사드, 도면, 평면도, 투시도, 조감도, 건축모형, 모형, 건축가, 가구, 의자, 소파, 테이블, 책상, 수납장, 선반, 조명, 침대, 소품, 오브제, 하드웨어, 부속품, 목공, 금속공예, 가구제작, 디자인, 시각디자인, 영상디자인, 제품디자인, 타이포그래피, 브랜딩, 로고, UX, UI, 패키지디자인, 패션, 드로잉, 사진, 포토그래피, 인물사진, 스튜디오, 영화, 영상, 음악, 전시, 미술품, 표현, 책, 매거진, 인터뷰, 에세이, 리뷰, 비평, 논설, 칼럼, 기획, 전략, 사업공고, 조언, 작업, 그리드, 색감, 다이어그램, 질감, 텍스처, 타이포배치, 미니멀리즘, 음식, 플레이팅, ai, 미분류, 복합"

    for attempt in range(max_retries):
        try:
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": "gpt-oss:20b",
                "prompt": f"Analyze the following text. Map it to 1-3 of the following strict categories: [{categories}]. Only output the comma-separated categories and nothing else. If it absolutely does not fit any, output 'NONE'. Text: {text[:2000]}",
                "stream": False
            }
            response = requests.post(url, json=payload, timeout=60)
            response.raise_for_status()

            result = response.json().get("response", "").strip()

            if "NONE" in result.upper() or not result:
                return []

            # Filter tags to ensure they are from the predefined list
            valid_categories = [c.strip() for c in categories.split(',')]
            tags = [tag.strip() for tag in result.split(',') if tag.strip() in valid_categories]
            logger.info(f"Architectural text classified into taxonomy: {tags}")
            return tags
        except Exception as e:
            logger.warning(f"Architectural text classification failed (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt == max_retries - 1:
                return []

def extract_image_ocr(filepath: str) -> str:
    """이미지 파일에서 OCR을 사용하여 텍스트를 추출합니다."""
    try:
        image = Image.open(filepath)
        text = pytesseract.image_to_string(image, lang='kor+eng')
        logger.info(f"이미지 OCR 추출 완료: {filepath}")
        return text.strip()
    except Exception as e:
        logger.error(f"이미지 OCR 처리 중 오류 발생 {filepath}: {e}")
        return ""

def extract_image_semantics(filepath: str, max_retries: int = 2) -> tuple[str, list[str]]:
    """Generates detailed image description and tags via local vision model. Resizes image first to prevent timeout/token overflow."""
    for attempt in range(max_retries):
        try:
            # Resize image to mitigate token exhaustion
            with Image.open(filepath) as img:
                img.thumbnail((1024, 1024))
                buffered = io.BytesIO()
                # Convert img to RGB if it is RGBA to save as JPEG
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")
                img.save(buffered, format="JPEG")
                encoded_string = base64.b64encode(buffered.getvalue()).decode('utf-8')
            
            categories = "건축, 공간디자인, 실내건축, 주거공간, 상업공간, 공공건축, 전시공간, 파사드, 도면, 평면도, 투시도, 조감도, 건축모형, 모형, 건축가, 가구, 의자, 소파, 테이블, 책상, 수납장, 선반, 조명, 침대, 소품, 오브제, 하드웨어, 부속품, 목공, 금속공예, 가구제작, 디자인, 시각디자인, 영상디자인, 제품디자인, 타이포그래피, 브랜딩, 로고, UX, UI, 패키지디자인, 패션, 드로잉, 사진, 포토그래피, 인물사진, 스튜디오, 영화, 영상, 음악, 전시, 미술품, 표현, 책, 매거진, 인터뷰, 에세이, 리뷰, 비평, 논설, 칼럼, 기획, 전략, 사업공고, 조언, 작업, 그리드, 색감, 다이어그램, 질감, 텍스처, 타이포배치, 미니멀리즘, 음식, 플레이팅, ai, 미분류, 복합"
            
            url = "http://localhost:11434/api/generate"
            payload = {
                "model": "gpt-oss:20b",
                "prompt": f"Analyze this image and describe what you see in detail. Keep it within 3-4 sentences. At the very end of your response, write exactly 'TAGS:' followed by 1 to 4 comma separated keywords chosen ONLY from this strict list: [{categories}]. Do not make up any new tags.",
                "images": [encoded_string],
                "stream": False
            }
            # Increase timeout threshold
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            
            result = response.json().get("response", "")
            
            description = result
            tags = []
            # Parse the TAGS: keyword specifically explicitly requested in the prompt
            if "TAGS:" in result.upper():
                parts = result.upper().split("TAGS:")
                description = result[:len(parts[0])].strip() # Maintain original casing for description
                tag_str = parts[1].strip()
                
                # Filter tags to ensure they are from the predefined list
                valid_categories = [c.strip() for c in categories.split(',')]
                tags = [tag.strip() for tag in tag_str.split(',') if tag.strip() in valid_categories]
            else:
                # Fallback if the model ignores the formatting instruction
                tags = ["vision_processed"]
                
            logger.info(f"Image semantic analysis complete: {filepath}")
            return (description, tags)
        except Exception as e:
            logger.warning(f"Ollama vision analysis failed (attempt {attempt + 1}/{max_retries}) {filepath}: {e}")
            if attempt == max_retries - 1:
                return ("", [])

class VisionFileHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.is_directory:
            return
        
        filepath = event.src_path
        logger.info(f"File creation detected. Enqueuing: {filepath}")
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

# 단일 스캔용 함수 (MCP 도구 연동용)
def scan_directory_once(watch_dir: str) -> dict:
    results = {"pdfs": 0, "images": 0, "texts": 0}
    if not os.path.exists(watch_dir):
        return results
        
    for root, _, files in os.walk(watch_dir):
        for filename in files:
            filepath = os.path.join(root, filename)
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
