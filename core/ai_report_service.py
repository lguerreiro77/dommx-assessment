import json
from datetime import datetime
import streamlit as st
from openai import OpenAI

# Usa mesma config do sistema (ajuste se já tiver client centralizado)
client = OpenAI()

def generate_ai_report(user_id, project_id, answers, locale="en"):
    """
    Gera relatório IA baseado nas respostas do assessment.
    Não salva nada. Apenas retorna texto.
    """

    if not answers:
        return "No answers available."

    # Estrutura simplificada para IA
    structured_data = []

    for domain_key, questions in answers.items():
        for q_id, score in questions.items():
            structured_data.append({
                "domain": domain_key,
                "question": q_id,
                "maturity_score": score
            })

    payload = {
        "user_id": user_id,
        "project_id": project_id,
        "generated_at": datetime.utcnow().isoformat(),
        "responses": structured_data
    }

    system_prompt = """
    You are a senior Data Governance expert.
    Generate a professional executive assessment report.

    The report must include:
    - Executive Summary
    - Overall Maturity Overview
    - Strengths
    - Weaknesses
    - Risk Areas
    - Strategic Recommendations
    - Suggested Roadmap (short, medium, long term)

    Keep it structured, concise and professional.
    """

    user_prompt = f"""
    Generate an executive Data Governance assessment report
    based on the following JSON responses:

    {json.dumps(payload, indent=2)}
    """

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )

        return response.choices[0].message.content.strip()

    except Exception as e:
        return f"AI REPORT ERROR: {str(e)}"