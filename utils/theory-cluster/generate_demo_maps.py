from pathlib import Path
import yaml
import json
import re
from collections import Counter, defaultdict


BASE_DIR = Path(__file__).resolve().parents[2]
GENERAL_DIR = BASE_DIR / "data" / "general"
INPUT_DIR = BASE_DIR / "utils" / "theory-cluster" / "input"
DEMO_OUTPUT_DIR = BASE_DIR / "utils" / "theory-cluster" / "output" / "demo"

# Captura códigos do tipo:
#  "1. Document Control"
#  "3 Domain and Context Framing"
#  "3.2 Organizational Context: ..."
#  "5.4 Step-by-Step Execution Structure:"
CODE_LINE_RE = re.compile(r"(?m)^\s*(\d+(?:\.\d+)*)(?:\.)?\s+(.+?)\s*$")


def norm(s: str) -> str:
    s = (s or "").strip().lower()
    s = re.sub(r"\s+", " ", s)
    # normaliza acentos básicos sem depender de unidecode
    s = s.replace("á", "a").replace("à", "a").replace("â", "a").replace("ã", "a")
    s = s.replace("é", "e").replace("ê", "e")
    s = s.replace("í", "i")
    s = s.replace("ó", "o").replace("ô", "o").replace("õ", "o")
    s = s.replace("ú", "u").replace("ç", "c")
    return s


# Âncoras mínimas multi-idioma (curtas e robustas)
ANCHORS = {
    # seção "Definição de Domínio e Contexto" (normalmente 3)
    "domain_context_section": [
        "definicao de dominio e contexto",
        "definicion de dominio y contexto",
        "domain and context",
        "definition du domaine et contexte",
        "definizione del dominio e contesto",
        "domaene und kontext",
        "domain and context framing",
    ],

    # subseção “Contexto Organizacional” (normalmente 3.2)
    "organizational_context_subsection": [
        "contexto organizacional",
        "organizational context",
        "contexte organisationnel",
        "contesto organizzativo",
        "organisatorischer kontext",
    ],

    # seção “Definição de Procedimento” (normalmente 5)
    "procedure_definition_section": [
        "definicao de procedimento",
        "definicion de procedimiento",
        "procedure definition",
        "definition de procedure",
        "definizione di procedura",
        "prozedurdefinition",
    ],

    # subseção “Step-by-Step Execution Structure” (normalmente 5.4)
    "execution_structure_subsection": [
        "step-by-step execution structure",
        "estrutura de execucao passo a passo",
        "estructura de ejecucion paso a paso",
        "structure dexecution pas a pas",
        "struttura di esecuzione passo dopo passo",
        "schritt-fur-schritt",
        "execution structure",
        "passo a passo",
    ],

    # seção “Mecanismos de Controle e Supervisão” (normalmente 7)
    "control_supervision_section": [
    "mecanismos de controle",
    "mecanismos de supervisao",
    "control and supervision",
    "control and oversight",
    "oversight mechanisms",
    "oversight",
    "control framework",
    ],

    # subseção monitoramento e kpis (normalmente 7.1)
    "monitoring_subsection": [
        "monitoramento e kpis",
        "monitoring and kpis",
        "monitoreo y kpis",
        "suivi et kpis",
        "monitoraggio e kpi",
        "monitoring und kpis",
        "monitoramento",
        "kpi",
    ],

    # subseção escalonamento (normalmente 7.3)
    "escalation_subsection": [
        "modelo de escalonamento",
        "operational escalation",
        "modelo de escalamiento",
        "modele descalade",
        "modello di escalation",
        "eskalationsmodell",
        "escalation model",
        "escalonamento",
        "escalation",
    ],
}


def load_language_possible() -> list[str]:
    p = GENERAL_DIR / "app_config.yaml"
    if not p.exists():
        return ["us", "pt", "es", "fr", "it", "de"]

    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    langs = data.get("language_possible") or []
    langs = [str(x).strip().lower() for x in langs if str(x).strip()]
    return langs or ["us", "pt", "es", "fr", "it", "de"]


def iter_demo_files() -> list[Path]:
    if not DEMO_OUTPUT_DIR.exists():
        return []

    files = list(DEMO_OUTPUT_DIR.rglob("*_theory_demo_output_PATCHED.json"))
    if files:
        return files

    return list(DEMO_OUTPUT_DIR.rglob("*_PATCHED.json"))


def extract_code_hits_from_text(demo_text: str) -> list[tuple[str, str]]:
    hits = []
    for code, title in CODE_LINE_RE.findall(demo_text or ""):
        hits.append((code.strip(), title.strip().rstrip(":").strip()))
    return hits


def choose_best_code(candidate_codes: list[str]) -> str:
    if not candidate_codes:
        return ""
    c = Counter(candidate_codes)
    return c.most_common(1)[0][0]


