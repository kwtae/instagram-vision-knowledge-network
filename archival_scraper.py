import os
import json
import logging
import asyncio
import random
from datetime import datetime
from playwright.async_api import async_playwright

logger = logging.getLogger("mcp_vision_server.archival_scraper")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

COOKIES_FILE = "cookies.json"
HISTORY_FILE = "scraped_history.json"
MASTER_LINKS_FILE = "master_saved_links.json"
DOWNLOAD_DIR = "./watched_files/instagram"

async def ensure_download_dir():
    if not os.path.exists(DOWNLOAD_DIR):
        os.makedirs(DOWNLOAD_DIR)

async def harvest_all_links(page) -> list[str]:
    """브라우저의 JS 엔진에 직접 침투하여 가상 DOM 소멸 현상을 우회하고 모든 URL을 수거합니다."""
    logger.info("=====================================================")
    logger.info("🚀 [1단계] 초고속 딥 스캔 하베스팅(Harvesting) 가동")
    logger.info("=====================================================")
    logger.info("인스타그램 화면 하단으로 무한 강하하며 3년 치 링크를 캐싱합니다. (최대 수 분 소요)")
    
    js_script = """
    async () => {
        return new Promise((resolve) => {
            const collectedLinks = new Set();
            let lastScrollHeight = 0;
            let unchangedScrollCount = 0;
            
            const extractLinks = () => {
                const links = document.querySelectorAll('a[href*="/p/"]', 'a[href*="/reel/"]');
                links.forEach(a => {
                    const href = a.getAttribute('href');
                    if (href.includes('/p/') || href.includes('/reel/')) {
                        collectedLinks.add(href);
                    }
                });
            };

            const scrollInterval = setInterval(() => {
                extractLinks();
                window.scrollTo(0, document.body.scrollHeight);
                
                if (document.body.scrollHeight === lastScrollHeight) {
                    unchangedScrollCount++;
                    if (unchangedScrollCount > 8) { // 약 10~15초간 더 이상 페이지가 안 늘어나면 바닥에 도달한 것으로 간주
                        clearInterval(scrollInterval);
                        resolve(Array.from(collectedLinks));
                    }
                } else {
                    lastScrollHeight = document.body.scrollHeight;
                    unchangedScrollCount = 0;
                }
            }, 1200); // 1.2초마다 하강 및 스캔
            
            // 첫 화면 스캔
            extractLinks();
        });
    }
    """
    links = await page.evaluate(js_script)
    logger.info(f"🎯 하베스팅 완료! 총 {len(links)}개의 고유한 포스트 링크를 획득했습니다.")
    return links

