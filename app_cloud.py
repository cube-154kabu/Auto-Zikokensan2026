import streamlit as st
import google.generativeai as genai
import os
import json
import datetime
from duckduckgo_search import DDGS
from dotenv import load_dotenv
import io

# -------------------------------------------------------------
# 【注意】このファイルはクラウド（Linux等のWebサーバー）での動作を
# 前提とした「方法4」専用のアプリケーションです。
# 動作には「docxtpl」ライブラリが必要です。
# ( pip install docxtpl )
# -------------------------------------------------------------
try:
    from docxtpl import DocxTemplate
except ImportError:
    st.error("docxtplがインストールされていません。ターミナルで `pip install docxtpl` を実行してください。")
    st.stop()

# .envファイルがあれば読み込む
load_dotenv()

st.set_page_config(page_title="自己啓発レポート自動生成 (Cloud版)", layout="wide")

st.title("自己啓発レポート 自動作成ツール ☁️クラウド版")
st.write("このバージョンはiPadやスマホなど、ブラウザ経由でどこからでもアクセスし、Wordファイルを直接ダウンロードできるように設計されています。")

# 環境変数またはStreamlit SecretsからAPIキーを取得
api_key = ""
try:
    if "GOOGLE_API_KEY" in st.secrets:
        api_key = st.secrets["GOOGLE_API_KEY"]
except:
    pass
if not api_key:
    api_key = os.environ.get("GOOGLE_API_KEY", "")

if api_key:
    genai.configure(api_key=api_key)
else:
    st.error("API Key が設定されていません。.envファイルを確認してください。")
    st.stop()

# セッションステートの初期化
if "report_parts" not in st.session_state:
    st.session_state.report_parts = {
        "part1": "", "part2": "", "part3": "", "part4": ""
    }
if "search_context" not in st.session_state:
    st.session_state.search_context = ""
if "author_candidates" not in st.session_state:
    st.session_state.author_candidates = []

# --- 検索・生成処理関数（ローカル版と共通） ---
def fetch_search_context(category, title):
    search_context = ""
    if not title: return search_context
    try:
        query = f"{title} 概要"
        if category == "読書感想文": query = f"{title} 本 あらすじ 概要"
        elif category == "講習等の受講": query = f"{title} 講習 セミナー 概要"
        with DDGS() as ddgs:
            results = ddgs.text(query, max_results=3)
            search_context = "\n".join([r.get('body', '') for r in results])
    except Exception:
        pass
    return search_context

def search_author_with_ai(title, category):
    if not title: return []
    label = "著者名" if category == "読書感想文" else "主催者名や講師名"
    prompt = f"以下の題名に関連する「{label}」の候補を最大3つ挙げてください。必ずJSONの文字列配列形式（例: [\"候補1\", \"候補2\"]）で出力してください。\n題名: {title}"
    try:
        model = genai.GenerativeModel("gemini-2.5-flash", generation_config={"response_mime_type": "application/json"})
        response = model.generate_content(prompt)
        res = json.loads(response.text)
        if isinstance(res, list): 
            return [str(x) for x in res]
        elif isinstance(res, dict):
            for k, v in res.items():
                if isinstance(v, list): return [str(x) for x in v]
    except:
        pass
    return []

