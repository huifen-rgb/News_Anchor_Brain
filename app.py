import streamlit as st
import google.generativeai as genai
import re
import os

# --- 1. 頁面配置 ---
st.set_page_config(page_title="Producer AI | 專業編播 v17.3", page_icon="📺", layout="wide")

# --- 2. 專業新聞視覺樣式 ---
st.markdown("""
    <style>
    .main { background-color: #121212; color: white; }
    .news-box {
        background-color: #1a1a1a;
        padding: 16px;
        border-left: 14px solid #e63946;
        margin-bottom: 12px;
        border-radius: 4px;
        font-family: "Microsoft JhengHei", sans-serif;
        font-size: 24px;
        letter-spacing: 1px;
    }
    .side-box {
        background-color: #1a1a1a;
        padding: 12px 16px;
        border-left: 14px solid #3a86ff;
        margin-bottom: 10px;
        border-radius: 4px;
        font-family: "Microsoft JhengHei", sans-serif;
        font-size: 26px;
        font-weight: bold;
        color: #f1faee;
    }
    .char-warn { font-size: 12px; color: #ff4b4b; margin-left: 4px; font-weight: bold; }
    .char-ok { font-size: 12px; color: #888; margin-left: 4px; }
    .anchor-text { color: #e63946; font-weight: 900; }
    .separator { color: #f1faee; font-weight: bold; opacity: 0.5; padding: 0 4px; }
    .highlight-note { color: #ffb703; font-size: 14px; font-weight: bold; margin-bottom: 5px; }
    .regen-note { color: #ffb703; font-size: 13px; font-weight: bold; margin-bottom: 4px; }
    </style>
""", unsafe_allow_html=True)

# --- 3. 安全 API Key 讀取邏輯 (解決 Render 崩潰問題) ---
API_KEY = os.environ.get("GEMINI_API_KEY") # 優先讀取 Render 環境變數

if not API_KEY:
    try:
        # 僅在本地或 Streamlit Cloud 嘗試讀取 secrets
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            API_KEY = st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass

