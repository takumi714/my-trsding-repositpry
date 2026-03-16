import streamlit as st
import pandas as pd
import numpy as np
import datetime
import os
import random
import subprocess
import time
import platform
import plotly.express as px
import plotly.graph_objects as go
from PIL import Image
import google.generativeai as genai

# --- 基本設定 ---
APP_TITLE = "Kelly Strategic Console"
LOG_FILE = "investment_diary.csv"

st.set_page_config(page_title=APP_TITLE, layout="wide")

# --- カスタムスタイル（ダークテーマ） ---
custom_css = """
<style>
:root {
  --bg-color: #050712;
  --panel-bg: #0d101c;
  --panel-elevated: #141827;
  --accent: #3b82f6;
  --accent-soft: rgba(59, 130, 246, 0.12);
  --text-color: #e5e7eb;
  --muted-text: #9ca3af;
  --danger: #f97373;
  --warning: #fbbf24;
  --success: #4ade80;
  --border-subtle: #1f2933;
}

.stApp {
  background-color: var(--bg-color) !important;
  color: var(--text-color) !important;
  font-family: "Inter", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

section.main > div {
  padding-top: 1.25rem;
}

.stSidebar {
  background: #03040a !important;
  border-right: 1px solid var(--border-subtle);
}

.stSidebar > div {
  padding-top: 1.5rem;
}

h1, h2, h3, h4 {
  color: var(--text-color) !important;
  letter-spacing: 0.04em;
}

.stTabs [data-baseweb="tab-list"] {
  gap: 0.25rem;
}

.stTabs [data-baseweb="tab"] {
  background: transparent;
  border-radius: 0;
  padding: 0.6rem 1.15rem;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--muted-text);
}

.stTabs [aria-selected="true"][data-baseweb="tab"] {
  border-bottom: 2px solid var(--accent);
  color: var(--text-color);
  background: rgba(15, 23, 42, 0.6);
}

div[data-testid="stMetric"] {
  background: var(--panel-elevated);
  border-radius: 0.5rem;
  padding: 0.75rem 0.9rem;
  border: 1px solid var(--border-subtle);
}

div[data-testid="stMetric"] label {
  color: var(--muted-text);
  font-size: 0.78rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
}

div[data-testid="stMetric"] > div:nth-child(2) {
  color: var(--text-color);
}

.stButton > button {
  width: 100%;
  border-radius: 0.35rem;
  border: 1px solid rgba(148, 163, 184, 0.5);
  background: linear-gradient(135deg, #111827, #020617);
  color: var(--text-color);
  font-weight: 500;
}

.stButton > button:hover {
  border-color: var(--accent);
  background: linear-gradient(135deg, #020617, #111827);
}

.stTextInput > div > div > input,
.stNumberInput input,
.stTextArea textarea,
.stDateInput input {
  background: #020617 !important;
  border-radius: 0.35rem;
  border: 1px solid rgba(55, 65, 81, 0.9);
  color: var(--text-color) !important;
}

.stSlider > div > div > div[data-baseweb="slider"] > div {
  background: var(--accent-soft) !important;
}

.stSlider span[data-baseweb="slider"] {
  background: var(--accent) !important;
}

.stAlert {
  border-radius: 0.35rem;
}

.stAlert[data-baseweb="alert"] {
  background: var(--panel-elevated) !important;
}

div[data-testid="stHorizontalBlock"] > div {
  background: transparent;
}

.block-container {
  padding-top: 1.5rem;
}
</style>
"""

st.markdown(custom_css, unsafe_allow_html=True)


# --- 仮想ヒストリカルデータ生成（トレード練習道場用） ---
def fetch_simulator_data(symbol_name: str, timeframe_name: str, required_bars: int):
    # 外部APIを一切使わず、本物そっくりのランダム相場を生成する
    np.random.seed()
    total_bars = required_bars + 50
    dates = pd.date_range(end=datetime.datetime.today(), periods=total_bars)

    # ランダムウォークで価格推移を作成（初期値150円付近）
    close_prices = 150.0 + np.cumsum(np.random.randn(total_bars) * 0.3)

    df = pd.DataFrame(
        {
            "Open": close_prices + np.random.randn(total_bars) * 0.1,
            "Close": close_prices,
            "High": close_prices + np.abs(np.random.randn(total_bars) * 0.2),
            "Low": close_prices - np.abs(np.random.randn(total_bars) * 0.2),
            "Volume": np.random.randint(1000, 50000, size=total_bars),
        },
        index=dates,
    )

    # High/Low の論理的一貫性を強制補正
    df["High"] = df[["Open", "Close", "High"]].max(axis=1)
    df["Low"] = df[["Open", "Close", "Low"]].min(axis=1)

    # 必要な本数分だけ切り出し
    start_idx = np.random.randint(0, len(df) - required_bars)
    sliced_df = df.iloc[start_idx : start_idx + required_bars].copy()

    # 既存の呼び出し側との互換性を保つため、ダミーのシンボル・タイムフレームも返す
    return sliced_df, symbol_name, timeframe_name