def generate_report(target_part="all"):
    daily_duties_text = f"日常業務: {keywords}" if keywords else "日常業務の詳細: 未入力（部門名から推測してください）"

    prompt = f"""
あなたは会社へ提出する自己啓発レポート（{category}）を作成する優秀なアシスタントです。
以下の情報を元に、指定された項目についてレポートの本文を作成してください。

【基本情報】
部門: {department}
{daily_duties_text}
レポートの種類: {category}
題名: {title}

【作成上の注意】
・日常業務の記載がある場合は、その具体的な業務内容と「題名（書籍/講習）」の内容を深く関連付けて記述してください。
・日常業務の記載がない場合は、部門名から一般的な業務を推測して関連付けてください。
・「今後の活かし方」と「具体的に取組んでいること」は、特に具体的なアクションに結びつけて作成してください。

【インターネット検索による情報（参考）】
{st.session_state.search_context}
"""
    req_instructions = []
    if target_part == "all" or target_part == "part1":
        req_instructions.append('"part1": "「概要と選んだ目的」の本文のみ（見出し不要）約400字"')
    if target_part == "all" or target_part == "part2":
        req_instructions.append('"part2": "「私が学んだこと」の本文のみ（見出し不要）約600字"')
    if target_part == "all" or target_part == "part3":
        req_instructions.append('"part3": "「今後の仕事（部門の業務）への活かし方」の本文のみ（見出し不要）約900字。部門や使いたいワードを自然に織り交ぜて具体的に。" ')
    if target_part == "all" or target_part == "part4":
        req_instructions.append('"part4": "「具体的に取組んでいること」の本文のみ（見出し不要）約850字。部門や使いたいワードを自然に織り交ぜて具体的に。"')

    prompt += "以下のJSON形式のフォーマットに沿って、必要な項目だけを出力してください。キー以外の文字列は出力しないでください。\n{\n  " + ",\n  ".join(req_instructions) + "\n}"

    model = genai.GenerativeModel("gemini-2.5-flash", generation_config={"response_mime_type": "application/json"})
    
    try:
        response = model.generate_content(prompt)
        result_json = json.loads(response.text)
        if target_part == "all":
            st.session_state.report_parts["part1"] = result_json.get("part1", "")
            st.session_state.report_parts["part2"] = result_json.get("part2", "")
            st.session_state.report_parts["part3"] = result_json.get("part3", "")
            st.session_state.report_parts["part4"] = result_json.get("part4", "")
        else:
            st.session_state.report_parts[target_part] = result_json.get(target_part, "")
    except Exception as e:
        if "ResourceExhausted" in str(e) or "429" in str(e):
            st.error("⚠️ AIの利用制限（アクセス集中）に達しました。1〜2分ほど待ってから再度お試しください！")
        else:
            st.error(f"文章の生成中にエラーが発生しました: {e}")
        return False
    return True

# --- 画面UI ---
with st.container():
    col1, col2, col3 = st.columns(3)
    with col1:
        submission_date = st.date_input("提出日", value=datetime.date.today())
        department = st.text_input("部門", placeholder="例: 営業部、開発部、総務部など")
        emp_code = st.text_input("社員コード")
        emp_name = st.text_input("氏名")
    with col2:
        category = st.selectbox("名称", ["読書感想文", "講習等の受講", "その他"])
        title = st.text_input("題名（書籍名や講習名など）")
        cost = st.text_input("費用", value="0", placeholder="例: 1500")
        author_label = "著者名" if category == "読書感想文" else "主催者等"
        st.markdown(f"**{author_label}**")
        col_btn, col_sel = st.columns([1, 1])
        with col_btn:
            if st.button("AIで候補を検索"):
                if not title:
                    st.warning("先に題名を入力してください。")
                else:
                    with st.spinner("検索中..."):
                        st.session_state.author_candidates = search_author_with_ai(title, category)
                    st.rerun()
        with col_sel:
            options = st.session_state.author_candidates + ["手動入力する"]
            selected_author_opt = st.selectbox("候補から選択", options, label_visibility="collapsed")
        if selected_author_opt == "手動入力する":
            author_final = st.text_input(f"{author_label}（手入力）", placeholder=f"正しい{author_label}を入力")
        else:
            author_final = selected_author_opt

    with col3:
        keywords = st.text_area("あなたの日常業務", placeholder="例: 自動車部品の品質管理、顧客への提案営業など。具体的に書くほど精度の高いレポートになります。", height=280)

    if st.button("全体を新しく生成する（全自動）", type="primary", use_container_width=True):
        if not department or not title:
            st.error("「部門」と「題名」は必須入力です。")
        else:
            with st.spinner("情報を検索し、レポート全体を生成しています..."):
                st.session_state.search_context = fetch_search_context(category, title)
                success = generate_report("all")
            if success:
                st.rerun()

st.divider()

