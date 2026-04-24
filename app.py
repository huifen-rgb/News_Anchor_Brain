import streamlit as st
import google.generativeai as genai
import re

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

import os

# --- 核心邏輯：相容 Render 環境變數 ---
API_KEY = ""
try:
    # 1. 嘗試從 Streamlit 內部讀取 (適用於 Streamlit Cloud)
    if "GEMINI_API_KEY" in st.secrets:
        API_KEY = st.secrets["GEMINI_API_KEY"]
    else:
        # 2. 如果找不到，嘗試從 Render 的系統環境變數讀取
        API_KEY = os.environ.get("GEMINI_API_KEY", "")
except Exception:
    # 3. 萬一 st.secrets 直接崩潰，則強制使用系統環境變數
    API_KEY = os.environ.get("GEMINI_API_KEY", "")

# 如果完全沒抓到，給予警告提示（這部分可以幫你 debug）
if not API_KEY:
    st.error("⚠️ 偵測不到 API 金鑰！請確認 Render 環境變數設定。")

# --- 工具：中文數字轉阿拉伯數字 ---
def force_arabic_numerals(text):
    """
    處理 1-99 常見中文數字，避免「十一」變「101」。
    可處理：十、十一、二十、二十一、三十五、兩岸中的「兩」若單獨出現會轉 2。
    """
    zh_digit = {
        "零": 0, "〇": 0,
        "一": 1, "二": 2, "兩": 2, "三": 3, "四": 4,
        "五": 5, "六": 6, "七": 7, "八": 8, "九": 9
    }

    def convert_under_100(match):
        s = match.group(0)
        if s == "十":
            return "10"
        if "十" in s:
            left, right = s.split("十", 1)
            tens = zh_digit.get(left, 1) if left else 1
            ones = zh_digit.get(right, 0) if right else 0
            return str(tens * 10 + ones)
        return str(zh_digit.get(s, s))

    text = re.sub(r'[一二兩三四五六七八九]?十[一二兩三四五六七八九]?', convert_under_100, text)

    for zh, ar in {
        "零": "0", "〇": "0", "一": "1", "二": "2", "兩": "2", "三": "3", "四": "4",
        "五": "5", "六": "6", "七": "7", "八": "8", "九": "9"
    }.items():
        text = text.replace(zh, ar)

    return text

# --- 清理 AI 文字 ---
def clean_ai_output(line):
    line = re.sub(r'^[\d\.\s\*\-、\)）]+', '', line)
    line = re.sub(r'[【】\[\]「」『』（）()，。、！？：；,.!?;:]', '', line)
    line = force_arabic_numerals(line.replace(" ", ""))
    return line.strip()

# --- 大事框 Prompt ---
def get_system_prompt(anchor_count, line_count, highlights):
    base = f"""
你是一位19年資歷的電視新聞製作人。任務：產出 {line_count} 條大事框。

【格式規格】
每一行必須剛好是：
主標//內容//細節

【絕對限制】
1. 總共只能輸出 {line_count} 行，禁止多吐文字。
2. 第一段主標：7-8字。
3. 第二段內容：7-9字。
4. 第三段細節：7-9字。
5. 數字必須使用阿拉伯數字。
6. 禁止標點、括號、表情符號、編號、說明文字。
7. 禁止空行。
"""

    highlight_logic = f"\n【製作人特別交辦】\n{highlights}\n請優先寫入上述重點。\n" if highlights else ""

    if anchor_count == 1:
        strategy = f"\n【定錨命令】請擬定1個主標，這 {line_count} 條第一段必須完全相同。"
    elif anchor_count == 2:
        split = line_count // 2
        strategy = f"\n【定錨命令】前 {split} 條用主標A，其餘用主標B。A與B必須不同，同組第一段必須完全相同。"
    else:
        s1, s2 = line_count // 3, (line_count // 3) * 2
        strategy = f"\n【定錨命令】分為A、B、C三組主標。第1到第{s1}條A，第{s1+1}到第{s2}條B，其餘C。同組第一段必須完全相同。"

    return f"{base}{highlight_logic}{strategy}\n【內容遞進】內容與細節禁止重複，請依稿件發展推進。直接輸出結果，不准廢話。"

