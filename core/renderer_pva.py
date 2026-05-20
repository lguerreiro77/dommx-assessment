import time
from datetime import datetime

import streamlit as st

from data.repository_factory import get_repository

repo = get_repository()


# =========================================================
# PVA DIMENSIONS
# =========================================================
PVA_DIMENSIONS = [

    {
        "key": "Conceptual Clarity",
        "description": (
            "Evaluates the understanding, coherence "
            "and conceptual structure of the model."
        )
    },

    {
        "key": "Framework Alignment",
        "description": (
            "Evaluates theoretical alignment with "
            "DAMA-DMBOK2, DCAM and CMMI."
        )
    },

    {
        "key": "Diagnostic Capacity",
        "description": (
            "Evaluates the model capacity to identify "
            "maturity levels and organizational gaps."
        )
    },

    {
        "key": "Recommendation Quality",
        "description": (
            "Evaluates relevance, coherence and "
            "applicability of recommendations."
        )
    },

    {
        "key": "Organizational Applicability",
        "description": (
            "Evaluates feasibility of use in "
            "real corporate environments."
        )
    },

    {
        "key": "Methodological Consistency",
        "description": (
            "Evaluates logic, traceability and "
            "coherence between assessment, "
            "decision and recommendation."
        )
    },

    {
        "key": "Evolution Capacity",
        "description": (
            "Evaluates support for continuous "
            "maturity evolution."
        )
    },

    {
        "key": "Governance Utility",
        "description": (
            "Evaluates practical and strategic "
            "value for Data Governance initiatives."
        )
    },
]


# =========================================================
# CHECK IF EXISTS
# =========================================================
def has_pva_response(user_id: str, project_id: str):

    rows = repo.fetch_all("PVA") or []

    uid = str(user_id).strip()
    pid = str(project_id).strip()

    answered_dimensions = set()

    required_dimensions = {
        item["key"]
        for item in PVA_DIMENSIONS
    }

    for r in rows:

        if str(r.get("user_id", "")).strip() != uid:
            continue

        if str(r.get("project_id", "")).strip() != pid:
            continue

        dimension = str(
            r.get("Dimension", "")
        ).strip()

        rate = str(
            r.get("Rate", "")
        ).strip()

        if dimension == "General Comments":
            continue

        if rate:
            answered_dimensions.add(dimension)

    return answered_dimensions == required_dimensions


# =========================================================
# SAFE UPSERT
# =========================================================
def safe_upsert_pva(
    user_id,
    project_id,
    dimension,
    rate,
    timestamp,
    existing_index
):

    payload = {
        "user_id": user_id,
        "project_id": project_id,
        "Dimension": dimension,
        "Rate": rate if rate is not None else "",
        "timestamp": timestamp,
    }

    retries = 3

    for attempt in range(retries):

        try:

            # UPDATE
            if dimension in existing_index:

                repo.update(
                    "PVA",
                    {
                        "user_id": user_id,
                        "project_id": project_id,
                        "Dimension": dimension,
                    },
                    payload
                )

            # INSERT
            else:

                repo.insert(
                    "PVA",
                    payload
                )

            return True

        except Exception as e:

            error_text = str(e)

            # GOOGLE SHEETS 429
            if "429" in error_text:

                wait_time = (attempt + 1) * 2

                time.sleep(wait_time)

                continue

            raise

    raise Exception(
        "Google Sheets quota exceeded. "
        "Please wait a few seconds and try again."
    )


