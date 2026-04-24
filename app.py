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
    .char-warn { font-size: 12px; color: #ff4b4b; margin-left: 4px; font-weight: bold; }
    .char-ok { font-size: 12px; color: #888; margin-left: 4px; }
    .anchor-text { color: #e63946; font-weight: 900; }
    .separator { color: #f1faee; font-weight: bold; opacity: 0.5; padding: 0 4px; }
    .highlight-note { color: #ffb703; font-size: 14px; font-weight: bold; margin-bottom: 5px; }
    .regen-note { color: #ffb703; font-size: 13px; font-weight: bold; margin-bottom: 4px; }
    </style>
""", unsafe_allow_html=True)

# --- API Key 獲取 (相容 Streamlit Cloud 與 Render) ---
API_KEY = st.secrets.get("GEMINI_API_KEY", os.environ.get("GEMINI_API_KEY", ""))

if not API_KEY:
    st.error("⚠️ 偵測不到 API 金鑰！請在側邊欄手動輸入或設定環境變數。")

# --- 工具：中文數字轉阿拉伯數字 ---
def force_arabic_numerals(text):
    zh_digit = {
        "零": 0, "〇": 0, "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9
    }
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

# --- 清理 AI 文字 ---
def clean_ai_output(line):
    line = re.sub(r'^[\d\.\s\*\-、\)）]+', '', line)
    line = re.sub(r'[【】\[\]「」『』（）()，。、！？：；,.!?;:]', '', line)
    return force_arabic_numerals(line.replace(" ", "")).strip()

# --- 大事框 Prompt ---
def get_system_prompt(anchor_count, line_count, highlights):
    base = f"你是一位19年資歷的電視新聞製作人。任務：產出 {line_count} 條大事框。\n規格：主標//內容//細節\n【字數】主標7-8字，其餘7-9字。"
    highlight_logic = f"\n【重點交辦】：\n{highlights}\n" if highlights else ""
    if anchor_count == 1:
        strategy = f"\n【定錨】1個主標，全數一致。"
    elif anchor_count == 2:
        split = line_count // 2
        strategy = f"\n【定錨】前 {split} 條主標A，其餘主標B。"
    else:
        s1, s2 = line_count // 3, (line_count // 3) * 2
        strategy = f"\n【定錨】分A、B、C三組主標（分界：{s1}, {s2}）。"
    return f"{base}{highlight_logic}{strategy}\n數字用阿拉伯數字，禁止標點空行。直接輸出，不准廢話。"

# --- 10字側標 Prompt ---
def get_side_slogan_prompt(line_count, highlights):
    return f"電視資深編輯任務：產出 {line_count} 條新聞側標。每行精準10字，數字用阿拉伯數字，禁止標點。內容聚焦細節而非概括。重點：{highlights}"

# --- Gemini 呼叫：低溫 + 物理截斷 + 模型 fallback ---
def generate_content(prompt, news_text, expected_lines=None, temperature=0.2):
    if not API_KEY: return None
    genai.configure(api_key=API_KEY)
    
    # 修正縮排與型號名稱
    model_candidates = ["gemini-3.1-flash-lite", "gemini-1.5-pro", "gemini-1.5-flash"]
    
    last_error = ""
    for model_name in model_candidates:
        try:
            model = genai.GenerativeModel(model_name=model_name, system_instruction=prompt)
            response = model.generate_content(f"稿件：\n{news_text}", generation_config={"temperature": temperature})
            all_lines = [l.strip() for l in response.text.strip().split("\n") if l.strip()]
            if expected_lines: return all_lines[:expected_lines]
            return all_lines
        except Exception as e:
            last_error = str(e)[:80]
            continue
    return [f"連線失敗//重試//原因:{last_error}"]

# --- 驗證與重生邏輯 (為了精簡空間，以下維持妳原本的 is_valid_big_event_line, regenerate 等函數邏輯) ---
def is_valid_big_event_line(line, anchor_text=""):
    if line.count("//") != 2: return False
    parts = line.split("//")
    if len(parts) != 3: return False
    p1, p2, p3 = parts
    if anchor_text and p1 != anchor_text: return False
    return 7 <= len(p1) <= 8 and 7 <= len(p2) <= 9 and 7 <= len(p3) <= 9

def get_expected_anchor_for_index(anchors, anchor_mode, index, total_lines):
    if not anchors: return ""
    if anchor_mode == 1: return anchors[0]
    if anchor_mode == 2: return anchors[0] if index < total_lines // 2 else anchors[-1]
    s1, s2 = total_lines // 3, (total_lines // 3) * 2
    if index < s1: return anchors[0]
    if index < s2: return anchors[s1] if len(anchors) > s1 else anchors[-1]
    return anchors[-1]

def regenerate_big_event_line(news_text, bad_line, highlights, anchor_text="", max_retry=2):
    if not API_KEY: return bad_line, False
    fix_prompt = f"修正這行大事框：{bad_line}\n主標須為：{anchor_text if anchor_text else '7-8字'}\n字數：7-8//7-9//7-9\n提示：{highlights}"
    for _ in range(max_retry):
        lines = generate_content(fix_prompt, news_text, expected_lines=1, temperature=0.1)
        if not lines: continue
        fixed = clean_ai_output(lines[0])
        if is_valid_big_event_line(fixed, anchor_text): return fixed, True
    return bad_line, False

def regenerate_side_line(news_text, bad_line, highlights, max_retry=2):
    if not API_KEY: return bad_line, False
    fix_prompt = f"修正這行側標為精準10字：{bad_line}\n提示：{highlights}"
    for _ in range(max_retry):
        lines = generate_content(fix_prompt, news_text, expected_lines=1, temperature=0.1)
        if not lines: continue
        fixed = clean_ai_output(lines[0])
        if len(fixed) == 10: return fixed, True
    return bad_line, False

# --- UI 介面 (延續妳的配置) ---
st.title("📺 Producer AI 智慧分流管理系統 v17.2")
with st.sidebar:
    st.header("⚙️ 編播控制台")
    if not API_KEY: API_KEY = st.text_input("Gemini API Key", type="password")
    anchor_mode = st.radio("1. 主標數量", [1, 2, 3], index=1)
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
        with st.spinner("正在編排大事框..."):
            results = generate_content(get_system_prompt(anchor_mode, line_total, highlights), news_input, line_total)
            if results:
                copy_text = ""
                clean_results = [clean_ai_output(l) for l in results]
                anchors_sample = [l.split("//")[0] for l in clean_results if l.count("//") == 2]
                for i, clean_line in enumerate(clean_results):
                    expected_anchor = get_expected_anchor_for_index(anchors_sample, anchor_mode, i, line_total)
                    valid = is_valid_big_event_line(clean_line, expected_anchor)
                    if not valid and auto_regen:
                        clean_line, ok = regenerate_big_event_line(news_input, clean_line, highlights, expected_anchor)
                        if ok: st.markdown(f'<div class="regen-note">🔁 第 {i+1} 行已重生</div>', unsafe_allow_html=True)
                    if clean_line.count("//") == 2:
                        p1, p2, p3 = clean_line.split("//")
                        l1, l2, l3 = len(p1), len(p2), len(p3)
                        t1 = f'({l1}字)' if 7<=l1<=8 else f'({l1}字⚠️)'
                        if "僅後二段" in format_type:
                            st.markdown(f'<div class="news-box">{p2}<span class="separator">//</span>{p3}</div>', unsafe_allow_html=True)
                            copy_text += f"{p2}//{p3}\n"
                        else:
                            st.markdown(f'<div class="news-box"><span class="anchor-text">{p1}</span><span class="char-ok">{t1}</span><span class="separator">//</span>{p2}<span class="separator">//</span>{p3}</div>', unsafe_allow_html=True)
                            copy_text += f"{clean_line}\n"
                st.text_area("📋 複製區 (大事框)", value=copy_text.strip(), height=150)

    if side_btn and news_input:
        with st.spinner("生成側標中..."):
            results = generate_content(get_side_slogan_prompt(side_line_total, highlights), news_input, side_line_total)
            if results:
                copy_text = ""
                for i, line in enumerate(results):
                    clean_line = clean_ai_output(line)
                    if len(clean_line) != 10 and auto_regen:
                        clean_line, ok = regenerate_side_line(news_input, clean_line, highlights)
                    st.markdown(f'<div class="side-box">{clean_line} ({len(clean_line)}字)</div>', unsafe_allow_html=True)
                    copy_text += f"{clean_line}\n"
                st.text_area("📋 複製區 (側標)", value=copy_text.strip(), height=150)
