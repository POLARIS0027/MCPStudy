"""
FastMCP myMcp Server
"""

from fastmcp import FastMCP, Context
import httpx
import pandas as pd
import os
from dotenv import load_dotenv
import asyncio 

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
async def generate_bug_reports_from_ids(xlsx_path: str, item_ids: list[str], ctx: Context) -> str:
    """
    주어진 시험항목ID들을 참조해 버그 리포트의 초안을 작성하기 위한 데이터를 가져옵니다.
    LLM을 사용하여 '기대결과'와 '비고'를 바탕으로 개선된 타이틀을 생성합니다.

     Args:
        xlsx_path (str): 분석할 Excel 파일 경로
        item_ids(list[str]): 버그 리포트의 초안작성 대상인 시험 항목들의 목록
        ctx (Context): FastMCP 컨텍스트 객체 (LLM 호출용)
    Returns:
        report_list: 작성된 초안 리스트 문자열
    """

    try:
        # ctx의 메소드들이 대부분 비동기라 비동기로 하는게 나음
        df = await asyncio.to_thread(pd.read_excel, xlsx_path)
        report_list = []
        llm_failures = 0 # LLM 호출 실패 횟수

        for item_id in item_ids:
            row = df[df["시험항목ID"] == item_id]
            if row.empty:
                report_list.append(f"⚠️ {item_id} → 데이터 없음\\n")
                continue

            row_data = row.iloc[0]

            expected_result = row_data.get('기대결과', 'N/A') # .get()으로 키 존재 확인
            actual_result_notes = row_data.get('비고', 'N/A') # .get()으로 키 존재 확인

            generated_title = f"임의작성" # 기본값 설정

            try:
                # LLM에게 타이틀 생성 요청
                prompt = f'''다음 정보를 바탕으로 버그 리포트의 제목을 "기대 결과는 A 였으나 시험 결과는 B였음" 형식으로 간결하게 작성해 주세요:

                기대 결과: {expected_result}
                실제 결과 또는 비고: {actual_result_notes}

                제목:'''
                title_response = await ctx.sample(prompt, max_tokens=100) # max_tokens는 적절히 조절
                generated_title = title_response.text.strip() if title_response.text else generated_title

            except Exception as llm_error:
                # LLM 호출 실패 시 로그 남기고 기본 타이틀 사용
                await ctx.warning(f"LLM 제목 생성 실패 (ID: {item_id}): {llm_error}")
                llm_failures += 1
                # generated_title은 기본값으로 유지됨

            report = f'''
                 **타이틀: {generated_title}**

                 **확인내용**
                 {row_data.get('확인내용', 'N/A')}

                 **재현 절차**
                {row_data.get('시험순서', 'N/A')}

                 **기대 결과**
                {expected_result}

                 **비고**
                {actual_result_notes}

                ・시험 ID : {item_id}
                ・어플리케이션 버전 : {row_data.get('어플리케이션 버전', 'N/A')}
                ・이용단말 : {row_data.get('이용단말', 'N/A')}
                ---'''
            report_list.append(report)

        final_report = "\\n\\n".join(report_list) # 줄바꿈 수정
        if llm_failures > 0:
             await ctx.warning(f"총 {llm_failures}개의 항목에 대해 LLM 제목 생성에 실패했습니다.")

        return final_report

    except FileNotFoundError:
        await ctx.error(f"버그리포트 생성 중 오류: 파일을 찾을 수 없습니다 - {xlsx_path}") # 에러 로그 추가
        return f"❌ 버그리포트 생성 중 오류: 파일을 찾을 수 없습니다 - {xlsx_path}"
    except KeyError as e:
         await ctx.error(f"버그리포트 생성 중 오류: Excel 파일에 필요한 컬럼({e})이 없습니다.") # 에러 로그 추가
         return f"❌ 버그리포트 생성 중 오류: Excel 파일에 필요한 컬럼({e})이 없습니다."
    except Exception as e:
        # 오류 발생 시 Context를 통해 로그 남기기 (선택 사항)
        if ctx: # ctx가 주입되었는지 확인
             await ctx.error(f"generate_bug_reports_from_ids의 예상치 못한 오류: {e}") # 에러 로그 추가
        return f"❌ 버그리포트 생성 중 오류: {e}"

EXPECTED_HEADERS = [
    "시험항목ID", "확인내용", "시험순서", "기대결과",
    "시험결과", "이용단말", "어플리케이션 버전", "비고", "내부버그DB"
]

@mcp.tool()
def add_test_item_to_excel(
    xlsx_path: str,
    item_id: str,
    check_content: str,
    test_procedure: str,
    expected_result: str,
) -> str:
    """
    엑셀 파일에 새로운 시험 항목을 추가합니다.
    '시험결과'는 'NY'로 고정되며, '이용단말', '어플리케이션 버전', '비고', '내부버그DB'는 비워둡니다.
    파일이 없으면 헤더와 함께 새로 생성합니다.

    Args:
        xlsx_path (str): 대상 Excel 파일 경로.
        item_id (str): 추가할 시험항목ID.
        check_content (str): 추가할 확인내용.
        test_procedure (str): 추가할 시험순서.
        expected_result (str): 추가할 기대결과.

    Returns:
        str: 작업 성공 또는 실패 메시지.
    """
    try:
        df = None
        # 1. 파일 읽기 시도 (동기)
        try:
            df = pd.read_excel(xlsx_path)
            # 기존 파일 헤더 확인 및 누락된 헤더 추가
            missing_headers = [h for h in EXPECTED_HEADERS if h not in df.columns]
            if missing_headers:
                 for header in missing_headers:
                     df[header] = pd.NA
                 df = df[EXPECTED_HEADERS]

        except FileNotFoundError:
            df = pd.DataFrame(columns=EXPECTED_HEADERS)
        except Exception as read_error:
             return f"❌ 파일 읽기 오류: {read_error}"

        # 2. 새로운 데이터 행 생성 (동일)
        new_data = {
            "시험항목ID": item_id,
            "확인내용": check_content,
            "시험순서": test_procedure,
            "기대결과": expected_result,
            "시험결과": "NY",
            "이용단말": pd.NA,
            "어플리케이션 버전": pd.NA,
            "비고": pd.NA,
            "내부버그DB": pd.NA
        }
        new_row_df = pd.DataFrame([new_data])

        # 3. 기존 DataFrame에 새 행 추가 (동일)
        df = pd.concat([df, new_row_df], ignore_index=True)

        # 4. 수정된 DataFrame을 엑셀 파일로 저장 (동기)
        try:
            df.to_excel(xlsx_path, index=False, engine='openpyxl')
            return f"✅ 시험 항목 '{item_id}' 추가 완료."

        except Exception as write_error:
            return f"❌ 파일 저장 오류: {write_error}"

    except Exception as e:
        return f"❌ 처리 중 오류: {e}"