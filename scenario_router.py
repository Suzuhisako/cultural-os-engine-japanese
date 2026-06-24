"""
Cultural OS シナリオルーター
本モジュールはユーザからのシナリオを分析し、15のCultural OSペアリングのいずれかに分類し、ハイパーパーソナライズされたコンプライアンス制約を適用します。
"""

SCENARIO_TARGET_MAP = {
    # 1. 意思決定・組織運営 (Decision & Governance)
    "decision_and_governance": {
        "keywords": ["根回し", "合意形成", "即決", "持ち帰り", "コンセンサス", "会議", "儀式", "アジェンダ"],
        "forced_constraints": "日本の企業統治、ringi-sho（稟議書）システムの歴史的背景、集団指導体制における意思決定速度の国際比較データ、およびJ-SOX法や社内規程における承認プロセスの厳格性"
    },
    
    # 2. 評価・キャリア・ジョブ型 (Evaluation & Career)
    "evaluation_and_career": {
        "keywords": ["成果主義", "数値目標", "KPI", "評価制度", "職務", "異動", "長期雇用", "市場価値", "ジョブ型"],
        "forced_constraints": "日本型雇用慣行（終身雇用・年功序列）の変遷、厚生労働省のジョブ型雇用推進ガイドライン、企業におけるエンゲージメントスコアの統計、および労働契約法に基づく配転命令（異動）の有効性判例"
    },
    
    # 3. 指示・コミュニケーション・評価 (Instruction & Feedback)
    "instruction_and_feedback": {
        "keywords": ["よしなに", "忖度", "仕様書", "オブラート", "指摘", "フィードバック", "コミュニケーション", "ミス"],
        "forced_sections": "エドワード・ホール（Edward T. Hall）の高文脈（ハイコンテキスト）文化理論における日本の位置づけ、ビジネスコミュニケーションにおける直接的・間接的フィードバックの心理的影響データ"
    },
    
    # 4. トラブル対応・リーガルリスク (Crisis & Legal Risk)
    "crisis_and_legal_risk": {
        "keywords": ["障害", "謝罪", "関係維持", "責任の所在", "法務", "ベンダー", "過失", "法的リスク"],
        "forced_constraints": "日本の民法における不法行為責任（民法709条）、示談・和解の法的性質、日本特有の「謝罪」が持つ社会的・関係修復的意味合いと、欧米法におけるADR（裁判外紛争解決手続）や責任承認リスクの比較データ"
    },
    
    # 5. 品質・開発プロセス (Quality & Agile)
    "quality_and_agile": {
        "keywords": ["職人肌", "エンジニア", "品質", "バグゼロ", "アジャイル", "プロダクトマネージャー", "リリース", "納期"],
        "forced_constraints": "日本製造業の『カイゼン』『QC（品質管理）サークル』の統計データ、ソフトウェア開発におけるIPA（情報処理推進機構）のバグ密度基準、およびMVP（実効最小限の製品）戦略の市場浸透率データ"
    },

    # 6. 地域社会・同調圧力 (Community & Harmony)
    "community_and_harmony": {
        "keywords": ["住民会議", "ゴミ集積所", "同調圧力", "和の精神", "自治会", "一斉清掃", "義務", "強制参加"],
        "forced_constraints": "日本の最高裁判所における自治会費・自治会参加義務に関する判例、地方自治法第260条の2（地縁団体）、および地域コミュニティにおける社会的孤立（孤独死など）の人口動態データ"
    },

    # 7. 境界線・生活習慣・マナー (Boundaries & Social Manners)
    "boundaries_and_manners": {
        "keywords": ["行けたら行く", "断り方", "不信感", "ルール", "マナー違反", "厳守", "寛容さ", "合理性"],
        "forced_constraints": "日本における『本音と建前』の社会心理学的研究データ、マンション管理組合の標準管理規約（国土交通省）における共有部分の使用ルール、および都市部における近隣トラブルの相談件数統計"
    },

    # 8. ギフト経済・プライバシー (Gift Economy & Privacy)
    "gift_and_privacy": {
        "keywords": ["お土産", "お返し", "義理", "ギブ＆テイク", "近所付き合い", "家族構成", "干渉", "孤立"],
        "forced_constraints": "日本伝来の『贈答文化（お中元・お歳暮・返礼）』の市場規模推移データ、個人情報保護法改正に伴うプライバシー意識の変容、および現代日本の隣人関係に関する内閣府の世論調査データ"
    }
}

def build_precision_engine_prompt(user_scenario: str, target_country: str) -> str:
    """
    ユーザーのシチュエーション文からキーワードをスキャンし、
    対応する日本の法規制や文化的背景データ（アンカー）を抽出した上で、
    日本語版の最高傑作プロンプトを動的に組み立てます。
    """
    cleaned_input = user_scenario.strip()
    
    # Default safety anchors if no keyword matches perfectly
    selected_constraints = "適用される法定労働基準、現地のコンプライアンス枠組み、および確立された地域の企業慣習"
    detected_framework_pairing = "標準的なコンプライアンス・コンテキスト"
    
    # Sequential scanning across all 15 custom pairings
    for pairing, config in SCENARIO_TARGET_MAP.items():
        if any(keyword in cleaned_input for keyword in config["keywords"]):
            selected_constraints = config["forced_constraints"]
            detected_framework_pairing = pairing
            break # Stop at the first precise match to avoid cross-triggers
            
    # Compile the final structured prompt for the search/generation engine
    precision_prompt = (
        f" あなたは、{target_country}　向けの精密な現地のコンプライアンスエンジンです。\n"
        f"ユーザーシナリオ入力: '{user_scenario}'\n\n"
        f"不可欠なエンジンパラメーター:\n"
        f"1.{target_country}内の 現在の{selected_constraints}を正確にクロスリファレンスすること。\n"
        f"2. 一般的なアドバイスは提供しないでください。このシナリオに関連する具体的な法的、統治的、または文化的境界を抽出してください。\n"
        f"3. 注記: このシナリオはCultural OSアーキテクチャ範疇に該当します: [{detected_framework_pairing}]."
    )
    
    return precision_prompt

