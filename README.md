# 🌌 Vision Knowledge Network (VKN) 
> **AI 기반 공간 디자인 아카이빙 및 지식 그래프 시스템**

인스타그램, PDF, 이미지 등 흩어져 있는 디자인 영감들을 로컬 LLM(LLaVA)이 스스로 분석하고, 의미적 연관성을 찾아 **Nebula 지식 그래프**로 시각화하는 로컬 퍼스트 AI 에이전트 시스템입니다.

---

## 🚀 시스템의 효용 (Value Proposition)

1. **무한한 아카이빙의 자동화**: 수천 개의 인스타그램 저장물이나 디자인 레퍼런스를 일일이 분류할 필요가 없습니다. AI가 이미지의 '공간 DNA'를 읽고 자동으로 태깅합니다.
2. **시각적 맥락 발견**: 단순한 폴더 구조를 넘어, 디자인 스타일(미니멀리즘, 재질, 조명 방식 등)이 유사한 데이터들을 그래프상에서 가깝게 배치하여 새로운 영감을 제안합니다.
3. **개인 맞춤형 지식 체계**: 전용 대시보드(Next.js)를 통해 나만의 디자인 라이브러리를 Pinterest 스타일의 그리드 또는 인터랙티브한 성운(Nebula) 그래프로 탐색할 수 있습니다.
4. **로컬 LLM (Private AI)**: 모든 이미지 분석은 **Ollama (LLaVA-7b)** 모델을 통해 사용자의 로컬 GPU/CPU에서 수행됩니다. 데이터 외부 유출이 없으며 별도의 API 비용(GPT-4V 등)이 영구적으로 발생하지 않습니다.

---

## ⏱️ 빌드 및 설치 소요 시간 (Estimated Build Time)

*   **시스템 전체 설정**: 약 20 ~ 30분 (네트워크 환경에 따라 다름)
    *   Ollama 및 LLaVA-7b 모델 다운로드 (4.7GB): 약 10 ~ 15분
    *   Python 가상환경 및 종속성 설치: 약 5분
    *   Next.js 프론트엔드 빌드: 약 3분
*   **데이터 처리 속도**: 이미지 1장당 약 15 ~ 30초 (GPU 성능에 따라 상이)

---

## 🛠️ 설치 및 실행 (Installation)

### 1단계: 로컬 AI 서버 (Ollama) 설정
본 프로젝트는 로컬에서 실행되는 **Ollama** 서버가 반드시 필요합니다.
1. [Ollama 공식 홈페이지](https://ollama.com/)에서 설치 프로그램을 다운로드합니다.
2. 터미널에서 비전 모델을 미리 내려받습니다.
   ```bash
   ollama pull llava:7b
   ```

### 2단계: Python 가상환경 및 종속성 설치
```bash
python -m venv venv
.\venv\Scripts\activate  # Windows 기준
pip install -r requirements.txt
```

### 3단계: 프론트엔드 의존성 설치
```bash
cd vision_dashboard
npm install
```

---

## 📸 인스타그램 데이터 수집 가이드

### 세션 쿠키 추출 (필수)
인스타그램 계정에서 '저장됨' 게시물을 가져오려면 브라우저의 로그인 세션이 필요합니다.
1. 브라우저에서 인스타그램 로그인 후 `EditThisCookie` 확장 프로그램 등으로 쿠키를 JSON 형식으로 복사합니다.
2. 루트 디렉토리에 `cookies.json` 파일을 생성하고 붙여넣습니다.

### 실행 명령어
*   **백엔드 감시 서버**: `python main.py` (파일 추가 시 실시간 AI 분석 수행)
*   **스크래퍼 실행**: `python run_scraper.py` (인스타그램 최신 저장물 수집)
*   **대시보드 접속**: `cd vision_dashboard` -> `npm run dev` (`http://localhost:3000`)

---

## ⚠️ 설치 시 주의사항 및 해결 방법 (Troubleshooting)

실수하거나 오류가 발생하기 쉬운 지점들을 미리 체크하세요.

1. **Ollama 실행 여부**: 
   - **오류**: "Connection refused" 또는 분석 결과가 빈 값으로 나옴.
   - **해결**: Ollama 앱이 트레이 아이콘에 떠 있는지 확인하고, `ollama serve` 상태인지 체크하세요.

2. **Tesseract OCR 경로 (OCR 미작동 시)**:
   - **오류**: 이미지 내 텍스트 추출이 전혀 안 됨.
   - **해결**: Windows 사용자는 [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)을 별도 설치해야 할 수 있습니다. 설치 후 환경 변수(Path)에 등록하거나 `file_manager.py`에서 실행 파일 경로를 직접 지정해야 합니다.

3. **쿠키 세션 만료**:
   - **오류**: 인스타그램 스크래퍼가 로그인 페이지에서 멈춤.
   - **해결**: `cookies.json` 값은 시간이 지나면 만료됩니다. 스크래핑이 안 된다면 브라우저에서 다시 쿠키를 추출해 갱신해 주세요.

4. **ChromaDB 경로 불일치**:
   - **오류**: 대시보드에서 이미지가 엑스박스로 뜨거나 그래프에 데이터가 없음.
   - **해결**: 파일을 수동으로 폴더 이동한 경우 DB가 이전 경로를 기억하고 있을 수 있습니다. `python sync_db_paths.py`를 실행하여 현재 파일 위치와 DB를 동기화하세요.

5. **Python venv 미활성화**:
   - **오류**: `ModuleNotFoundError` 발생.
   - **해결**: 항상 `.\venv\Scripts\activate`를 먼저 실행하여 가상환경 내부에서 명령어를 입력하세요.