def detect_structural_codes_from_items(items: list[dict]) -> dict[str, str]:
    observed = defaultdict(list)

    for it in items:
        demo = str(it.get("demo") or "").strip()
        if not demo:
            continue

        hits = extract_code_hits_from_text(demo)

        for code, title in hits:
            t = norm(title)

            for key, anchors in ANCHORS.items():
                if any(norm(a) in t for a in anchors):
                    # Para chaves "section" queremos o major
                    if key in ("domain_context_section", "procedure_definition_section", "control_supervision_section"):
                        observed[key].append(code.split(".")[0])
                    else:
                        observed[key].append(code)

    out = {}
    for key in ANCHORS.keys():
        out[key] = choose_best_code(observed.get(key, []))

    return out


def load_items_from_demo_json(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))

    if isinstance(data, dict) and isinstance(data.get("items"), list):
        return [x for x in data["items"] if isinstance(x, dict)]

    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]

    if isinstance(data, dict) and ("demo" in data):
        return [data]

    return []


def generate_dynamic_demo_map() -> dict:
    files = iter_demo_files()

    all_observed = defaultdict(list)

    for fp in files:
        items = load_items_from_demo_json(fp)
        detected = detect_structural_codes_from_items(items)

        for k, v in detected.items():
            if v:
                all_observed[k].append(v)

    structural_codes = {}
    for k in ANCHORS.keys():
        structural_codes[k] = choose_best_code(all_observed.get(k, []))

    # mantém todas as chaves, mesmo vazias (pra você ver o que não detectou)
    return {
        "demo_code_map": {
            "structural_codes": structural_codes,
            "sources_scanned": [str(p.relative_to(BASE_DIR)) for p in files],
        }
    }


# textos default (se a tag não existir no input)
DEFAULT_TAG_TEXT = {
    "section_3_common_elements_intro": {
        "us": "This section consolidates structural elements that apply to the entire governance document, independent of any specific domain.",
        "pt": "Esta seção consolida elementos estruturais que se aplicam ao documento de governança como um todo, independentemente do domínio.",
        "es": "Esta sección consolida elementos estructurales aplicables al documento de gobernanza en su conjunto, independientemente del dominio.",
        "fr": "Cette section consolide des éléments structurels applicables au document de gouvernance dans son ensemble, indépendamment du domaine.",
        "it": "Questa sezione consolida elementi strutturali applicabili all’intero documento di governance, indipendentemente dal dominio.",
        "de": "Dieser Abschnitt konsolidiert strukturelle Elemente, die für das gesamte Governance-Dokument gelten, unabhängig vom jeweiligen Domäne.",
    },
    "section_3_common_template_intro": {
        "us": "Standard template blocks used across all domains to ensure consistency, traceability, and reusability of the governance artefact.",
        "pt": "Blocos padrão usados em todos os domínios para garantir consistência, rastreabilidade e reuso do artefato de governança.",
        "es": "Bloques estándar usados en todos los dominios para garantizar consistencia, trazabilidad y reutilización del artefacto de gobernanza.",
        "fr": "Blocs standard utilisés dans tous les domaines pour garantir cohérence, traçabilité et réutilisation de l’artefact de gouvernance.",
        "it": "Blocchi standard usati in tutti i domini per garantire coerenza, tracciabilità e riuso dell’artefatto di governance.",
        "de": "Standardbausteine für alle Domänen, um Konsistenz, Nachvollziehbarkeit und Wiederverwendbarkeit des Governance-Artefakts sicherzustellen.",
    },
    "section_3_common_transversal_intro": {
        "us": "Transversal structural elements that remain valid across domains, supporting control, evidence, and accountability.",
        "pt": "Elementos estruturais transversais válidos entre domínios, suportando controle, evidências e responsabilização.",
        "es": "Elementos estructurales transversales válidos entre dominios, que soportan control, evidencias y rendición de cuentas.",
        "fr": "Éléments structurels transverses valables entre domaines, soutenant contrôle, preuves et responsabilité.",
        "it": "Elementi strutturali trasversali validi tra domini, a supporto di controllo, evidenze e responsabilità.",
        "de": "Domänenübergreifende Strukturelemente zur Unterstützung von Kontrolle, Evidenzen und Verantwortlichkeit.",
    },
    "section_3_procedure_pack_intro": {
        "us": "This pack provides prescriptive procedures aligned with the assessed maturity level and the next-step action for this domain.",
        "pt": "Este pacote apresenta procedimentos prescritivos alinhados ao nível de maturidade avaliado e à ação de próximo passo para este domínio.",
        "es": "Este paquete presenta procedimientos prescriptivos alineados con el nivel de madurez evaluado y la acción de siguiente paso para este dominio.",
        "fr": "Ce pack présente des procédures prescriptives alignées sur le niveau de maturité évalué et l’action de prochain pas pour ce domaine.",
        "it": "Questo pacchetto fornisce procedure prescrittive allineate al livello di maturità valutato e alla prossima azione per questo dominio.",
        "de": "Dieses Paket liefert präskriptive Verfahren, abgestimmt auf das bewertete Reifegradniveau und die nächste Aktion für diese Domäne.",
    },
    "section_3_document_governance_intro": {
        "us": "Rules to keep this report controlled, auditable, and maintainable over time.",
        "pt": "Regras para manter este relatório controlado, auditável e sustentável ao longo do tempo.",
        "es": "Reglas para mantener este informe controlado, auditable y sostenible en el tiempo.",
        "fr": "Règles pour maintenir ce rapport contrôlé, auditable et durable dans le temps.",
        "it": "Regole per mantenere questo report controllato, verificabile e sostenibile nel tempo.",
        "de": "Regeln, um diesen Bericht kontrolliert, prüfbar und langfristig wartbar zu halten.",
    },
    "section_3_minimum_evidence_intro": {
        "us": "Minimum organizational evidences required to sustain governance adoption and verification.",
        "pt": "Evidências organizacionais mínimas necessárias para sustentar adoção e verificação da governança.",
        "es": "Evidencias organizacionales mínimas necesarias para sostener la adopción y verificación de la gobernanza.",
        "fr": "Preuves organisationnelles minimales nécessaires pour soutenir l’adoption et la vérification de la gouvernance.",
        "it": "Evidenze organizzative minime necessarie per sostenere l’adozione e la verifica della governance.",
        "de": "Minimale organisatorische Evidenzen zur Unterstützung von Einführung und Nachweis der Governance.",
    },
    "section_3_evolution_criteria_intro": {
        "us": "Criteria used to validate readiness to evolve to the next cycle and maturity level.",
        "pt": "Critérios usados para validar prontidão para evoluir para o próximo ciclo e nível de maturidade.",
        "es": "Criterios usados para validar la preparación para evolucionar al siguiente ciclo y nivel de madurez.",
        "fr": "Critères utilisés pour valider la préparation à évoluer vers le prochain cycle et niveau de maturité.",
        "it": "Criteri usati per validare la prontezza ad evolvere al prossimo ciclo e livello di maturità.",
        "de": "Kriterien zur Validierung der Bereitschaft für den nächsten Zyklus und Reifegrad.",
    },
    "section_3_domain_context_title": {
        "us": "Domain Definition and Context",
        "pt": "Definição de Domínio e Contexto",
        "es": "Definición de Dominio y Contexto",
        "fr": "Définition du Domaine et Contexte",
        "it": "Definizione del Dominio e Contesto",
        "de": "Domänendefinition und Kontext",
    },
}


