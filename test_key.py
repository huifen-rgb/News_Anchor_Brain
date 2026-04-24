from google import genai

# 填入妳在「新專案」申請的新金鑰
client = genai.Client(api_key="AIzaSyDKnbMWPRM6UIUBm_3au2IWXQN_iZDkT0s")

try:
    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents="你好，請幫我寫一句給製作人的打氣話"
    )
    print("✅ 成功！AI 回應：", response.text)
except Exception as e:
    print("❌ 依然失敗，請見報錯細節：\n", e)