# --- データの読み書き（ルール遵守項目を追加） ---
def load_data():
    if os.path.isfile(LOG_FILE):
        try:
            df = pd.read_csv(LOG_FILE)
            if "RR比" not in df.columns: df["RR比"] = 0.0
            if "ルール遵守" not in df.columns: df["ルール遵守"] = True
            return df
        except:
            return pd.DataFrame(columns=["日付", "対象", "収支", "メモ", "RR比", "ルール遵守"])
    return pd.DataFrame(columns=["日付", "対象", "収支", "メモ", "RR比", "ルール遵守"])

def save_investment_log(date, topic, income, memo, rr, rule_followed):
    df_new = pd.DataFrame({"日付": [date], "対象": [topic], "収支": [income], "メモ": [memo], "RR比": [rr], "ルール遵守": [rule_followed]})
    if not os.path.isfile(LOG_FILE):
        df_new.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")
    else:
        df_new.to_csv(LOG_FILE, mode='a', header=False, index=False, encoding="utf-8-sig")

# --- アプリメイン表示 ---
st.title(APP_TITLE)
df_history = load_data()

# --- 規律メトリクスの集計 ---
rule_adherence = None
rule_violations_today = 0

if not df_history.empty and "ルール遵守" in df_history.columns:
    rule_adherence = (df_history["ルール遵守"].sum() / len(df_history)) * 100
    today_str = str(datetime.date.today())
    try:
        violations = df_history[
            (df_history["日付"].astype(str) == today_str) & (df_history["ルール遵守"] == False)
        ]
        rule_violations_today = len(violations)
    except Exception:
        rule_violations_today = 0

# --- サイドバー ---
st.sidebar.header("コントロールパネル")

if rule_adherence is not None:
    st.sidebar.subheader("規律メトリクス")
    st.sidebar.metric("現在の鉄則遵守率", f"{round(rule_adherence, 1)} %")
    st.sidebar.metric("本日のルール違反回数", int(rule_violations_today))
    st.sidebar.divider()

st.sidebar.subheader("リスクプロファイル")
bankroll = st.sidebar.number_input("現在の証拠金・総資金 (円)", value=100000, step=1000)
win_rate = st.sidebar.slider("予想勝率 (0.0〜1.0)", 0.0, 1.0, 0.6)

st.sidebar.divider()
st.sidebar.subheader("RR（リスクリワード）設定")
entry = st.sidebar.number_input("エントリー価格", value=100.0)
target = st.sidebar.number_input("利益確定価格", value=120.0)
stop = st.sidebar.number_input("損切り価格", value=90.0)

reward = abs(target - entry)
risk = abs(entry - stop)
rr_ratio = reward / risk if risk != 0 else 0

st.sidebar.divider()
st.sidebar.subheader("投資日記入力")
selected_date = st.sidebar.date_input("日付を選択", datetime.date.today())
target_topic = st.sidebar.text_input("投資対象", "BTC / ドル円")
income_amount = st.sidebar.number_input("本日の収支 (円)", value=0)
strategy_memo = st.sidebar.text_area("振り返りメモ（外れた理由など）")
rule_followed = st.sidebar.checkbox("鉄則（マイルール）を完全に守った", value=True)

st.sidebar.divider()
st.sidebar.subheader("AIトレード添削（プロメンター）")
gemini_api_key = st.sidebar.text_input("Gemini APIキー", type="password")
uploaded_chart = st.sidebar.file_uploader("チャートのスクリーンショットをアップロード", type=["png", "jpg", "jpeg"])

mentor_feedback = st.session_state.get("mentor_feedback", None)

