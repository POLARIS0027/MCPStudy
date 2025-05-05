"""
FastMCP myMcp Server
"""

from fastmcp import FastMCP
import httpx
import pandas as pd
import os
from dotenv import load_dotenv

load_dotenv() # .env 파일에서 환경 변수 로드

# --- 노션관련 ---
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
DATABASE_ID = os.getenv("DATABASE_ID")
NOTION_VERSION = os.getenv("NOTION_VERSION")

# 환경 변수 로드 확인
if not NOTION_TOKEN or not DATABASE_ID or not NOTION_VERSION:
    raise ValueError("오류: .env 파일에서 Notion 관련 환경 변수를 찾을 수 없습니다. (.env 파일 생성 및 내용 확인 필요)")

# 허용된 상태 값 리스트
ALLOWED_STATUS_VALUES = ["NY", "NG", "BK", "QA", "OK", "진행중"]

# Create server
mcp = FastMCP("myMCP Server")

headers = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": NOTION_VERSION,
    "Content-Type": "application/json"
}

@mcp.tool()
async def read_notion_database() -> str:
    """노션 데이터베이스 내용을 비동기로 가져오는 MCP 툴 (상태, 담당자 포함)"""
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers)
            response.raise_for_status()

            results = response.json().get("results", [])
            output_lines = []
            for page in results:
                props = page.get("properties", {})

                # 값 추출
                title_prop = props.get("제목", {}).get("title", []) 
                title = title_prop[0]["text"]["content"] if title_prop else "제목 없음"

                text_prop = props.get("텍스트", {}).get("rich_text", [])
                text = text_prop[0]["text"]["content"] if text_prop else "-"

                date_prop = props.get("날짜", {}).get("date")
                date = date_prop["start"] if date_prop and date_prop.get("start") else "-"

                # '상태' 속성 읽기 (Status 타입)
                status_prop = props.get("상태", {}).get("status") # 'status' 키 사용
                status = status_prop["name"] if status_prop and status_prop.get("name") else "-"

                # '담당자' 속성 읽기 
                assignee_prop = props.get("담당자", {}).get("people", [])
                if assignee_prop:
                    assignee = ", ".join([person.get("name", "이름없음") for person in assignee_prop if person])
                else:
                    assignee_prop = props.get("담당자", {}).get("rich_text", [])
                    if assignee_prop:
                         assignee = assignee_prop[0]["text"]["content"] if assignee_prop else "-"
                    else:
                        assignee = "-" 

                # 출력 문자열
                output_lines.append(f"[{date}] {title} - {text}(상태: {status}, 담당자: {assignee})")

            return "\n".join(output_lines) if output_lines else "데이터베이스가 비어 있습니다."

        except httpx.HTTPStatusError as e:
            error_details = e.response.text
            try:
                notion_error = e.response.json()
                error_details = notion_error.get("message", error_details)
            except Exception:
                pass
            return f"❌ 읽기 실패! 상태 코드 {e.response.status_code}. 이유: {error_details}"
        except httpx.RequestError as e:
            return f"❌ 읽기 실패! 네트워크 오류: {e}"
        except Exception as e:
            return f"❌ read_notion_database 오류: {e}"

