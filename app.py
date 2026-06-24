import os
import json
import logging
from flask import Flask, request, jsonify, render_template_string
from dotenv import load_dotenv
from google import genai
from scenario_router import build_precision_engine_prompt
import io
from flask import send_file
from xhtml2pdf import pisa
import time
from google.genai.errors import APIError # Assuming the standard SDK error wrapper


# Load environment variables
load_dotenv()

# Setup safe system logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

app = Flask(__name__)

# Verify API key presence using our resilient fallback check
API_KEY = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("GEMINI_API_KEY or GOOGLE_API_KEY environment variable not set.")

client = genai.Client(api_key=API_KEY)

# --- Define explicit model references to eliminate ambiguity ---
MODEL_NAME = "gemini-2.5-flash"

DB_FILE = "scenarios.json"
OUTPUT_DIR = "output_entries"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def generate_with_retry(precision_prompt, config, max_retries=3):
    delay = 2  # Start with a 2-second delay
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=precision_prompt,
                config=config
            )
            return response.text
            
        except Exception as e:
            # If we hit a server overload (429 or 503) and have retries left...
            if attempt < max_retries - 1:
                print(f"Google Server busy (Error: {e}). Retrying in {delay} seconds...")
                time.sleep(delay)
                delay *= 2  # Exponentially backoff (2s -> 4s -> 8s)
            else:
                # If it fails after all retries, raise the error to the frontend
                raise e

# =====================================================================
# INSERTED ROUTER FUNCTION (AI Studio / google-genai version)
# =====================================================================
def handle_user_cultural_query(user_scenario_input: str, target_country: str) -> str:
    """
    UI画面からユーザー入力を受け取り、シナリオルーターを通じて変換し、ライブのGoogle Searchグラウンディングと自動429リトライ操作で
    Google AI Studio Client を使用して Gemini で実行します。
    """
    precision_prompt = build_precision_engine_prompt(user_scenario_input, target_country)
    
    config = {
        "max_output_tokens": 8192,
        "tools": [{"google_search": {}}]
    }
    
    # 🟢 RETRY CONFIGURATION
    max_retries = 3
    delay = 2  # Start with a 2-second pause if Google is busy
    
    for attempt in range(max_retries):
        try:
            # Execute the network call
            response = client.models.generate_content(
                model=MODEL_NAME,
                contents=precision_prompt,
                config=config
            )
            return response.text  # 🎉 Success! Return the data immediately.
            
            
        except Exception as e:
            # If we hit a 429 server block and have retries left, pause and try again
            if attempt < max_retries - 1:
                print(f"Google API busy (Attempt {attempt + 1}/{max_retries}). Retrying in {delay}s... Error: {e}")
                time.sleep(delay)
                delay *= 2  # Double the wait time for the next try (2s -> 4s)
            else:
                # 🛑 Out of retries. Catch the final failure gracefully for the UI
                print(f"Final API failure after {max_retries} attempts: {e}")
                return (
                    "<div class='p-5 border border-red-200 bg-red-50 text-red-700 rounded-xl shadow-sm'>"
                    "   <h3 class='font-bold text-sm mb-1'>⏳ Google Server Capacity Exhausted</h3>"
                    "   <p class='text-xs opacity-90 leading-relaxed'>"
                    "       The shared free-tier AI Studio servers are temporarily overloaded globally. "
                    f"       The application automatically retried {max_retries} times but was throttled. "
                    "       Please wait a minute and hit 'Analyze' again. "
                    "   </p>"
                    "</div>"
                )          

def load_db():
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Database Auto-Healing Layer
            healed = False
            for record in data:
                if "type" not in record:
                    record["type"] = "corporate"
                    healed = True
            if healed:
                with open(DB_FILE, "w", encoding="utf-8") as wf:
                    json.dump(data, wf, ensure_ascii=False, indent=4)
                logging.info("💾 Database Auto-Healed: Successfully upgraded older scenarios to 'corporate' type.")
            return data
    except Exception as e:
        logging.error(f"Error loading database: {e}")
        return []