# --- 10字側標 Prompt ---
def get_side_slogan_prompt(line_count, highlights):
    return f"""
你是一位電視新聞資深編輯。任務：產出 {line_count} 條新聞側標。

【核心規則】
1. 每行字數必須精準10個字。
2. 總共只能輸出 {line_count} 行。
3. 禁止標點、括號、表情符號、編號、說明文字。
4. 數字必須使用阿拉伯數字。
5. 禁止空行，禁止重複。
6. 不要寫概括主標，要寫具體細節、動作、數據、衝突點或即時狀態。
7. 側標要與常見大事框第一段明顯區隔。

【製作人提示】
{highlights if highlights else "依稿件內容發揮"}

請直接輸出 {line_count} 行文字，每行10字，不要解釋。
"""

# --- Gemini 呼叫：低溫 + 物理截斷 + 模型 fallback ---
def generate_content(prompt, news_text, expected_lines=None, temperature=0.7):
    if not API_KEY:
        return [f"錯誤//偵測不到API Key//請檢查環境變數"]
    
    genai.configure(api_key=API_KEY)
    
    # --- 修正後的模型清單 (確保拼字正確，並移除不穩定的預覽版) ---
    model_candidates = [
        "gemini-1.5-flash",      # 最穩定、速度快
        "gemini-1.5-pro",        # 邏輯更強，適合作為備援
        "gemini-2.0-flash-exp",  # 如果 API 支援，這是目前更強的版本
    ]

    last_error = ""
    for model_name in model_candidates:
        try:
            # 建立模型實例
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=prompt
            )
            
            # 生成內容
            response = model.generate_content(
                f"稿件：\n{news_text}",
                generation_config={
                    "temperature": temperature,
                    "top_p": 0.95,
                    "top_k": 40,
                }
            )
            
            # 檢查回應是否包含有效文字
            if not response.text:
                continue
                
            all_lines = [l.strip() for l in response.text.strip().split("\n") if l.strip()]
            
            # 如果有指定行數，則進行裁切；否則全部回傳
            if expected_lines:
                return all_lines[:expected_lines]
            return all_lines

        except Exception as e:
            # 擷取錯誤訊息以便除錯
            last_error = str(e).replace(" ", "") # 移除空格方便辨識
            continue # 嘗試下一個模型

    # 如果所有模型都失敗，回傳最後一個錯誤
    return [f"系統//連線失敗//原因:{last_error[:50]}"]

# --- 驗證大事框單行 ---
def is_valid_big_event_line(line, anchor_text=""):
    if line.count("//") != 2:
        return False

    parts = line.split("//")
    if len(parts) != 3:
        return False

    p1, p2, p3 = parts

    if anchor_text and p1 != anchor_text:
        return False

    return 7 <= len(p1) <= 8 and 7 <= len(p2) <= 9 and 7 <= len(p3) <= 9

# --- 預期主標判斷 ---
def get_expected_anchor_for_index(anchors, anchor_mode, index, total_lines):
    if not anchors:
        return ""

    if anchor_mode == 1:
        return anchors[0]

    if anchor_mode == 2:
        split = total_lines // 2
        return anchors[0] if index < split else anchors[-1]

    s1, s2 = total_lines // 3, (total_lines // 3) * 2
    if index < s1:
        return anchors[0]
    if index < s2:
        return anchors[s1] if len(anchors) > s1 else anchors[-1]
    return anchors[-1]

# --- 單行自動重生：大事框 ---
def regenerate_big_event_line(news_text, bad_line, highlights, anchor_text="", max_retry=2):
    if not API_KEY:
        return bad_line, False

    anchor_rule = f"第一段主標必須完全使用：{anchor_text}" if anchor_text else "第一段主標必須7到8字"

    fix_prompt = f"""
你是一位電視新聞製作人。請只修正下面這一行大事框。

【原錯誤行】
{bad_line}

【製作人提示】
{highlights if highlights else "依稿件內容修正"}

【強制格式】
主標//內容//細節

【主標規則】
{anchor_rule}

【字數規則】
主標7到8字，內容7到9字，細節7到9字

【禁止】
標點、括號、編號、說明文字、空行

【數字】
一律使用阿拉伯數字

請只輸出修正後的單行，不要解釋。
"""

    current = bad_line
    for _ in range(max_retry):
        lines = generate_content(fix_prompt, news_text, expected_lines=1, temperature=0.1)
        if not lines:
            continue
        fixed = clean_ai_output(lines[0])
        if is_valid_big_event_line(fixed, anchor_text):
            return fixed, True
        current = fixed

    return current, False

