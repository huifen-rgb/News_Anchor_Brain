import streamlit as st
import google.generativeai as genai
import re
import os

# --- 頁面配置 ---
st.set_page_config(page_title="Producer AI | 專業編播 v17.2", page_icon="📺", layout="wide")

# --- 專業新聞樣式 ---
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
    .char-badge { font-size: 14px; margin-left: 4px; font-weight: bold; }
    .char-ok { color: #888; }
    .char-warn { color: #ff4b4b; }
    .anchor-text { color: #e63946; font-weight: 900; }
    .separator { color: #f1faee; font-weight: bold; opacity: 0.3; padding: 0 4px; }
    </style>
""", unsafe_allow_html=True)

# --- API_KEY 抓取 ---
try:
    API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
except Exception:
    API_KEY = os.environ.get("GEMINI_API_KEY", "")

# --- 工具：中文數字轉阿拉伯數字 ---
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

# --- 大事框 Prompt ---
def get_system_prompt(anchor_count, line_count, highlights):
    base = f"""
    你是一位19年資歷的電視新聞製作人。任務：產出 {line_count} 條大事框。
    規格：每一行必須剛好是 [主標]//[內容]//[細節]
    
    【絕對限制】：
    1. 總共「只能輸出 {line_count} 行」。
    2. 第一段主標：7-8字。
    3. 第二、三段：7-9字。
    4. 數字必須使用阿拉伯數字。
    """
    highlight_logic = f"\n【製作人特別交辦】：\n{highlights}" if highlights else ""
    if anchor_count == 1:
        strategy = f"\n【定錨命令】：請擬定 1 個主標，這 {line_count} 條的第一段必須完全相同。"
    elif anchor_count == 2:
        split = line_count // 2
        strategy = f"\n【定錨命令】：前 {split} 條用主標A，其餘用主標B。"
    else:
        s1, s2 = line_count // 3, (line_count // 3) * 2
        strategy = f"\n【定錨命令】：分為A、B、C三組主標。"

    return f"{base}{highlight_logic}{strategy}\n【內容遞進】：內容禁止重複。直接輸出結果。"

# --- 側標 Prompt ---
def get_side_slogan_prompt(line_count, highlights):
    return f"""
    任務：產出 {line_count} 條側標。字數必須精準 10 個字。
    規則：禁止標點、數字用阿拉伯數字、不准重複。直接輸出 {line_count} 行。
    【特別要求】：{highlights}
    """

def clean_ai_output(line):
    line = re.sub(r'^[\d\.\s\*\-、\)）]+', '', line)
    line = re.sub(r'[【】\[\]「」『』（）()，。、！？：；,.!?;:]', '', line)
    return force_arabic_numerals(line.replace(" ", "")).strip()

def generate_content(prompt, news_text, expected_lines):
    if not API_KEY: return None
    genai.configure(api_key=API_KEY)
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview", system_instruction=prompt)
    try:
        response = model.generate_content(f"稿件：\n{news_text}", generation_config={"temperature": 0.2})
        all_lines = [l.strip() for l in response.text.strip().split('\n') if l.strip()]
        return all_lines[:expected_lines] 
    except Exception as e:
        return [f"錯誤//重試//原因:{str(e)[:15]}"]

# --- 字數檢查顯示 ---
def get_char_count_html(text, min_l, max_l):
    l = len(text)
    cls = "char-ok" if min_l <= l <= max_l else "char-warn"
    return f'<span class="char-badge {cls}">({l}字)</span>'

# --- UI ---
st.title("📺 Producer AI 智慧分流管理系統 v17.2")

with st.sidebar:
    st.header("⚙️ 編播智慧控制")
    if not API_KEY:
        API_KEY = st.text_input("Gemini API Key", type="password")
    anchor_mode = st.radio("1. 指定主標數量", [1, 2, 3], index=0)
    format_type = st.radio("2. 鏡面格式", ["完整三段", "僅後二段"], index=1)
    line_total = st.slider("3. 產出行數", 3, 12, 6)
    side_line_total = st.slider("4. 側標行數", 1, 5, 3)

col_in, col_out = st.columns([2, 3])

with col_in:
    news_input = st.text_area("📝 貼入原始稿件", height=250)
    highlights = st.text_area("💡 重點提示", height=100)
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1: run_btn = st.button("🚀 執行：大事框", use_container_width=True)
    with btn_col2: side_btn = st.button("🏷️ 執行：10字側標", use_container_width=True)

with col_out:
    if run_btn and news_input:
        with st.spinner("正在對齊主標邏輯中..."):
            results = generate_content(get_system_prompt(anchor_mode, line_total, highlights), news_input, line_total)
            if results:
                copy_text_list = []
                for i, line in enumerate(results):
                    clean_line = clean_ai_output(line)
                    parts = clean_line.split("//")
                    
                    if len(parts) == 3:
                        p1, p2, p3 = parts
                        
                        if format_type == "僅後二段":
                            # 核心修正：只顯示並複製後兩段
                            c2 = get_char_count_html(p2, 7, 9)
                            c3 = get_char_count_html(p3, 7, 9)
                            st.markdown(f'<div class="news-box">{p2}{c2}<span class="separator">//</span>{p3}{c3}</div>', unsafe_allow_html=True)
                            copy_text_list.append(f"{p2}//{p3}")
                        else:
                            # 顯示完整三段
                            c1 = get_char_count_html(p1, 7, 8)
                            c2 = get_char_count_html(p2, 7, 9)
                            c3 = get_char_count_html(p3, 7, 9)
                            st.markdown(f'<div class="news-box"><span class="anchor-text">{p1}</span>{c1}<span class="separator">//</span>{p2}{c2}<span class="separator">//</span>{p3}{c3}</div>', unsafe_allow_html=True)
                            copy_text_list.append(clean_line)
                
                st.text_area("📋 複製區 (直接貼入鏡面)", value="\n".join(copy_text_list), height=150)

    if side_btn and news_input:
        with st.spinner("生成10字側標中..."):
            results = generate_content(get_side_slogan_prompt(side_line_total, highlights), news_input, side_line_total)
            if results:
                copy_text = ""
                for line in results:
                    clean_line = clean_ai_output(line)
                    c_html = get_char_count_html(clean_line, 10, 10)
                    st.markdown(f'<div class="side-box">{clean_line}{c_html}</div>', unsafe_allow_html=True)
                    copy_text += f"{clean_line}\n"
                st.text_area("📋 複製區 (側標)", value=copy_text.strip(), height=150)

# --- 訊號檢查模組 (檢查完可刪除) ---
if st.sidebar.button("🔍 檢查 API 支援型號"):
    if not API_KEY:
        st.error("請先輸入或設定 API Key")
    else:
        try:
            genai.configure(api_key=API_KEY)
            st.write("### 📡 目前 API Key 支援的型號清單：")
            
            # 列出所有支援 generateContent 的模型
            available_models = []
            for m in genai.list_models():
                if 'generateContent' in m.supported_generation_methods:
                    available_models.append(m.name)
            
            # 以表格或清單顯示
            st.table(available_models)
            
        except Exception as e:
            st.error(f"無法抓取型號清單，原因：{str(e)}")
