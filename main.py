# -*- coding: utf-8 -*-

import openai
import os
import sys
import aiohttp
from datetime import datetime, timedelta
from fastapi import Request, FastAPI, HTTPException
from linebot import (
    AsyncLineBotApi, WebhookParser
)
from linebot.aiohttp_async_http_client import AiohttpAsyncHttpClient
from linebot.exceptions import (
    InvalidSignatureError
)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
)
from dotenv import load_dotenv, find_dotenv
import logging

# 安裝 openai 套件的命令被移除，因為它應該在環境中進行安裝，而非於程式碼中。

# 設置日誌紀錄
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 讀取環境變數
_ = load_dotenv(find_dotenv())

# Dictionary to store user message counts and reset times
user_message_counts = {}

# User daily limit
USER_DAILY_LIMIT = 10

def reset_user_count(user_id):
    user_message_counts[user_id] = {
        'count': 0,
        'reset_time': datetime.now() + timedelta(days=1)
    }

# 呼叫 OpenAI 助手 API
async def call_openai_assistant_api(user_message):
    openai.api_key = os.getenv('OPENAI_API_KEY')  # 確保使用環境變數中正確的 API key

    try:
        response = await openai.Assistants.create(
            assistant_id='asst_HVKXE6R3ZcGb6oW6fDEpbdOi',  # 使用指定的助理 ID
            vector_store_id='vs_O4EC1xmZuHy3WiSlcmklQgsR',  # 使用指定的向量存儲 ID
            messages=[
                {"role": "user", "content": user_message}
            ]
        )
        logger.info(f"Response from OpenAI assistant: {response}")
        return response['message']['content']  # 根據 API 文檔的格式提取回應內容
    except openai.error.OpenAIError as e:
        logger.error(f"OpenAI API Error: {e}")
        return "抱歉，我無法處理您的請求，請稍後再試。"
    except Exception as e:
        logger.error(f"Unknown error while calling OpenAI assistant: {e}")
        return "系統出現錯誤，請稍後再試。"

# 獲取 channel_secret 和 channel_access_token
channel_secret = os.getenv('ChannelSecret', None)
channel_access_token = os.getenv('ChannelAccessToken', None)
if channel_secret is None:
    logger.error('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if channel_access_token is None:
    logger.error('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

# Initialize LINE Bot Messaging API
app = FastAPI()
session = aiohttp.ClientSession()
async_http_client = AiohttpAsyncHttpClient(session)
line_bot_api = AsyncLineBotApi(channel_access_token, async_http_client)
parser = WebhookParser(channel_secret)

# Introduction message
introduction_message = (
    "我是 彰化基督教醫院 內分泌暨新陳代謝科 小助理，如果您有任何關於：糖尿病、高血壓、甲狀腺的相關問題，您可以詢問我。"
    "但基本上我是由大型語言模型訓練，所以您有任何疑問建議您要向您的醫療團隊做進一步的諮詢，謝謝！"
)

@app.post("/callback")
async def handle_callback(request: Request):
    signature = request.headers.get('X-Line-Signature')

    # get request body as text
    body = await request.body()
    logger.info(f"Request body: {body.decode()}")
    body = body.decode()

    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature")
        raise HTTPException(status_code=400, detail="Invalid signature")

    for event in events:
        if not isinstance(event, MessageEvent) or not isinstance(event.message, TextMessage):
            continue

        user_id = event.source.user_id
        user_message = event.message.text

        logger.info(f"Received message from user {user_id}: {user_message}")

        # 檢查訊息計數是否需要重置
        if user_id in user_message_counts:
            if datetime.now() >= user_message_counts[user_id]['reset_time']:
                reset_user_count(user_id)
        else:
            reset_user_count(user_id)

        # 檢查用戶是否超過每日限制
        if user_message_counts[user_id]['count'] >= USER_DAILY_LIMIT:
            logger.info(f"User {user_id} exceeded daily limit")
            await line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text="您今天的用量已經超過，請明天再詢問。")
            )
            continue

        # 處理特殊請求（如介紹）
        if "介紹" in user_message or "你是誰" in user_message:
            await line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=introduction_message)
            )
            continue

        # 呼叫 OpenAI 助手，並處理可能的錯誤
        result_text = await call_openai_assistant_api(user_message)
        
        # 更新用戶訊息計數
        user_message_counts[user_id]['count'] += 1

        # 回應用戶訊息
        await line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text=result_text)
        )

    return 'OK'
