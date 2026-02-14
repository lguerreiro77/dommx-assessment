import streamlit as st
import yaml
import os
import json

st.set_page_config(page_title="DOMMx Assessment", layout="wide")
st.title("🛡️ DOMMx Technical Diagnostic")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# -------------------------------------------------
# STYLE (LIKERT COLORS + EXPANDER BORDER)
# -------------------------------------------------
st.markdown(
    """
<style>
/* Likert buttons */
div.stButton > button {
    width: 100%;
    padding: 12px !important;
    border-radius: 10px !important;
    font-weight: 700 !important;
    border: 1px solid #cfcfcf !important;
}

/* Expander look */
div[data-testid="stExpander"] {
    border-radius: 10px;
    border: 2px solid #e9e9e9;
    overflow: hidden;
}
</style>
""",
    unsafe_allow_html=True,
)

LIKERT = {
    0: ("🔴", "Initial", "#d32f2f"),
    1: ("🟠", "Ad-hoc", "#f57c00"),
    2: ("🟡", "Developing", "#fbc02d"),
    3: ("🟢", "Defined", "#7cb342"),
    4: ("🟢", "Managed", "#388e3c"),
    5: ("🔵", "Optimized", "#1976d2"),
}

# -------------------------------------------------
# RESOLVE PATH CASE INSENSITIVE
# -------------------------------------------------
def resolve_path(base_path, relative_path):
    if not relative_path:
        return None
    parts = relative_path.replace("\\", "/").split("/")
    current = base_path
    for part in parts:
        if not os.path.exists(current):
            return None
        found = None
        for item in os.listdir(current):
            if item.lower() == part.lower():
                found = item
                break
        if not found:
            return None
        current = os.path.join(current, found)
    return current


def safe_load(path):
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except:
        return None


# -------------------------------------------------
# LOAD CORE
# -------------------------------------------------
fs_setup = safe_load(resolve_path(BASE_DIR, "FileSystem_Setup.yaml"))
if not fs_setup or "orchestrator_config" not in fs_setup:
    st.error("FileSystem_Setup.yaml invalid")
    st.stop()

config = fs_setup["orchestrator_config"]

flow = safe_load(resolve_path(BASE_DIR, config.get("main_flow")))
orch = safe_load(resolve_path(BASE_DIR, config.get("main_orchestration")))

if not flow or not orch:
    st.error("Flow/Execution not found")
    st.stop()

# -------------------------------------------------
# SESSION
# -------------------------------------------------
if "dom_idx" not in st.session_state:
    st.session_state.dom_idx = 0
if "q_idx" not in st.session_state:
    st.session_state.q_idx = 0
if "answers" not in st.session_state:
    st.session_state.answers = {}
if "last_saved_snapshot" not in st.session_state:
    st.session_state.last_saved_snapshot = {}
    

# -------------------------------------------------
# EXECUTION
# -------------------------------------------------
req_list = orch.get("execution_request", [])
if not req_list:
    st.error("execution_request empty")
    st.stop()

current_req = req_list[st.session_state.dom_idx]

domain_flow = flow.get("Domain_flow") or flow.get("domain_flow")
if not domain_flow:
    st.error("Domain_flow missing")
    st.stop()

dom_meta = next(
    (d for d in domain_flow if str(d.get("domain_id")) == str(current_req.get("domain"))),
    None
)
if not dom_meta:
    st.error("Domain metadata not found")
    st.stop()

lang_requested = orch.get("language", "Default")
language_root = resolve_path(BASE_DIR, "data/domains/Language")
if not language_root:
    st.error("Language root not found")
    st.stop()

available_langs = os.listdir(language_root)
lang_match = next((l for l in available_langs if l.lower() == lang_requested.lower()), None)
if not lang_match:
    st.error("Language folder not found")
    st.stop()

domain_base = f"data/domains/Language/{lang_match}"

tree_path = resolve_path(BASE_DIR, f"{domain_base}/{dom_meta['files']['decision_tree']}")
catalog_path = resolve_path(BASE_DIR, f"{domain_base}/{dom_meta['files']['action_catalog']}")

tree_data = safe_load(tree_path)
catalog_data = safe_load(catalog_path)

if not tree_data or not catalog_data:
    st.error("Domain files missing")
    st.stop()

# -------------------------------------------------
# NORMALIZE TREE
# -------------------------------------------------
if "decision_tree" in tree_data:
    question_block = tree_data["decision_tree"]
elif "questions" in tree_data:
    question_block = tree_data["questions"]
else:
    question_block = tree_data

if isinstance(question_block, list):
    question_block = {q["id"]: q for q in question_block}

question_block = {k.lower(): v for k, v in question_block.items()}

