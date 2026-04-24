import google.generativeai as genai

# 請貼入妳剛申請到的金鑰
API_KEY = "AIzaSyBj3_PVY_8mnxsRfaSqPca7A-Bo2H7S6dE"

genai.configure(api_key=API_KEY)

print("--- 妳的金鑰支援的型號清單如下 ---")
try:
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print(f"型號名稱: {m.name}")
except Exception as e:
    print(f"查詢失敗，原因：{e}")