# =========================================================
# MODAL
# =========================================================
@st.dialog("DOMMx Post Validation Assessment")
def render_pva_page():

    user_id = st.session_state.get("user_id")
    project_id = st.session_state.get("active_project")

    # =====================================================
    # SUBMIT LOCK
    # =====================================================
    if "pva_submit_locked" not in st.session_state:
        st.session_state.pva_submit_locked = False

    # =====================================================
    # LOAD EXISTING
    # =====================================================
    existing_rows = repo.fetch_all("PVA") or []

    existing_index = {}

    for r in existing_rows:

        if str(r.get("user_id", "")).strip() != str(user_id).strip():
            continue

        if str(r.get("project_id", "")).strip() != str(project_id).strip():
            continue

        dim = str(r.get("Dimension", "")).strip()

        existing_index[dim] = r

    # =====================================================
    # HEADER
    # =====================================================
    st.info(
        st._tr(
            """
            Please evaluate the DOMMx model based on your assessment experience.

            All dimensions must be answered before submission.
            (1 = Bad to 5 = Excellent)
            """
        )
    )

    # =====================================================
    # FORM
    # =====================================================
    with st.form("pva_form"):

        answers = {}

        # =================================================
        # QUESTIONS
        # =================================================
        for item in PVA_DIMENSIONS:

            dimension = item["key"]

            st.markdown(
                f"### {st._tr(dimension)}"
            )

            st.caption(
                st._tr(item["description"])
            )

            existing_rate = None

            existing = existing_index.get(dimension)

            if existing:

                try:
                    existing_rate = int(existing.get("Rate"))
                except Exception:
                    existing_rate = None

            score = st.select_slider(
                st._tr("Rate"),
                options=[1, 2, 3, 4, 5],
                value=existing_rate,
                key=f"pva_{dimension}"
            )

            if score is not None:
                answers[dimension] = score

        # =================================================
        # COMMENTS
        # =================================================
        existing_comment = ""

        if "General Comments" in existing_index:

            existing_comment = (
                existing_index["General Comments"]
                .get("Rate", "")
            )

        comments = st.text_area(
            st._tr("General Comments"),
            value=existing_comment,
            height=150,
            key="pva_general_comments"
        )

        # =================================================
        # VALIDATION
        # =================================================
        all_answered = (
            len(answers) == len(PVA_DIMENSIONS)
        )

        if not all_answered:

            missing = (
                len(PVA_DIMENSIONS) - len(answers)
            )

            st.warning(
                st._tr(
                    f"{missing} dimension(s) still need to be answered."
                )
            )

        # =================================================
        # SUBMIT
        # =================================================
        submit_clicked = st.form_submit_button(
            st._tr("Submit Evaluation"),
            use_container_width=True,
            type="primary",
            disabled=(
                (not all_answered)
                or st.session_state.pva_submit_locked
            )
        )

    # =====================================================
    # CLICK -> LOCK
    # =====================================================
    if submit_clicked:

        st.session_state.pva_submit_locked = True
        st.rerun()

    # =====================================================
    # EXECUTE SAVE
    # =====================================================
    if st.session_state.pva_submit_locked:

        timestamp = datetime.utcnow().isoformat()

        try:

            with st.spinner(
                st._tr("Saving evaluation...")
            ):

                # -----------------------------------------
                # SAVE DIMENSIONS
                # -----------------------------------------
                for dimension, rate in answers.items():

                    safe_upsert_pva(
                        user_id=user_id,
                        project_id=project_id,
                        dimension=dimension,
                        rate=rate,
                        timestamp=timestamp,
                        existing_index=existing_index
                    )

                    # evita burst no Google Sheets
                    time.sleep(0.25)

                # -----------------------------------------
                # SAVE COMMENTS
                # -----------------------------------------
                comment_dimension = "General Comments"

                comment_payload = {
                    "user_id": user_id,
                    "project_id": project_id,
                    "Dimension": comment_dimension,
                    "Rate": comments.strip(),
                    "timestamp": timestamp,
                }

                # UPDATE
                if comment_dimension in existing_index:

                    safe_upsert_pva(
                        user_id=user_id,
                        project_id=project_id,
                        dimension=comment_dimension,
                        rate=comments.strip(),
                        timestamp=timestamp,
                        existing_index=existing_index
                    )

                # INSERT
                else:

                    repo.insert(
                        "PVA",
                        comment_payload
                    )

            st.session_state["pva_completed"] = True
            st.session_state["open_pva"] = False

            # UNLOCK
            st.session_state.pva_submit_locked = False

            st.success(
                st._tr(
                    "PVA evaluation submitted successfully."
                )
            )

            st.rerun()

        except Exception as e:

            st.session_state.pva_submit_locked = False

            st.error(
                f"PVA ERROR: {e}"
            )