def generate_report_texts_generated() -> dict:
    original_path = INPUT_DIR / "report_texts.yaml"
    if not original_path.exists():
        raise FileNotFoundError(f"report_texts.yaml not found in: {INPUT_DIR}")

    original = yaml.safe_load(original_path.read_text(encoding="utf-8")) or {}
    report_text = original.get("report_text", {}) or {}

    languages = load_language_possible()

    # garante base 'us'
    if "us" not in report_text or not isinstance(report_text.get("us"), dict):
        report_text["us"] = {}

    # garante todos idiomas do app_config
    for lg in languages:
        if lg not in report_text or not isinstance(report_text.get(lg), dict):
            report_text[lg] = dict(report_text["us"])

    required_tags = list(DEFAULT_TAG_TEXT.keys())

    # injeta defaults (por idioma) se faltar
    for lg in languages:
        content = report_text.get(lg, {})
        if not isinstance(content, dict):
            content = {}
            report_text[lg] = content

        for tag in required_tags:
            if tag not in content or content.get(tag) in (None, ""):
                content[tag] = DEFAULT_TAG_TEXT.get(tag, {}).get(lg) or DEFAULT_TAG_TEXT.get(tag, {}).get("us") or f"[{tag}]"

    return {"report_text": report_text}


def main():
    demo_map = generate_dynamic_demo_map()
    report_texts_generated = generate_report_texts_generated()

    GENERAL_DIR.mkdir(parents=True, exist_ok=True)

    (GENERAL_DIR / "demo_code_map_GENERATED.yaml").write_text(
        yaml.dump(demo_map, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    (GENERAL_DIR / "report_texts_GENERATED.yaml").write_text(
        yaml.dump(report_texts_generated, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    print("Generated:")
    print("- data/general/demo_code_map_GENERATED.yaml")
    print("- data/general/report_texts_GENERATED.yaml")


if __name__ == "__main__":
    main()