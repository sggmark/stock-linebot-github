import os
from openai import AzureOpenAI
from configparser import ConfigParser
import csv   #匯入 Python 標準庫中的 csv 模組
import requests
from bs4 import BeautifulSoup
import datetime as dt
import yfinance as yf
import numpy as np



#-------取得所有環境變數 KEY 的值-----------------------------------------
#config = ConfigParser()
#config.read("config.ini")

#-------建立AzureOpenAI物件-----------------------------------------
client = AzureOpenAI(
    azure_endpoint=os.getenv("ENDPOINT"),
    api_version=os.getenv("VERSION"),
    api_key=os.getenv("KEY"),
)
model=os.getenv("GPT4o_DEPLOYMENT_NAME")

#-----先下載股票對照表name_df.csv取得股票代號，股票名稱-----------------------------------------
db = {} #使用一個字典來模擬資料庫
# 檢查是否已建構資料庫
if 'initialized' not in db.keys():
  #file_path = os.path.join('name_df.csv')
  with open('name_df.csv', 'r', encoding='utf-8') as csvfile:
    csvreader = csv.reader(csvfile) #讀取 CSV 檔案的內容
    header = next(csvreader)  # 跳過首行（表頭）

    for row in csvreader:
        index = row[0]
        stock_id = row[1]     
        stock_name = row[2]
        industry = row[3]
        
        # 存到資料庫中
        db[stock_id] = {'stock_name': stock_name, 
                        'industry': industry}
  
  # 在資料庫中設置 'initialized'，用於標記資料庫是否建立
  db['initialized'] = True
  #print( db,"資料庫建立完成")



#---------從鉅亨網news.cnyes.com取得股票個股新聞資訊----------------------------------------------------
def stock_news(stock_name ="大盤"):
    if stock_name == "大盤":
      stock_name="台股 -盤中速報"

    data=[]
    # 取得 Json 格式資料
    json_data = requests.get(f'https://ess.api.cnyes.com/ess/api/v1/news/keyword?q={stock_name}&limit=5&page=1').json()

  # 依照格式擷取資料
    items=json_data['data']['items']
    for item in items:
      # 網址、標題和日期
        news_id = item["newsId"]
        title = item["title"]
        publish_at = item["publishAt"]
      # 使用 UTC 時間格式
        utc_time = dt.datetime.utcfromtimestamp(publish_at)
        formatted_date = utc_time.strftime('%Y-%m-%d')
      # 前往鉅亨網取得新聞內容
        url = requests.get(f'https://news.cnyes.com/'
                        f'news/id/{news_id}').content
        soup = BeautifulSoup(url, 'html.parser')
        p_elements=soup.find_all('p')
      # 提取段落内容
        p=''
        for paragraph in p_elements[4:]:
            p+=paragraph.get_text()
        data.append([stock_name, formatted_date ,title,p])
    return data

# -------從 yfinance 取得股票近十日股價資料-------------------------
def stock_price(stock_id="大盤", days = 10):
    if stock_id == "大盤":
        stock_id="^TWII"
    else:
        stock_id += ".TW"
  
    end = dt.date.today() # 資料結束時間
    start = end - dt.timedelta(days=days) # 資料開始時間      
    df = yf.download(stock_id, start=start)  # 下載資料  
    # # 更換列名
    df.columns = ['開盤價', '最高價', '最低價','收盤價', '調整後收盤價', '成交量']
    
    data = {
       '日期': df.index.strftime('%Y-%m-%d').tolist(),
       '收盤價': df['收盤價'].tolist(),
       '每日報酬': df['收盤價'].pct_change().tolist(),
       '漲跌價差': df['調整後收盤價'].diff().tolist()
       }
  
    return data

#---------從 yfinance 取得股票基本面資料----------------------------
def stock_fundamental(stock_id="大盤"):
    if stock_id == "大盤":
        return None
    # 將股票代號構造成 yfinance 格式 -->0000.TW
    stock_id += ".TW"
    stock = yf.Ticker(stock_id)

    # 取得股票營收成長率
    quarterly_revenue_growth = np.round(
      stock.quarterly_financials.loc["Total Revenue"].pct_change(
        -1, fill_method=None).dropna().tolist(), 2)

    # 取得股票每季EPS
    quarterly_eps = np.round(
      stock.quarterly_financials.loc["Basic EPS"].dropna().tolist(), 2)

    # 取得股票EPS季增率
    quarterly_eps_growth = np.round(
      stock.quarterly_financials.loc["Basic EPS"].pct_change(
        -1, fill_method=None).dropna().tolist(), 2)

    # 轉換日期
    dates = [
      date.strftime('%Y-%m-%d') for date in stock.quarterly_financials.columns
    ]

    data = {
      '季日期': dates[:len(quarterly_revenue_growth)],
      '營收成長率': quarterly_revenue_growth.tolist(),
      'EPS': quarterly_eps[0:3].tolist(),
      'EPS 季增率': quarterly_eps_growth[0:3].tolist()
    }

    return data


# ----------利用 GPT 4 模型，傳送messages訊息，並獲得reply回覆內容---------------------------------
def get_reply(messages):
    try:
        response = client.chat.completions.create(
            model=model,
            messages=messages)
        reply = response.choices[0].message.content
    except Exception as err:
        reply = f"發生錯誤{err}"
    return reply

# -------------------組合建立user的Prompt提示內容---------------
def generate_content_msg(stock_id):
    
    stock_name = db[stock_id]["stock_name"] if stock_id != "大盤" else stock_id
    #print(stock_name)
    price_data = stock_price(stock_id)
    news_data = stock_news(stock_name)

    content_msg = '你現在是一位專業的證券分析師, \
      你會依據以下資料來進行分析並給出一份完整的分析報告:\n'

    content_msg += f'近期價格資訊:\n {price_data}\n'

    if stock_id != "大盤":
        stock_value_data = stock_fundamental(stock_id)
        content_msg += f'每季營收資訊：\n {stock_value_data}\n'

    content_msg += f'近期新聞資訊: \n {news_data}\n'
    content_msg += f'請給我{stock_name}近期的趨勢報告,請以詳細、\
      嚴謹及專業的角度撰寫此報告,並提及重要的數字, 以繁體中文回答'

    return content_msg

# --------組合要傳送給GPT-4o的訊息內容-------------------------
def stock_gpt(stock_id):
    content_msg = generate_content_msg(stock_id)

    msg = [{
        "role": "system",
        "content": "你現在是一位專業的證券分析師, 你會統整近期的股價\
      、基本面、新聞資訊等方面並進行分析, 然後生成一份專業的趨勢分析報告"
    }, {
        "role": "user",
        "content": content_msg
    }]

    reply_data = get_reply(msg)
    return reply_data

#-----------------測試-----------------------------------------
#print(stock_gpt("2330"))
#print(stock_gpt(stock_id="大盤"))