import pandas as pd
import xml.etree.ElementTree as ET
from io import BytesIO
from data.repository_factory import get_repository


TABLE_NAME = "comments"


def export_all_comments_to_excel():

    repo = get_repository()
    rows = repo.fetch_all(TABLE_NAME)

    if not rows:
        return None

    parsed = []

    for row in rows:
        xml_raw = row.get("comment")

        try:
            root = ET.fromstring(xml_raw)

            parsed.append({
                "user_id": row.get("user_id"),
                "project_id": row.get("project_id"),
                "created_at": row.get("created_at"),
                "Domain": root.findtext("Domain"),
                "Question": root.findtext("Question"),
                "MaturityScore": root.findtext("MaturityScore"),
                "CommentText": root.findtext("Text"),
            })

        except Exception:
            continue

    df = pd.DataFrame(parsed)

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Comments")

    output.seek(0)
    return output.getvalue()