if any(st.session_state.report_parts.values()):
    st.markdown("### 生成されたレポートの編集")
    
    col_p1_text, col_p1_btn = st.columns([4, 1])
    with col_p1_text: st.session_state.report_parts["part1"] = st.text_area("1. 概要と選んだ目的（約400字）", st.session_state.report_parts["part1"], height=150)
    with col_p1_btn:
        st.write(""); st.write("")
        if st.button("🔄 1だけ再生成", key="btn_p1"):
            with st.spinner("再生成中..."): generate_report("part1")
            st.rerun()

    col_p2_text, col_p2_btn = st.columns([4, 1])
    with col_p2_text: st.session_state.report_parts["part2"] = st.text_area("2. 私が学んだこと（約600字）", st.session_state.report_parts["part2"], height=200)
    with col_p2_btn:
        st.write(""); st.write("")
        if st.button("🔄 2だけ再生成", key="btn_p2"):
            with st.spinner("再生成中..."): generate_report("part2")
            st.rerun()

    col_p3_text, col_p3_btn = st.columns([4, 1])
    with col_p3_text: st.session_state.report_parts["part3"] = st.text_area("3. 今後の活かし方（約900字）", st.session_state.report_parts["part3"], height=250)
    with col_p3_btn:
        st.write(""); st.write("")
        if st.button("🔄 3だけ再生成", key="btn_p3"):
            with st.spinner("再生成中..."): generate_report("part3")
            st.rerun()

    col_p4_text, col_p4_btn = st.columns([4, 1])
    with col_p4_text: st.session_state.report_parts["part4"] = st.text_area("4. 具体的に取組んでいること（約850字）", st.session_state.report_parts["part4"], height=150)
    with col_p4_btn:
        st.write(""); st.write("")
        if st.button("🔄 4だけ再生成", key="btn_p4"):
            with st.spinner("再生成中..."): generate_report("part4")
            st.rerun()

    st.divider()
    st.markdown("### 最終出力（クラウド用）")
    
    # クラウド版では、docxtplを使用してタグ付きのdocxファイルにデータを差し込みます。
    # ここでは、ダウンロードボタンを生成する処理を行います。
    template_path = "template_cloud_tagged.docx"
    
    if not os.path.exists(template_path):
        st.warning(f"⚠️ テンプレートファイル `{template_path}` が見つかりません。")
        st.info("※クラウドで動かすためには、元のWordファイルに `{{ department }}` などのタグを埋め込んだ専用のテンプレートが必要です。")
    else:
        try:
            # 本文の整形処理
            import re
            def clean_part(text):
                text = re.sub(r'^【.*?】\s*', '', text.strip())
                text = re.sub(r'^\d+\.\s*.*?(?:\r|\n|）|\))*\s*', '', text.strip())
                return text
                
            def add_indent_space(text):
                paragraphs = text.split('\n')
                return '\n'.join(['　' + p if p.strip() != '' else p for p in paragraphs])
            
            p1 = add_indent_space(clean_part(st.session_state.report_parts['part1']))
            p2 = add_indent_space(clean_part(st.session_state.report_parts['part2']))
            p3 = add_indent_space(clean_part(st.session_state.report_parts['part3']))
            p4 = add_indent_space(clean_part(st.session_state.report_parts['part4']))
            
            # 見出し付きの本文結合
            body_text = f"1. 本の概要と選んだ目的（15）\n{p1}\n\n"
            body_text += f" 2. 私が学んだこと(25)\n{p2}\n\n"
            body_text += f"3. 今後の（仕事への）活かし方（30）\n{p3}\n\n"
            body_text += f"4. 具体的に取組んでいること（30）　\n※本を読み終えたあと、実践していること・したことなど\n{p4}"

            # 差し込むデータ
            context = {
                "date": f"{submission_date.year}年 {submission_date.month}月 {submission_date.day}日",
                "department": department,
                "emp_code": emp_code,
                "emp_name": emp_name,
                "category": category,
                "title": title,
                "author_label": "主催者等" if category != "読書感想文" else "著者名",
                "author": author_final,
                "cost": f"{cost}円",
                "body": body_text
            }

            # テンプレートのレンダリング
            doc = DocxTemplate(template_path)
            doc.render(context)
            
            # メモリ上に保存してダウンロードボタン化
            bio = io.BytesIO()
            doc.save(bio)
            
            date_str = datetime.datetime.now().strftime("%Y%m%d")
            safe_name = emp_name if emp_name else "未入力"
            dl_filename = f"{date_str}_{safe_name}_自己啓発レポート.docx"
            
            st.download_button(
                label="📥 完成したWord（.docx）をダウンロード",
                data=bio.getvalue(),
                file_name=dl_filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Wordファイルの生成中にエラーが発生しました: {e}")
