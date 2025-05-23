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
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def crawl_recent_pages(pages_to_check=5):
    """최근 N페이지 크롤링"""
    driver = setup_driver()
    recent_data = []
    
    try:
        url = "https://emedi.mfds.go.kr/cliTrial/MNU20307#list"
        driver.get(url)
        time.sleep(5)
        
        for page_num in range(1, pages_to_check + 1):
            print(f"크롤링 중: {page_num}/{pages_to_check} 페이지")
            
            if page_num > 1:
                try:
                    driver.execute_script(f"fn_egov_link_page({page_num})")
                    time.sleep(3)
                except:
                    continue
            
            try:
                table = driver.find_element(By.XPATH, '//*[@id="searchResultList"]/div/div[2]/table')
                rows = table.find_elements(By.XPATH, ".//tbody/tr")
                
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
    
    finally:
        driver.quit()
    
    return pd.DataFrame(recent_data)

def load_previous_data():
    """이전 데이터 로드"""
    if os.path.exists('previous_data.csv'):
        return pd.read_csv('previous_data.csv')
    return pd.DataFrame()

def find_new_items(current_df, previous_df):
    """새로운 항목 찾기"""
    if previous_df.empty:
        # 처음 실행인 경우 모든 데이터를 새로운 것으로 간주하지 않음
        return pd.DataFrame()
    
    previous_numbers = set(previous_df['연번'].astype(str))
    new_items = current_df[~current_df['연번'].astype(str).isin(previous_numbers)]
    
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
    digital_items = new_items_df[new_items_df['임상시험의 제목'].str.contains('[디지털의료기기]', regex=False, na=False)]
    
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
    
    html_body += "</body></html>"
    
    try:
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

def main():
    """메인 실행 함수"""
    print(f"모니터링 시작: {datetime.now()}")
    
    # 설정 확인
    if not all([CONFIG['SENDER_EMAIL'], CONFIG['SENDER_PASSWORD'], CONFIG['RECIPIENT_EMAIL']]):
        print("환경변수 설정이 필요합니다!")
        sys.exit(1)
    
    # 크롤링
    current_data = crawl_recent_pages(CONFIG['MAX_PAGES_TO_CHECK'])
    
    if current_data.empty:
        print("크롤링 실패")
        sys.exit(1)
    
    # 이전 데이터와 비교
    previous_data = load_previous_data()
    new_items = find_new_items(current_data, previous_data)
    
    # 이메일 전송
    if not new_items.empty:
        print(f"새로운 항목 {len(new_items)}건 발견!")
        send_email_notification(new_items, CONFIG)
    
    # 현재 데이터 저장
    current_data.to_csv('previous_data.csv', index=False)
    print(f"모니터링 완료: {datetime.now()}")

if __name__ == "__main__":
    main()