@mcp.tool()
async def add_notion_page(
    title: str,
    text: str,
    date: str,
    status: str | None = None, # 있으면 좋고 아님 말고
    assignee: str | None = None  # 있으면 좋고 아님 말고
) -> str:
    """
    노션에 새 할 일을 비동기적으로 추가하는 MCP 툴.
    상태가 지정되지 않으면 'NY'를 사용.
    담당자가 지정되면 해당 값으로 설정하고, 지정되지 않으면 설정하지 않음.
    """
    url = "https://api.notion.com/v1/pages"

    # 상태 값 처리: 없으면 'NY' 사용, 있으면 체크
    final_state = status if status is not None else "NY"

    if final_state not in ALLOWED_STATUS_VALUES:
        return f"❌ 추가 실패! '상태' 값은 {', '.join(ALLOWED_STATUS_VALUES)} 중 하나여야 합니다. 입력값: {final_state}"

    properties_payload = {
        "제목": {"title": [{"text": {"content": title}}]},
        "텍스트": {"rich_text": [{"text": {"content": text}}]},
        "날짜": {"date": {"start": date}},
        "상태": {"status": {"name": final_state}},
    }

    # 담당자 값이 있음녀 추가
    if assignee is not None:
        # 담당자 속성은 노션에서 가져와야하는데 없으니까 일단 텍스트
        properties_payload["담당자"] = {"rich_text": [{"text": {"content": assignee}}]}

    data = {
        "parent": { "database_id": DATABASE_ID },
        "properties": properties_payload
    }

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=data)
            response.raise_for_status()

            # 성공 메시지 업데이트 (담당자 설정 여부 표시)
            assignee = f"담당자: {assignee}" if assignee is not None else "담당자 미지정"
            return f"✅ 등록 성공! (상태: {final_state}, {assignee})"

        except httpx.HTTPStatusError as e:
            error_details = e.response.text
            try:
                notion_error = e.response.json()
                error_details = notion_error.get("message", error_details)
            except Exception:
                pass
            return (f"❌ 추가 실패! 상태 코드 {e.response.status_code}. 이유: {error_details}\n"
                    f"전송된 데이터: {properties_payload}")
        except httpx.RequestError as e:
            return f"❌ 추가 실패! 네트워크 오류: {e}"
        except Exception as e:
            return f"❌ 추가 실패! 예상치 못한 오류: {e}"

@mcp.tool()
def find_ng_items_without_bug_id(xlsx_path: str, sheet_name: str = None) -> list[str]:
    """
    xlsx 파일에서 '시험결과'가 'NG'이고 '내부버그DB'가 비어있는 항목의 '시험항목ID'를 리스트로 반환합니다.
    즉 JIRA에 등록이 안 된 항목들을 알려줍니다.

    Args:
        xlsx_path (str): 분석할 Excel 파일 경로
        sheet_name (str, optional): 지정된 시트 이름. 생략 시 첫 번째 시트 사용

    Returns:
        list[str]: 조건에 맞는 시험항목ID 배열
    """


    try:
        df = pd.read_excel(xlsx_path, sheet_name=sheet_name)

        # 필수 컬럼 확인
        required_columns = ["시험항목ID", "시험결과", "내부버그DB"]
        for col in required_columns:
            if col not in df.columns:
                return [f"❌ '{col}' 컬럼이 존재하지 않습니다. 확인해주세요."]

        # 필터링
        filtered = df[
            (df["시험결과"] == "NG") &
            (df["내부버그DB"].isnull() | (df["내부버그DB"].astype(str).str.strip() == ""))
        ]

        return filtered["시험항목ID"].dropna().astype(str).tolist()

    except Exception as e:
        return [f"❌ 오류 발생: {e}"]


@mcp.tool()
def generate_bug_reports_from_ids(xlsx_path: str, item_ids: list[str]) -> str:
    """
    주어진 시험항목ID들을 참조해 버그 리포트의 초안을 작성하기 위한 데이터를 가져옵니다.

     Args:
        xlsx_path (str): 분석할 Excel 파일 경로
        item_ids(list[str]): 버그 리포트의 초안작성 대상인 시험 항목들의 목록
    Returns:
        report_list: 작성된 초안 리스트
    """

    try:
        df = pd.read_excel(xlsx_path)
        report_list = []

        for item_id in item_ids:
            row = df[df["시험항목ID"] == item_id]
            if row.empty:
                report_list.append(f"⚠️ {item_id} → 데이터 없음\n")
                continue

            row_data = row.iloc[0]
            report = f"""
                 **타이틀: 임의작성**

                 **확인내용** 
                 {row_data['확인내용']}

                 **재현 절차**
                {row_data['시험순서']}

                 **기대 결과**
                {row_data['기대결과']}

                 **비고**
                {row_data['비고'] or 'N/A'}
                
                ・시험 ID : {item_id}
                ・어플리케이션 버전 : {row_data['어플리케이션 버전']}
                ・이용단말 : {row_data['이용단말']}
                ---"""
            report_list.append(report)

        return "\n\n".join(report_list)

    except Exception as e:
        return f"❌ 버그리포트 생성 중 오류: {e}"