if st.sidebar.button("AIメンターに添削を依頼する"):
    if not gemini_api_key:
        st.sidebar.error("Gemini APIキーを入力してください。")
    elif not strategy_memo.strip():
        st.sidebar.error("振り返りメモを入力してください。")
    elif uploaded_chart is None:
        st.sidebar.error("チャートのスクリーンショット画像をアップロードしてください。")
    else:
        try:
            genai.configure(api_key=gemini_api_key)
            model = genai.GenerativeModel('gemini-1.5-flash')

            image = Image.open(uploaded_chart).convert("RGB")

            rules_prompt = """
あなたはプロ中のプロである機関投資家トレーダー兼メンターです。感情や甘さを完全に排除し、期待値・リスク管理・プロスペクト理論の観点から、容赦なく厳しく添削してください。

前提となる「絶対ルール」は以下です（第1章〜第5章の要点）:

【第1章：投資の鉄則と資金管理】
- プロスペクト理論を理解し、損失回避バイアスに負けずに機械的に損切りすること。
- 1回の取引での最大損失額は証拠金（総資金）の3%（最大でも5%）まで。初心者は1%。
- 平均利益 ÷ 平均損失（RR比）は必ず1.0以上、理想は2.0〜3.0となる場面だけでエントリー。
- エントリーと同時に逆指値（ストップロス）を必ず入れる。
- 「なぜ動いたか」「高値/安値」「今後の見通し」「トレード戦略」「外れた理由」を投資日記として必ず記録し、振り返る。

【第2章：相場の地合いとファンダメンタルズ】
- 個別銘柄や通貨ペアより前に、全体相場のトレンド・金利・為替・株価の関係を確認する。

【第3章：テクニカル分析の極意】
- 移動平均線のパーフェクトオーダー（ローソク足 > 25日 > 75日 > 200日）など、統計的に優位性のある形のみを狙う。
- 落ちるナイフを掴まない。下降トレンドへの逆張りは禁止。
- 水平線・サポート/レジスタンス・ローソク足パターン・オシレーターのダイバージェンスなどを総合的に判断する。

【第4章：日本株特有の需給】
- 信用倍率や板の厚みなど、需給要因を必ず確認し、需給が悪い銘柄は避ける。

【第5章：FX実践トレード・スキャルピング術】
- ゴールデンタイム（日本時間22:00〜23:00）以外、特に魔の時間帯（24:00〜朝8:00）や重要指標直後のエントリーは極力避ける。
- 大衆のストップが溜まる位置（OANDAオープンオーダー、ラウンドナンバーなど）を意識し、ストップ狩りを逆手に取る。

これらのルールを絶対基準として、「今回のトレードがどのルールに違反しているか」「期待値的にそもそもエントリーする価値があったか」「感情的な判断がどこに入り込んでいるか」を、プロ目線で冷徹に評価してください。

出力フォーマット:
1. 総評（今回のトレードを一言でいうと？）
2. ルール違反チェック（第1章〜第5章ごとに、どの項目を破っているか／守れているかを箇条書きで）
3. 期待値・RR比の観点からの評価（「このセットアップは長期的に勝てる／勝てない」など）
4. 感情的バイアスの指摘（プロスペクト理論の観点から、どのような感情が働いていると推察されるか）
5. 次回以降の具体的な改善アクション（チェックリスト形式で、再現性のある行動レベルのアドバイス）
"""

            user_context = f"""
【トレードの振り返りメモ】:
{strategy_memo}

【補足】:
- ルール遵守フラグ: {"遵守" if rule_followed else "未遵守"}
- 投資対象: {target_topic}
- 本日の収支: {income_amount} 円
"""

            full_prompt = rules_prompt + "\n\n" + user_context

            response = model.generate_content(
                [full_prompt, image],
                safety_settings="BLOCK_NONE",
            )

            feedback_text = response.text if hasattr(response, "text") else str(response)
            st.session_state["mentor_feedback"] = feedback_text
            mentor_feedback = feedback_text
            st.sidebar.success("AIメンターからのフィードバックを取得しました。下部のメイン画面をご確認ください。")
        except Exception as e:
            st.sidebar.error(f"Gemini API呼び出し中にエラーが発生しました: {e}")

if st.sidebar.button("日記を保存する"):
    save_investment_log(selected_date, target_topic, income_amount, strategy_memo, rr_ratio, rule_followed)
    st.sidebar.success("記録完了！")
    st.rerun()

# --- タブ表示（虎の巻を追加） ---
tab1, tab2, tab3, tab4, tab5 = st.tabs(
    ["戦略コンソール", "統計・自己分析", "投資の鉄則（虎の巻）", "トレード練習道場", "📈 バックテスト (R言語エンジン)"]
)

