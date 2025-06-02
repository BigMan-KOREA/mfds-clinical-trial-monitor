import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
from datetime import datetime
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
import os
import sys

# 환경변수에서 설정값 읽기
CONFIG = {
    'SENDER_EMAIL': os.environ.get('SENDER_EMAIL'),
    'SENDER_PASSWORD': os.environ.get('SENDER_PASSWORD'),
    'RECIPIENT_EMAIL': os.environ.get('RECIPIENT_EMAIL'),
    'MAX_PAGES_TO_CHECK': 5,
}

def setup_driver():
    """Chrome 드라이버 설정"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    
    # Chromium 경로 명시
    chrome_options.binary_location = '/usr/bin/chromium-browser'
    
    service = Service('/usr/lib/chromium-browser/chromedriver')
    
    try:
        driver = webdriver.Chrome(service=service, options=chrome_options)
        print("Chrome 드라이버 생성 성공")
        return driver
    except Exception as e:
        print(f"Chrome 드라이버 생성 실패: {e}")
        raise

def crawl_recent_pages(pages_to_check=5):
    """최근 N페이지 크롤링"""
    print(f"크롤링 시작: {pages_to_check}페이지")
    driver = None
    recent_data = []
    
    try:
        driver = setup_driver()
        url = "https://emedi.mfds.go.kr/cliTrial/MNU20307#list"
        print(f"페이지 접속: {url}")
        driver.get(url)
        time.sleep(5)
        
        for page_num in range(1, pages_to_check + 1):
            print(f"크롤링 중: {page_num}/{pages_to_check} 페이지")
            
            if page_num > 1:
                try:
                    driver.execute_script(f"fn_egov_link_page({page_num})")
                    time.sleep(3)
                except Exception as e:
                    print(f"페이지 {page_num} 이동 실패: {e}")
                    continue
            
            try:
                table = driver.find_element(By.XPATH, '//*[@id="searchResultList"]/div/div[2]/table')
                rows = table.find_elements(By.XPATH, ".//tbody/tr")
                print(f"찾은 행 수: {len(rows)}")
                
                for row in rows:
                    cols = row.find_elements(By.TAG_NAME, "td")
                    if len(cols) >= 4:
                        data = {
                            '연번': cols[0].text.strip(),
                            '승인일자': cols[1].text.strip(),
                            '품목명': cols[2].text.strip(),
                            '임상시험의 제목': cols[3].text.strip(),
                            '크롤링일시': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }
                        recent_data.append(data)
                
            except Exception as e:
                print(f"데이터 추출 실패: {e}")
            
            time.sleep(1)
    
    except Exception as e:
        print(f"크롤링 중 오류 발생: {e}")
        
    finally:
        if driver:
            driver.quit()
            print("드라이버 종료")
    
    print(f"총 {len(recent_data)}개 데이터 수집")
    return pd.DataFrame(recent_data)

def load_previous_data():
    """이전 데이터 로드"""
    if os.path.exists('previous_data.csv'):
        print("이전 데이터 파일 발견")
        try:
            df = pd.read_csv('previous_data.csv')
            print(f"이전 데이터 {len(df)}개 로드")
            return df
        except Exception as e:
            print(f"이전 데이터 로드 실패: {e}")
            return pd.DataFrame()
    else:
        print("이전 데이터 파일 없음 - 첫 실행")
        return pd.DataFrame()

def find_new_items(current_df, previous_df):
    """새로운 항목 찾기"""
    if previous_df.empty:
        print("첫 실행이므로 새로운 항목 확인 스킵")
        # 첫 실행 시 테스트를 위해 최근 5개만 반환
        if len(current_df) > 5:
            print("테스트: 최근 5개 항목을 새로운 항목으로 간주")
            return current_df.head(5)
        return pd.DataFrame()
    
    previous_numbers = set(previous_df['연번'].astype(str))
    new_items = current_df[~current_df['연번'].astype(str).isin(previous_numbers)]
    print(f"새로운 항목 {len(new_items)}개 발견")
    
    return new_items

def send_email_notification(new_items_df, config):
    """이메일 전송"""
    if new_items_df.empty:
        print("새로운 항목이 없습니다.")
        return
    
    subject = f"[MFDS 임상시험] 신규 승인 {len(new_items_df)}건 - {datetime.now().strftime('%Y-%m-%d')}"
    
    # HTML 본문 생성
    html_body = f"""
    <html>
    <body>
        <h2>MFDS 임상시험 신규 승인 알림</h2>
        <p>새로 승인된 임상시험이 <strong>{len(new_items_df)}건</strong> 있습니다.</p>
        
        <h3>디지털의료기기 임상시험</h3>
    """
    
    # 디지털의료기기 필터링
    try:
        digital_items = new_items_df[new_items_df['임상시험의 제목'].str.contains('[디지털의료기기]', regex=False, na=False)]
    except:
        digital_items = pd.DataFrame()
    
    if not digital_items.empty:
        html_body += f"<p>디지털의료기기: <strong>{len(digital_items)}건</strong></p>"
        html_body += "<table border='1' cellpadding='5'>"
        html_body += "<tr><th>연번</th><th>승인일자</th><th>품목명</th><th>임상시험 제목</th></tr>"
        
        for _, row in digital_items.iterrows():
            html_body += f"""
            <tr>
                <td>{row['연번']}</td>
                <td>{row['승인일자']}</td>
                <td>{row['품목명']}</td>
                <td>{row['임상시험의 제목']}</td>
            </tr>
            """
        html_body += "</table>"
    else:
        html_body += "<p>디지털의료기기 임상시험은 없습니다.</p>"
    
    # 전체 목록 추가
    html_body += "<h3>전체 신규 승인 목록</h3>"
    html_body += "<table border='1' cellpadding='5'>"
    html_body += "<tr><th>연번</th><th>승인일자</th><th>품목명</th><th>임상시험 제목</th></tr>"
    
    for _, row in new_items_df.iterrows():
        html_body += f"""
        <tr>
            <td>{row['연번']}</td>
            <td>{row['승인일자']}</td>
            <td>{row['품목명']}</td>
            <td>{row['임상시험의 제목']}</td>
        </tr>
        """
    
    html_body += "</table></body></html>"
    
    try:
        print(f"이메일 전송 시작: {config['RECIPIENT_EMAIL']}")
        
        msg = MIMEMultipart()
        msg['From'] = config['SENDER_EMAIL']
        msg['To'] = config['RECIPIENT_EMAIL']
        msg['Subject'] = subject
        
        msg.attach(MIMEText(html_body, 'html'))
        
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(config['SENDER_EMAIL'], config['SENDER_PASSWORD'])
        server.send_message(msg)
        server.quit()
        
        print(f"이메일 전송 완료: {config['RECIPIENT_EMAIL']}")
        
    except Exception as e:
        print(f"이메일 전송 실패: {e}")
        raise

def main():
    """메인 실행 함수"""
    print("="*50)
    print(f"MFDS 모니터링 시작: {datetime.now()}")
    print("="*50)
    
    # 설정 확인
    print("환경변수 확인:")
    print(f"- SENDER_EMAIL: {'설정됨' if CONFIG['SENDER_EMAIL'] else '미설정'}")
    print(f"- SENDER_PASSWORD: {'설정됨' if CONFIG['SENDER_PASSWORD'] else '미설정'}")
    print(f"- RECIPIENT_EMAIL: {'설정됨' if CONFIG['RECIPIENT_EMAIL'] else '미설정'}")
    
    if not all([CONFIG['SENDER_EMAIL'], CONFIG['SENDER_PASSWORD'], CONFIG['RECIPIENT_EMAIL']]):
        print("환경변수 설정이 필요합니다!")
        sys.exit(1)
    
    try:
        # 크롤링
        current_data = crawl_recent_pages(CONFIG['MAX_PAGES_TO_CHECK'])
        
        if current_data.empty:
            print("크롤링 실패 - 데이터 없음")
            sys.exit(1)
        
        print(f"현재 데이터: {len(current_data)}개")
        
        # 이전 데이터와 비교
        previous_data = load_previous_data()
        new_items = find_new_items(current_data, previous_data)
        
        # 이메일 전송
        if not new_items.empty:
            print(f"새로운 항목 {len(new_items)}건 발견!")
            send_email_notification(new_items, CONFIG)
        else:
            print("새로운 항목 없음")
        
        # 현재 데이터 저장
        current_data.to_csv('previous_data.csv', index=False)
        print("현재 데이터 저장 완료")
        
    except Exception as e:
        print(f"실행 중 오류 발생: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    
    print("="*50)
    print(f"모니터링 완료: {datetime.now()}")
    print("="*50)

if __name__ == "__main__":
    main()
