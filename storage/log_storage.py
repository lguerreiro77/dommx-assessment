import datetime
import xml.etree.ElementTree as ET
from data.repository_factory import get_repository

repo = get_repository()


def save_log_snapshot(user_id, project_id, messages):

    user_id = str(user_id).strip()
    project_id = str(project_id).strip()

    # -----------------------------
    # Build XML
    # -----------------------------
    root = ET.Element("Messages")

    for msg in messages:
        msg_el = ET.SubElement(root, "Message")

        type_el = ET.SubElement(msg_el, "Type")
        type_el.text = str(msg.get("type") or "")

        text_el = ET.SubElement(msg_el, "Text")
        text_el.text = str(msg.get("text") or "")

    xml_string = ET.tostring(root, encoding="unicode")

    # -----------------------------
    # UPSERT (sobrescreve sempre)
    # -----------------------------
    repo.upsert(
        "logs",
        {"user_id": user_id, "project_id": project_id},
        {
            "msg_log": xml_string,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }
    )