with tab1:
    st.subheader("搭乗前チェックリスト（Pre-flight Check）")
    st.write("エントリー前に以下の条件を全てクリアしているか確認してください。")
    col_chk1, col_chk2 = st.columns(2)
    with col_chk1:
        chk1 = st.checkbox("全体相場の地合いは良いか？（上位足のトレンド確認）")
        chk2 = st.checkbox("オシレーターの過熱感（買われすぎ/売られすぎ）はないか？")
        chk3 = st.checkbox("エントリーと同時に逆指値（損切り）を入れる覚悟があるか？")
    with col_chk2:
        chk4 = st.checkbox("落ちるナイフ（下降トレンド）の逆張りではないか？")
        chk5 = st.checkbox("魔の時間帯（24:00〜朝8:00）や指標発表直後ではないか？")
        chk6 = st.checkbox("プロスペクト理論を理解し、機械的に損切りできるか？")
    
    all_checked = chk1 and chk2 and chk3 and chk4 and chk5 and chk6

    st.divider()

    col1, col2 = st.columns([1, 1])
    b = rr_ratio if rr_ratio > 0 else 1.0
    p = win_rate
    edge = (p * b) - (1 - p)
    max_loss_3percent = bankroll * 0.03 # 3%ルール
    
    with col1:
        st.subheader("リスク・資金管理分析")
        st.metric("RR比", f"1 : {round(rr_ratio, 2)}")
        st.metric("許容最大リスク (3%ルール)", f"{int(max_loss_3percent):,} 円")
        
        if rr_ratio < 1.0:
            st.error("RR比が1.0未満です。優位性がありません（見送り推奨）")
        elif not all_checked:
            st.warning("チェックリストが全て完了していません。エントリーを控えてください。")
        elif edge > 0:
            f_star = edge / b
            raw_bet = (bankroll * f_star) * 0.5 
            # 3%ルールを適用（ケリー基準の推奨額が3%ルールを超えないようにガード）
            bet = min(raw_bet, max_loss_3percent / risk * entry if risk != 0 else raw_bet)
            
            st.success(f"### 最終推奨投資額: **{int(bet):,} 円**")
            st.info("3%ルールとケリー基準を統合した推奨投資額です。")
        else:
            st.error("### 待機推奨（期待値マイナス）")

    if mentor_feedback:
        st.divider()
        st.subheader("AIメンターからのフィードバック")
        st.info(mentor_feedback)

    with col2:
        st.subheader("資産推移予測")
        if edge > 0 and all_checked and rr_ratio >= 1.0:
            history = [bankroll]
            current = bankroll
            for _ in range(100):
                current += (current * (f_star * 0.5) * edge)
                history.append(current)
            st.area_chart(pd.DataFrame(history, columns=["想定資産"]))
        else:
            st.info("優位性が確認され、チェックリストが完了するとグラフが表示されます。")

