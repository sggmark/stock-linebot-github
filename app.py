import os
from configparser import ConfigParser
from flask import Flask, request, abort
from linebot.v3 import WebhookHandler
from linebot.v3.exceptions import (InvalidSignatureError)
from linebot.v3.webhooks import (MessageEvent,TextMessageContent)
from linebot.v3.messaging import (Configuration,ApiClient,MessagingApi,ReplyMessageRequest,TextMessage)
from linebot.models import TextSendMessage
from linebot import LineBotApi
from gpt40 import stock_gpt
from openai import AzureOpenAI

#-------取得所有環境變數 KEY 的值-----------------------------------------
#config = ConfigParser()
#config.read("config.ini")

app = Flask(__name__)
#------------LINE BOT 設定-----------------------------------------
#CHANNEL_ACCESS_TOKEN = config["LINEBOT"]["CHANNEL_ACCESS_TOKEN"]
#CHANNEL_SECRET = config["LINEBOT"]["CHANNEL_SECRET"]
#if CHANNEL_SECRET is None:
#    print('Specify LINE_CHANNEL_SECRET as environment variable.')
#    sys.exit(1)
#if CHANNEL_ACCESS_TOKEN is None:
#    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
#    sys.exit(1)

#------取得所有環境變數 KEY 的值-------------------------------------
CHANNEL_ACCESS_TOKEN = os.getenv("CHANNEL_ACCESS_TOKEN")
CHANNEL_SECRET = os.getenv("CHANNEL_SECRET")

line_handler = WebhookHandler(CHANNEL_SECRET)
configuration = Configuration(access_token=CHANNEL_ACCESS_TOKEN)
linebot_api_v2 = LineBotApi(CHANNEL_ACCESS_TOKEN)

#------------ Azure OpenAI Key 設定 ----------------------
client = AzureOpenAI(
    api_key=os.getenv("KEY"),
    api_version=os.getenv("VERSION"),
    azure_endpoint=os.getenv("ENDPOINT"),
)
#------------ Azure OpenAI 詢問----------------------
def azure_openai(user_message):
    message_text = [
        {
            "role": "system",
            "content": "",
        },
        {"role": "user", "content": user_message},
    ]

    message_text[0]["content"] += "你是一個人工智慧理財顧問, "
    message_text[0]["content"] += "請一律用繁體中文回答。"

    completion = client.chat.completions.create(
        model=os.getenv("GPT4o_DEPLOYMENT_NAME"),
        messages=message_text,
        max_tokens=800,
        top_p=0.95,
        frequency_penalty=0,
        presence_penalty=0,
        stop=None,
    )
    print(completion)
    return completion.choices[0].message.content

@app.route("/callback", methods=['POST'])
def callback():
    # 取得 X-Line-Signature 表頭電子簽章內容
    signature = request.headers['X-Line-Signature']

    # 以文字形式取得請求內容
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # 比對電子簽章並處理請求內容
    try:
        line_handler.handle(body, signature)
    except InvalidSignatureError:
        print("電子簽章錯誤, 請檢查密鑰是否正確？")
        abort(400)

    return 'OK'

# 處理訊息
@line_handler.add(MessageEvent, message=TextMessageContent)
def handle_message(event):
    user_message = event.message.text
    #-------- 判斷用戶是否輸入4位數股票代號或輸入"大盤" ----------------
    if (len(user_message) == 4 and user_message.isdigit()) or user_message == '大盤':
        reply_text = stock_gpt(user_message)
        linebot_api_v2.reply_message(
        event.reply_token,
        TextSendMessage(text=reply_text))
    # 一般問題詢問訊息
    else:
        reply_text=azure_openai(user_message)
        with ApiClient(configuration) as api_client:
            line_bot_api = MessagingApi(api_client)
            line_bot_api.reply_message_with_http_info(
                ReplyMessageRequest(
                        reply_token=event.reply_token,
                        messages=[TextMessage(text=reply_text)]
                )
            )
    #user_message = event.message.text
    #print(user_message)
    

    # 將 reply_text 包裝成 TextSendMessage
    #reply_message = TextSendMessage(text=reply_text)
      
    #line_bot_api.reply_message(
    #    ReplyMessageRequest(
    #                reply_token=event.reply_token,
    #                messages=[reply_message]
    #    )
    #)
      
if __name__ == "__main__":
    app.run()