# --- 單行自動重生：側標 ---
def regenerate_side_line(news_text, bad_line, highlights, max_retry=2):
    if not API_KEY:
        return bad_line, False

    fix_prompt = f"""
你是一位電視新聞側標編輯。請只修正下面這一行側標。

【原錯誤行】
{bad_line}

【製作人提示】
{highlights if highlights else "依稿件內容修正"}

【強制規則】
1. 必須精準10個字。
2. 禁止標點、括號、編號、說明文字、空行。
3. 必須使用阿拉伯數字。
4. 不要寫概括主標，要寫具體細節、動作、數據、狀態。

請只輸出修正後的10字側標，不要解釋。
"""

    current = bad_line
    for _ in range(max_retry):
        lines = generate_content(fix_prompt, news_text, expected_lines=1, temperature=0.1)
        if not lines:
            continue
        fixed = clean_ai_output(lines[0])
        if len(fixed) == 10:
            return fixed, True
        current = fixed

    return current, False

# --- UI 介面 ---
st.title("📺 Producer AI 智慧分流管理系統 v17.2")

with st.sidebar:
    st.header("⚙️ 編播智慧控制")

    if not API_KEY:
        API_KEY = st.text_input("Gemini API Key", type="password")

    st.subheader("🔹 大事框設定")
    anchor_mode = st.radio("1. 指定主標數量", [1, 2, 3], index=1)
    format_type = st.radio("2. 鏡面格式", ["完整三段", "僅後二段"])
    line_total = st.slider("3. 產出行數", 3, 12, 6)

    st.divider()
    st.subheader("🔸 側標設定")
    side_line_total = st.slider("4. 側標行數", 1, 5, 3)

    st.divider()
    st.subheader("🛠️ 自動修正")
    auto_regen = st.checkbox("自動重生錯誤行", value=True)

col_in, col_out = st.columns([2, 3])

with col_in:
    news_input = st.text_area("📝 貼入原始稿件", height=250)
    highlights = st.text_area("💡 重點提示", height=100)

    btn_col1, btn_col2 = st.columns(2)
    with btn_col1:
        run_btn = st.button("🚀 執行：大事框", use_container_width=True)
    with btn_col2:
        side_btn = st.button("🏷️ 執行：10字側標", use_container_width=True)