with tab2:
    if not df_history.empty:
        st.subheader("実績分析")

        # 基本集計
        df_history["累積収支"] = df_history["収支"].cumsum()
        st.line_chart(df_history.set_index("日付")["累積収支"])

        col_a, col_b = st.columns(2)
        with col_a:
            st.metric("累計収支", f"{df_history['収支'].sum():,} 円")
            st.metric("平均RR比", f"1 : {round(df_history['RR比'].mean(), 2)}")
            if rule_adherence is not None:
                st.metric("鉄則遵守率", f"{round(rule_adherence, 1)} %")

            # 勝率（収支がプラスの割合）
            total_trades = len(df_history)
            win_trades = (df_history["収支"] > 0).sum()
            win_rate_overall = (win_trades / total_trades) * 100 if total_trades > 0 else 0.0
            st.metric("全体勝率", f"{win_rate_overall:.1f} %")

        with col_b:
            # RR比と収支の散布図
            fig = px.scatter(df_history, x="RR比", y="収支", color="対象")
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.subheader("詳細分析ボード")

        # 銘柄（対象）ごとの勝率と合計損益
        df_history["is_win"] = df_history["収支"] > 0
        grouped = df_history.groupby("対象").agg(
            取引回数=("収支", "count"),
            勝率=("is_win", lambda x: 100 * x.sum() / len(x) if len(x) > 0 else 0.0),
            合計損益=("収支", "sum"),
        ).reset_index()

        st.markdown("**銘柄ごとの勝率と合計損益**")
        st.dataframe(grouped.style.format({"勝率": "{:.1f}", "合計損益": "{:,.0f}"}), use_container_width=True)

        # ルール遵守別パフォーマンス比較
        if "ルール遵守" in df_history.columns:
            st.markdown("**ルール遵守別パフォーマンス比較**")
            perf = df_history.groupby("ルール遵守").agg(
                取引回数=("収支", "count"),
                平均損益=("収支", "mean"),
                合計損益=("収支", "sum"),
                勝率=("is_win", lambda x: 100 * x.sum() / len(x) if len(x) > 0 else 0.0),
            ).reset_index()
            perf["ルール"] = perf["ルール遵守"].map({True: "遵守", False: "未遵守"})

            cols_perf = st.columns(2)
            with cols_perf[0]:
                st.dataframe(
                    perf[["ルール", "取引回数", "勝率", "平均損益", "合計損益"]].style.format(
                        {"勝率": "{:.1f}", "平均損益": "{:,.0f}", "合計損益": "{:,.0f}"}
                    ),
                    use_container_width=True,
                )

            with cols_perf[1]:
                perf_chart = perf.copy()
                perf_chart["ラベル"] = perf_chart["ルール"]
                fig_perf = px.bar(
                    perf_chart,
                    x="ラベル",
                    y="合計損益",
                    color="ラベル",
                    labels={"ラベル": "ルール遵守", "合計損益": "合計損益"},
                )
                fig_perf.update_layout(showlegend=False)
                st.plotly_chart(fig_perf, use_container_width=True)

        st.divider()
        st.subheader("トレード履歴の編集／削除")

        editable_df = st.data_editor(
            df_history.drop(columns=["累積収支", "is_win"], errors="ignore"),
            num_rows="dynamic",
            use_container_width=True,
            key="trade_editor",
        )

        if st.button("変更を保存する"):
            try:
                # CSVへ上書き保存
                editable_df.to_csv(LOG_FILE, index=False, encoding="utf-8-sig")
                st.success("変更を保存しました。")
            except Exception as e:
                st.error(f"保存中にエラーが発生しました: {e}")
    else:
        st.info("まだデータがありません。")

with tab3:
    st.header("生き残るための絶対ルール（虎の巻）")
    
    with st.expander("第1章：投資の鉄則と資金管理（生き残るための絶対ルール）", expanded=True):
        st.markdown("""
        相場の世界で最も重要なのは「稼ぐこと」以上に「退場しないこと」です。
        * **プロスペクト理論の克服:** 人間は「利益」より「損失」を重く感じるため、損切りを先延ばしにしてしまう生き物。この心理を理解し、機械的に損切りする。
        * **許容リスク（3%ルール）:** 1回の取引での最大損失額は**「証拠金（総資金）の3%（最大5%）」**まで。初心者は「1%」を徹底。
        * **リスクリワードレシオ（損益比率）:** 「平均利益 ÷ 平均損失」が必ず1.0以上（理想は2.0〜3.0）になるポイントでのみエントリーする。
        * **逆指値（ストップロス）の必須化:** エントリーと同時に必ず逆指値注文（損切り）を入れる。IFO注文やOCO注文を活用。
        * **投資日誌の義務化:** 「なぜ動いたか」「高値/安値」「今後の見通し」「トレード戦略」「外れた理由」を必ず自分の言葉で記録し振り返る。
        """)
        
    with st.expander("第2章：相場の地合いとファンダメンタルズ（大局観）"):
        st.markdown("""
        木（個別銘柄）を見る前に、森（全体相場）を見る。
        * **全体相場の見極め:** 日経平均先物が上昇していれば地合い良し、下落していれば悪し。日経寄与度トップ3（ファストリ・東エレ・SBG）の動きを見る。米国市場（S&P500、NYダウ、NASDAQ100）が好調な局面が一番利益を上げやすい。
        * **金利と為替・株価の関係:** インフレ率上昇 ＝ 金利上昇。金利上昇 ＝ 株価下落圧力。金利上昇 ＝ その国の通貨高。
        * **テンバガー（10倍株）の発掘条件:** 時価総額1,000億円以下。毎年20%以上の増収増益。赤字からの黒字転換やPBR1倍割れ。
        """)

    with st.expander("第3章：テクニカル分析の極意（売買タイミング）"):
        st.markdown("""
        数学的根拠に基づいたチャート分析で優位性を保つ。
        * **移動平均線（SMA）:** パーフェクトオーダー（ローソク足 > 25日 > 75日 > 200日）が強い上昇トレンド。週足200日線超えは買いスタンバイ。グランビルの法則（順張りの買い①、売り⑤）を狙う。
        * **水平線（サポート＆レジスタンス）:** 過去の高値・安値は強力な抵抗帯。下降トレンドの株は買わない（落ちるナイフは掴まない）。上場来高値更新は「絶対正義」。
        * **オシレーターとダイバージェンス:** RSI(70%超で買われすぎ、30%以下で売られすぎ)。MACDのクロス。ダイバージェンス（価格高値更新なのにオシレーター下落）はトレンド転換の強力なサイン。
        * **ローソク足とチャートパターン:** 三尊、ダブルトップ/ボトム、カップウィズハンドル。天井圏の「長い上ヒゲ」「十字線」「包み足」、底値圏の「長い下ヒゲ」。
        """)

    with st.expander("第4章：日本株特有の「需給」読み"):
        st.markdown("""
        株価は最終的に「買いたい人」と「売りたい人」の需給で決まる。
        * **信用倍率（最強の先行指標）:** 株価上昇＋信用倍率低下（今後も上がりやすい）。株価下落＋信用倍率上昇（下落の可能性大）。株価下落中の信用倍率急上昇は「絶対に買ってはいけない」。
        * **板読み（注文の厚み）:** 株価は「板が厚いほう」に向かって動く。
        """)

    with st.expander("第5章：FX実践トレード・スキャルピング術"):
        st.markdown("""
        大衆心理（ストップ狩り）を逆手に取る戦術。
        * **時間帯と立ち回り:** ゴールデンタイムは日本時間 22:00〜23:00。魔の時間帯（24:00〜朝8:00）は避ける。指標発表直後はスプレッドが開くため10〜15分待つ。
        * **OANDA オープンオーダー:** 大衆の「損切り」が溜まっている方向へ順張りし、ストップを巻き込んだブレイクアウトを狙う。
        * **ラウンドナンバーとEMA13:** 140.00などのキリ番は強力な壁。一発目のタッチは反発しやすい。明確なブレイク後、すぐに出たEMA13タッチは勝率が高い。
        * **V字回復とリターンムーブ:** 強い下落後、EMA100にタッチせず落ちた相場は反発も強い。節目ブレイク後のリターンムーブ（第2波）を狙う。
        """)