def save_db(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logging.error(f"Error saving database: {e}")

# =====================================================================
# SYSTEM PROMPTS & ARCHETYPES
# =====================================================================

ROUTER_PROMPT = """
あなたはトリアージュルーティングの専門エージェントです。人間世界の摩擦を分析し、以下の2つのカテゴリのいずれかに分類してください:
1. 'corporate' - プロフェッショナルな環境、オフィスの政治、上司と部下の摩擦、チームのパフォーマンス、クライアントの問題、または企業のワークフローに関連する問題。
2. 'everyday' - 隣人、家庭の物流、友人関係、小売/コミュニティの相互作用、家族システム、または公共の行動に関連する問題。

正確に1つの単語で応答してください: 'corporate' または 'everyday'。マークダウンや句読点は含めないでください。
"""

# Base layout components kept in storage variables for bulletproof layout execution
MASTERPIECE_HEAD_LAYOUT = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Cultural OS Engine - 診断レポート</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap');
        
        body {
            font-family: 'Plus Jakarta Sans', sans-serif;
            background-color: #f8fafc;
            line-height: 1.75;
        }
        
        .hero-gradient-corporate {
            background: linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%);
            border: 1px solid #bfdbfe; /* Fixed a small typo here ('border' to 'solid') */
        }
        
        .hero-gradient-everyday {
            background: linear-gradient(135deg, #f3e8ff 0%, #fae8ff 100%);
            border: 1px solid #e9d5ff; /* Fixed a small typo here ('border' to 'solid') */
        }

        /* =====================================================================
        FORCE ALL SEARCH GROUNDING LINKS TO BE VISIBLE & BRAND-COLORED
        ===================================================================== */
        .bg-slate-50 ul a,
        .bg-slate-50 a[href] {
            color: #2563eb !important;          /* Crisp Tailwind Blue-600 */
            text-decoration: underline !important; /* Forces the underline so it looks like a link */
            font-weight: 600 !important;          /* Makes the text slightly thicker */
            transition: color 0.15s ease-in-out;
        }

        /* Change color dynamically when hovering over the link */
        .bg-slate-50 ul a:hover,
        .bg-slate-50 a[href]:hover {
            color: #1d4ed8 !important;          /* Darker Blue-700 on hover */
        }
    </style>
</head>
<body class="p-4 md:p-8 max-w-7xl mx-auto text-slate-800">
"""

MASTERPIECE_FOOT_LAYOUT = """
</body>
</html>
"""

CORE_ENGINE_PROMPT = """
あなたは、極めて優秀な「カルチュラルOS（Cultural OS）アナリスト」です。
与えられたシチュエーションについて、二面性を持つ厳格な「デュアル軸フレームワーク」を用いて詳細に分析し、検索ツール（Google Search）から得た現実世界の正確なデータを用いて厳密なグラウンディング（根拠付け）を行ってください。

【シナリオタイプ（Scenario_Type）に基づくアーキタイプ判定】
割り当てられた 'Scenario_Type' に応じて、適切なアーキタイプとカラーテーマを決定してください：
- 'corporate'（ビジネス・組織）の場合：
  「軸A：タスク優先の実行（Task-First Execution）」 vs 「軸B：関係性優先の協働（Relationship-First Collaboration）」
  カラーテーマは深みのあるブルー/グリーン系（deep blues/greens）を使用。
- 'everyday'（日常・一般社会）の場合：
  「軸A：個人の自立　自立型）」 vs 「軸B：コミュニティの相互依存（調和重視型）」
  カラーテーマは深みのあるパープル/アンバー系（deep purples/ambers）を使用。

【出力の絶対ルール】
1. マークダウンのコードブロック（```html や 
```）は絶対に含めないでください。
2. 以下のHTMLレイアウト構造を、完全に保ったまま出力してください。
3. [ ] で囲まれたプレースホルダー部分（例: [OS_LABEL], [THEME_TITLE] など）を、あなたが日本語（または指定の英語表記）で分析・作成した内容に正しく置き換えてください。それ以外のHTMLタグや既存のクラス名、URLリンクは1文字も変更しないでください。
4. すべての国名とメタデータフィールドを必ず日本語で出力してください（例: 'Czech'ではなく'チェコ' ）

【タイトルの厳格なルール】
[THEME_TITLE] には、シャープでエグゼクティブ感のある、プロフェッショナルな見出しを生成してください。
- タイトルの冒頭に、「〜のナビゲート」「〜の理解」「〜の架け橋」「〜のバランス」といった、AIが好みがちな陳腐な表現（"Navigating", "Understanding" など）は絶対に避けてください。
- 「精密性とパートナーシップのパラドックス」「ベンダー紛争の解決策」「属性の重複」のように、直接的でインパクトのあるタイトルにすること。

以下のレイアウトタグから出力を直接開始してください：

<div class="[HERO_GRADIENT_CLASS] rounded-2xl p-6 md:p-8 mb-8 shadow-sm relative group">
    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-4">
        <div class="flex items-center gap-3">
            <span class="text-xs uppercase font-bold tracking-widest px-3 py-1 rounded-full text-white [BADGE_BG_CLASS]">[OS_LABEL]</span>
            <span class="inline-flex items-center px-3 py-1 rounded-full text-xs font-bold text-gray-800 bg-white border border-gray-200 shadow-sm">
                📍 法域: [TARGET_COUNTRY]
            </span>
        </div>
        
        <div class="flex items-center gap-4 self-start sm:self-auto">
            <a href="/api/export-pdf/[ID_PLACEHOLDER]" class="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-700 bg-white hover:bg-slate-100 px-3 py-1.5 rounded-lg border border-slate-200 shadow-sm transition-colors duration-200">
                <svg class="w-3.5 h-3.5 text-slate-600" fill="none" stroke="currentColor" stroke-width="2.5" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3"></path>
                </svg>
                PDFダウンロード
            </a>
            
            <a href="/index.html" class="inline-flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-slate-500 hover:text-slate-800 px-2 py-1 transition-colors duration-200">
                &larr; ライブラリダッシュボード
            </a>
        </div>
    </div>
    
    <h1 class="text-2xl md:text-4xl font-extrabold tracking-tight text-slate-900 mb-4">[THEME_TITLE]</h1>
    <p class="text-slate-700 text-base md:text-lg max-w-3xl leading-relaxed"><strong>シチュエーション:</strong> [USER_SCENARIO]</p>
</div>

<div class="bg-gradient-to-r from-slate-900 to-slate-800 text-white p-6 md:p-8 rounded-2xl shadow-md mb-8">
    <h2 class="text-xl font-bold text-amber-400 mb-3">ハイブリッドソリューション</h2>
    <div class="text-slate-200 space-y-4 leading-relaxed">[両方のスペクトラム（軸Aと軸B）を犠牲にすることなく、互いの長所を融合させた、洗練されたステップ・バイ・ステップの解決策を日本語で記述してください。Google検索で得られた現代のベストプラクティスや構造的ガイドラインに厳密に基づいた、具体的かつ明確な指示を含めること。]</div>
</div>

<div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-8">
    <div class="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm">
        <h2 class="text-lg font-bold [AXIS_A_TEXT_CLASS] mb-3">[軸Aのタイトル（例：タスク優先の実行）]</h2>
        <div class="text-slate-600 space-y-3 leading-relaxed">[このシチュエーションを、完全に軸Aのマインドセットから詳細に分析してください。分析を裏付けるために、Google検索で取得した関連データ、文化的インサイト、企業の統計データ、または地域の法的な規範や慣習を組み込み、確実なグラウンディングを行ってください。]</div>
    </div>
    <div class="bg-white p-6 rounded-2xl border border-slate-100 shadow-sm">
        <h2 class="text-lg font-bold [AXIS_B_TEXT_CLASS] mb-3">[軸Bのタイトル（例：関係性優先の協働）]</h2>
        <div class="text-slate-600 space-y-3 leading-relaxed">[このシチュエーションを、完全に軸Bのマインドセットから詳細に分析してください。分析を裏付けるために、Google検索で取得した関連データ、文化的インサイト、企業の統計データ、または地域の法的な規範や慣習を組み込み、確実なグラウンディングを行ってください。]</div>
    </div>
</div>

<!-- GROUNDED RESEARCH FOOTNOTES SECTION -->
<div class="bg-slate-50 border border-slate-200 rounded-2xl p-5 mb-8">
    <h3 class="text-xs font-bold uppercase tracking-wider text-slate-500 mb-3 flex items-center gap-2">
        🔍 検証済みの現実世界検索データ（グラウンディング）
    </h3>
    <p class="text-xs text-slate-500 mb-4">この行動分析を確かな事実、現地の法律、および文化的基準に裏付けるため、リアルタイムで以下のウェブソースを照会しました：</p>
    <ul class="space-y-2 text-xs text-slate-600">
        [Google検索の結果から使用した2〜3の重要な情報源を、箇条書きのリストとして生成してください。URLを指すクリーンなタイトルを持つクリック可能なアンカータグ（<a class="text-blue-600 hover:underline" href="...">サイト名</a>）と、そこから抽出したデータについての簡潔な1文の説明を添えてください。]
    </ul>
</div>

<!-- ACTIONS FOOTER NAVIGATION ROW -->
<div class="mt-8 pt-6 border-t border-slate-200 flex flex-col sm:flex-row justify-between items-center gap-4">
    <a href="/index.html" class="inline-flex items-center gap-2 text-sm font-semibold text-slate-600 hover:text-slate-900 transition-colors order-2 sm:order-1">
        &larr; ライブラリ・ダッシュボードに戻る
    </a>
</div>
"""


# =====================================================================
# DASHBOARD TEMPLATE UI
# =====================================================================

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Corporate OS Library - Console</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Plus Jakarta Sans', sans-serif; background-color: #FAF9F6; }
    </style>
</head>
<body class="max-w-7xl mx-auto px-4 py-8 md:py-12">
    <header class="mb-12">
        <h1 class="text-3xl font-extrabold tracking-tight text-slate-900 md:text-4xl">カルチャーOS アーキテクチャーマトリクス</h1>
        <p class="text-slate-500 mt-2 text-sm md:text-base">ライブGoogle検索グラウンディングを備えたオーケストレーション型マルチエージェント分析プラットフォーム.</p>
    </header>

    <main class="grid grid-cols-1 lg:grid-cols-3 gap-8">
        <section class="lg:col-span-1 bg-white p-6 rounded-2xl border border-slate-100 shadow-sm h-fit">
            <h2 class="text-lg font-bold text-slate-900 mb-4">摩擦が起こっている状況を書き込んでください</h2>
            <form id="scenarioForm" onsubmit="return false;" class="space-y-4">
                <div>
                    <label class="block text-xs font-semibold text-slate-500 uppercase tracking-wider mb-2">シナリオの詳細</label>
                    <textarea id="scenarioText" rows="6" required class="w-full p-4 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-slate-900 transition-all placeholder:text-slate-400" placeholder="緊張点や行動上の摩擦について説明してください..."></textarea>
                    
                    <div class="input-group" style="margin-bottom: 1.5rem;">
                        <label for="countrySelect" style="display: block; font-weight: bold; margin-bottom: 0.5rem; color: #b59410;">
                            対象法域/国
                        </label>
                        <select id="countrySelect" style="
                            width: 100%; 
                            padding: 0.75rem; 
                            border-radius: 6px; 
                            border: 1px solid #ccc; 
                            background-color: #fff; 
                            font-size: 1rem;
                            box-shadow: inset 0 1px 3px rgba(0,0,0,0.1);
                        ">
                            <option value="" disabled selected>-- 国を選択してください --</option>
                            <option value="United States">米国</option>
                            <option value="Germany">ドイツ</option>
                            <option value="France">フランス</option>
                            <option value="Japan">日本</option>
                            <option value="United Kingdom">イギリス</option>
                            <option value="Singapore">シンガポール</option>
                            <option value="Australia">オーストラリア</option>
                            <option value="Brazil">ブラジル</option>
                            <option value="Egypt">エジプト</option>
                            <option value="Czech">チェコ</option>
                            <option value="Switzerland">スイス</option>
                            <option value="South Korea">韓国</option>
                        </select>
                    </div>
                </div>
                <button type="submit" id="submitBtn" class="w-full bg-slate-900 hover:bg-slate-800 text-white font-semibold py-3 px-4 rounded-xl text-sm transition-colors shadow-sm flex items-center justify-center gap-2">
                    <span>分析と分類実行</span>
                </button>  
            </form>
        </section>

        <section class="lg:col-span-2">
            <h2 class="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
                分析記録カード
                <span id="recordCount" class="bg-slate-100 text-slate-600 text-xs px-2.5 py-1 rounded-full font-bold">{{ scenarios|length }}</span>
            </h2>

            <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-6">
                <div class="flex items-center gap-2 bg-slate-100 p-1.5 rounded-xl max-w-md flex-1">
                    <button onclick="filterCards('all')" id="btn-filter-all" class="flex-1 text-xs font-bold uppercase tracking-wider py-2 px-3 rounded-lg bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/50 transition-all duration-150 text-center">
                        すべて
                    </button>
                    <button onclick="filterCards('corporate')" id="btn-filter-corporate" class="flex-1 text-xs font-semibold uppercase tracking-wider py-2 px-3 rounded-lg text-slate-400 hover:text-slate-700 transition-all duration-150 text-center">
                        コーポレートOS
                    </button>
                    <button onclick="filterCards('everyday')" id="btn-filter-everyday" class="flex-1 text-xs font-semibold uppercase tracking-wider py-2 px-3 rounded-lg text-slate-400 hover:text-slate-700 transition-all duration-150 text-center">
                        エブリデイOS
                    </button>
                </div> 

                <div class="flex items-center gap-2">
                    <label for="countrySort" class="text-xs font-bold uppercase tracking-wider text-slate-400">並べ替え:</label>
                    <select id="countrySort" onchange="sortCardsByCountry(this.value)" class="text-xs font-semibold text-slate-700 bg-white border border-slate-200 p-2.5 rounded-xl shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500/20">
                        <option value="none">最新</option>
                        <option value="asc">国名(あいうえお順)</option>
                    </select>
                </div>  
            </div>
                    
            <div id="cardsContainer" class="grid grid-cols-1 md:grid-cols-2 gap-4">
                {% for s in scenarios %}
                <div class="bg-white p-5 rounded-2xl border border-slate-100 shadow-sm relative group hover:border-slate-300 transform opacity-100 translate-y-0 transition-all duration-300 flex flex-col justify-between h-60" id="card-{{ s.id }}" data-os-type="{{ s.type }}" data-country="{{ s.country | lower }}">
                    <div>
                        <div class="flex justify-between items-start mb-3">
                            <div class="flex flex-col gap-1">
                                <span class="card-number-label text-xs font-bold text-slate-400 tracking-wider">シナリオ番号</span>
                                {% if s.country %}
                                <span class="inline-flex items-center gap-1 mt-0.5 text-[10px] font-bold text-slate-600 uppercase tracking-wider bg-slate-100 border border-slate-200/80 px-2 py-0.5 rounded-md w-fit">
                                    📍 {{ s.country }}
                                </span>
                                {% endif %}
                            </div>
                            {% if s.type == "corporate" %}
                            <span class="text-xs bg-blue-600 text-white font-bold px-3 py-1 rounded-full uppercase tracking-wider shadow-sm">コーポレートOS</span>
                            {% else %}
                            <span class="text-xs bg-purple-600 text-white font-bold px-3 py-1 rounded-full uppercase tracking-wider shadow-sm">エブリデイOS</span>
                            {% endif %}
                        </div>
                        <p class="text-slate-800 font-semibold text-sm line-clamp-3 mb-4 pr-6">{{ s.snippet }}</p>
                    </div>
                    <div class="flex gap-2 mt-auto items-center">
                        <a href="/output_entries/{{ s.id }}.html" target="_self" class="flex-1 text-center bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-bold py-2.5 px-4 rounded-xl border border-slate-200 transition-colors">
                            分析マトリクスを開く
                        </a>
                        <span class="text-[11px] font-mono font-bold text-slate-500 tracking-wider select-none">ID-{{ s.id }}</span>
                        
                        <button onclick="deleteCard({{ s.id }})" class="p-2.5 rounded-xl border border-red-200 text-red-500 hover:bg-red-50 transition-colors shadow-sm">
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg>
                        </button>
                    </div>
                </div>
                {% endfor %}
            </div>
        </section>
    </main>

    <script>
        
        // 🟢 1. Form Submission Hook (Event Listener)
             document.getElementById("scenarioForm").addEventListener("submit", async (e) => {
            e.preventDefault();

            const btn = document.getElementById("submitBtn");
            if (btn.disabled) return; 

            const textValue = document.getElementById("scenarioText").value.trim();
            if (!textValue) return;

            const selectedCountry = document.getElementById("countrySelect").value;

            if (!selectedCountry) {
                alert("Please select a target country before generating your compliance mapping.");
                return; 
            }

            btn.disabled = true;
            btn.innerHTML = '<svg class="animate-spin h-4 w-4 text-white inline mr-2" fill="none" viewBox="0 0 24 24"><circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle><path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path></svg><span>検索・処理中</span>';

            try { 
                const response = await fetch("/api/generate", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ 
                        scenario: textValue,      
                        country: selectedCountry  
                    })
                });
                
                const contentType = response.headers.get("content-type");
                if (!contentType || !contentType.includes("application/json")) {
                    throw new Error("Server error: Received unexpected raw response markup from environment backend.");
                }

                const result = await response.json();
                if (result.error) throw new Error(result.error);

                appendCard(result.data);
                
                // 🧼 Clear the text input area
                document.getElementById("scenarioText").value = ""; 
                
                // 🟢 Reset the country selector dropdown back to its empty default option
                document.getElementById("countrySelect").value = "";
                
            } catch (err) {
                alert("Execution Deficit: " + err.message);
            } finally {
                btn.disabled = false;
                btn.innerHTML = "<span>分析と分類実行</span>";
            }
        });

        // 🟢 Update this inside the <script> block of your DASHBOARD_HTML string
        function appendCard(data) {
            const container = document.getElementById("cardsContainer");
            const card = document.createElement("div");
            
            card.setAttribute("data-os-type", data.type);
            card.setAttribute("data-country", (data.country || "").toLowerCase());
            card.className = "bg-white p-5 rounded-2xl border border-slate-100 shadow-sm relative group hover:border-slate-300 transform opacity-100 translate-y-0 transition-all duration-300 flex flex-col justify-between h-60";
            card.id = "card-" + data.id;  

            // 🎌 1. COUNTRY TRANSLATION MAP
            // This dynamically converts the database's English country names into beautiful Japanese on display.
            const countryMap = {
                'czech': 'チェコ',
                'germany': 'ドイツ',
                'france': 'フランス',
                'united states': 'アメリカ',
                'japan': '日本',
                'united kingdom': 'イギリス',
                'south korea': '韓国',
                'singapore': 'シンガポール',
                'australia': 'オーストラリア',
                'brazil': 'ブラジル',
                'egypt': 'エジプト',
                'switzerland': 'スイス'
            };
            
            // Safely get the lowercase version to protect against variations like "Czech" vs "czech"
            const lookupKey = (data.country || "").toLowerCase();
            const displayCountry = countryMap[lookupKey] || data.country;

            // 🟢 THE FIX: Set the attribute using the raw lookupKey directly!
            card.setAttribute("data-sort-name", lookupKey);
            
            card.className = "bg-white p-5 rounded-2xl border border-slate-100 shadow-sm relative group hover:border-slate-300 transform opacity-100 translate-y-0 transition-all duration-300 flex flex-col justify-between h-60";

            let countryBadgeHtml = '';
            if (data.country) {
                // 🟢 FIXED: Using displayCountry instead of raw data.country
                countryBadgeHtml = '<span class="inline-flex items-center gap-1 mt-0.5 text-[10px] font-bold text-slate-600 uppercase tracking-wider bg-slate-100 border border-slate-200/80 px-2 py-0.5 rounded-md w-fit">📍 ' + displayCountry + '</span>';
            }

            // 🎌 2. TYPE LABELS IN JAPANESE
            let badgeColor = data.type === 'corporate' ? 'bg-blue-600' : 'bg-purple-600';
            // 🟢 FIXED: Swapped 'Corporate OS' and 'Everyday OS' strings directly to Japanese display texts
            let badgeLabel = data.type === 'corporate' ? 'コーポレートOSアセット' : 'エブリデイOSアセット';

            card.innerHTML = 
                '<div>' +
                    '<div class="flex justify-between items-start mb-3">' +
                        '<div class="flex flex-col gap-1">' +
                            // 🟢 Visual Placeholder
                            '<span class="card-number-label text-xs font-bold text-slate-400 tracking-wider">シナリオ番号</span>' + 
                            countryBadgeHtml +
                        '</div>' +
                        '<span class="text-xs ' + badgeColor + ' text-white font-bold px-3 py-1 rounded-full uppercase tracking-wider shadow-sm">' +
                            badgeLabel +
                        '</span>' +
                    '</div>' +
                    '<p class="text-slate-800 font-semibold text-sm line-clamp-3 mb-4 pr-6">' + data.snippet + '</p>' +
                '</div>' +

                '<div class="flex gap-2 mt-auto items-center">' +
                    '<a href="/output_entries/' + data.id + '.html" target="_self" class="flex-1 text-center bg-slate-50 hover:bg-slate-100 text-slate-700 text-xs font-bold py-2.5 px-4 rounded-xl border border-slate-200 transition-colors">分析マトリクスを開く</a>' +
                    '<span class="text-[11px] font-mono font-bold text-slate-500 tracking-wider select-none">ID-' + data.id + '</span>' +
                    '<button onclick="deleteCard(' + data.id + ')" class="p-2.5 rounded-xl border border-red-200 text-red-500 hover:bg-red-50 transition-colors shadow-sm"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" /></svg></button>' +
                '</div>';
            
            container.insertBefore(card, container.firstChild);
            reindexCards();
        }          

        // 🟢 3. Dynamic Filtering Layout Processor
        function filterCards(type) {
            const container = document.getElementById("cardsContainer");
            const cards = container.children;
            
            for (let i = 0; i < cards.length; i++) {
                let card = cards[i];
                let cardType = card.getAttribute("data-os-type");
                
                if (type === "all" || cardType === type) {
                    card.style.display = "flex";
                    card.classList.remove("opacity-0", "translate-y-2");
                    card.classList.add("opacity-100", "translate-y-0");
                } else {
                    card.style.display = "none";
                    card.classList.remove("opacity-100", "translate-y-0");
                    card.classList.add("opacity-0", "translate-y-2");
                }
            }
            
            const filterTypes = ['all', 'corporate', 'everyday'];
            for (let j = 0; j < filterTypes.length; j++) {
                let t = filterTypes[j];
                let btn = document.getElementById("btn-filter-" + t);
                if (!btn) continue;

                if (t === type) {
                    btn.className = "flex-1 text-xs font-extrabold uppercase tracking-wider py-2 px-3 rounded-lg bg-white text-slate-900 shadow-sm ring-1 ring-slate-200/50 scale-[1.02] transition-all duration-200 text-center";
                } else {
                    btn.className = "flex-1 text-xs font-semibold uppercase tracking-wider py-2 px-3 rounded-lg text-slate-400 hover:text-slate-700 transition-all duration-200 text-center";
                }
            }
        }

        // 🟢 4. True Japanese Syllabary (あいうえお順) Sorting Engine
        function sortCardsByCountry(order) {
            const container = document.getElementById('cardsContainer');
            // Grab elements by your 'group' utility class name
            const cards = Array.from(container.getElementsByClassName('group'));
            
            // 🎌 INTERNAL HIRAGANA ORDER MAP (For precise あいうえお順 calculations)
            const kanaMap = {
                'united states': 'あめりか',
                'australia': 'おーすとらりあ',
                'egypt': 'えじぷと',
                'united kingdom': 'いぎりす',
                'switzerland': 'すいす',
                'singapore': 'しんがぽーる',
                'czech': 'ちぇこ',
                'germany': 'どいつ',
                'brazil': 'ぶらじる',
                'france': 'ふらんす',
                'japan': 'にほん',
                'south korea': 'かんこく'
            };
            
            if (order === 'none') {
                // 🟢 Forcefully sort by ID descending (highest ID / newest on top)
                cards.sort((a, b) => {
                    let idA = parseInt(a.id.replace('card-', '')) || 0;
                    let idB = parseInt(b.id.replace('card-', '')) || 0;
                    return idB - idA; 
                });
            } else if (order === 'asc') {
                // 🎌 True Japanese Syllabary Sort
                cards.sort((a, b) => {
                    // 1. Fetch the baseline raw country values (e.g., 'japan', 'czech')
                    let rawA = (a.getAttribute('data-country') || '').trim().toLowerCase();
                    let rawB = (b.getAttribute('data-country') || '').trim().toLowerCase();
                    
                    // Fallback string if attribute is missing
                    if (!rawA) return 1;
                    if (!rawB) return -1;

                    // 2. Map the English database keys to pure Hiragana calculation keys
                    let phoneticA = kanaMap[rawA] || rawA;
                    let phoneticB = kanaMap[rawB] || rawB;
                    
                    // 3. Compare utilizing native Japanese linguistic rules
                    return phoneticA.localeCompare(phoneticB, 'ja');
                });
            }
            
            // Clear and re-append in the guaranteed correct order
            for (let k = 0; k < cards.length; k++) {
                container.appendChild(cards[k]);
            }
            
            // Always refresh numbers after changing the structural order
            reindexCards();
        }

        // 🟢 Dynamic Reindexing Engine (With Country Translation Sync)
        function reindexCards() {
            const container = document.getElementById("cardsContainer");
            const cards = container.children; 
            const count = cards.length;
            
            document.getElementById("recordCount").innerText = count;
            
            const countryMap = {
                'czech': 'チェコ',
                'germany': 'ドイツ',
                'france': 'フランス',
                'united states': 'アメリカ',
                'japan': '日本',
                'united kingdom': 'イギリス',
                'south korea': '韓国',
                'singapore': 'シンガポール',
                'australia': 'オーストラリア',
                'brazil': 'ブラジル',
                'egypt': 'エジプト',
                'switzerland': 'スイス'
            };
            
            for (let i = 0; i < count; i++) {
                const card = cards[i];
                
                // 1. Force clean sequential numbers visually
                const label = card.getElementsByClassName("card-number-label")[0];
                if (label) {
                    label.innerText = "シナリオ番号 " + (count - i);
                }
                
                // 2. Sync and translate country names on redraw
                const rawCountry = card.getAttribute("data-country") || "";
                const lookupKey = rawCountry.trim().toLowerCase();
                if (lookupKey && countryMap[lookupKey]) {
                    const spans = card.getElementsByTagName("span");
                    for (let j = 0; j < spans.length; j++) {
                        if (spans[j].textContent.includes("📍")) {
                            spans[j].textContent = "📍 " + countryMap[lookupKey];
                            break; 
                        }
                    }
                }

                // 3. 🟢 FIX: Ensure the link button text stays locked in Japanese on reload
                const actionButton = card.querySelector("a");
                if (actionButton) {
                    actionButton.textContent = "分析マトリクスを開く";
                }

                // 4. 🟢 FIX: Ensure the OS category label text stays locked as "コーポレートOSアセット"
                const osType = card.getAttribute("data-os-type");
                if (osType) {
                    // Find the category badge (the one on the right side of the card header)
                    const badges = card.querySelectorAll("span");
                    badges.forEach(badge => {
                        if (badge.textContent.includes("OS")) {
                            badge.textContent = osType === 'corporate' ? 'コーポレートOS' : 'エブリデイOS';
                        }
                    });
                }
            }
        }

        // 🟢 Record Eraser Function
        async function deleteCard(id) {
            if (!confirm("Are you sure you want to permanently delete this operational scenario archive?")) return;
            
            try {
                const response = await fetch("/api/delete/" + id, { method: "DELETE" });
                const result = await response.json();
                
                if (result.success) {
                    const card = document.getElementById("card-" + id);
                    if (card) {
                        card.remove();
                        reindexCards();
                    }
                } else {
                    alert("Deletion Deficit: " + result.error);
                }
            } catch (err) {
                alert("System Deficit: Could not contact your local server endpoint.");
            }
        }

        // 🎌 BACK-BUTTON CACHE INTERCEPTOR
        // This forces the dashboard to translate country names and fix sequence counts
        // even if the user arrives here via the browser's "Back" button.
        window.addEventListener('pageshow', function(event) {
            // event.persisted is true if the page was loaded from the browser cache
            console.log("🔄 Dashboard view activated. Persisted from cache:", event.persisted);
            
            // Force a structural sync no matter how the user reached the page
            if (typeof reindexCards === 'function') {
                reindexCards();
            }
        });

    </script>
</body>
</html>
"""

# =====================================================================
# SYSTEM CONTROL ROUTES
# =====================================================================

@app.route("/")
@app.route("/index.html")
def index_route():
    scenarios = load_db()
    # 🟢 Reverse the list so the newest scenarios sit at the top of the deck!
    scenarios_reversed = scenarios[::-1]

    return render_template_string(DASHBOARD_HTML, scenarios=scenarios_reversed)

@app.route("/output_entries/<filename>")
def serve_output_entry(filename):
    filepath = os.path.join(OUTPUT_DIR, filename)
    if not os.path.exists(filepath):
         return "Analysis page not compiled.", 404
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return f"Error opening matrix entry: {e}", 500

@app.route("/api/generate", methods=["POST"])
def api_generate():   

    try:
        # EXTRACT USER INPUT AND THE NEW COUNTRY VARIABLE FROM FRONTEND PAYLOAD
        user_input = request.json.get("scenario", "").strip()
        country = request.json.get("country", "").strip()
        
        if not user_input:
            return jsonify({"error": "Empty prompt package received."}), 400
            
        if not country:
            return jsonify({"error": "Missing target jurisdiction / country selection."}), 400
        
        # ---- STAGE 1: EXECUTE PERSONA MULTI-AGENT ROUTING (UPDATED SYNTAX) ----
        router_response = client.models.generate_content(
            model=MODEL_NAME,
            contents=f"{ROUTER_PROMPT}\n\nScenario to triage:\n\"{user_input}\""
        )
        router_res = router_response.text.strip().lower()

        # =====================================================================
        # STAGE 1.2: RESOLVE ARCHETYPE & STYLING VARIABLES (MOVED UP)
        # =====================================================================
        resolved_type = "corporate" if "corporate" in router_res else "everyday"
        logging.info(f"🚦 Multi-Agent Orchestrator routed input to archetype: {resolved_type.upper()}")        
       
        if resolved_type == "corporate":
            hero_grad = "hero-gradient-corporate"
            badge_bg = "bg-blue-600"
            os_lbl = "Corporate OS Asset"
            os_lbl_ja = "コーポレートOSアセット"  # 🟢 New Japanese Display Variable
            ax_a_cls = "text-blue-700"
            ax_b_cls = "text-emerald-700"
        else:
            hero_grad = "hero-gradient-everyday"
            badge_bg = "bg-purple-600"
            os_lbl = "Everyday OS Asset"
            os_lbl_ja = "エブリデイOSアセット"   # 🟢 New Japanese Display Variable
            ax_a_cls = "text-indigo-700"
            ax_b_cls = "text-amber-700"

        # =====================================================================
        # STAGE 1.5: GENERATE PRECISION CONSTRAINTS (UPDATED WITH COUNTRY VARIABLE)
        # =====================================================================
        # Pass the dynamically selected country instead of "the target region"
        precision_prompt = build_precision_engine_prompt(user_input, country)

        # All variables inside here exist perfectly! 👍
        execution_prompt = (
            f"{CORE_ENGINE_PROMPT}\n\n"
            f"Execution Parameters Assigned:\n"
            f"- Scenario_Type: '{resolved_type}'\n"
            f"- Target_Jurisdiction: '{country}'\n" 
            f"- [HERO_GRADIENT_CLASS]: '{hero_grad}'\n"
            f"- [BADGE_BG_CLASS]: '{badge_bg}'\n"
            f"- [OS_LABEL]: '{os_lbl_ja}'\n"
            f"- [AXIS_A_TEXT_CLASS]: '{ax_a_cls}'\n"
            f"- [AXIS_B_TEXT_CLASS]: '{ax_b_cls}'\n\n"
            f"Analyze this input scenario using real-time search context inputs:\n"
            f"{precision_prompt}"
        )

        # ---- STAGE 2: CONFIGURING EXPERT ENGINE + LIVE GOOGLE SEARCH GROUNDING ----
        # Build search grounding configuration layout using types mapping
        search_config = {
            "tools": [{"google_search": {}}],
            "temperature": 0.3
        }

       # Call the unified client directly, passing our search configuration
        expert_response = client.models.generate_content(
            model=MODEL_NAME,
            contents=execution_prompt,
            config=search_config
        )

        # 1. Extract and clean the AI response text first
        analysis_markup = expert_response.text.strip()

        # Clean markdown code boundaries if any are added by the engine
        if analysis_markup.startswith("```html"):
            analysis_markup = analysis_markup[7:]
        if analysis_markup.endswith("```"):
            analysis_markup = analysis_markup[:-3]
        analysis_markup = analysis_markup.strip()

        # 🟢 FINAL TYPE SAFETIES (Moved here: right before the strings are injected!)
        if isinstance(os_lbl_ja, (list, tuple)):
            os_lbl_ja = os_lbl_ja[0] if os_lbl_ja else ""
            
        if isinstance(country, (list, tuple)):
            country = country[0] if country else ""

        # 2. Directly swap out the template tokens inside the AI's response markup
        analysis_markup = analysis_markup.replace("[HERO_GRADIENT_CLASS]", str(hero_grad))
        analysis_markup = analysis_markup.replace("[BADGE_BG_CLASS]", str(badge_bg))
        analysis_markup = analysis_markup.replace("[OS_LABEL]", str(os_lbl_ja))
        analysis_markup = analysis_markup.replace("[TARGET_COUNTRY]", str(country))
        analysis_markup = analysis_markup.replace("[AXIS_A_TEXT_CLASS]", str(ax_a_cls))
        analysis_markup = analysis_markup.replace("[AXIS_B_TEXT_CLASS]", str(ax_b_cls))
        analysis_markup = analysis_markup.replace("[USER_SCENARIO]", str(user_input))

        # 2. Safety Clean: Remove any accidental loose back-buttons the AI hardcoded by habit
        analysis_markup = analysis_markup.replace('&larr; Return to Library Dashboard', '')
        analysis_markup = analysis_markup.replace('Return to Library Dashboard', '')
    
        # 1. Combine layouts into the final full page string
        final_compiled_html = f"{MASTERPIECE_HEAD_LAYOUT}\n{analysis_markup}\n{MASTERPIECE_FOOT_LAYOUT}"

        # ---- STAGE 2.5: EXTRACT OR FALLBACK FOR TITLE ----
       
        try:
            # Captures the first 4 words of the input as a clean asset title
            short_title = " ".join(user_input.split()[:4]) if user_input else "Operational Scenario"
        except Exception:
            short_title = "Operational Scenario Data"

        # ---- STAGE 3: CALCULATE DATABASE LEDGER IDS ----
        scenarios = load_db()
        next_id = max([s["id"] for s in scenarios]) + 1 if scenarios else 1        
        snippet = user_input[:110] + "..." if len(user_input) > 110 else user_input

        # Run string corrections FIRST while next_id is fresh!
        final_compiled_html = final_compiled_html.replace("[ID_PLACEHOLDER]", str(next_id))

        # The AI-Proof Shield: Catch ANY creative text IDs Gemini tries to inject!
        import re
        final_compiled_html = re.sub(r'/api/export-pdf/[a-zA-Z0-9_-]+', f'/api/export-pdf/{next_id}', final_compiled_html)

        # 🚨 DIAGNOSTIC LINE (Now correctly placed after the replacement happens)
        print(f"--- DEBUG: Next ID is {next_id}. Does placeholder exist? {'[ID_PLACEHOLDER]' in final_compiled_html}")

        # 2. Build final database dictionary container with the fully finalized HTML string!
        new_record = {
            "id": next_id,
            "title": short_title,
            "snippet": snippet,
            "type": resolved_type,
            "country": country, 
            "analysis_html": final_compiled_html 
        }
        
        # 3. Commit cleanly to local database storage files
        scenarios.append(new_record)
        save_db(scenarios)

        # 4. Write cleanly to independent standalone file container
        with open(os.path.join("output_entries", f"{next_id}.html"), "w", encoding="utf-8") as hf:
            hf.write(final_compiled_html)

        return jsonify({"success": True, "data": new_record})
            
    except Exception as e:
        logging.error(f"Error in api_generate: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500           
    
    
@app.route("/api/export-pdf/<int:scenario_id>", methods=["GET"])
def export_pdf(scenario_id):
    try:
        # 🟢 Force the path engine to look inside your true OUTPUT_ENTRIES folder
        file_path = os.path.join("output_entries", f"{scenario_id}.html")
        
        logging.info(f"Checking for ledger file at target path: {file_path}")
        
        if not os.path.exists(file_path):
            logging.error(f"PDF Export Failed: File container '{file_path}' does not exist.")
            return jsonify({"success": False, "error": f"Scenario layout file {scenario_id}.html was not found."}), 404
            
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()
        
        import re
        
        # 1. Strip out external web font configurations
        html_content = re.sub(r'@import\s+url\([^)]+\);', '', html_content)
        html_content = re.sub(r'@font-face\s*{[^}]+}', '', html_content)

        # 2. Strip all '!important' tags to keep the CSS parser happy
        html_content = re.sub(r'\s*!important\s*', '', html_content)

        # 3. 🟢 THE IRONCLAD SHIELD: Neutralize any raw python lists hidden in the text fields
        # If Gemini wrote a list layout like ["constraint_1", "constraint_2"], 
        # this regex safely strips the brackets and quotes, turning it into pure plain text.
        html_content = re.sub(r"\[\s*['\"](.*?)['\"]\s*\]", r"\1", html_content)

        # 4. Force turn the final product into a guaranteed plain text string
        html_content = str(html_content)

        # 🎌 XHTML2PDF PROPRIETARY CJK WRAPPING PATCH 
        japanese_css_patch = """
        <style>
            hhtml, body, div, p, span, h1, h2, h3, h4, th, td, b, strong {
                font-family: HeiseiKakuGo-W5 !important; 
                -pdf-word-wrap: CJK !important;
                color: #000000 !important;              
                font-size: 13px !important;             
                line-height: 1.5 !important;             
            }
            h1, h2, h3, h4, th, b, strong {
                font-weight: bold;
                font-size: 16px;
            }
        </style>
        """
        
        # Securely combine the patch layout with your sanitized file content
        full_html_to_compile = japanese_css_patch + html_content
       
        # Build in-memory PDF stream container        
        pdf_buffer = io.BytesIO()

        # Compile the 100% clean string matrix to PDF format        
        pisa_status = pisa.CreatePDF(full_html_to_compile, dest=pdf_buffer)
        
        if pisa_status.err:
            return jsonify({"success": False, "error": "PDF compilation engine failure."}), 500
            
        pdf_buffer.seek(0)

        return send_file(
            pdf_buffer,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=f"Cultural_OS_Report_{scenario_id}.pdf"
        )

    except Exception as e:
        logging.error(f"Unexpected error in export_pdf: {str(e)}")
        return jsonify({"success": False, "error": str(e)}), 500

@app.route("/api/delete/<int:id>", methods=["DELETE"])
def api_delete(id):
    try:
        scenarios = load_db()
        filtered_scenarios = [s for s in scenarios if s["id"] != id]
        
        if len(scenarios) == len(filtered_scenarios):
            return jsonify({"success": False, "error": "Record element not matched."}), 404
            
        save_db(filtered_scenarios)
        
        html_path = os.path.join(OUTPUT_DIR, f"{id}.html")
        if os.path.exists(html_path):
            os.remove(html_path)
            
        return jsonify({"success": True})
    except Exception as e:
        logging.error(f"Delete Router Exception: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)