# --- 4. 專業工具函數 ---
def force_arabic_numerals(text):
    zh_digit = {"零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    def convert_under_100(match):
        s = match.group(0)
        if s == "十": return "10"
        if "十" in s:
            left, right = s.split("十", 1)
            tens = zh_digit.get(left, 1) if left else 1
            ones = zh_digit.get(right, 0) if right else 0
            return str(tens * 10 + ones)
        return str(zh_digit.get(s, s))
    text = re.sub(r'[一二兩三四五六七八九]?十[一二兩三四五六七八九]?', convert_under_100, text)
    for zh, ar in {"零":"0","〇":"0","一":"1","二":"2","兩":"2","三":"3","四":"4","五":"5","六":"6","七":"7","八":"8","九":"9"}.items():
        text = text.replace(zh, ar)
    return text

def clean_ai_output(line):
    line = re.sub(r'^[\d\.\s\*\-、\)）]+', '', line)
    line = re.sub(r'[【】\[\]「」『』（）()，。、！？：；,.!?;:]', '', line)
    return force_arabic_numerals(line.replace(" ", "")).strip()

# --- 修正後的「2026 旗艦」模型清單 ---
def generate_content(prompt, news_text, expected_lines=None, temperature=0.2):
    if not API_KEY:
        return None

    genai.configure(api_key=API_KEY)

# --- 工具：清理 AI 文字 (修正：不再刪除小數點) ---
def clean_ai_output(line):
    # 移除標點符號，但保留小數點 . 避免破壞模型名稱與數據
    line = re.sub(r'^[\d\.\s\*\-、\)）]+', '', line)
    line = re.sub(r'[【】\[\]「」『』（）()，。、！？：；,!?;:]', '', line) # 這裡移除了點號
    return force_arabic_numerals(line.replace(" ", "")).strip()

# --- Gemini 呼叫：2026 旗艦對頻 ---
def generate_content(prompt, news_text, expected_lines=None, temperature=0.2):
    if not API_KEY: return None
    genai.configure(api_key=API_KEY)
    
    # 2026 官方標準名稱：優先使用最新的 Gemini 3
    model_candidates = [
        "gemini-3-flash",      # 2026 旗艦：最聰明、對頻最快
        "gemini-1.5-flash",    # 穩定老將
        "gemini-1.5-pro",      # 深度分析
    ]
    
    last_error = ""
    for model_name in model_candidates:
        try:
            model = genai.GenerativeModel(model_name=model_name, system_instruction=prompt)
            response = model.generate_content(f"稿件：\n{news_text}", generation_config={"temperature": temperature})
            all_lines = [l.strip() for l in response.text.strip().split("\n") if l.strip()]
            if expected_lines: return all_lines[:expected_lines]
            return all_lines
        except Exception as e:
            # 這裡記錄原始錯誤，不再透過 clean 函數，讓製作人看清楚
            last_error = f"[{model_name}] {str(e)}"
            continue
    return [f"連線失敗//請檢查後台//原因:{last_error}"]

# --- 6. 字數驗證邏輯 ---
def is_valid_big_event_line(line, anchor_text=""):
    if line.count("//") != 2: return False
    parts = line.split("//")
    if len(parts) != 3: return False
    p1, p2, p3 = parts
    if anchor_text and p1 != anchor_text: return False
    return 7 <= len(p1) <= 8 and 7 <= len(p2) <= 9 and 7 <= len(p3) <= 9

# --- 7. UI 與 執行邏輯 ---
st.title("📺 Producer AI 智慧分流管理系統 v17.3")

with st.sidebar:
    st.header("⚙️ 編播控制台")
    if not API_KEY:
        API_KEY = st.text_input("Gemini API Key", type="password")
    anchor_mode = st.radio("1. 指定主標數量", [1, 2, 3], index=1)
    format_type = st.radio("2. 鏡面格式", ["完整三段", "僅後二段"])
    line_total = st.slider("3. 大事框行數", 3, 12, 6)
    side_line_total = st.slider("4. 側標行數", 1, 5, 3)
    auto_regen = st.checkbox("自動重生錯誤行", value=True)

col_in, col_out = st.columns([2, 3])

with col_in:
    news_input = st.text_area("📝 貼入原始稿件", height=250)
    highlights = st.text_area("💡 重點提示 (AI優先寫入)", height=100)
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1: run_btn = st.button("🚀 執行：大事框", use_container_width=True)
    with btn_col2: side_btn = st.button("🏷️ 執行：10字側標", use_container_width=True)

with col_out:
    if not API_KEY:
        st.warning("請在側邊欄輸入 API Key 或設定環境變數。")
    
    if run_btn and news_input:
        with st.spinner("正在精準編排大事框..."):
            # 獲取大事框 Prompt 並執行
            prompt = f"製作人任務：產出 {line_total} 條大事框。規格：主標//內容//細節。字數：7-8//7-9//7-9。重點：{highlights}。"
            results = generate_content(prompt, news_input, line_total)
            if results:
                copy_text = ""
                for i, line in enumerate(results):
                    clean_line = clean_ai_output(line)
                    if clean_line.count("//") == 2:
                        p1, p2, p3 = clean_line.split("//")
                        st.markdown(f'<div class="news-box">{p1} // {p2} // {p3}</div>', unsafe_allow_html=True)
                        copy_text += clean_line + "\n"
                st.text_area("📋 複製區", value=copy_text.strip(), height=150)

    if side_btn and news_input:
        with st.spinner("生成側標中..."):
            side_prompt = f"側標編輯任務：產出 {side_line_total} 條側標。每行精準 10 字。禁止標點。重點：{highlights}。"
            results = generate_content(side_prompt, news_input, side_line_total)
            if results:
                copy_text = ""
                for line in results:
                    clean_line = clean_ai_output(line)
                    st.markdown(f'<div class="side-box">{clean_line} ({len(clean_line)}字)</div>', unsafe_allow_html=True)
                    copy_text += clean_line + "\n"
                st.text_area("📋 複製區", value=copy_text.strip(), height=150)
