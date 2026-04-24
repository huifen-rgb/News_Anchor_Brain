import streamlit as st
import google.generativeai as genai
import re
import os  # <--- 加入這一行

# --- 頁面配置 ---
st.set_page_config(page_title="Producer AI | 專業編播 v17.1", page_icon="📺", layout="wide")

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
    .char-warn { font-size: 12px; color: #ff4b4b; margin-left: 4px; font-weight: bold; }
    .char-ok { font-size: 12px; color: #888; margin-left: 4px; }
    .anchor-text { color: #e63946; font-weight: 900; }
    .separator { color: #f1faee; font-weight: bold; opacity: 0.5; padding: 0 4px; }
    .highlight-note { color: #ffb703; font-size: 14px; font-weight: bold; margin-bottom: 5px; }
    .regen-note { color: #ffb703; font-size: 13px; font-weight: bold; }
    </style>
""", unsafe_allow_html=True)

# --- 強效版 API_KEY 抓取邏輯 ---
try:
    # 優先嘗試從 Streamlit Secrets 讀取
    API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))
except Exception:
    # 如果完全沒有 Secrets 檔案 (如 Render 環境)，直接抓系統環境變數
    API_KEY = os.environ.get("GEMINI_API_KEY", "")

# 偵錯用：如果還是空的，在頁面上提醒妳 (部署成功後可刪除這行)
if not API_KEY:
    st.error("⚠️ 尚未偵測到 API Key，請檢查 Render 的 Environment Variables 設定。")

# --- 工具：中文數字轉阿拉伯數字 ---
def force_arabic_numerals(text):
    # 先處理二位數邏輯，避免十一變成101
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

# --- 原有大事框 Prompt ---
def get_system_prompt(anchor_count, line_count, highlights):
    base = f"""
    你是一位19年資歷的電視新聞製作人。任務：產出 {line_count} 條大事框。
    規格：每一行必須剛好是 [主標]//[內容]//[細節]
    
    【絕對限制】：
    1. 總共「只能輸出 {line_count} 行」，禁止多吐文字。
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
        strategy = f"\n【定錨命令】：分為A、B、C三組主標（分組點：{s1}, {s2}）。"

    return f"{base}{highlight_logic}{strategy}\n【內容遞進】：內容禁止重複。直接輸出結果，不准廢話。"

# --- 10字側標 Prompt ---
def get_side_slogan_prompt(line_count, highlights):
    return f"""
    任務：產出 {line_count} 條側標。字數必須精準 10 個字。
    規則：禁止標點、數字用阿拉伯數字、不准重複。直接輸出 {line_count} 行。
    【特別要求】：{highlights}
    """

# --- 清理 AI 文字 ---
def clean_ai_output(line):
    line = re.sub(r'^[\d\.\s\*\-、\)）]+', '', line)
    line = re.sub(r'[【】\[\]「」『』（）()，。、！？：；,.!?;:]', '', line)
    return force_arabic_numerals(line.replace(" ", "")).strip()

# --- Gemini 呼叫 (加入溫度控制與物理截斷) ---
def generate_content(prompt, news_text, expected_lines):
    if not API_KEY: return None
    genai.configure(api_key=API_KEY)
    # 使用 3.1 Flash Lite 以獲得最佳邏輯理解
    model = genai.GenerativeModel(model_name="gemini-3.1-flash-lite-preview", system_instruction=prompt)
    try:
        response = model.generate_content(
            f"稿件：\n{news_text}",
            generation_config={"temperature": 0.2} # 降低溫度確保精準度
        )
        # 物理截斷：只拿前 N 行
        all_lines = [l.strip() for l in response.text.strip().split('\n') if l.strip()]
        return all_lines[:expected_lines] 
    except Exception as e:
        return [f"錯誤//重試//原因:{str(e)[:15]}"]

# --- 驗證大事框單行 ---
def is_valid_big_event_line(line, anchor_text=""):
    if line.count("//") != 2: return False
    parts = line.split("//")
    if len(parts) != 3: return False
    p1, p2, p3 = parts
    if anchor_text and p1 != anchor_text: return False
    return 7 <= len(p1) <= 8 and 7 <= len(p2) <= 9 and 7 <= len(p3) <= 9

# --- 側標與大事框單行重生邏輯維持原樣 (省略以節省空間，請沿用妳 v17.0 的函數) ---
# [此處請保留妳原本 v17.0 的 regenerate_big_event_line 與 regenerate_side_line]

def get_expected_anchor_for_index(anchors, anchor_mode, index, total_lines):
    if not anchors: return ""
    if anchor_mode == 1: return anchors[0]
    if anchor_mode == 2: return anchors[0] if index < total_lines // 2 else anchors[-1]
    s1, s2 = total_lines // 3, (total_lines // 3) * 2
    if index < s1: return anchors[0]
    if index < s2: return anchors[s1] if len(anchors) > s1 else anchors[-1]
    return anchors[-1]

# --- UI 介面 ---
st.title("📺 Producer AI 智慧分流管理系統 v17.1")

with st.sidebar:
    st.header("⚙️ 編播智慧控制")
    if not API_KEY:
        API_KEY = st.text_input("Gemini API Key", type="password")
    anchor_mode = st.radio("1. 指定主標數量", [1, 2, 3], index=1)
    format_type = st.radio("2. 鏡面格式", ["完整三段", "僅後二段"])
    line_total = st.slider("3. 產出行數", 3, 12, 6)
    side_line_total = st.slider("4. 側標行數", 1, 5, 3)
    auto_regen = st.checkbox("自動重生錯誤行", value=True)

col_in, col_out = st.columns([2, 3])

with col_in:
    news_input = st.text_area("📝 貼入原始稿件", height=250)
    highlights = st.text_area("💡 重點提示", height=100)
    btn_col1, btn_col2 = st.columns(2)
    with btn_col1: run_btn = st.button("🚀 執行：大事框", use_container_width=True)
    with btn_col2: side_btn = st.button("🏷️ 執行：10字側標", use_container_width=True)

with col_out:
    if run_btn and news_input:
        with st.spinner("正在精準對齊行數中..."):
            results = generate_content(get_system_prompt(anchor_mode, line_total, highlights), news_input, line_total)
            if results:
                copy_text = ""
                clean_lines = [clean_ai_output(l) for l in results]
                
                # 抓取第一遍產出的主標樣板
                anchors_sample = [l.split("//")[0] for l in clean_lines if "//" in l]
                
                for i, clean_line in enumerate(clean_lines):
                    expected_anchor = get_expected_anchor_for_index(anchors_sample, anchor_mode, i, line_total)
                    # 進行驗證與重生邏輯... (其餘顯示邏輯與妳 v17.0 完全一致)
                    # [這裡繼續跑妳原本的顯示與 text_area 邏輯]
                    parts = clean_line.split("//")
                    if len(parts) == 3:
                        p1, p2, p3 = parts
                        l1, l2, l3 = len(p1), len(p2), len(p3)
                        t1 = f'({l1}字)'
                        st.markdown(f'<div class="news-box"><span class="anchor-text">{p1}</span>{t1}<span class="separator">//</span>{p2}<span class="separator">//</span>{p3}</div>', unsafe_allow_html=True)
                        copy_text += f"{clean_line}\n"
                
                st.text_area("📋 複製區", value=copy_text.strip(), height=150)

    if side_btn and news_input:
        with st.spinner("生成10字側標中..."):
            results = generate_content(get_side_slogan_prompt(side_line_total, highlights), news_input, side_line_total)
            if results:
                copy_text = ""
                for line in results:
                    clean_line = clean_ai_output(line)
                    st.markdown(f'<div class="side-box">{clean_line}</div>', unsafe_allow_html=True)
                    copy_text += f"{clean_line}\n"
                st.text_area("📋 複製區 (側標)", value=copy_text.strip(), height=150)
