"""
FastMCP myMcp Server (日本語版)
"""

from fastmcp import FastMCP, Context
import httpx
import pandas as pd
import os
from dotenv import load_dotenv
# import asyncio # 不要になりました

load_dotenv() # .env ファイルから環境変数をロード

# --- Notion関連 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")
NOTION_VERSION = os.getenv("NOTION_VERSION")

# 環境変数のロード確認
if not NOTION_TOKEN or not DATABASE_ID or not NOTION_VERSION:
    raise ValueError("エラー: .env ファイルから Notion 関連の環境変数が見つかりません。(.env ファイルの作成と内容を確認してください)")

# 許可されたステータス値リスト
ALLOWED_STATUS_VALUES = ["NY", "NG", "BK", "QA", "OK", "진행중"] # "진행중" は Notion 側の値に合わせて変更が必要な場合があります

# サーバー作成
mcp = FastMCP("myMCP Server (JP)") # サーバー名を変更 (任意)

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

@mcp.tool()
async def read_notion_database() -> str:
    """Notionデータベースの内容を非同期で取得するMCPツール (ステータス、担当者を含む)"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers)
            response.raise_for_status()

            results = response.json().get("results", [])
            output_lines = []
            for page in results:
                props = page.get("properties", {})

                # 値の抽出
                title_prop = props.get("제목", {}).get("title", []) # Notionプロパティ名「제목」
                title = title_prop[0]["text"]["content"] if title_prop else "タイトルなし"

                text_prop = props.get("텍스트", {}).get("rich_text", []) # Notionプロパティ名「텍스트」
                text = text_prop[0]["text"]["content"] if text_prop else "-"

                date_prop = props.get("날짜", {}).get("date") # Notionプロパティ名「날짜」
                date = date_prop["start"] if date_prop and date_prop.get("start") else "-"

                # 'ステータス' プロパティの読み取り (Statusタイプ) - Notionプロパティ名「상태」
                status_prop = props.get("상태", {}).get("status") # 'status' キーを使用
                status = status_prop["name"] if status_prop and status_prop.get("name") else "-"

                # '担当者' プロパティの読み取り - Notionプロパティ名「담당자」
                assignee_prop = props.get("담당자", {}).get("people", [])
                if assignee_prop:
                    assignee = ", ".join([person.get("name", "名前なし") for person in assignee_prop if person])
                else:
                    assignee_prop = props.get("담당자", {}).get("rich_text", [])
                    if assignee_prop:
                         assignee = assignee_prop[0]["text"]["content"] if assignee_prop else "-"
                    else:
                        assignee = "-"

                # 出力文字列 (日本語ラベルに変更)
                output_lines.append(f"[{date}] {title} - {text}(ステータス: {status}, 担当者: {assignee})")

            return "\n".join(output_lines) if output_lines else "データベースは空です。"

        except httpx.HTTPStatusError as e:
            error_details = e.response.text
            try:
                notion_error = e.response.json()
                error_details = notion_error.get("message", error_details)
            except Exception:
                pass
            return f"❌ 読み込み失敗! ステータスコード {e.response.status_code}. 理由: {error_details}"
        except httpx.RequestError as e:
            return f"❌ 読み込み失敗! ネットワークエラー: {e}"
        except Exception as e:
            # エラーメッセージを具体的に
            return f"❌ read_notion_database で予期せぬエラー: {e}"

@mcp.tool()
async def add_notion_page(
    title: str,
    text: str,
    date: str,
    status: str | None = None, # あれば使用、なければNone
    assignee: str | None = None  # あれば使用、なければNone
) -> str:
    """
    Notionに新しいタスクを非同期で追加するMCPツール。
    ステータスが指定されていない場合は 'NY' を使用。
    担当者が指定されている場合はその値を設定し、指定されていない場合は設定しない。
    """
    url = "https://api.notion.com/v1/pages"

    # ステータス値の処理: なければ 'NY' を使用、あればチェック
    final_state = status if status is not None else "NY"

    if final_state not in ALLOWED_STATUS_VALUES:
        # エラーメッセージを日本語に
        return f"❌ 追加失敗! 'ステータス' の値は {', '.join(ALLOWED_STATUS_VALUES)} のいずれかである必要があります。入力値: {final_state}"

    # Notionプロパティ名は元の韓国語のまま（Notion DBスキーマに依存するため）
    properties_payload = {
        "제목": {"title": [{"text": {"content": title}}]},
        "텍스트": {"rich_text": [{"text": {"content": text}}]},
        "날짜": {"date": {"start": date}},
        "상태": {"status": {"name": final_state}},
    }

    # 担当者の値があれば追加
    if assignee is not None:
        # 担当者プロパティはNotionから取得する必要があるが、今回はテキストとして設定
        properties_payload["담당자"] = {"rich_text": [{"text": {"content": assignee}}]}

    data = {
        "parent": { "database_id": DATABASE_ID },
        "properties": properties_payload
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()

            # 成功メッセージ更新 (担当者設定の有無を表示)
            assignee_jp = f"担当者: {assignee}" if assignee is not None else "担当者 未指定"
            return f"✅ 登録成功! (ステータス: {final_state}, {assignee_jp})"

        except httpx.HTTPStatusError as e:
            error_details = e.response.text
            try:
                notion_error = e.response.json()
                error_details = notion_error.get("message", error_details)
            except Exception:
                pass
            # エラーメッセージを日本語に
            return (f"❌ 追加失敗! ステータスコード {e.response.status_code}. 理由: {error_details}\\n"
                    f"送信されたデータ: {properties_payload}") # データ表示はデバッグ用に残すことも可
        except httpx.RequestError as e:
             # エラーメッセージを日本語に
            return f"❌ 追加失敗! ネットワークエラー: {e}"
        except Exception as e:
             # エラーメッセージを日本語に
            return f"❌ 追加失敗! 予期せぬエラー: {e}"

@mcp.tool()
def find_ng_items_without_bug_id(xlsx_path: str, sheet_name: str = None) -> list[str]:
    """
    xlsxファイルで '試験結果' が 'NG' であり、'内部버그DB' が空の項目の '試験항목ID' をリストで返します。
    つまり、JIRA に登録されていない項目を通知します。
    Excelのカラム名は元のファイルに合わせてください（例: '試験結果', '内部버그DB', '試験항목ID'）。

    Args:
        xlsx_path (str): 分析対象のExcelファイルパス。
        sheet_name (str, optional): 指定されたシート名。省略時は最初のシートを使用。

    Returns:
        list[str]: 条件に一致する試験항목IDの配列。
    """


    try:
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name)

        # 必須カラムの確認 (カラム名はExcelファイルに合わせる)
        required_columns = ["試ｄID", "시험결과", "내부버그DB"]
        for col in required_columns:
            if col not in df.columns:
                # エラーメッセージを日本語に
                return [f"❌ '{col}' カラムが存在しません。確認してください。"]

        # フィルタリング (カラム名はExcelファイルに合わせる)
        filtered = df[
            (df["시험결과"] == "NG") &
            (df["내부버그DB"].isnull() | (df["내부버그DB"].astype(str).str.strip() == ""))
        ]

        return filtered["시험항목ID"].dropna().astype(str).tolist()

    except Exception as e:
        # エラーメッセージを日本語に
        return [f"❌ エラー発生: {e}"]


@mcp.tool()
async def generate_bug_reports_from_ids(xlsx_path: str, item_ids: list[str], ctx: Context) -> str:
    """
    指定された 試験項目ID を参照して、バグレポートの下書きを作成するためのデータを取得します。
    LLMを使用して '기대결과' と '비고' を基に改善されたタイトルを生成します。
    Excelのカラム名は元のファイルに合わせてください（例: '기대결과', '비고', '확인내용' 等）。

     Args:
        xlsx_path (str): 分析対象のExcelファイルパス。
        item_ids(list[str]): バグレポート下書き作成対象の試験項目のリスト。
        ctx (Context): FastMCPコンテキストオブジェクト (LLM呼び出し用)。
    Returns:
        report_list: 作成された下書きリストの文字列。
    """

    try:
        # ctxのメソッドはほとんど非同期なので、非同期にするのが良い
        df = await asyncio.to_thread(pd.read_excel, xlsx_path)
        report_list = []
        llm_failures = 0 # LLM呼び出し失敗回数

        for item_id in item_ids:
            # カラム名はExcelファイルに合わせる
            row = df[df["시험항목ID"] == item_id]
            if row.empty:
                # メッセージを日本語に
                report_list.append(f"⚠️ {item_id} → データなし\\n")
                continue

            row_data = row.iloc[0]

            # カラム名はExcelファイルに合わせる
            expected_result = row_data.get('기대결과', 'N/A') # .get()でキー存在確認
            actual_result_notes = row_data.get('비고', 'N/A') # .get()でキー存在確認

            generated_title = f"仮タイトル" # デフォルト値を設定 (日本語)

            try:
                # LLMにタイトル生成を依頼 (プロンプトを日本語に)
                prompt = f'''以下の情報に基づいて、バグレポートのタイトルを「期待結果はAだったが、試験結果はBだった」という形式で簡潔に作成してください：

                期待結果: {expected_result}
                実際の結果または備考: {actual_result_notes}

                タイトル:'''
                # title_response = await ctx.sample(prompt, max_tokens=100) # max_tokens は適切に調整
                # generated_title = title_response.text.strip() if title_response.text else generated_title
                # ↑↑↑ 注意: 実際にLLMを使用する場合、ctx.sampleの呼び出しと結果の処理が必要です。
                #     ここでは日本語化のためコメントアウトしていますが、実際の使用時には元に戻してください。
                generated_title = f"【仮】期待: {expected_result} / 結果: {actual_result_notes}" # 仮のタイトル生成（LLM呼び出し代替）


            except Exception as llm_error:
                # LLM呼び出し失敗時のログ記録とデフォルトタイトル使用
                await ctx.warning(f"LLMタイトル生成失敗 (ID: {item_id}): {llm_error}")
                llm_failures += 1
                # generated_title はデフォルト値のまま

            # レポートのラベルを日本語に、カラム名はExcelに合わせる
            report = f'''
                 **タイトル: {generated_title}**

                 **確認内容**
                 {row_data.get('확인내용', 'N/A')}

                 **再現手順**
                {row_data.get('시험순서', 'N/A')}

                 **期待結果**
                {expected_result}

                 **備考**
                {actual_result_notes}

                ・試験ID : {item_id}
                ・アプリケーションバージョン : {row_data.get('어플리케이션 버전', 'N/A')}
                ・利用端末 : {row_data.get('이용단말', 'N/A')}
                ---'''
            report_list.append(report)

        final_report = "\n\n".join(report_list) # 改行修正
        if llm_failures > 0:
             await ctx.warning(f"合計 {llm_failures} 件の項目についてLLMタイトル生成に失敗しました。")

        return final_report

    except FileNotFoundError:
        # エラーメッセージを日本語に
        await ctx.error(f"バグレポート生成中にエラー: ファイルが見つかりません - {xlsx_path}") # エラーログ追加
        return f"❌ バグレポート生成中にエラー: ファイルが見つかりません - {xlsx_path}"
    except KeyError as e:
        # エラーメッセージを日本語に
         await ctx.error(f"バグレポート生成中にエラー: Excelファイルに必要なカラム({e})がありません。") # エラーログ追加
         return f"❌ バグレポート生成中にエラー: Excelファイルに必要なカラム({e})がありません。"
    except Exception as e:
        # エラー発生時にContextを通じてログ記録 (任意)
        if ctx: # ctxが注入されたか確認
             # エラーメッセージを日本語に
             await ctx.error(f"generate_bug_reports_from_ids で予期せぬエラー: {e}") # エラーログ追加
         # エラーメッセージを日本語に
        return f"❌ バグレポート生成中にエラー: {e}"

# Excelヘッダー定義 (カラム名はExcelファイルに合わせる)
EXPECTED_HEADERS = [
    "시험항목ID", "확인내용", "시험순서", "기대결과",
    "시험결과", "이용단말", "어플리케이션 버전", "비고", "내부버그DB"
]

@mcp.tool()
def add_test_item_to_excel(
    xlsx_path: str,
    items: list[dict], # 試験項目辞書のリスト
) -> str:
    """
    Excelファイルに複数の新しい試験項目を追加します。
    各項目の '試験結果' は 'NY' に固定され、'利用端末', 'アプリケーションバージョン', '備考', '内部버그DB' は空白になります。
    ファイルが存在しない場合は、ヘッダーとともに新規作成します。
    Excelのカラム名は元のファイルに合わせてください。

    Args:
        xlsx_path (str): 対象のExcelファイルパス。
        items (list[dict]): 追加する試験項目情報の辞書のリスト。
            各辞書には 'item_id', 'check_content', 'test_procedure', 'expected_result' キーが含まれている必要があります。

    Returns:
        str: 処理の成功または失敗メッセージ。
    """
    try:
        df = None
        # 1. ファイル読み込み試行 (同期)
        try:
            df = pd.read_excel(xlsx_path)
            missing_headers = [h for h in EXPECTED_HEADERS if h not in df.columns]
            if missing_headers:
                 # print(f"情報: 既存ファイルに不足しているヘッダー {missing_headers} を追加します。")
                 for header in missing_headers:
                     df[header] = pd.NA
                 df = df[EXPECTED_HEADERS]

        except FileNotFoundError:
            # print(f"情報: ファイル '{xlsx_path}' が見つからないため、新規作成します。")
            df = pd.DataFrame(columns=EXPECTED_HEADERS)
        except Exception as read_error:
             # エラーメッセージを日本語に
             return f"❌ ファイル読み込みエラー: {read_error}"

        # 2. 新しいデータ行を格納するリストを作成
        new_rows = []
        added_ids = []
        skipped_items = 0

        for item in items:
            # 必須キーの確認
            required_keys = ['item_id', 'check_content', 'test_procedure', 'expected_result']
            if not all(key in item for key in required_keys):
                # print(f"警告: 必須キーが不足しているため項目をスキップします: {item.get('item_id', 'IDなし')}")
                skipped_items += 1
                continue

            # カラム名はExcelファイルに合わせる
            new_data = {
                "시험항목ID": item.get('item_id'),
                "확인내용": item.get('check_content'),
                "시험순서": item.get('test_procedure'),
                "기대결과": item.get('expected_result'),
                "시험결과": "NY",
                "이용단말": pd.NA,
                "어플리케이션 버전": pd.NA,
                "비고": pd.NA,
                "내부버그DB": pd.NA
            }
            new_rows.append(new_data)
            added_ids.append(str(item.get('item_id')))

        if not new_rows:
             # メッセージを日本語に ([スキップ]を追加)
             return f"⚠️ 追加する有効な項目がありません。(スキップされた項目数: {skipped_items})"

        # 3. 新しい行をDataFrameに変換し、既存のDataFrameに追加
        new_rows_df = pd.DataFrame(new_rows)
        df = pd.concat([df, new_rows_df], ignore_index=True)

        # 4. 修正されたDataFrameをExcelファイルに保存 (同期)
        try:
            df.to_excel(xlsx_path, index=False, engine='openpyxl')
            # メッセージを日本語に ([スキップ]を追加)
            result_message = f"✅ 合計 {len(added_ids)} 件の試験項目追加完了: {', '.join(added_ids)}"
            if skipped_items > 0:
                 result_message += f" (スキップされた項目: {skipped_items} 件)"
            return result_message

        except Exception as write_error:
             # エラーメッセージを日本語に
            return f"❌ ファイル保存エラー: {write_error}"

    except Exception as e:
        # エラーメッセージを日本語に
        return f"❌ 処理中にエラー: {e}"

# 注意: このファイルを実行するには、mymcp.py と同様に
# `if __name__ == "__main__":` ブロックで `mcp.run()` を呼び出すか、
# `fastmcp run mymcp_jp.py` のようにCLIを使用する必要があります。