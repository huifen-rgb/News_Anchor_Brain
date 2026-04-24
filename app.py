import streamlit as st
import google.generativeai as genai
import re
import os

# --- 1. 頁面配置 ---
st.set_page_config(page_title="Producer AI | 專業編播 v17.5", page_icon="📺", layout="wide")

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

# --- 3. API Key 讀取 ---
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    try:
        if hasattr(st, "secrets") and "GEMINI_API_KEY" in st.secrets:
            API_KEY = st.secrets["GEMINI_API_KEY"]
    except: pass

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

def clean_news_text(line):
    """新聞顯示專用：移除所有標點"""
    line = re.sub(r'^[\d\.\s\*\-、\)）]+', '', line)
    line = re.sub(r'[【】\[\]「」『』（）()，。、！？：；,.!?;:]', '', line)
    return force_arabic_numerals(line.replace(" ", "")).strip()

# --- 5. Gemini 核心生成 (2026 對頻) ---
def generate_content(prompt, news_text, expected_lines=None, temperature=0.2):
    if not API_KEY: return None
    genai.configure(api_key=API_KEY)
    
    # 2026 官方穩定型號
   model_candidates = [
    "gemini-2.5-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-pro",
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
            last_error = f"[{model_name}] {str(e)}"
            continue
    return [f"連線失敗//訊號中斷//原因:{last_error}"]

# --- 6. 邏輯校對函數 ---
def is_valid_line(line, min_l, max_l, anchor_text=""):
    if line.count("//") != 2: return False
    parts = line.split("//")
    if len(parts) != 3: return False
    p1, p2, p3 = parts
    if anchor_text and p1 != anchor_text: return False
    return min_l <= len(p1) <= max_l # 這裡簡化檢查，主標邏輯在 UI 層處理

def get_expected_anchor(anchors, mode, idx, total):
    if not anchors: return ""
    if mode == 1: return anchors[0]
    if mode == 2: return anchors[0] if idx < total // 2 else anchors[-1]
    s1, s2 = total // 3, (total // 3) * 2
    if idx < s1: return anchors[0]
    if idx < s2: return anchors[s1] if len(anchors) > s1 else anchors[-1]
    return anchors[-1]

# --- 7. UI 與執行 ---
st.title("📺 Producer AI 智慧分流系統 v17.5")

with st.sidebar:
    st.header("⚙️ 編播控制台")
    if not API_KEY:
        API_KEY = st.text_input("Gemini API Key", type="password")
    anchor_mode = st.radio("1. 指定主標數量", [1, 2, 3], index=1)
    line_total = st.slider("2. 大事框行數", 3, 12, 6)
    side_line_total = st.slider("3. 側標行數", 1, 5, 3)
    auto_regen = st.checkbox("自動重生錯誤行", value=True)

col_in, col_out = st.columns([2, 3])

with col_in:
    news_input = st.text_area("📝 貼入原始稿件", height=250)
    highlights = st.text_area("💡 重點提示 (必含)", height=100)
    btn1, btn2 = st.columns(2)
    run_btn = btn1.button("🚀 大事框", use_container_width=True)
    side_btn = btn2.button("🏷️ 10字側標", use_container_width=True)

with col_out:
    if run_btn and news_input:
        with st.spinner("製作人審稿中..."):
            prompt = f"製作人任務：產出 {line_total} 條大事框。格式：主標//內容//細節。字數：7-8//7-9//7-9。主標分組：{anchor_mode}。重點：{highlights}。"
            results = generate_content(prompt, news_input, line_total)
            
            if results and "//" in results[0]:
                copy_text = ""
                clean_lines = [clean_news_text(l) for l in results]
                # 抓取主標樣板
                sample_anchors = [l.split("//")[0] for l in clean_lines if "//" in l]
                
                for i, line in enumerate(clean_lines):
                    if line.count("//") == 2:
                        p1, p2, p3 = line.split("//")
                        # 定錨強制校正
                        expected = get_expected_anchor(sample_anchors, anchor_mode, i, line_total)
                        if expected: p1 = expected
                        
                        l1, l2, l3 = len(p1), len(p2), len(p3)
                        t1 = f"({l1}字)" if 7<=l1<=8 else f"({l1}字⚠️)"
                        st.markdown(f'<div class="news-box"><span class="anchor-text">{p1}</span>{t1}<span class="separator">//</span>{p2}<span class="separator">//</span>{p3}</div>', unsafe_allow_html=True)
                        copy_text += f"{p1}//{p2}//{p3}\n"
                st.text_area("📋 複製區", value=copy_text.strip(), height=150)
            else:
                st.error(results[0] if results else "生成失敗")

    if side_btn and news_input:
        with st.spinner("生成側標中..."):
            side_prompt = f"側標編輯任務：產出 {side_line_total} 條側標。每行精準 10 字。禁止標點。重點：{highlights}。"
            results = generate_content(side_prompt, news_input, side_line_total)
            if results:
                copy_text = ""
                for line in results:
                    clean_l = clean_news_text(line)
                    st.markdown(f'<div class="side-box">{clean_l} ({len(clean_l)}字)</div>', unsafe_allow_html=True)
                    copy_text += clean_l + "\n"
                st.text_area("📋 複製區", value=copy_text.strip(), height=150)