async def run_archival_dump():
    if not os.path.exists(COOKIES_FILE):
        logger.error(f"'{COOKIES_FILE}' 파일이 없습니다.")
        return

    await ensure_download_dir()
    
    processed_hrefs = set()
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                processed_hrefs = set(json.load(f))
        except:
            pass
            
    try:
        master_links = []
        if os.path.exists(MASTER_LINKS_FILE):
            logger.info("📦 로컬 캐시에서 기존 마스터 링크 목록을 불러옵니다. (새 데이터를 원하면 이 파일을 지우세요)")
            with open(MASTER_LINKS_FILE, "r", encoding="utf-8") as f:
                master_links = json.load(f)
        else:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
                context = await browser.new_context(viewport={'width': 1280, 'height': 800}, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                await context.add_cookies(cookies)
                page = await context.new_page()
                
                logger.info("안전하고 은밀하게 인스타그램 본진에 진입합니다...")
                await page.goto("https://www.instagram.com/", wait_until="domcontentloaded")
                await asyncio.sleep(3)
                
                profile_link_element = await page.wait_for_selector('a[href^="/"]:has(img)', timeout=15000)
                if not profile_link_element:
                    logger.error("세션이 만료되었습니다. 쿠키를 다시 교체해야 합니다.")
                    await browser.close()
                    return
                    
                profile_href = await profile_link_element.get_attribute("href")
                saved_url = f"https://www.instagram.com{profile_href}saved/all-posts/"
                
                logger.info(f"아카이브 페이지로 직행: {saved_url}")
                await page.goto(saved_url, wait_until="domcontentloaded")
                await asyncio.sleep(4)
                
                master_links = await harvest_all_links(page)
                with open(MASTER_LINKS_FILE, "w", encoding="utf-8") as f:
                    json.dump(master_links, f)
                await browser.close()

        links_to_process = [link for link in master_links if link not in processed_hrefs]
        logger.info(f"🔥 총 {len(links_to_process)}개의 새 자료를 다운로드 큐에 등록했습니다.")
        if len(links_to_process) == 0:
            logger.info("더 이상 다운로드할 새로운 아카이브 항목이 없습니다.")
            return

        logger.info("=====================================================")
        logger.info("🚀 [2단계] 개별 게시물 독립 다운로드 (Direct Extraction) - GC 모드")
        logger.info("=====================================================")
        
        CHUNK_SIZE = 500
        total_processed = 0

        for chunk_idx in range(0, len(links_to_process), CHUNK_SIZE):
            chunk = links_to_process[chunk_idx:chunk_idx + CHUNK_SIZE]
            logger.info(f"🧹 메모리 가비지 컬렉션(GC): 브라우저 인스턴스를 (재)시작합니다. 예상 RAM 확보 [Chunk {chunk_idx//CHUNK_SIZE + 1}]")
            
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True, args=['--disable-blink-features=AutomationControlled'])
                context = await browser.new_context(viewport={'width': 1280, 'height': 800}, user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
                with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                    cookies = json.load(f)
                await context.add_cookies(cookies)
                page = await context.new_page()

                for i, link in enumerate(chunk, 1):
                    total_processed += 1
                    logger.info(f"[{total_processed}/{len(links_to_process)}] 추출 중: {link}")
                    try:
                        target_url = f"https://www.instagram.com{link}"
                        await page.goto(target_url, wait_until="domcontentloaded")
                        await asyncio.sleep(random.uniform(0.7, 1.2))

                        shortcode = link.strip("/").split("/")[-1]
                        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                        filename_base = f"ig_{shortcode}_{timestamp}"

                        # 게시물 DOM 변경 혹은 Reel 대응을 위해 fallback 추가
                        article = page.locator('article')
                        if await article.count() == 0:
                            article = page.locator('main[role="main"]')
                        if await article.count() == 0:
                            article = page.locator('body')
                            
                        article = article.first
                        await article.wait_for(state="visible", timeout=12000)

                        post_text = await article.inner_text()
                        txt_path = os.path.join(DOWNLOAD_DIR, f"{filename_base}.txt")
                        with open(txt_path, "w", encoding="utf-8") as f:
                            f.write(post_text)

                        carousel_idx = 0
                        while True:
                            img_path = os.path.join(DOWNLOAD_DIR, f"{filename_base}_{carousel_idx}.png")
                            await article.screenshot(path=img_path)

                            next_btn = article.locator('button[aria-label="Next"]')
                            if await next_btn.count() > 0:
                                await next_btn.click()
                                await asyncio.sleep(0.4)
                                carousel_idx += 1
                            else:
                                break

                        processed_hrefs.add(link)
                        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
                            json.dump(list(processed_hrefs), f)

                        sleep_time = random.uniform(1.5, 3.0)
                        logger.info(f"  -> 완료 (슬라이드 {carousel_idx + 1}장). 사람처럼 {sleep_time:.1f}초 휴식합니다...")
                        await asyncio.sleep(sleep_time)

                    except Exception as e:
                        logger.warning(f"  -> 엑세스 에러 (건너뜀): {link} - {e}")
                        await asyncio.sleep(2)
                
                await browser.close()
                logger.info("🧹 청크 달성 완료. 메모리 정리를 위해 브라우저를 닫습니다.")
                await asyncio.sleep(3)

        logger.info("🎉 3년 치 아카이브 전체 강제 덤프 프로세스가 무사히 종료되었습니다!")

    except Exception as e:
        logger.error(f"시스템 치명적 오류: {e}")

if __name__ == "__main__":
    asyncio.run(run_archival_dump())