with tab4:
    st.header("トレード練習道場（シミュレーター）")

    # シンボルとタイムフレームの選択
    col_cfg1, col_cfg2, col_cfg3 = st.columns([1, 1, 1])
    with col_cfg1:
        symbol_label = st.selectbox(
            "銘柄",
            ["USD/JPY", "EUR/USD", "BTC/USD", "日経平均", "S&P500"],
            index=0,
        )
    with col_cfg2:
        timeframe = st.selectbox("タイムフレーム", ["日足", "1時間足", "15分足"], index=0)
    with col_cfg3:
        window_length = st.selectbox("練習本数（最大表示本数）", [150, 200, 250], index=1)

    # セッションステートの初期化
    if "sim_data" not in st.session_state:
        st.session_state.sim_data = None
        st.session_state.sim_index = None
        st.session_state.sim_symbol = None  # 選択中の銘柄ラベル
        st.session_state.sim_interval = None  # 選択中のタイムフレームラベル
        st.session_state.sim_pnl = 0.0
        st.session_state.sim_position = None  # {"side": "long"/"short", "entry": float}
        st.session_state.sim_closed_trades = []

    def reset_simulation():
        try:
            sim_slice, _, _ = fetch_simulator_data(symbol_label, timeframe, window_length)
            if sim_slice is None or sim_slice.empty:
                raise ValueError("シミュレーション用データの生成に失敗しました。")

            st.session_state.sim_data = sim_slice
            st.session_state.sim_index = 30  # 最初は30本だけ表示
            st.session_state.sim_symbol = symbol_label
            st.session_state.sim_interval = timeframe
            st.session_state.sim_pnl = 0.0
            st.session_state.sim_position = None
            st.session_state.sim_closed_trades = []
        except Exception as e:
            st.error(f"データ生成中にエラーが発生しました: {e}")

    col_btn1, col_btn2, col_btn3, col_btn4, col_btn5 = st.columns([1, 1, 1, 1, 1])
    with col_btn1:
        if st.button("リセット（別期間で再スタート）"):
            reset_simulation()
    with col_btn2:
        next_candle = st.button("次の足へ進む")
    with col_btn3:
        buy_btn = st.button("買いエントリー")
    with col_btn4:
        sell_btn = st.button("売りエントリー")
    with col_btn5:
        close_btn = st.button("決済する")

    # シミュレーションデータが未取得、または銘柄／タイムフレームが変更された場合は自動で初期化
    if (
        st.session_state.sim_data is None
        or st.session_state.sim_symbol != symbol_label
        or st.session_state.sim_interval != timeframe
    ):
        reset_simulation()

    sim_data = st.session_state.sim_data
    sim_index = st.session_state.sim_index

    if sim_data is not None and sim_index is not None:
        # 足を1本進める
        if next_candle:
            if sim_index < len(sim_data) - 1:
                st.session_state.sim_index += 1
                sim_index = st.session_state.sim_index

        current_slice = sim_data.iloc[: sim_index + 1]
        last_price = float(current_slice["Close"].iloc[-1])

        # エントリー・決済ロジック
        if buy_btn:
            if st.session_state.sim_position is None:
                st.session_state.sim_position = {"side": "long", "entry": last_price}
            else:
                st.warning("既にポジションを保有しています。決済してから新規エントリーしてください。")

        if sell_btn:
            if st.session_state.sim_position is None:
                st.session_state.sim_position = {"side": "short", "entry": last_price}
            else:
                st.warning("既にポジションを保有しています。決済してから新規エントリーしてください。")

        if close_btn and st.session_state.sim_position is not None:
            pos = st.session_state.sim_position
            side = pos["side"]
            entry = pos["entry"]
            diff = last_price - entry
            if side == "short":
                diff = -diff

            # USD/JPY 前提でpips換算（0.01を1pipsとみなす）
            pips = diff * 100

            st.session_state.sim_pnl += diff
            st.session_state.sim_closed_trades.append(
                {
                    "サイド": "買い" if side == "long" else "売り",
                    "エントリー価格": entry,
                    "決済価格": last_price,
                    "価格差": diff,
                    "獲得pips": pips,
                }
            )
            st.session_state.sim_position = None

        # チャート描画（未来は非表示）
        fig_sim = go.Figure(
            data=[
                go.Candlestick(
                    x=current_slice.index,
                    open=current_slice["Open"],
                    high=current_slice["High"],
                    low=current_slice["Low"],
                    close=current_slice["Close"],
                    increasing_line_color="#22c55e",
                    decreasing_line_color="#ef4444",
                    increasing_fillcolor="#16a34a",
                    decreasing_fillcolor="#b91c1c",
                    showlegend=False,
                )
            ]
        )
        fig_sim.update_layout(
            xaxis_rangeslider_visible=False,
            template="plotly_dark",
            margin=dict(l=10, r=10, t=40, b=20),
            paper_bgcolor="#050712",
            plot_bgcolor="#050712",
        )
        st.plotly_chart(fig_sim, use_container_width=True)

        # 成績表示
        col_stat1, col_stat2, col_stat3 = st.columns(3)
        with col_stat1:
            st.metric("現在値", f"{last_price:.3f}")
        with col_stat2:
            open_pos = st.session_state.sim_position
            if open_pos is not None:
                side = "買い" if open_pos["side"] == "long" else "売り"
                st.metric("現在のポジション", f"{side} @ {open_pos['entry']:.3f}")
            else:
                st.metric("現在のポジション", "ノーポジション")
        with col_stat3:
            st.metric("累計損益（価格差合計）", f"{st.session_state.sim_pnl:.3f}")

        if st.session_state.sim_closed_trades:
            st.subheader("約定履歴")
            trades_df = pd.DataFrame(st.session_state.sim_closed_trades)
            st.dataframe(
                trades_df.style.format(
                    {"エントリー価格": "{:.3f}", "決済価格": "{:.3f}", "価格差": "{:.3f}", "獲得pips": "{:.1f}"}
                ),
                use_container_width=True,
            )
    else:
        st.info("データを準備中です。数秒後にもう一度お試しください。")

