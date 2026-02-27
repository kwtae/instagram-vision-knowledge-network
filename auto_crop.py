import os
import logging
from ultralytics import YOLO
from PIL import Image

logger = logging.getLogger("mcp_vision_server.auto_crop")

# 사전 훈련된 YOLOv8 모델 로드 (첫 실행 시 자동 다운로드)
model = YOLO('yolov8n.pt')

# COCO 데이터셋 기준 가구/인테리어 관련 클래스 ID
# 56: 의자(chair), 57: 소파(couch), 58: 화분(potted plant), 59: 침대(bed), 60: 식탁(dining table), 62: TV(tv), 71: 싱크대(sink), 72: 냉장고(refrigerator)
TARGET_CLASSES = [56, 57, 58, 59, 60, 62, 71, 72]

def crop_furniture(image_path: str) -> list[str]:
    """YOLOv8을 사용하여 이미지 내 가구를 감지하고 크롭하여 개별 파일로 저장합니다."""
    cropped_files = []
    try:
        results = model(image_path, verbose=False)
        img = Image.open(image_path)
        
        base_dir, filename = os.path.split(image_path)
        name, ext = os.path.splitext(filename)
        
        count = 0
        for result in results:
            boxes = result.boxes
            for box in boxes:
                cls_id = int(box.cls[0])
                if cls_id in TARGET_CLASSES:
                    # Bounding Box 좌표 (x1, y1, x2, y2)
                    x1, y1, x2, y2 = map(int, box.xyxy[0])
                    cropped_img = img.crop((x1, y1, x2, y2))
                    
                    crop_filename = f"{name}_crop_{count}{ext}"
                    crop_filepath = os.path.join(base_dir, crop_filename)
                    cropped_img.save(crop_filepath)
                    
                    cropped_files.append(crop_filepath)
                    count += 1
                    logger.info(f"가구(클래스:{cls_id}) 크롭 완료: {crop_filepath}")
                    
    except Exception as e:
        logger.error(f"이미지 크롭 중 오류 발생 {image_path}: {e}")
        
    return cropped_files
