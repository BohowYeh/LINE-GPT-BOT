from flask import Flask, request, abort
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage,
    ImageMessage, ImageSendMessage)
from PIL import Image
import numpy as np
from PIL import ImageDraw
from io import BytesIO
from flagchat import chat, func_table
import openai
import os

api = LineBotApi(os.getenv('LINE_TOKEN'))
handler = WebhookHandler(os.getenv('LINE_SECRET'))

app = Flask(__name__)

@app.post("/")
def callback():
    # 取得 X-Line-Signature 表頭電子簽章內容
    signature = request.headers['X-Line-Signature']

    # 以文字形式取得請求內容
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # 比對電子簽章並處理請求內容
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        print("電子簽章錯誤, 請檢查密鑰是否正確？")
        abort(400)

    return 'OK'

def txt_to_img_url(prompt):
    response = openai.Image.create(prompt=prompt, n=1, 
                                   size='1024x1024')
    return response['data'][0]['url']

func_table.append({
    "chain": False,  # 生圖後不需要傳回給 API
    "func": txt_to_img_url,
    "spec": {        # function calling 需要的函式規格
        "name": "txt_to_img_url",
        "description": "可由文字生圖並傳回圖像網址",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "描述要產生圖像內容的文字",
                }
            },
            "required": ["prompt"],
        },
    }
})

def img_variation():
    try:
        os.stat('image.png')
    except FileNotFoundError:
        return "你還沒上傳檔案"
    res = openai.Image.create_variation(
        image=open('image.png', 'rb'), n=1,
                   size='1024x1024')
    return res['data'][0]['url']

func_table.append({
    "chain": False,  # 生圖後不需要傳回給 API
    "func": img_variation,
    "spec": {  # function calling 需要的函式規格
        "name": "img_variation",
        "description": "可變化已經上傳的圖像",
        "parameters": {
            "type": "object",
            "properties": {},
        }
    }
})

def img_edit(prompt):
    try:
        os.stat('image_nb.png')
    except FileNotFoundError:
        return "你還沒上傳檔案"
    res = openai.Image.create_edit(
        prompt=prompt,
        image=open('image_nb.png', 'rb'), n=1,
                   size='1024x1024')
    return res['data'][0]['url']

func_table.append({
    "chain": False,  # 生圖後不需要傳回給 API
    "func": img_edit,
    "spec": {        # function calling 需要的函式規格
        "name": "img_edit",
        "description": "可依照文字描述修改上傳圖像並傳回圖像網址",
        "parameters": {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": "描述要修改圖像內容的文字",
                }
            },
            "required": ["prompt"],
        },
    }
})

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    for reply in chat('使用繁體中文的小助手，製作者是葉柏皓', event.message.text):
        pass

    if reply.startswith('https://'):
        api.reply_message(
            event.reply_token,
            ImageSendMessage(original_content_url=reply,
                             preview_image_url=reply))
    else:
        api.reply_message(event.reply_token, 
                          TextSendMessage(text=reply))

def convert_transparent(img):
    # 轉換成有透明通道的圖像
    img = img.convert("RGBA")
    width, height = img.size
    pixdata = np.array(img) # 將像素轉成 numpy 陣列
    
    # 取得圖像最上方邊緣顏色的平均值, 如果這是去背圖在轉成 JPG 檔
    # 那最邊緣應該都是被轉成同樣顏色 (通常是白色或黑色) 的背景
    bg_color = tuple(np.average(pixdata[0,:,:], 
                                axis=0).astype(int))
    
    # 建立用來執行 flood fill 演算法的遮罩
    mask = Image.new('L', (width + 2, height + 2), 0)
    
    # 在遮罩上執行 flood fill 
    ImageDraw.floodfill(mask, (0, 0), 255)
    
    # 建立新圖像資料
    new_data = []
    for y in range(height):
        for x in range(width):
            # 如果是遮罩範圍內的點而且是與背景同色
            # 把這個點變更為透明
            if (mask.getpixel((x+1, y+1)) == 255 and 
                pixdata[y, x, :3].tolist() == list(bg_color[:3])):
                new_data.append((255, 255, 255, 0))
            else:
                new_data.append(tuple(pixdata[y, x]))
    
    # 建立具有透明通道的新圖像
    img_transparent = Image.new('RGBA', img.size)
    img_transparent.putdata(new_data)
    return img_transparent

@handler.add(MessageEvent, message=ImageMessage)
def handle_image_message(event):
    message_id = event.message.id  # 取得圖片訊息的 ID
    # 向 Line 請求圖片內容
    message_content = api.get_message_content(message_id)
    content = message_content.content  # 取得圖片的二進位內容
    img = Image.open(BytesIO(content))
    img.save('image.png', 'PNG')
    img_nb = convert_transparent(img)
    img_nb.save('image_nb.png', 'PNG')
    api.reply_message(event.reply_token, 
                      TextSendMessage(text="已保存圖片"))

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=5000)