with col_out:
    # --- 處理大事框 ---
    if run_btn and news_input:
        with st.spinner("正在精準編排大事框中..."):
            results = generate_content(
                get_system_prompt(anchor_mode, line_total, highlights),
                news_input,
                expected_lines=line_total,
                temperature=0.2
            )

            copy_text = ""
            clean_results = []

            if results:
                if len(results) != line_total:
                    st.warning(f"⚠️ AI輸出行數異常：預期 {line_total} 行，實際 {len(results)} 行")

                clean_results = [clean_ai_output(line) for line in results]

                anchors_sample = []
                for line in clean_results:
                    if line.count("//") == 2:
                        anchors_sample.append(line.split("//")[0])

                final_lines = []

                for i, clean_line in enumerate(clean_results):
                    expected_anchor = get_expected_anchor_for_index(
                        anchors_sample,
                        anchor_mode,
                        i,
                        line_total
                    )

                    valid = is_valid_big_event_line(clean_line, expected_anchor if expected_anchor else "")

                    if not valid and auto_regen:
                        fixed_line, fixed_ok = regenerate_big_event_line(
                            news_input,
                            clean_line,
                            highlights,
                            expected_anchor
                        )
                        if fixed_ok:
                            st.markdown(
                                f'<div class="regen-note">🔁 第 {i+1} 行已自動重生</div>',
                                unsafe_allow_html=True
                            )
                            clean_line = fixed_line
                        else:
                            st.error(f"❌ 第 {i+1} 行自動重生仍未合格：{fixed_line}")
                            clean_line = fixed_line

                    elif not valid:
                        st.error(f"❌ 第 {i+1} 行格式或字數錯誤：{clean_line}")

                    if clean_line.count("//") != 2:
                        continue

                    final_lines.append(clean_line)

                # --- 主標一致性檢查 ---
                final_anchors = [line.split("//")[0] for line in final_lines if line.count("//") == 2]

                if anchor_mode == 1 and final_anchors and len(set(final_anchors)) != 1:
                    st.warning("⚠️ 主標不一致（應全部相同）")

                elif anchor_mode == 2 and final_anchors:
                    split = line_total // 2
                    group_a = final_anchors[:split]
                    group_b = final_anchors[split:]
                    if (group_a and len(set(group_a)) != 1) or (group_b and len(set(group_b)) != 1):
                        st.warning("⚠️ 兩組主標未正確分組")

                elif anchor_mode == 3 and final_anchors:
                    split1 = line_total // 3
                    split2 = (line_total // 3) * 2
                    group_a = final_anchors[:split1]
                    group_b = final_anchors[split1:split2]
                    group_c = final_anchors[split2:]
                    if (
                        (group_a and len(set(group_a)) != 1) or
                        (group_b and len(set(group_b)) != 1) or
                        (group_c and len(set(group_c)) != 1)
                    ):
                        st.warning("⚠️ 三組主標未正確分組")

                # --- 顯示大事框 ---
                for clean_line in final_lines:
                    parts = clean_line.split("//")
                    p1, p2, p3 = parts[0], parts[1], parts[2]

                    l1, l2, l3 = len(p1), len(p2), len(p3)
                    t1 = f'<span class="char-warn">({l1}字⚠️)</span>' if l1 < 7 or l1 > 8 else f'<span class="char-ok">({l1}字)</span>'
                    t2 = f'<span class="char-warn">({l2}字⚠️)</span>' if l2 < 7 or l2 > 9 else f'<span class="char-ok">({l2}字)</span>'
                    t3 = f'<span class="char-warn">({l3}字⚠️)</span>' if l3 < 7 or l3 > 9 else f'<span class="char-ok">({l3}字)</span>'

                    if "僅後二段" in format_type:
                        st.markdown(
                            f'<div class="news-box">{p2}{t2}<span class="separator">//</span>{p3}{t3}</div>',
                            unsafe_allow_html=True
                        )
                        copy_text += f"{p2}//{p3}\n"
                    else:
                        st.markdown(
                            f'<div class="news-box"><span class="anchor-text">{p1}</span>{t1}<span class="separator">//</span>{p2}{t2}<span class="separator">//</span>{p3}{t3}</div>',
                            unsafe_allow_html=True
                        )
                        copy_text += f"{p1}//{p2}//{p3}\n"

                st.text_area("📋 複製區 (大事框)", value=copy_text.strip(), height=150)

    # --- 處理 10字側標 ---
    if side_btn and news_input:
        with st.spinner("正在生成10字側標中..."):
            results = generate_content(
                get_side_slogan_prompt(side_line_total, highlights),
                news_input,
                expected_lines=side_line_total,
                temperature=0.2
            )

            copy_text = ""

            if results:
                if len(results) != side_line_total:
                    st.warning(f"⚠️ AI輸出行數異常：預期 {side_line_total} 行，實際 {len(results)} 行")

                for i, line in enumerate(results):
                    clean_line = clean_ai_output(line)

                    if len(clean_line) != 10 and auto_regen:
                        fixed_line, fixed_ok = regenerate_side_line(
                            news_input,
                            clean_line,
                            highlights
                        )
                        if fixed_ok:
                            st.markdown(
                                f'<div class="regen-note">🔁 第 {i+1} 行側標已自動重生</div>',
                                unsafe_allow_html=True
                            )
                            clean_line = fixed_line
                        else:
                            st.error(f"❌ 第 {i+1} 行側標自動重生仍未合格：{fixed_line}")
                            clean_line = fixed_line

                    elif len(clean_line) != 10:
                        st.error(f"❌ 第 {i+1} 行側標不是10字：{clean_line}")

                    char_len = len(clean_line)
                    t_side = f'<span class="char-warn">({char_len}字⚠️)</span>' if char_len != 10 else f'<span class="char-ok">({char_len}字)</span>'

                    st.markdown(
                        f'<div class="side-box">{clean_line} {t_side}</div>',
                        unsafe_allow_html=True
                    )
                    copy_text += f"{clean_line}\n"

                st.text_area("📋 複製區 (側標)", value=copy_text.strip(), height=150)
