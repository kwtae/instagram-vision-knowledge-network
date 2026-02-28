import json
import os
import logging
from instaloader import Instaloader, Profile

logger = logging.getLogger("mcp_vision_server.secure_scraper")
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def run_secure_download():
    # Instaloader 설정: 메타데이터 빼고 필요한 사진/텍스트만 타겟 폴더에 즉시 저장
    L = Instaloader(
        dirname_pattern="watched_files/instagram",
        download_video_thumbnails=False,
        save_metadata=False, # json 저장 안힘
        download_comments=False,
        download_geotags=False
    )
    
    # 이미 로컬에 있는 안전한 cookies.json 재사용 (비밀번호 입력 불필요, 차단 회피)
    cookie_file = "cookies.json"
    if not os.path.exists(cookie_file):
        logger.error("cookies.json 파일이 없습니다. Playwright 자동화에 사용된 그 쿠키가 필요합니다.")
        return

    with open(cookie_file, "r", encoding="utf-8") as f:
        cookie_data = json.load(f)

    # 파이썬 세션 객체에 쿠키 하나씩 주입
    for c in cookie_data:
        domain = c.get('domain', '')
        # Instaloader 세션에 쿠키 강제 이식
        L.context._session.cookies.set(c['name'], c['value'], domain=domain, path=c.get('path', '/'))

    # 로그인 상태라고 속이고 유저네임 타겟 지정
    username = "kwtaee"
    L.context.username = username
    
    try:
        logger.info("안전한 쿠키를 사용하여 프로필 연결을 시도합니다...")
        profile = Profile.from_username(L.context, username)
        logger.info(f"성공! 보안 경고 없이 인증되었습니다: {profile.username}")
    except Exception as e:
        logger.error(f"쿠키 인증에 실패했습니다: {e}")
        return

    logger.info("방대한 3년 치 '저장됨' 데이터 일괄 안전 다운로드를 시작합니다...")
    # 프로필의 저장됨 포스트 무한 이터레이션 (API 통신 방식이므로 DOM 스크롤 한계 없음)
    try:
        count = 0
        for post in profile.get_saved_posts():
            # 이미 다운로드된 경우 스킵할 수 있는 옵션을 켜두면 더 빠릅니다. (Instaloader 기본동작)
            L.download_post(post, target="watched_files/instagram")
            count += 1
            if count % 10 == 0:
                logger.info(f"진행 상황: {count}개의 포스트를 안전하게 가져왔습니다...")
    except KeyboardInterrupt:
        logger.info("사용자에 의해 다운로드가 중지되었습니다.")
    except Exception as e:
        logger.error(f"다운로드 중 오류가 발생했지만, 나중에 다시 실행하면 이어서 받습니다: {e}")

    logger.info("모든 저장됨 포스트 다운로드 프로세스가 종료되었습니다.")

if __name__ == "__main__":
    run_secure_download()
