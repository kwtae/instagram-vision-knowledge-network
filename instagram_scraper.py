import os
import json
import logging
import asyncio
from datetime import datetime
from playwright.async_api import async_playwright

logger = logging.getLogger("mcp_vision_server.instagram_scraper")

# 쿠키 파일 경로
COOKIES_FILE = "cookies.json"
# 스크래핑 기록 저장용 (자동화 이어서 크롤링)
HISTORY_FILE = "scraped_history.json"
# 저장할 다운로드 디렉토리 (File Manager가 모니터링하는 곳)
DOWNLOAD_DIR = "./watched_files/instagram"

async def ensure_download_dir():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

async def scrape_saved_posts(limit: int = 10) -> list[str]:
    """사용자의 '저장됨' 게시물을 스크랩합니다."""
    if not os.path.exists(COOKIES_FILE):
        logger.error(f"'{COOKIES_FILE}' 파일이 존재하지 않습니다. 인스타그램 로그인 쿠키가 필요합니다.")
        return []

    downloaded_files = []
    
    try:
        async with async_playwright() as p:
            # 브라우저 실행 (Headless 모드)
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            
            # 쿠키 적용
            with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                cookies = json.load(f)
            await context.add_cookies(cookies)
            
            page = await context.new_page()
            
            # 인스타그램 홈으로 이동하여 세션 유효성 확인
            logger.info("인스타그램에 접속합니다...")
            await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
            
            # 사용자의 프로필 URL 찾기 (보통 사이드바나 네비게이션에 존재)
            # 여기서는 편의상 프로필 링크를 클릭하거나, 직접 URL을 찾습니다.
            profile_link_element = await page.wait_for_selector('a[href^="/"]:has(img)', timeout=10000)
            if not profile_link_element:
                logger.error("로그인 정보를 확인할 수 없습니다. 쿠키가 만료되었을 수 있습니다.")
                await browser.close()
                return []
                
            profile_href = await profile_link_element.get_attribute("href")
            saved_url = f"https://www.instagram.com{profile_href}saved/all-posts/"
            
            logger.info(f"'저장됨' 페이지로 이동합니다: {saved_url}")
            await page.goto(saved_url, wait_until="domcontentloaded")
            
            await ensure_download_dir()
            
            # Debug screenshot
            await page.screenshot(path="debug_saved.png")
            
            # 갤러리 이미지 링크 로드 대기
            await page.wait_for_selector('a[href*="/p/"]', timeout=15000)
            
            # 과거 이력 로딩
            processed_hrefs = set()
            if os.path.exists(HISTORY_FILE):
                try:
                    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                        processed_hrefs = set(json.load(f))
                except Exception:
                    pass
            logger.info(f"기존에 수집된 데이터 {len(processed_hrefs)}개를 기억하고 스킵합니다.")
            
            link_index = 0
            download_count = 0
            
            while download_count < limit:
                # Re-query handles stale elements if DOM changes
                links = await page.locator('a[href*="/p/"]').all()
                if not links or len(links) <= link_index:
                    # Scroll down or break if no more links
                    await page.mouse.wheel(0, 1000)
                    await asyncio.sleep(2)
                    links = await page.locator('a[href*="/p/"]').all()
                    if len(links) <= link_index:
                        break
                
                link = links[link_index]
                href = await link.get_attribute("href")
                
                if href in processed_hrefs:
                    link_index += 1
                    continue
                    
                processed_hrefs.add(href)
                
                try:
                    # Scroll into view and click
                    await link.scroll_into_view_if_needed()
                    await link.click()
                    
                    # Wait for modal dialog and inner article
                    modal = page.locator('div[role="dialog"] article')
                    await modal.wait_for(state="visible", timeout=10000)
                    
                    # Let the image load inside the modal
                    await asyncio.sleep(1.5)
                    
                    # Extract unique shortcode from URL (e.g., /p/Cxz1234abcd/ -> Cxz1234abcd)
                    shortcode = href.strip("/").split("/")[-1]
                    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename_base = f"ig_{shortcode}_{timestamp}"
                    
                    # 1. Extract Full Text (Caption, comments, hashtags)
                    post_text = await modal.inner_text()
                    txt_path = os.path.join(DOWNLOAD_DIR, f"{filename_base}.txt")
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(post_text)
                    logger.info(f"인스타그램 본문 스크래핑 완료: {txt_path}")
                    
                    # 2. Capture Full Screenshots (Handle Carousels)
                    carousel_idx = 0
                    while True:
                        img_path = os.path.join(DOWNLOAD_DIR, f"{filename_base}_{carousel_idx}.png")
                        await modal.screenshot(path=img_path)
                        downloaded_files.append(img_path)
                        logger.info(f"인스타그램 스크린샷 캡쳐 완료 (슬라이드 {carousel_idx}): {img_path}")
                        
                        # Look for 'Next' button in the carousel
                        next_btn = modal.locator('button[aria-label="Next"]')
                        if await next_btn.count() > 0:
                            await next_btn.click()
                            await asyncio.sleep(1.2) # wait for sliding animation
                            carousel_idx += 1
                        else:
                            break
                    
                    download_count += 1
                    link_index += 1
                    
                    # 실시간 이력 저장
                    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                        json.dump(list(processed_hrefs), f)
                    
                    # Close modal
                    close_btn = page.locator('div[role="dialog"] svg[aria-label="Close"]').locator('..')
                    if await close_btn.count() > 0:
                        await close_btn.click()
                    else:
                        await page.keyboard.press("Escape")
                        
                    await page.wait_for_selector('div[role="dialog"]', state="hidden", timeout=5000)
                    
                except Exception as e:
                    logger.warning(f"게시물 모달 캡쳐 실패 {href}: {e}")
                    await page.keyboard.press("Escape")
                    await asyncio.sleep(1)
                
                # Add delay to prevent limits
                await asyncio.sleep(3)
                        
            await browser.close()
            logger.info(f"총 {len(downloaded_files)}개의 이미지를 다운로드했습니다.")
            
    except Exception as e:
        logger.error(f"스크래핑 도중 오류 발생: {e}")
        
    return downloaded_files

def run_scraper_sync(limit: int = 10) -> list[str]:
    """동기 환경에서 비동기 스크래퍼를 실행하기 위한 래퍼 함수입니다."""
    return asyncio.run(scrape_saved_posts(limit))