with tab5:
    st.header("📈 バックテスト (R言語エンジン)")
    st.write("Python から R スクリプトを呼び出し、バックテストエンジンとの連携をテストします。")

    if st.button("🧠 R言語エンジンをテスト起動する"):
        script_path = os.path.join(os.path.dirname(__file__), "backtest_engine.R")

        # Rスクリプトが存在するか確認
        if not os.path.isfile(script_path):
            st.error("backtest_engine.R が見つかりません。R側のバックテストエンジンを配置してください。")
            st.stop()

        # 実行環境ごとに Rscript のパスを決定
        system_name = platform.system()
        rscript_path = None

        if system_name == "Windows":
            # ローカル Windows 環境では既知の絶対パス候補を探索
            candidate_paths = [
                "C:/Program Files/R/R-4.5.0/bin/Rscript.exe",
                "C:/Program Files/R/R-4.5.0/bin/x64/Rscript.exe",
            ]
            for cand in candidate_paths:
                if os.path.exists(cand):
                    rscript_path = cand
                    break
        else:
            # Linux / クラウド環境では標準パスにある Rscript を使用
            rscript_path = "Rscript"

        if rscript_path is None:
            st.error(
                "Rscript の場所を特定できませんでした。"
                "\nWindows の場合は R 4.5.0 のインストールパスを確認してください。"
            )
        else:
            try:
                result = subprocess.run(
                    [rscript_path, "--vanilla", "--slave", script_path],
                    capture_output=True,
                    text=False,
                    check=False,
                )

                # エンコーディングを utf-8 / cp932 の順で試行
                def safe_decode(data: bytes) -> str:
                    if data is None:
                        return ""
                    for enc in ("utf-8", "cp932"):
                        try:
                            return data.decode(enc)
                        except Exception:
                            continue
                    # どちらでも失敗した場合は、置換モードでデコード
                    return data.decode("utf-8", errors="replace")

                stdout = safe_decode(result.stdout)
                stderr = safe_decode(result.stderr)

                if result.returncode == 0:
                    output = stdout.strip()
                    if not output:
                        st.error("Rスクリプトは正常終了しましたが、標準出力が空でした。R側のロジックを確認してください。")
                    else:
                        # "key: value" 形式の行をパースして辞書に格納
                        data: dict[str, float | str] = {}
                        for line in output.splitlines():
                            line = line.strip()
                            if not line or ":" not in line:
                                continue
                            key, val = line.split(":", 1)
                            key = key.strip()
                            val_str = val.strip()
                            # 数値に変換できるものは数値に、それ以外は文字列として保持
                            try:
                                if "." in val_str:
                                    num_val = float(val_str)
                                else:
                                    num_val = int(val_str)
                                data[key] = num_val
                            except ValueError:
                                data[key] = val_str

                        st.subheader("バックテスト結果（Rエンジン）")
                        col_bt1, col_bt2, col_bt3, col_bt4 = st.columns(4)
                        with col_bt1:
                            total_trades = int(data.get("total_trades", 0) or 0)
                            st.metric("総トレード回数", f"{total_trades}")
                        with col_bt2:
                            final_pnl = float(data.get("final_pnl", 0) or 0.0)
                            st.metric("最終損益", f"{int(final_pnl):,} 円")
                        with col_bt3:
                            pf_raw = data.get("profit_factor", None)
                            pf_val = None
                            if isinstance(pf_raw, (int, float)):
                                pf_val = float(pf_raw)
                            elif isinstance(pf_raw, str):
                                try:
                                    pf_val = float(pf_raw)
                                except ValueError:
                                    pf_val = None
                            pf_text = f"{pf_val:.2f}" if pf_val is not None else "-"
                            st.metric("プロフィットファクター", pf_text)
                        with col_bt4:
                            dd_raw = data.get("max_drawdown", 0)
                            try:
                                dd_val = float(dd_raw)
                            except (TypeError, ValueError):
                                dd_val = 0.0
                            st.metric("最大ドローダウン", f"{int(dd_val):,} 円")

                        equity_rel = data.get("equity_curve_path", None)
                        if isinstance(equity_rel, str) and equity_rel:
                            # app.py と同じフォルダ内を基準に画像パスを解決
                            app_dir = os.path.dirname(__file__)
                            equity_path = os.path.join(app_dir, equity_rel)

                            # 画像生成のタイムラグを考慮して数回リトライ
                            found = False
                            for _ in range(3):
                                if os.path.isfile(equity_path):
                                    found = True
                                    break
                                time.sleep(0.3)

                            if found:
                                st.markdown("**資産曲線**")
                                st.image(equity_path, use_column_width=True)
                            else:
                                st.warning(
                                    "資産曲線画像が見つかりませんでした。"
                                    f"\n想定パス: {equity_path}"
                                )
                else:
                    err_msg = stderr.strip()
                    if not err_msg:
                        err_msg = "Rスクリプト実行中に不明なエラーが発生しました（stderr が空です）。"
                    st.error(
                        f"Rエンジンの実行に失敗しました（コード: {result.returncode}）。\n"
                        f"エラーメッセージ:\n{err_msg}"
                    )
            except Exception as e:
                st.error(f"Rエンジン呼び出し中に予期せぬエラーが発生しました: {e}")