# -------------------------------------------------
# QUESTION
# -------------------------------------------------
q_plan = current_req["selected_questions"][st.session_state.q_idx]
q_id = q_plan["id"]
q_content = question_block.get(q_id.lower())

if not q_content:
    st.error("Question not found in decision tree")
    st.stop()

st.header(f"Assessment: {dom_meta['name']}")
st.subheader(f"{q_id}: {q_content.get('text','')}")

# -------------------------------------------------
# LIKERT (COLORED SELECTED BUTTON)
# -------------------------------------------------
st.markdown("### Maturity Level")

current_answer = st.session_state.answers.get(q_id)

cols = st.columns(6)

for i, col in enumerate(cols):
    emoji, label, color = LIKERT[i]
    selected = (current_answer == i)

    with col:
        if selected:
            st.markdown(
                f"""
                <style>
                div[data-testid="stButton"] > button[kind="secondary"][key="{q_id}_{i}"] {{
                    background: {color} !important;
                    color: white !important;
                    border: 1px solid {color} !important;
                }}
                </style>
                """,
                unsafe_allow_html=True,
            )

        clicked = st.button(
            f"{emoji}\n{label}",
            key=f"{q_id}_{i}",
            use_container_width=True,
            type="secondary",
        )

        if clicked:
            st.session_state.answers[q_id] = i
            st.rerun()

# -------------------------------------------------
# ACTION
# -------------------------------------------------
if q_id in st.session_state.answers:
    score = st.session_state.answers[q_id]

    mapping = q_content.get("score_action_mapping")
    if not mapping:
        st.error("score_action_mapping missing")
        st.stop()

    action_code = mapping[score]["action_code"]
    action = catalog_data.get("action_catalog", {}).get(action_code)

    header_color = LIKERT[score][2]
    st.divider()
    st.markdown(
        f"""
        <div style="
            background:{header_color};
            padding:18px;
            border-radius:10px;
            margin-top:10px;
            color:white;
            font-weight:700;
            font-size:20px;">
            Prescriptive Action: {action_code}
        </div>
        """,
        unsafe_allow_html=True,
    )

    if action:
        st.markdown(f"**{action.get('title','')}**")

        for proc in action.get("procedures", []):
            if proc.get("number") in q_plan.get("procedures", []):
                with st.expander(f"Proc {proc['number']}: {proc['name']}"):

                    if proc.get("prerequisite"):
                        st.markdown("**Prerequisite**")
                        st.write(proc["prerequisite"])

                    if proc.get("deliverable"):
                        st.markdown("**Deliverable**")
                        st.write(proc["deliverable"])

                    if proc.get("recommendations"):
                        st.markdown("**Recommendations**")
                        for rec in proc["recommendations"]:
                            st.write(f"- {rec}")

                    note_value = proc.get("note") or proc.get("notes")
                    if note_value:
                        st.markdown("**Note**")
                        if isinstance(note_value, list):
                            for n in note_value:
                                st.write(f"- {n}")
                        else:
                            st.write(note_value)

# -------------------------------------------------
# NAVIGATION + SAVE
# -------------------------------------------------

total_q = len(current_req["selected_questions"])
current_q_id = q_id
current_answer = st.session_state.answers.get(current_q_id)

nav_mode = (orch.get("navigation_mode", "Sequential") or "Sequential").lower()

col_save, col_prev, col_next = st.columns([6, 2, 2])

# --- SAVE (apenas se houve mudança)
with col_save:

    has_answers = len(st.session_state.answers) > 0
    changed = st.session_state.answers != st.session_state.last_saved_snapshot

    if has_answers:
        if st.button(
            "💾 Save Progress",
            use_container_width=True,
            disabled=not changed
        ):

            output = {
                "domain": current_req.get("domain"),
                "language": lang_match,
                "answers": st.session_state.answers,
            }

            output_path = os.path.join(BASE_DIR, "assessment_results_partial.json")

            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(output, f, indent=2, ensure_ascii=False)

            st.session_state.last_saved_snapshot = dict(st.session_state.answers)
            st.session_state.just_saved = True

            st.rerun()

# Mostrar mensagem após rerun
if st.session_state.get("just_saved"):
    st.success("Progress saved.")
    st.session_state.just_saved = False




# --- PREVIOUS (somente se modo free)
with col_prev:
    if nav_mode == "free":
        prev_disabled = st.session_state.q_idx == 0
        if st.button(
            "⬅ Previous",
            use_container_width=True,
            disabled=prev_disabled
        ):
            st.session_state.q_idx -= 1
            st.rerun()

# --- NEXT (apenas se respondeu a atual)
with col_next:
    next_disabled = (
        current_answer is None or
        st.session_state.q_idx >= total_q - 1
    )

    if st.button(
        "➡ Next",
        use_container_width=True,
        disabled=next_disabled
    ):
        st.session_state.q_idx += 1
        st.rerun()
