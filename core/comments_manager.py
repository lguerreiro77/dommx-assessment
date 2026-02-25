import streamlit as st
from datetime import datetime
import xml.etree.ElementTree as ET
    
from data.repository_factory import get_repository


TABLE_NAME = "comments"


def _build_comment_xml(user_id, project_id, domain, question, maturity, comment_text):
    root = ET.Element("Comment")

    ET.SubElement(root, "User").text = str(user_id)
    ET.SubElement(root, "Project").text = str(project_id)
    ET.SubElement(root, "Domain").text = str(domain)
    ET.SubElement(root, "Question").text = str(question)
    ET.SubElement(root, "MaturityScore").text = str(maturity)
    ET.SubElement(root, "Text").text = comment_text

    return ET.tostring(root, encoding="unicode")


def save_comment(user_id, project_id, domain, question, maturity, comment_text):

    if not comment_text or not str(comment_text).strip():
        return

    MAX_LEN = 10000

    if len(comment_text) > MAX_LEN:
        raise ValueError("COMMENT_TOO_LONG")

    if not comment_text or not str(comment_text).strip():
        return  # não salva vazio

    repo = get_repository()

    rows = repo.fetch_all(TABLE_NAME)

    # Verifica se já existe comentário para mesma questão
    for row in rows:
        if (
            str(row.get("user_id")) == str(user_id)
            and str(row.get("project_id")) == str(project_id)
        ):
            try:
                root = ET.fromstring(row.get("comment", ""))
                if (
                    root.findtext("Domain") == str(domain)
                    and root.findtext("Question") == str(question)
                ):
                    # Atualiza em vez de inserir novo
                    xml_content = _build_comment_xml(
                        user_id, project_id, domain, question, maturity, comment_text
                    )

                    repo.update(
                        TABLE_NAME,
                        row,
                        {
                            "comment": xml_content,
                            "created_at": datetime.utcnow().isoformat(),
                        },
                    )
                    return
            except Exception:
                pass

    # Se não encontrou, insere novo
    xml_content = _build_comment_xml(
        user_id, project_id, domain, question, maturity, comment_text
    )

    repo.insert(
        TABLE_NAME,
        {
            "user_id": user_id,
            "project_id": project_id,
            "created_at": datetime.utcnow().isoformat(),
            "comment": xml_content,
        },
    )

def load_comment(user_id, project_id, domain, question):
    repo = get_repository()

    rows = repo.fetch_all(TABLE_NAME)

    for row in reversed(rows):
        if (
            str(row.get("user_id")) == str(user_id)
            and str(row.get("project_id")) == str(project_id)
        ):
            try:
                root = ET.fromstring(row.get("comment", ""))
                if (
                    root.findtext("Domain") == str(domain)
                    and root.findtext("Question") == str(question)
                ):
                    return root.findtext("Text")
            except Exception:
                pass

    return ""
    
    
def delete_comment(user_id, project_id, domain, question):

    repo = get_repository()
    rows = repo.fetch_all(TABLE_NAME)

    for row in rows:
        if (
            str(row.get("user_id")) == str(user_id)
            and str(row.get("project_id")) == str(project_id)
        ):
            try:
                root = ET.fromstring(row.get("comment", ""))
                if (
                    root.findtext("Domain") == str(domain)
                    and root.findtext("Question") == str(question)
                ):
                    repo.delete(TABLE_NAME, row)
                    return
            except Exception:
                pass    
    
    