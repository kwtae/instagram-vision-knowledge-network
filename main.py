import logging
import asyncio
from mcp.server.fastmcp import FastMCP

# 한국어(ko-KR) 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("mcp_vision_server")

# FastMCP 서버 인스턴스 생성
mcp = FastMCP("AutoVisionServer")

from file_manager import DirectoryMonitor, scan_directory_once
from instagram_scraper import scrape_saved_posts
from db_manager import db

@mcp.tool()
async def scan_local_directory(path: str) -> str:
    """수동으로 지정된 디렉토리의 이미지 및 PDF 파일을 스캔하고 분석합니다."""
    logger.info(f"디렉토리 스캔을 시작합니다: {path}")
    results = scan_directory_once(path)
    return f"스캔이 완료되었습니다: {path} (PDF: {results['pdfs']}건, 이미지: {results['images']}건 처리됨)"

from instagram_scraper import scrape_saved_posts

@mcp.tool()
async def sync_instagram_saved(limit: int = 10) -> str:
    """사용자의 인스타그램 '저장됨' 게시물을 스크랩하고 저장합니다."""
    logger.info("인스타그램 저장됨 게시물 동기화를 시작합니다.")
    downloaded = await scrape_saved_posts(limit)
    if not downloaded:
        return "다운로드된 이미지가 없거나 쿠키가 잘못되었습니다. 로그를 확인하세요."
    return f"총 {len(downloaded)}개의 인스타그램 이미지를 동기화했습니다."

@mcp.tool()
async def search_references(query: str) -> str:
    """의미론적 태그나 OCR 텍스트를 기반으로 레퍼런스를 검색합니다."""
    logger.info(f"레퍼런스 검색을 요청했습니다: 질의어 '{query}'")
    results = db.search_similar(query)
    
    if not results:
        return f"'{query}'에 대한 검색 결과가 없습니다."
        
    response = [f"'{query}'에 대한 검색 결과:"]
    for r in results:
        path = r['metadata'].get('filepath', 'Unknown')
        tags = r['metadata'].get('tags', '')
        response.append(f"- 파일: {path} (태그: {tags}, 유사도 거리: {r['distance']:.4f})")
        
    return "\n".join(response)

@mcp.tool()
async def get_file_network(file_id: str) -> str:
    """공유된 태그를 기반으로 파일 간의 관계(네트워크)를 반환합니다."""
    logger.info(f"파일 네트워크 정보를 요청했습니다: 파일 ID '{file_id}'")
    network = db.get_file_network(file_id)
    
    if not network:
        return f"파일 '{file_id}'의 네트워크 관계를 찾을 수 없습니다."
        
    response = [f"파일 '{file_id}'와(과) 유사한 파일 네트워크:"]
    for r in network:
        path = r['metadata'].get('filepath', 'Unknown')
        tags = r['metadata'].get('tags', '')
        response.append(f"- 유사 파일: {path} (태그: {tags})")
        
    return "\n".join(response)

from visualize_network import generate_graph_html

@mcp.tool()
async def build_network_graph_html(distance_threshold: float = 0.5) -> str:
    """
    ChromaDB의 태그 및 문서 연관성을 바탕으로 파일들의 구조를 분석하여 옵시디언 형태의 인터랙티브 네트워크 시각화 맵(HTML)을 생성합니다.
    사용자는 생성된 HTML을 브라우저에서 열어 탐색할 수 있습니다.
    """
    logger.info("파일 네트워크 시각화 맵 (D3.js) 생성을 요청했습니다.")
    path = generate_graph_html("network_graph.html", distance_threshold)
    
    if path:
        return f"옵시디언 뷰 네트워크 맵 파일이 성공적으로 생성되었습니다. 브라우저에서 다음 파일을 열람하세요:\n{path}"
    else:
        return "네트워크 시각화 생성에 실패했거나 데이터베이스가 비어 있습니다."

def main():
    logger.info("MCP 비전 서버가 시작되었습니다.")
    
    # 백그라운드 모니터링 시작 (예: "./watched_files" 디렉토리)
    import threading
    monitor = DirectoryMonitor("./watched_files")
    monitor.start()
    
    try:
        mcp.run()
    finally:
        monitor.stop()

if __name__ == "__main__":
    main()
