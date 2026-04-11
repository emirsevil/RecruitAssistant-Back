"""
services/ai_generator.py
─────────────────────────
Core service layer for AI-powered CV and Cover Letter generation.
- Streams OpenAI to produce raw LaTeX
- Compiles LaTeX → PDF via pdflatex (with graceful fallback)
- ATS Optimized & Premium Design focus.
"""

import os
import json
import uuid
import base64
import shutil
import logging
import tempfile
import subprocess
import re
import io
import zipfile
import unicodedata
import xml.etree.ElementTree as ET
from typing import Optional, Generator

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# OpenAI client
# ──────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=OPENAI_API_KEY) if OPENAI_API_KEY else None

MODEL = "gpt-4o"  # Best quality for complex LaTeX generation

COMMON_SKILLS = [
    "Python", "JavaScript", "TypeScript", "React", "React Native", "Next.js", "Node.js",
    "Express.js", "FastAPI", "Django", "Flask", "SQL", "PostgreSQL", "MongoDB", "Redis",
    "AWS", "Azure", "GCP", "Docker", "Kubernetes", "CI/CD", "Git", "GitHub",
    "Tailwind CSS", "HTML", "CSS", "GraphQL", "REST", "REST API", "OpenAI API",
    "Machine Learning", "Deep Learning", "Data Analysis", "Data Visualization",
    "Product Analytics", "Accessibility", "Design Systems", "Playwright", "Testing",
    "Unit Testing", "Leadership", "Agile", "Scrum", "Recruiting", "HR Analytics",
    "Experimentation", "A/B Testing", "Java", "Spring", "Spring Boot", "C#", ".NET",
    "PHP", "Laravel", "Vue", "Angular", "Figma", "Jira", "NoSQL", "MySQL",
    "Microservices", "Linux", "Bash", "TensorFlow", "PyTorch", "Pandas", "NumPy",
    "Scikit-learn", "LLM", "LLMs", "Generative AI", "Prompt Engineering",
    "LangChain", "RAG", "Vector Database", "Pinecone", "Supabase", "Firebase",
    "Prisma", "Drizzle", "Redux", "Zustand", "Sass", "Bootstrap", "Material UI",
    "Ant Design", "Vite", "Webpack", "Turbopack", "Vercel", "Netlify",
]

SKILL_LABELS = {
    "skills", "skill", "technical skills", "technologies", "technology", "tools",
    "programming languages", "frameworks", "libraries", "databases", "cloud",
    "languages", "certifications", "certificates", "achievements", "soft skills",
    "yetenekler", "beceriler", "teknik yetenekler", "teknolojiler", "diller",
    "sertifikalar", "başarılar", "basarilar", "yetkinlikler",
}

NON_SKILL_TOKENS = {
    "languages", "language", "certifications", "certification", "certificate",
    "certificates", "achievements", "achievement", "awards", "award",
    "english", "turkish", "german", "french", "spanish", "native", "fluent",
    "professional", "elementary", "intermediate", "advanced", "beginner",
    "dil", "diller", "türkçe", "turkce", "ingilizce", "almanca", "fransızca",
    "fransizca", "anadil", "ileri", "orta", "başlangıç", "baslangic",
}

SECTION_ALIASES = {
    "summary": ["summary", "professional summary", "profile", "objective", "about", "özet", "profil", "hakkımda", "kariyer hedefi"],
    "experience": ["experience", "work experience", "professional experience", "employment", "career history", "deneyim", "iş deneyimi", "iş tecrübesi", "profesyonel deneyim", "çalışma deneyimi", "tecrübe"],
    "education": ["education", "academic background", "school experience", "studies", "eğitim", "öğrenim", "akademik geçmiş", "okul deneyimi", "çalışmalar"],
    "projects": ["projects", "selected projects", "personal projects", "academic projects", "selected work", "project experience", "projeler", "akademik projeler", "seçilmiş projeler", "secilmis projeler", "çalışmalar", "calismalar"],
    "skills": ["skills", "technical skills", "core skills", "technologies", "competencies", "skills achievements", "skills and achievements", "skills & achievements", "technical competencies", "yetenekler", "beceriler", "teknik yetenekler", "teknolojiler", "uzmanlıklar", "yetkinlikler", "yetenekler başarılar", "yetenekler ve başarılar", "beceriler başarılar", "beceriler ve başarılar"],
    "links": ["links", "profiles", "social", "portfolio", "bağlantılar", "linkler", "sosyal medya", "portföy"],
}


# ══════════════════════════════════════════════
#  SYSTEM PROMPTS (ATS OPTIMIZED & PREMIUM DESIGN)
# ══════════════════════════════════════════════

CV_SYSTEM_PROMPT = r"""You are an elite Career Strategy Expert and ATS Optimizer. 
Your task is to generate a world-class, single-page (extend to two pages ONLY if experience >10 years) resume in LaTeX format.

### PHASE 1: STRATEGIC AUDIT
1. **Keyword Analysis:** Identify the 'Must-Have' technologies and 'Soft Skills' in the Job Description. 
2. **Mirroring:** Rephrase the Candidate's existing accomplishments to use the EXACT terminology found in the JD (without fabricating facts).
3. **Hierarchy:** Prioritize the 'Skills' and 'Experience' that most directly solve the problems mentioned in the JD.

### PHASE 2: CONTENT ENGINEERING
1. **The Google XYZ Formula:** Every bullet point must follow: "Accomplished [X] as measured by [Y], by doing [Z]". 
   - *Bad:* "Managed a team of developers."
   - *Good:* "Led a cross-functional team of 5 developers to deliver a high-traffic e-commerce portal 2 weeks ahead of schedule, increasing conversion rates by 12%."
2. **Action Verbs:** Use powerful verbs (e.g., Orchestrated, Spearheaded, Engineered, Optimized).
3. **Truth Only:** Never add roles, dates, or skills not explicitly given in the JSON profile.

### PHASE 3: LATEX ARCHITECTURE (PREMIUM & ATS-SAFE)
1. **Font:** Use `\usepackage[scaled]{helvet}` and `\renewcommand\familydefault{\sfdefault}` for a clean, modern Sans-Serif look (Industry best for digital readability).
2. **Geometry:** Use `\usepackage[left=1.25cm,right=1.25cm,top=1.25cm,bottom=1.25cm]{geometry}`.
3. **No Decorative Elements:** Avoid graphics, icons, or complex tables. Use standard sections and horizontal rules (`\hrule`).
4. **Skills Section:** Group skills logically (e.g., Languages, Frameworks, Tools) to pass keyword-parsers instantly.
5. **Unicode:** Preserve names and Turkish characters exactly (ç, ğ, ı, İ, ö, ş, ü). Include UTF-8/T1 support.

### STRICT OUTPUT RULES
- NO MARKDOWN: Do NOT wrap in ```latex ... ``` blocks or add conversational text. Start exactly with `\documentclass` and end with `\end{document}`.
- IF YOU START WITH ```latex OR ANY MARKDOWN, YOU HAVE FAILED. 
- NO HALLUCINATIONS: If the candidate didn't provide a PhD, they don't have one.
- ESCAPE CHARACTERS: Ensure `# $ % & _ { } ~ ^ \` are escaped.
- PRESERVE UNICODE LETTERS: Do not transliterate Turkish names or content.
- Return ONLY raw LaTeX source. No conversational preamble. No preamble text of any kind. Just the source code.
"""


COVER_LETTER_SYSTEM_PROMPT = r"""You are a High-Stakes Career Coach and Persuasive Writer. 
Your task is to write a compelling, tailored Cover Letter in LaTeX that bridge the gap between the Candidate's profile and the Employer's needs.

### STRATEGY: THE AIDA MODEL
1. **Attention (The Hook):** Open with a strong, personalized statement about why the candidate is excited about this specific company and role. Use cues from the Job Description.
2. **Interest (Proof of Value):** Select 1-2 key achievements from the candidate's profile that directly map to the "Required Qualifications" in the JD.
3. **Desire (The Why):** Explain why the candidate is the solution to the company's specific pain points (e.g., scaling, optimization, leadership).
4. **Action (The Close):** A professional call to action, expressing readiness for an interview.

### LATEX FORMATTING (PREMIUM)
- Document Class: `\documentclass[11pt,a4paper]{article}`.
- Spacing: Use `\usepackage{parskip}` for modern paragraph spacing.
- Header: Match the professional header style of the CV (Name, Email, LinkedIn, etc. clearly positioned).
- Font: Use the same clean Sans-Serif font as the CV for brand consistency (`helvet`).
- Geometry: `\usepackage[left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm]{geometry}` for a balanced letter layout.
- Unicode: Preserve Turkish names and characters exactly.
- Do not include unresolved placeholders such as [Date], [Company Name], [Company Address], or [Hiring Manager Name]. Use \today and "Hiring Team" when exact employer details are missing.

### STRICT OUTPUT RULES
- NO MARKDOWN: Do NOT wrap in ```latex ... ``` blocks or add conversational text. No backticks. Start exactly with `\documentclass` and end with `\end{document}`.
- NO CONVIVIAL FILLER: Do not say "Certainly, here is your letter."
- Return ONLY the final LaTeX source code. No conversational filler or markdown fences.
"""


# ══════════════════════════════════════════════
#  LLM GENERATION (STREAMING)
# ══════════════════════════════════════════════

def _build_user_message(
    candidate_profile: Optional[dict],
    job_description: str,
    raw_cv_text: Optional[str] = None,
    additional_instructions: Optional[str] = None,
) -> str:
    """Format the user data into a structured prompt for the LLM."""
    source_block = (
        "=== SOURCE CV TEXT (RAW, USE AS FACT SOURCE) ===\n"
        f"{_clean_text(raw_cv_text or '')}\n\n"
        if raw_cv_text
        else "=== CANDIDATE PROFILE (JSON, USE AS FACT SOURCE) ===\n"
        f"{json.dumps(candidate_profile or {}, indent=2, ensure_ascii=False)}\n\n"
    )
    return (
        f"{source_block}"
        "=== JOB DESCRIPTION ===\n"
        f"{job_description}\n\n"
        "=== ADDITIONAL USER INSTRUCTIONS ===\n"
        f"{additional_instructions or ''}\n\n"
        "=== HARD CONSTRAINTS ===\n"
        "- Use only facts present in the source CV/profile.\n"
        "- Do not invent roles, dates, degrees, companies, projects, skills, addresses, or credentials.\n"
        "- If a company address or hiring manager is unknown, omit it or use a generic hiring team greeting.\n"
        "- Preserve Turkish characters exactly.\n"
    )


def _latex_escape(value: object) -> str:
    text = "" if value is None else str(value)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _clean_text(text: str) -> str:
    text = _repair_turkish_mojibake(text)
    text = unicodedata.normalize("NFKC", text)
    text = _strip_pdf_control_noise(text)
    text = _normalize_bullets_and_separators(text)
    text = _repair_fragmented_urls(text)
    text = _repair_fragmented_known_terms(text)
    text = _repair_fragmented_section_titles(text)
    text = _repair_phone_and_location_flow(text)
    text = text.replace("\ufeff", "")
    text = text.replace("\u00ad", "")
    text = text.replace("\u200b", "")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = _merge_broken_lines(text)
    text = _repair_fragmented_urls(text)
    text = _repair_fragmented_known_terms(text)
    text = _repair_fragmented_section_titles(text)
    text = _repair_turkish_identity_loss(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _strip_pdf_control_noise(text: str) -> str:
    text = text.replace("\x00", " ")
    text = text.replace("\ufeff", "")
    text = text.replace("\ufffd", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", "", text)
    text = re.sub(r"[\u0080-\u009f]", "", text)
    return text


def _normalize_bullets_and_separators(text: str) -> str:
    text = text.replace("·", " • ").replace("●", " • ").replace("◦", " • ")
    text = text.replace("•", "\n• ")
    text = re.sub(r"\n\s*[–—-]\s+", "\n• ", text)
    text = re.sub(r"[|]{2,}", "\n", text)
    text = re.sub(r"\s+[|]\s+", "\n", text)
    return text


def _repair_fragmented_urls(text: str) -> str:
    replacements = {
        r"\blink\s*ed\s*in\s*\.?\s*com\b": "linkedin.com",
        r"\blink\s*edin\s*\.?\s*com\b": "linkedin.com",
        r"\bgith\s*ub\s*\.?\s*com\b": "github.com",
        r"\bgit\s*hub\s*\.?\s*com\b": "github.com",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

    def compact_url(match: re.Match[str]) -> str:
        return re.sub(r"\s+", "", match.group(0))

    text = re.sub(
        r"(?:https?\s*:\s*/\s*/\s*)?(?:linkedin|github)\.com(?:\s*/\s*[A-Za-z0-9._~:/?#\[\]@!$&'()*+,;=%-]+)+",
        compact_url,
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(r"anil-y\s*esil", "anil-yesil", text, flags=re.IGNORECASE)
    text = re.sub(r"recruitassistant\s*\.\s*net", "RecruitAssistant.net", text, flags=re.IGNORECASE)
    return text


def _repair_fragmented_known_terms(text: str) -> str:
    replacements = {
        r"\bBilk\s*en\s*t\s+Univ\s*ersit\s*y\b": "Bilkent University",
        r"\bBilk\s*ent\s+Univ\s*ersity\b": "Bilkent University",
        r"\bNational\s+Taiwan\s+Univ\s*ersit\s*y\b": "National Taiwan University",
        r"\bsoft\s*w\s*are\s+engine\s*er\s*ing\b": "software engineering",
        r"\bsoft\s*w\s*are\b": "software",
        r"\bengine\s*er\s*ing\b": "engineering",
        r"\bTurk\s*ey\b": "Turkey",
        r"\bAnk\s*ara\b": "Ankara",
        r"\bJot\s*form\b": "Jotform",
        r"\bASEL\s*SAN\b": "ASELSAN",
        r"\bBahç\s*eden\b": "Bahçeden",
        r"\bBahc\s*eden\b": "Bahçeden",
        r"\bMEHMET\s+ANIL\s+YE\s*L\b": "Mehmet Anıl Yeşil",
        r"\bMEHMET\s+ANIL\s+YE\s*IL\b": "Mehmet Anıl Yeşil",
        r"\bMEHMET\s+ANIL\s+YE\s*Ş\s*İ?\s*L\b": "Mehmet Anıl Yeşil",
        r"\bMEHMET\s+ANL\s+YE\s*IL\b": "Mehmet Anıl Yeşil",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
    return text


def _repair_fragmented_section_titles(text: str) -> str:
    replacements = {
        r"(?im)^\s*SUMMAR\s*Y\s*$": "SUMMARY",
        r"(?im)^\s*EDUCA\s*TION\s*$": "EDUCATION",
        r"(?im)^\s*EXPERI\s*ENCE\s*$": "EXPERIENCE",
        r"(?im)^\s*PROJ\s*ECTS\s*$": "PROJECTS",
        r"(?im)^\s*SKILLS\s*&\s*ACHIEVE\s*MENTS\s*$": "SKILLS & ACHIEVEMENTS",
        r"(?im)^\s*SKILLS\s+ACHIEVE\s*MENTS\s*$": "SKILLS & ACHIEVEMENTS",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)
    return text


def _repair_phone_and_location_flow(text: str) -> str:
    text = re.sub(
        r"(\+\d{1,3})\s*\n\s*(\d{3})\s*\n?\s*(\d{3})\s*\n?\s*(\d{4})",
        r"\1 \2 \3 \4",
        text,
    )
    text = re.sub(r"\b(Ankara|Istanbul|İstanbul)\s*\n\s*,?\s*(Turkey|Turkiye|Türkiye)\b", r"\1, Turkey", text, flags=re.IGNORECASE)
    return text


def _merge_broken_lines(text: str) -> str:
    lines = [line.rstrip() for line in text.splitlines()]
    merged: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            merged.append("")
            continue
        if (
            merged
            and merged[-1]
            and not _is_probable_standalone_heading(merged[-1])
            and not _is_probable_standalone_heading(stripped)
            and not re.search(r"[.!?:;)]$", merged[-1])
            and "@" not in stripped
            and not _find_phone(stripped)
            and not re.search(r"https?://|linkedin|github", stripped, re.I)
            and stripped[:1].islower()
            and len(merged[-1]) < 90
        ):
            merged[-1] = f"{merged[-1]} {stripped}"
        else:
            merged.append(stripped)
    return "\n".join(merged)


def _is_probable_standalone_heading(value: str) -> bool:
    normalized = _normalize_heading_without_clean(value)
    if not normalized or len(normalized) > 64:
        return False
    if _classify_heading_normalized(normalized):
        return True
    letters = [char for char in value if char.isalpha()]
    if not letters:
        return False
    uppercase_ratio = sum(1 for char in letters if char.isupper()) / len(letters)
    return uppercase_ratio > 0.7 and len(value.split()) <= 5


def _repair_turkish_mojibake(text: str) -> str:
    if not text:
        return ""

    replacements = {
        "Ã‡": "Ç", "Ã§": "ç", "ÄŸ": "ğ", "Äž": "Ğ", "Ä°": "İ", "Ä±": "ı",
        "Ã–": "Ö", "Ã¶": "ö", "Åž": "Ş", "ÅŸ": "ş", "Ãœ": "Ü", "Ã¼": "ü",
        "Ã‡": "Ç", "Ã": "Ç", "Ã§": "ç", "Ä": "ğ", "Ä": "Ğ",
        "Ä°": "İ", "Ä±": "ı", "Å": "Ş", "Å": "ş",
        "Ð": "Ğ", "ð": "ğ", "Þ": "Ş", "þ": "ş", "Ý": "İ", "ý": "ı",
        "ðŸ": "ğ", "Å": "Ş",
        "YEL": "YEŞİL", "YEL": "YEŞİL", "YEL": "YEŞİL",
        "Yel": "Yeşil", "Yel": "Yeşil", "Yel": "Yeşil",
    }
    for broken, fixed in replacements.items():
        text = text.replace(broken, fixed)

    if any(marker in text for marker in ("Ã", "Ä", "Å")):
        try:
            candidate = text.encode("latin-1", errors="ignore").decode("utf-8", errors="ignore")
            if len(candidate) >= len(text) * 0.75:
                text = candidate
        except Exception:
            pass

    text = _repair_turkish_identity_loss(text)
    return text


def _repair_turkish_identity_loss(text: str) -> str:
    text = re.sub(
        r"\bMEHMET\s+AN[İIıi]?L?\s+YE[^\w\s]{0,6}\s*L\b",
        "Mehmet Anıl Yeşil",
        text,
        flags=re.IGNORECASE,
    )
    patterns = [
        r"\bMEHMET\s+AN[İIıi]?[ILıi]?\s+YE(?:Ş[İIıi]L|SIL|S[İIıi]L|[ŞS]?[İIıi]?L|IL|L)\b",
        r"\bMehmet\s+An[İIıi]?[ilı]?\s+Ye(?:şil|sil|s[ilı]|[şs]?[ilı]|il|l)\b",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "Mehmet Anıl Yeşil", text, flags=re.IGNORECASE)
    return text


def _normalize_token(value: str) -> str:
    value = _repair_turkish_mojibake(value).lower()
    value = "".join(char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char))
    translation = str.maketrans("çğıöşüİ", "cgiosui")
    value = value.translate(translation)
    return re.sub(r"[^a-z0-9+#.]+", "", value)


def _normalize_heading(value: str) -> str:
    value = _clean_text(value).lower()
    return _normalize_heading_without_clean(value)


def _normalize_heading_without_clean(value: str) -> str:
    value = _repair_turkish_mojibake(value).lower()
    value = value.strip(" :|•*-_")
    value = "".join(char for char in unicodedata.normalize("NFKD", value) if not unicodedata.combining(char))
    value = value.translate(str.maketrans("çğıöşüİ", "cgiosui"))
    value = value.replace("&", " and ")
    return re.sub(r"[^a-z0-9 ]+", " ", value).strip()


def _split_lines(text: str) -> list[str]:
    return [line.strip(" \t•-*") for line in text.splitlines() if line.strip(" \t•-*")]


def _find_email(text: str) -> str:
    match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text)
    return match.group(0) if match else ""


def _find_phone(text: str) -> str:
    match = re.search(
        r"(\+?\d[\d\s().-]{7,}\d)",
        text,
    )
    return match.group(1).strip() if match else ""


def _find_links(text: str) -> list[dict]:
    links = []
    seen = set()
    for url in re.findall(r"(https?://[^\s)>,]+|(?:linkedin|github)\.com/[^\s)>,]+)", text, re.I):
        clean_url = url.rstrip(".,")
        key = clean_url.lower()
        if key in seen:
            continue
        seen.add(key)
        label = "LinkedIn" if "linkedin" in key else "GitHub" if "github" in key else "Portfolio"
        if not clean_url.startswith("http"):
            clean_url = f"https://{clean_url}"
        links.append({"id": f"link-{len(links) + 1}", "label": label, "url": clean_url})
    return links


def _detect_skills(text: str) -> list[str]:
    normalized_text = _clean_text(text).lower()
    normalized_search = " ".join(_normalize_token(token) for token in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü0-9+#.]+", normalized_text))
    found = []
    for skill in COMMON_SKILLS:
        normalized_skill = _normalize_token(skill)
        if not normalized_skill or normalized_skill in {_normalize_token(token) for token in NON_SKILL_TOKENS}:
            continue
        compact_pattern = re.escape(normalized_skill)
        loose_pattern = re.escape(skill.lower()).replace(r"\ ", r"[\s/-]+")
        if re.search(rf"(?<![a-z0-9]){loose_pattern}(?![a-z0-9])", normalized_text) or re.search(
            rf"(?<![a-z0-9]){compact_pattern}(?![a-z0-9])",
            normalized_search.replace(" ", ""),
        ):
            found.append(skill)
    return _dedupe_preserve_order(found)


def _extract_section(text: str, headings: list[str], stop_headings: list[str]) -> str:
    heading_pattern = "|".join(re.escape(heading) for heading in headings)
    stop_pattern = "|".join(re.escape(heading) for heading in stop_headings)
    pattern = rf"(?ims)^\s*(?:{heading_pattern})\s*$\n(?P<body>.*?)(?=^\s*(?:{stop_pattern})\s*$|\Z)"
    match = re.search(pattern, text)
    return match.group("body").strip() if match else ""


def _extract_docx_text(file_bytes: bytes) -> str:
    """Extract text from a DOCX using only the standard library."""
    paragraphs: list[str] = []
    with zipfile.ZipFile(io.BytesIO(file_bytes)) as archive:
        for name in ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml"):
            if name not in archive.namelist():
                continue
            root = ET.fromstring(archive.read(name))
            namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
            for paragraph in root.findall(".//w:p", namespace):
                parts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
                text = "".join(parts).strip()
                if text:
                    paragraphs.append(text)
    return _clean_text("\n".join(paragraphs))


def _extract_pdf_text(file_bytes: bytes) -> str:
    return _clean_text(_extract_pdf_text_raw(file_bytes))


def _extract_pdf_text_raw(file_bytes: bytes) -> str:
    """
    Best-effort PDF text extraction.
    Uses system pdftotext when available, then Python PDF libraries, then a stream decoder fallback.
    """
    pdftotext = shutil.which("pdftotext")
    if pdftotext:
        tmp_dir = tempfile.mkdtemp(prefix="recruitassistant_pdf_")
        pdf_path = os.path.join(tmp_dir, "source.pdf")
        try:
            with open(pdf_path, "wb") as handle:
                handle.write(file_bytes)
            result = subprocess.run(
                [pdftotext, "-layout", "-enc", "UTF-8", pdf_path, "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout
        except Exception as exc:
            logger.info("pdftotext extraction failed: %s", exc)
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
            try:
                pages.append(page.extract_text(extraction_mode="layout") or "")
            except TypeError:
                pages.append(page.extract_text() or "")
        text = "\n".join(pages)
        if text:
            return text
    except Exception as exc:
        logger.info("pypdf extraction unavailable or failed: %s", exc)

    try:
        from PyPDF2 import PdfReader as PyPDF2Reader  # type: ignore

        reader = PyPDF2Reader(io.BytesIO(file_bytes))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n".join(pages)
        if text:
            return text
    except Exception as exc:
        logger.info("PyPDF2 extraction unavailable or failed: %s", exc)

    try:
        import zlib

        raw = file_bytes.decode("latin-1", errors="ignore")
        stream_texts: list[str] = []
        for match in re.finditer(r"stream\r?\n(.*?)\r?\nendstream", raw, re.S):
            encoded = match.group(1).encode("latin-1", errors="ignore")
            decoded = ""
            try:
                decoded = zlib.decompress(encoded).decode("latin-1", errors="ignore")
            except Exception:
                decoded = encoded.decode("latin-1", errors="ignore")
            for literal in re.findall(r"\((.*?)\)\s*Tj", decoded, re.S):
                stream_texts.append(_decode_pdf_literal(literal))
            for array in re.findall(r"\[(.*?)\]\s*TJ", decoded, re.S):
                stream_texts.extend(_decode_pdf_literal(item) for item in re.findall(r"\((.*?)\)", array, re.S))
            for hex_string in re.findall(r"<([0-9A-Fa-f]{4,})>\s*Tj", decoded):
                stream_texts.append(_decode_pdf_hex(hex_string))
        text = "\n".join(stream_texts)
        if text:
            return text
    except Exception as exc:
        logger.info("Fallback PDF extraction failed: %s", exc)

    return ""


def _decode_pdf_literal(value: str) -> str:
    value = re.sub(
        r"\\([0-7]{1,3})",
        lambda match: chr(int(match.group(1), 8)),
        value,
    )
    value = (
        value.replace(r"\(", "(")
        .replace(r"\)", ")")
        .replace(r"\\", "\\")
        .replace(r"\n", "\n")
        .replace(r"\r", "\n")
        .replace(r"\t", "\t")
    )
    return _repair_turkish_mojibake(value)


def _decode_pdf_hex(value: str) -> str:
    try:
        data = bytes.fromhex(value)
        if data.startswith(b"\xfe\xff"):
            return data.decode("utf-16-be", errors="ignore")
        decoded = data.decode("utf-8", errors="ignore")
        return decoded or data.decode("latin-1", errors="ignore")
    except Exception:
        return ""


def extract_cv_text(file_bytes: bytes, filename: str, content_type: str | None = None) -> tuple[str, str]:
    """Return extracted text and a normalized source type."""
    lower_name = filename.lower()
    if lower_name.endswith(".docx") or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        return _extract_docx_text(file_bytes), "DOCX"
    if lower_name.endswith(".pdf") or content_type == "application/pdf":
        return _extract_pdf_text(file_bytes), "PDF"
    raise ValueError("Only PDF and DOCX files are supported.")


def extract_cv_text_with_raw(file_bytes: bytes, filename: str, content_type: str | None = None) -> tuple[str, str, str]:
    """Return cleaned text, source type, and raw extracted text."""
    lower_name = filename.lower()
    if lower_name.endswith(".docx") or content_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        cleaned = _extract_docx_text(file_bytes)
        return cleaned, "DOCX", cleaned
    if lower_name.endswith(".pdf") or content_type == "application/pdf":
        raw = _extract_pdf_text_raw(file_bytes)
        return _clean_text(raw), "PDF", raw
    raise ValueError("Only PDF and DOCX files are supported.")


def parse_cv_text(text: str) -> tuple[dict, list[str], dict]:
    text = _clean_text(text)
    lines = _split_lines(text)
    warnings: list[str] = []

    if not text:
        warnings.append("Could not extract readable text from this file")
        quality = _build_quality(_empty_cv_data(), {}, extracted_text="")
        return _empty_cv_data(), warnings, quality

    blocks = _detect_section_blocks(text)
    personal = _parse_personal(text, lines)

    summary_text = blocks.get("summary", "")
    if not summary_text:
        possible_summary = [
            line for line in lines[:14]
            if line != personal["fullName"] and "@" not in line and not _find_phone(line) and len(line) > 42
        ]
        summary_text = possible_summary[0] if possible_summary else ""

    skills_text = blocks.get("skills", "")
    skills = _parse_skills(skills_text, full_text=text)

    experience = _parse_experience(blocks.get("experience", ""))
    if not experience:
        experience = _parse_experience(_remove_personal_header(text, personal))
    education = _parse_education(blocks.get("education", ""))
    if not education:
        education = _parse_education(_semantic_education_slice(text))
    projects = _parse_projects(blocks.get("projects", ""))
    if not projects:
        projects = _parse_projects(_semantic_projects_slice(text))
    links = _find_links(f"{blocks.get('links', '')}\n{text}")

    cv_data = {
        "personal": personal,
        "summary": summary_text,
        "education": education,
        "experience": experience,
        "projects": projects,
        "skills": skills[:24],
        "links": links,
    }

    quality = _build_quality(cv_data, blocks, extracted_text=text)

    for key, label in [
        ("personal", "Personal information"),
        ("experience", "Experience"),
        ("education", "Education"),
        ("projects", "Projects"),
        ("skills", "Skills"),
        ("links", "Links"),
    ]:
        status = quality["sections"][key]["status"]
        if status == "partial":
            warnings.append(f"{label} parsed partially. Review before applying.")
        elif status == "missing" and key in {"experience", "education", "skills"}:
            warnings.append(f"{label} was not detected.")

    if re.search(r"\b(19|20)\d{2}\b|present|current|günümüz|devam", text, re.I):
        warnings.append("Please review extracted dates")

    if quality["overallStatus"] != "confident":
        warnings.append("Extraction quality is limited. ATS analysis is based on partial data.")

    return cv_data, list(dict.fromkeys(warnings)), quality


def _empty_cv_data() -> dict:
    return {
        "personal": {"fullName": "", "headline": "", "email": "", "phone": "", "location": ""},
        "summary": "",
        "education": [],
        "experience": [],
        "projects": [],
        "skills": [],
        "links": [],
    }


def _parse_skills(section_text: str, full_text: str = "") -> list[str]:
    candidates = _detect_skills(section_text or full_text)
    clean_candidates: list[str] = []

    for line in _split_lines(section_text):
        normalized_line = _normalize_heading(line)
        if not normalized_line:
            continue
        label, _, value = line.partition(":")
        normalized_label = _normalize_heading(label)
        if normalized_label in {_normalize_heading(item) for item in SKILL_LABELS}:
            line = value
            if normalized_label in {
                "languages", "language", "diller", "certifications", "certification",
                "certificates", "sertifikalar", "achievements", "achievement", "basarilar",
            }:
                continue
        elif normalized_line in {_normalize_heading(item) for item in SKILL_LABELS}:
            continue

        for token in re.split(r"[,;|•·/]", line):
            candidate = token.strip(" -–—:()[]")
            if _is_valid_skill_candidate(candidate):
                clean_candidates.append(_canonical_skill(candidate))

    return _dedupe_preserve_order(candidates + clean_candidates)[:28]


def _is_valid_skill_candidate(value: str) -> bool:
    if not value:
        return False
    normalized = _normalize_token(value)
    if not normalized or normalized in {_normalize_token(item) for item in NON_SKILL_TOKENS | SKILL_LABELS}:
        return False
    if re.search(r"\b(native|fluent|intermediate|advanced|beginner|anadil|ileri|orta|başlangıç|baslangic|b1|b2|c1|c2|a1|a2)\b", value, re.I):
        return False
    if re.search(r"\b(certificate|certification|sertifika|course|kurs|award|achievement|başarı|basari)\b", value, re.I):
        return False
    if len(value) > 42 or len(value.split()) > 5:
        return False
    if re.search(r"[.!?]", value):
        return False
    if not re.search(r"[A-Za-zÇĞİÖŞÜçğıöşü+#.]", value):
        return False
    return True


def _canonical_skill(value: str) -> str:
    normalized = _normalize_token(value)
    for skill in COMMON_SKILLS:
        if _normalize_token(skill) == normalized:
            return skill
    return value.strip()


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    output: list[str] = []
    for value in values:
        clean = _clean_text(str(value)).strip(" ,;|")
        key = _normalize_token(clean)
        if not clean or not key or key in seen:
            continue
        seen.add(key)
        output.append(clean)
    return output


def _detect_section_blocks(text: str) -> dict[str, str]:
    lines = text.splitlines()
    headings: list[tuple[int, str]] = []

    for index, line in enumerate(lines):
        section = _classify_heading_line(line)
        if section:
            headings.append((index, section))
            continue

    blocks: dict[str, str] = {}
    for position, (line_index, section) in enumerate(headings):
        next_index = headings[position + 1][0] if position + 1 < len(headings) else len(lines)
        body = "\n".join(lines[line_index + 1:next_index]).strip()
        if body and section not in blocks:
            blocks[section] = body

    return blocks


def _classify_heading_line(line: str) -> Optional[str]:
    normalized = _normalize_heading(line)
    if not normalized or len(normalized) > 72:
        return None
    return _classify_heading_normalized(normalized)


def _classify_heading_normalized(normalized: str) -> Optional[str]:
    heading_to_section = {
        _normalize_heading_without_clean(alias): section
        for section, aliases in SECTION_ALIASES.items()
        for alias in aliases
    }
    if normalized in heading_to_section:
        return heading_to_section[normalized]
    for heading, section in heading_to_section.items():
        if normalized.startswith(heading) and abs(len(normalized) - len(heading)) <= 18:
            return section
        heading_words = set(heading.split())
        normalized_words = set(normalized.split())
        if heading_words and heading_words.issubset(normalized_words) and len(normalized_words) <= len(heading_words) + 3:
            return section
    if len(normalized.split()) <= 4:
        if {"skill", "achievement"} <= set(normalized.split()) or {"skills", "achievements"} <= set(normalized.split()):
            return "skills"
        if "internship" in normalized or "internships" in normalized:
            return "experience"
        if "study" in normalized or "studies" in normalized:
            return "education"
    return None


def _parse_personal(text: str, lines: list[str]) -> dict:
    email = _find_email(text)
    phone = _find_phone(text)
    full_name = ""
    headline = ""

    for line in lines[:10]:
        clean_line = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "", line)
        clean_line = clean_line.replace(phone, "") if phone else clean_line
        clean_line = clean_line.strip(" |,")
        words = clean_line.split()
        uppercase_ratio = sum(1 for char in clean_line if char.isupper()) / max(1, sum(1 for char in clean_line if char.isalpha()))
        if 2 <= len(words) <= 5 and uppercase_ratio > 0.45 and not re.search(r"\d", clean_line):
            full_name = clean_line.title() if clean_line.isupper() else clean_line
            full_name = _preserve_turkish_name_case(clean_line)
            break
        if not full_name and 2 <= len(words) <= 5 and not re.search(r"\d|@|linkedin|github", clean_line, re.I):
            full_name = clean_line
            break

    for line in lines[:12]:
        if line == full_name or "@" in line or _find_phone(line):
            continue
        if re.search(r"https?://|linkedin|github", line, re.I):
            continue
        if 8 <= len(line) <= 120 and not _is_heading_line(line):
            headline = line
            break

    return {
        "fullName": full_name,
        "headline": headline,
        "email": email,
        "phone": phone,
        "location": _guess_location(lines, email=email, phone=phone),
    }


def _remove_personal_header(text: str, personal: dict) -> str:
    lines = _split_lines(text)
    filtered = []
    for line in lines:
        if personal.get("fullName") and personal["fullName"] in line:
            continue
        if personal.get("email") and personal["email"] in line:
            continue
        if personal.get("phone") and personal["phone"] in line:
            continue
        filtered.append(line)
    return "\n".join(filtered)


def _semantic_education_slice(text: str) -> str:
    lines = _split_lines(text)
    selected: list[str] = []
    degree_pattern = re.compile(r"\b(B\.?S\.?|B\.?A\.?|M\.?S\.?|M\.?A\.?|MBA|PhD|Bachelor|Master|Doctor|Lisans|Yüksek Lisans|Yuksek Lisans|Doktora|University|Üniversitesi|Universitesi|College|Faculty|Fakültesi)\b", re.I)
    for index, line in enumerate(lines):
        if degree_pattern.search(line):
            if index > 0:
                selected.append(lines[index - 1])
            selected.append(line)
            if index + 1 < len(lines) and re.search(r"(?:19|20)\d{2}", lines[index + 1]):
                selected.append(lines[index + 1])
    return "\n".join(_dedupe_preserve_order(selected))


def _semantic_projects_slice(text: str) -> str:
    lines = _split_lines(text)
    selected: list[str] = []
    for index, line in enumerate(lines):
        normalized = _normalize_heading(line)
        if "project" in normalized or "proje" in normalized:
            selected.extend(lines[index:index + 4])
        elif _detect_skills(line) and index + 1 < len(lines) and len(lines[index + 1]) > 35:
            previous = lines[index - 1] if index > 0 else ""
            if previous and len(previous) < 80 and not _is_heading_line(previous):
                selected.extend([previous, line, lines[index + 1]])
    return "\n".join(_dedupe_preserve_order(selected))


def _preserve_turkish_name_case(value: str) -> str:
    if not value.isupper():
        return value
    return value


def _is_heading_line(line: str) -> bool:
    normalized = _normalize_heading(line)
    return any(normalized == _normalize_heading(alias) for aliases in SECTION_ALIASES.values() for alias in aliases)


def _guess_location(lines: list[str], email: str = "", phone: str = "") -> str:
    for line in lines[:10]:
        clean = line.replace(email, "") if email else line
        clean = clean.replace(phone, "") if phone else clean
        clean = re.sub(r"https?://\S+|(?:linkedin|github)\.com/\S+", "", clean, flags=re.I)
        clean = clean.strip(" |,")
        normalized = _normalize_heading(clean)
        if any(token in normalized for token in ["remote", "turkey", "turkiye", "istanbul", "ankara", "izmir", "united states", "usa", "san francisco", "new york", "london", "berlin"]):
            return clean
    return ""


def _parse_experience(section_text: str) -> list[dict]:
    lines = _split_lines(section_text)
    entries: list[dict] = []
    current: Optional[dict] = None
    consumed_indexes: set[int] = set()
    month = r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|Oca|Şub|Sub|Mar|Nis|May|Haz|Tem|Ağu|Agu|Eyl|Eki|Kas|Ara)[a-zçğıöşü]*\.?"
    date_pattern = re.compile(
        rf"((?:{month}\s+)?(?:19|20)\d{{2}})\s*(?:-|–|—|to|devam|/)\s*((?:Present|Current|Günümüz|Gunümüz|Gunumuz|Devam|Halen)|(?:{month}\s+)?(?:19|20)\d{{2}})",
        re.I,
    )

    for index, line in enumerate(lines):
        if index in consumed_indexes or _is_heading_line(line):
            continue
        date_match = date_pattern.search(line)
        looks_like_header = bool(date_match) or (" at " in line.lower() and len(line) < 120) or (" | " in line and len(line) < 140)
        if looks_like_header:
            if current:
                entries.append(current)
            start_date = date_match.group(1).strip() if date_match else ""
            end_date = date_match.group(2).strip() if date_match else ""
            date_text = date_match.group(0) if date_match else ""
            role_company = line.replace(date_text, "").strip(" -–—|,")
            if not role_company and index >= 1:
                role_company = lines[index - 1]
                consumed_indexes.add(index - 1)
                if index >= 2 and not re.search(r"\d|@", lines[index - 2]) and len(lines[index - 2]) < 90:
                    role_company = f"{lines[index - 2]} | {role_company}"
                    consumed_indexes.add(index - 2)
            role = role_company
            company = ""
            if " at " in role_company.lower():
                parts = re.split(r"\s+at\s+", role_company, maxsplit=1, flags=re.I)
                role, company = parts[0].strip(), parts[1].strip()
            elif " - " in role_company:
                parts = role_company.split(" - ", 1)
                role, company = parts[0].strip(), parts[1].strip()
            elif " | " in role_company:
                parts = role_company.split(" | ", 1)
                if _looks_like_role(parts[1]) and not _looks_like_role(parts[0]):
                    company, role = parts[0].strip(), parts[1].strip()
                elif _looks_like_company(parts[0]) and not _looks_like_company(parts[1]):
                    company, role = parts[0].strip(), parts[1].strip()
                else:
                    role, company = parts[0].strip(), parts[1].strip()
            current = {
                "id": f"exp-{len(entries) + 1}",
                "company": company,
                "role": role,
                "location": "",
                "startDate": start_date,
                "endDate": end_date,
                "bullets": [],
            }
        elif current and len(line) > 18:
            current["bullets"].append(line)

    if current:
        entries.append(current)

    return entries[:8]


def _looks_like_company(value: str) -> bool:
    return bool(re.search(r"\b(inc|llc|ltd|a\.ş|as|corp|company|labs|technologies|university|üniversitesi|holding|group)\b", value, re.I))


def _looks_like_role(value: str) -> bool:
    return bool(re.search(r"\b(engineer|developer|intern|manager|designer|analyst|consultant|specialist|assistant|lead|architect|mühendis|muhendis|geliştirici|gelistirici|stajyer|uzman|yönetici|yonetici)\b", value, re.I))


def _split_date_range(date_text: str) -> tuple[str, str]:
    if not date_text:
        return "", ""
    parts = re.split(r"\s*(?:-|–|to)\s*", date_text, maxsplit=1, flags=re.I)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()
    return date_text.strip(), ""


def _parse_education(section_text: str) -> list[dict]:
    lines = _split_lines(section_text)
    entries = []
    used: set[int] = set()
    degree_pattern = re.compile(r"\b(B\.?S\.?|B\.?A\.?|M\.?S\.?|M\.?A\.?|MBA|PhD|Bachelor|Master|Doctor|Lisans|Yüksek Lisans|Yuksek Lisans|Doktora|Ön Lisans|On Lisans)\b", re.I)
    for index, line in enumerate(lines[:12]):
        if index in used or _is_heading_line(line):
            continue
        if len(line) < 5:
            continue
        years = re.findall(r"(?:19|20)\d{2}", line)
        clean = re.sub(r"(?:19|20)\d{2}\s*(?:-|–|—|to)?\s*(?:19|20)\d{2}?", "", line).strip(" -–—,")
        degree = ""
        field = ""
        school = clean
        if degree_pattern.search(clean):
            degree = clean
            university_match = re.search(r"(.+?\b(?:University|Üniversitesi|Universitesi|College|Institute|Enstitüsü|Enstitusu))\b", clean, re.I)
            if university_match:
                school = university_match.group(1).strip(" ,-|")
                degree = clean.replace(university_match.group(1), "").strip(" ,-|")
            if index > 0 and index - 1 not in used and not degree_pattern.search(lines[index - 1]):
                school = lines[index - 1]
                used.add(index - 1)
            elif not school:
                school = ""
        elif index + 1 < len(lines) and degree_pattern.search(lines[index + 1]):
            school = clean
            degree_line = lines[index + 1]
            years = years or re.findall(r"(?:19|20)\d{2}", degree_line)
            degree = re.sub(r"(?:19|20)\d{2}\s*(?:-|–|—|to)?\s*(?:19|20)\d{2}?", "", degree_line).strip(" -–—,")
            used.add(index + 1)
        if "," in degree:
            parts = [part.strip() for part in degree.split(",", 1)]
            degree, field = parts[0], parts[1]
        entries.append({
            "id": f"edu-{index + 1}",
            "school": school,
            "degree": degree,
            "field": field,
            "startDate": years[0] if years else "",
            "endDate": years[-1] if len(years) > 1 else "",
            "details": "",
        })
    return entries[:4]


def _parse_projects(section_text: str) -> list[dict]:
    lines = _split_lines(section_text)
    projects = []
    current: Optional[dict] = None
    for line in lines:
        if _is_heading_line(line):
            continue
        if current and _detect_skills(line) and ("," in line or len(line.split()) <= 6):
            tech = _detect_skills(line)
            current["techStack"] = ", ".join(list(dict.fromkeys((current["techStack"].split(", ") if current["techStack"] else []) + tech)))
        elif len(line) < 90 and not line.endswith("."):
            if current:
                projects.append(current)
            current = {
                "id": f"project-{len(projects) + 1}",
                "name": line,
                "role": "",
                "techStack": ", ".join(_detect_skills(line)),
                "description": "",
            }
        elif current:
            current["description"] = f"{current['description']} {line}".strip()
            tech = _detect_skills(line)
            if tech:
                current["techStack"] = ", ".join(list(dict.fromkeys((current["techStack"].split(", ") if current["techStack"] else []) + tech)))
    if current:
        projects.append(current)
    return projects[:6]


def _build_quality(cv_data: dict, blocks: dict[str, str], extracted_text: str) -> dict:
    sections = {
        "personal": _section_quality(
            score=sum([
                bool(cv_data["personal"].get("fullName")),
                bool(cv_data["personal"].get("email")),
                bool(cv_data["personal"].get("phone")),
            ]) * 28 + (16 if cv_data["personal"].get("headline") else 0),
            detected=bool(cv_data["personal"].get("fullName") or cv_data["personal"].get("email")),
        ),
        "summary": _section_quality(
            score=92 if len(cv_data.get("summary", "")) > 80 else 65 if cv_data.get("summary") else 0,
            detected="summary" in blocks or bool(cv_data.get("summary")),
        ),
        "experience": _section_quality(
            score=_entry_score(cv_data.get("experience", []), ["role", "company", "startDate"], "bullets"),
            detected="experience" in blocks,
        ),
        "education": _section_quality(
            score=_entry_score(cv_data.get("education", []), ["school", "degree"], None),
            detected="education" in blocks,
        ),
        "projects": _section_quality(
            score=_entry_score(cv_data.get("projects", []), ["name", "description"], None),
            detected="projects" in blocks or bool(cv_data.get("projects")),
        ),
        "skills": _section_quality(
            score=min(96, len(cv_data.get("skills", [])) * 12),
            detected="skills" in blocks or bool(cv_data.get("skills")),
        ),
        "links": _section_quality(
            score=min(95, len(cv_data.get("links", [])) * 40),
            detected="links" in blocks or bool(cv_data.get("links")),
        ),
    }
    if not extracted_text:
        overall = 0
    else:
        weighted = (
            sections["personal"]["score"] * 1.2
            + sections["experience"]["score"] * 1.6
            + sections["education"]["score"] * 1.1
            + sections["skills"]["score"] * 1.1
            + sections["summary"]["score"]
            + sections["projects"]["score"] * 0.7
            + sections["links"]["score"] * 0.4
        )
        overall = round(weighted / 7.1)
    return {
        "overallScore": max(0, min(100, overall)),
        "overallStatus": _status_for_score(overall),
        "sections": sections,
    }


def _entry_score(entries: list[dict], important_fields: list[str], list_field: Optional[str]) -> int:
    if not entries:
        return 0
    entry_scores = []
    for entry in entries:
        field_score = sum(1 for field in important_fields if entry.get(field)) / max(1, len(important_fields))
        list_score = 0.25 if list_field and entry.get(list_field) else 0
        entry_scores.append(min(1, field_score * 0.8 + list_score))
    return round((sum(entry_scores) / len(entry_scores)) * 100)


def _section_quality(score: int, detected: bool) -> dict:
    score = max(0, min(100, score))
    if not detected and score < 35:
        return {"status": "missing", "score": score, "message": "Not detected"}
    status = _status_for_score(score)
    message = {
        "confident": "Ready",
        "partial": "Review needed",
        "missing": "Not detected",
    }[status]
    return {"status": status, "score": score, "message": message}


def _status_for_score(score: int) -> str:
    if score >= 78:
        return "confident"
    if score >= 35:
        return "partial"
    return "missing"


def analyze_cv(cv_data: dict, job_description: str, quality: Optional[dict] = None) -> dict:
    """Compute transparent ATS-style guidance without pretending to be an oracle."""
    job_text = job_description or ""
    profile_text = json.dumps(cv_data, ensure_ascii=False)
    required_skills = _detect_skills(job_text)
    candidate_skills = set(_normalize_token(skill) for skill in cv_data.get("skills", []))
    matched = [skill for skill in required_skills if _normalize_token(skill) in candidate_skills or skill.lower() in profile_text.lower()]
    missing = [skill for skill in required_skills if skill not in matched]

    has_email = bool(cv_data.get("personal", {}).get("email"))
    has_phone = bool(cv_data.get("personal", {}).get("phone"))
    has_summary = bool(cv_data.get("summary"))
    has_experience = bool(cv_data.get("experience"))
    has_skills = bool(cv_data.get("skills"))
    structural_score = sum([has_email, has_phone, has_summary, has_experience, has_skills]) * 8
    keyword_score = round((len(matched) / max(1, len(required_skills))) * 42) if required_skills else 24
    ats_score = max(35, min(98, 32 + structural_score + keyword_score))

    candidate_words = {_normalize_token(word) for word in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü+#.-]{2,}", profile_text)}
    job_words = {_normalize_token(word) for word in re.findall(r"[A-Za-zÇĞİÖŞÜçğıöşü][A-Za-zÇĞİÖŞÜçğıöşü+#.-]{2,}", job_text)}
    stop_words = {"the", "and", "for", "with", "you", "our", "are", "this", "that", "will", "role", "team", "work", "from"}
    candidate_words -= stop_words
    job_words -= stop_words
    overlap = len(candidate_words & job_words)
    role_match = max(30, min(97, 45 + round((overlap / max(1, len(job_words))) * 90)))

    recommendations = []
    if missing:
        recommendations.append("Review missing skills and add only the ones supported by real experience.")
    if not has_summary:
        recommendations.append("Add a concise professional summary aligned with the target role.")
    if has_experience:
        recommendations.append("Prioritize achievement bullets with measurable outcomes.")
    if not job_text.strip():
        recommendations.append("Paste a target job description for a stronger role match estimate.")

    overall_quality = quality.get("overallScore", 100) if quality else 100
    limited_confidence = overall_quality < 72
    if limited_confidence:
        ats_score = min(ats_score, 72)
        role_match = min(role_match, 72)
        recommendations.insert(0, "Review low-confidence source fields before trusting ATS or role-match estimates.")

    return {
        "atsScore": ats_score,
        "roleMatch": role_match,
        "missingSkills": missing[:8],
        "matchedSkills": matched[:12],
        "recommendations": recommendations[:4],
        "confidenceLabel": "Limited source confidence" if limited_confidence else "Based on reviewed CV data",
        "limitedConfidence": limited_confidence,
    }


def improve_section(section_name: str, cv_data: dict, job_description: str, instructions: str = "") -> dict:
    """Return visible, truthful AI-assistance suggestions for a CV section."""
    if client:
        try:
            response = client.chat.completions.create(
                model=MODEL,
                temperature=0.2,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You review CV content. Return JSON only with keys suggestions, warnings, improvedText. "
                            "Do not invent experience, employers, dates, degrees, or skills."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "section_name": section_name,
                                "cv_data": cv_data,
                                "job_description": job_description,
                                "instructions": instructions,
                            },
                            ensure_ascii=False,
                        ),
                    },
                ],
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or "{}"
            parsed = json.loads(content)
            improved_text = parsed.get("improvedText")
            if improved_text is not None and not isinstance(improved_text, str):
                improved_text = None
            return {
                "suggestions": [str(item) for item in parsed.get("suggestions", [])][:5],
                "warnings": [str(item) for item in parsed.get("warnings", [])][:5],
                "improvedText": improved_text,
            }
        except Exception as exc:
            logger.warning("OpenAI section improvement failed, using fallback: %s", exc)

    analysis = analyze_cv(cv_data, job_description)
    suggestions = [
        f"{section_name} reviewed against the target role without adding unsupported claims.",
        "Use the target role terminology where it accurately describes your existing work.",
        "Keep measurable outcomes visible near the top of the section.",
    ]
    if analysis["missingSkills"]:
        suggestions.append(f"Potential gaps to verify: {', '.join(analysis['missingSkills'][:3])}.")
    if instructions:
        suggestions.append("Additional instructions were considered as guidance, not as a source of new facts.")
    return {
        "suggestions": suggestions[:5],
        "warnings": ["Human review recommended before exporting."],
        "improvedText": None,
    }


def _fallback_cv_latex(candidate_profile: dict, job_description: str) -> str:
    name = candidate_profile.get("full_name") or "Candidate"
    email = candidate_profile.get("email") or ""
    phone = candidate_profile.get("phone") or ""
    location = candidate_profile.get("location") or ""
    summary = candidate_profile.get("summary") or "Experienced professional with a track record of delivering measurable outcomes."
    skills = candidate_profile.get("skills") or []
    experience = candidate_profile.get("experience") or []
    education = candidate_profile.get("education") or []
    projects = candidate_profile.get("projects") or []

    lines = [
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[left=1.25cm,right=1.25cm,top=1.25cm,bottom=1.25cm]{geometry}",
        r"\usepackage[scaled]{helvet}",
        r"\renewcommand\familydefault{\sfdefault}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{enumitem}",
        r"\usepackage[hidelinks]{hyperref}",
        r"\setlength{\parindent}{0pt}",
        r"\setlist[itemize]{leftmargin=*,topsep=2pt,itemsep=2pt}",
        r"\begin{document}",
        rf"{{\LARGE \textbf{{{_latex_escape(name)}}}}}\\",
        rf"{_latex_escape(email)} \quad {_latex_escape(phone)} \quad {_latex_escape(location)}",
        r"\vspace{0.5em}\hrule\vspace{0.8em}",
        r"\textbf{Professional Summary}\\",
        _latex_escape(summary),
        r"\vspace{0.8em}",
    ]
    if skills:
        lines.extend([r"\textbf{Skills}\\", _latex_escape(", ".join(skills)), r"\vspace{0.8em}"])
    if experience:
        lines.append(r"\textbf{Experience}")
        for item in experience:
            lines.append(rf"\textbf{{{_latex_escape(item.get('title', 'Role'))}}}, {_latex_escape(item.get('company', 'Company'))} \hfill {_latex_escape(item.get('start_date', ''))} -- {_latex_escape(item.get('end_date') or 'Present')}")
            bullets = item.get("bullets") or []
            if bullets:
                lines.append(r"\begin{itemize}")
                lines.extend(rf"\item {_latex_escape(bullet)}" for bullet in bullets[:4])
                lines.append(r"\end{itemize}")
        lines.append(r"\vspace{0.4em}")
    if projects:
        lines.append(r"\textbf{Projects}")
        for item in projects[:4]:
            tech = ", ".join(item.get("technologies") or [])
            lines.append(rf"\textbf{{{_latex_escape(item.get('name', 'Project'))}}} -- {_latex_escape(tech)}\\")
            lines.append(_latex_escape(item.get("description", "")))
        lines.append(r"\vspace{0.4em}")
    if education:
        lines.append(r"\textbf{Education}")
        for item in education:
            lines.append(rf"\textbf{{{_latex_escape(item.get('institution', 'Institution'))}}}, {_latex_escape(item.get('degree', 'Degree'))} \hfill {_latex_escape(item.get('start_date') or '')} -- {_latex_escape(item.get('end_date') or '')}\\")
    lines.append(r"\end{document}")
    return "\n".join(lines)


def _fallback_cover_letter_latex(candidate_profile: dict, job_description: str) -> str:
    name = candidate_profile.get("full_name") or "Candidate"
    email = candidate_profile.get("email") or ""
    summary = candidate_profile.get("summary") or "my background"
    first_experience = (candidate_profile.get("experience") or [{}])[0]
    role = first_experience.get("title", "the role")
    company = first_experience.get("company", "my previous teams")
    return "\n".join([
        r"\documentclass[11pt,a4paper]{article}",
        r"\usepackage[left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm]{geometry}",
        r"\usepackage[scaled]{helvet}",
        r"\renewcommand\familydefault{\sfdefault}",
        r"\usepackage[utf8]{inputenc}",
        r"\usepackage[T1]{fontenc}",
        r"\usepackage{parskip}",
        r"\begin{document}",
        rf"{{\Large \textbf{{{_latex_escape(name)}}}}}\\",
        _latex_escape(email),
        r"\vspace{1.5em}",
        r"Dear Hiring Team,",
        "",
        rf"I am excited to apply for this opportunity because it closely matches {_latex_escape(summary)}",
        "",
        rf"In my work as {_latex_escape(role)} with {_latex_escape(company)}, I built and improved products using the experience already reflected in my CV. I would bring the same source-grounded, outcome-focused approach to your team.",
        "",
        "I would welcome the chance to discuss how my background can support your goals.",
        "",
        "Sincerely,",
        _latex_escape(name),
        r"\end{document}",
    ])


def _profile_from_raw_text(raw_cv_text: str) -> dict:
    cv_data, _, _ = parse_cv_text(raw_cv_text)
    links = cv_data.get("links", [])
    linkedin = next((link.get("url") for link in links if "linkedin" in link.get("label", "").lower()), None)
    github = next((link.get("url") for link in links if "github" in link.get("label", "").lower()), None)
    return {
        "full_name": cv_data.get("personal", {}).get("fullName") or "Candidate",
        "email": cv_data.get("personal", {}).get("email") or "",
        "phone": cv_data.get("personal", {}).get("phone") or None,
        "linkedin": linkedin,
        "github": github,
        "location": cv_data.get("personal", {}).get("location") or None,
        "summary": cv_data.get("summary") or None,
        "skills": cv_data.get("skills") or [],
        "experience": [
            {
                "company": item.get("company", ""),
                "title": item.get("role", ""),
                "start_date": item.get("startDate", ""),
                "end_date": item.get("endDate") or None,
                "location": item.get("location") or None,
                "bullets": item.get("bullets", []),
            }
            for item in cv_data.get("experience", [])
        ],
        "education": [
            {
                "institution": item.get("school", ""),
                "degree": ", ".join(part for part in [item.get("degree", ""), item.get("field", "")] if part),
                "start_date": item.get("startDate") or None,
                "end_date": item.get("endDate") or None,
                "highlights": [item.get("details")] if item.get("details") else [],
            }
            for item in cv_data.get("education", [])
        ],
        "projects": [
            {
                "name": item.get("name", ""),
                "description": item.get("description", ""),
                "technologies": [skill.strip() for skill in item.get("techStack", "").split(",") if skill.strip()],
            }
            for item in cv_data.get("projects", [])
        ],
        "certifications": [],
        "languages": [],
    }


def generate_cv_latex_stream(
    candidate_profile: Optional[dict],
    job_description: str,
    raw_cv_text: Optional[str] = None,
    additional_instructions: Optional[str] = None,
) -> Generator[str, None, None]:
    """Stream OpenAI generated CV LaTeX using a generator."""
    if not client:
        yield _fallback_cv_latex(candidate_profile or _profile_from_raw_text(raw_cv_text or ""), job_description)
        return

    logger.info("Streaming CV LaTeX via OpenAI (%s)", MODEL)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.3,
            messages=[
                {"role": "system", "content": CV_SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_message(candidate_profile, job_description, raw_cv_text, additional_instructions)},
            ],
            stream=True,
        )

        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as exc:
        logger.warning("OpenAI CV generation failed, using fallback: %s", exc)
        yield _fallback_cv_latex(candidate_profile or _profile_from_raw_text(raw_cv_text or ""), job_description)


def generate_cover_letter_latex_stream(
    candidate_profile: Optional[dict],
    job_description: str,
    raw_cv_text: Optional[str] = None,
    additional_instructions: Optional[str] = None,
) -> Generator[str, None, None]:
    """Stream OpenAI generated Cover Letter LaTeX using a generator."""
    if not client:
        yield _fallback_cover_letter_latex(candidate_profile or _profile_from_raw_text(raw_cv_text or ""), job_description)
        return

    logger.info("Streaming Cover Letter LaTeX via OpenAI (%s)", MODEL)

    try:
        response = client.chat.completions.create(
            model=MODEL,
            temperature=0.5,
            messages=[
                {"role": "system", "content": COVER_LETTER_SYSTEM_PROMPT},
                {"role": "user", "content": _build_user_message(candidate_profile, job_description, raw_cv_text, additional_instructions)},
            ],
            stream=True,
        )

        for chunk in response:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as exc:
        logger.warning("OpenAI cover letter generation failed, using fallback: %s", exc)
        yield _fallback_cover_letter_latex(candidate_profile or _profile_from_raw_text(raw_cv_text or ""), job_description)


# ══════════════════════════════════════════════
#  LATEX → PDF COMPILATION (TECTONIC)
# ══════════════════════════════════════════════

def _find_tectonic() -> Optional[str]:
    """Locate the tectonic binary. Checks common install paths on macOS."""
    path = shutil.which("tectonic")
    if path:
        return path
    
    # Common Homebrew paths on Intel and Apple Silicon
    common_paths = [
        "/usr/local/bin/tectonic",
        "/opt/homebrew/bin/tectonic",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    return None


def compile_latex_to_pdf(latex_content: str) -> Optional[str]:
    """
    Compile a LaTeX string to PDF using Tectonic.

    Returns the PDF as a base64-encoded string, or None if compilation fails.
    Tectonic automatically handles multiple passes and downloads missing packages.
    """
    tectonic_bin = _find_tectonic()
    if not tectonic_bin:
        logger.warning(
            "tectonic not found on this system. "
            "Please install it via `brew install tectonic` (macOS) "
            "or visit https://tectonic-typesetting.github.io/ for installation instructions."
        )
        return _plain_text_pdf_base64(_latex_to_plain_text(latex_content))

    tmp_dir = tempfile.mkdtemp(prefix="recruitassistant_latex_")
    tex_filename = f"{uuid.uuid4().hex}.tex"
    tex_path = os.path.join(tmp_dir, tex_filename)
    pdf_path = tex_path.replace(".tex", ".pdf")

    content = sanitize_latex_for_compile(latex_content)
    
    try:
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Tectonic handles multiple passes automatically.
        # -X compile is the modern interface, but we'll use a robust fallback.
        result = subprocess.run(
            [
                tectonic_bin,
                "-X", "compile",
                tex_path,
                "--outdir", tmp_dir,
            ],
            capture_output=True,
            text=True,
            timeout=120, # Tectonic might download packages on first run
            cwd=tmp_dir,
        )

        if result.returncode != 0:
            logger.error(
                "Tectonic compilation failed:\nSTDOUT: %s\nSTDERR: %s",
                result.stdout[-2000:] if result.stdout else "",
                result.stderr[-2000:] if result.stderr else "",
            )
            return _plain_text_pdf_base64(_latex_to_plain_text(content))

        if not os.path.isfile(pdf_path):
            logger.error("PDF file was not generated at %s", pdf_path)
            # Try to find any PDF in the directory as fallback
            generated_pdfs = [f for f in os.listdir(tmp_dir) if f.endswith(".pdf")]
            if generated_pdfs:
                pdf_path = os.path.join(tmp_dir, generated_pdfs[0])
            else:
                return _plain_text_pdf_base64(_latex_to_plain_text(content))

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        return base64.b64encode(pdf_bytes).decode("utf-8")

    except subprocess.TimeoutExpired:
        logger.error("Tectonic timed out after 120 seconds")
        return _plain_text_pdf_base64(_latex_to_plain_text(latex_content))
    except Exception as e:
        logger.error("LaTeX compilation error: %s", str(e))
        return _plain_text_pdf_base64(_latex_to_plain_text(latex_content))
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def sanitize_latex_for_compile(latex_content: str) -> str:
    content = _clean_text(latex_content)
    content = content.replace("\ufeff", "").replace("\u200b", "")
    content = (
        content.replace("“", "``")
        .replace("”", "''")
        .replace("‘", "`")
        .replace("’", "'")
        .replace("–", "--")
        .replace("—", "---")
    )
    content = re.sub(r"```(?:latex)?", "", content, flags=re.I).replace("```", "").strip()
    placeholders = {
        "[Today’s Date]": r"\today",
        "[Today's Date]": r"\today",
        "[Date]": r"\today",
        "[Company Name]": "Hiring Team",
        "[Company Address]": "",
        "[Hiring Manager Name]": "Hiring Team",
        "[Recipient Name]": "Hiring Team",
    }
    for placeholder, replacement in placeholders.items():
        content = content.replace(placeholder, replacement)
    content = re.sub(r"\[[A-Za-z][^\]\n]{2,40}\]", "", content)
    if r"\documentclass" not in content:
        content = "\n".join([
            r"\documentclass[11pt,a4paper]{article}",
            r"\usepackage[left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm]{geometry}",
            r"\usepackage[utf8]{inputenc}",
            r"\usepackage[T1]{fontenc}",
            r"\usepackage{parskip}",
            r"\begin{document}",
            _latex_escape(content),
            r"\end{document}",
        ])
    if r"\usepackage[utf8]{inputenc}" not in content and r"\usepackage[utf8x]{inputenc}" not in content:
        content = re.sub(
            r"(\\documentclass(?:\[[^\]]*\])?\{[^}]+\})",
            lambda match: match.group(1) + "\n" + r"\usepackage[utf8]{inputenc}",
            content,
            count=1,
        )
    if r"\usepackage[T1]{fontenc}" not in content:
        content = re.sub(
            r"(\\usepackage\[utf8\]\{inputenc\})",
            lambda match: match.group(1) + "\n" + r"\usepackage[T1]{fontenc}",
            content,
            count=1,
        )
    if r"\href" in content and r"\usepackage{hyperref}" not in content and r"\usepackage[hidelinks]{hyperref}" not in content:
        content = re.sub(
            r"(\\usepackage(?:\[[^\]]*\])?\{[^}]+\}(?:\n\\usepackage(?:\[[^\]]*\])?\{[^}]+\})*)",
            lambda match: match.group(1) + "\n" + r"\usepackage[hidelinks]{hyperref}",
            content,
            count=1,
        )
    return content


def _latex_to_plain_text(latex_content: str) -> str:
    text = latex_content.strip()
    text = re.sub(r"```(?:latex)?|```", "", text, flags=re.I)
    text = re.sub(r"\\documentclass(?:\[[^\]]*\])?\{[^}]+\}", "", text)
    text = re.sub(r"\\usepackage(?:\[[^\]]*\])?\{[^}]+\}", "", text)
    text = re.sub(r"\\renewcommand[^\n]*", "", text)
    text = re.sub(r"\\begin\{document\}|\\end\{document\}", "", text)
    text = re.sub(r"\\begin\{itemize\}|\\end\{itemize\}", "", text)
    text = re.sub(r"\\item\s*", "• ", text)
    text = re.sub(r"\\(?:textbf|textit|href)\{([^{}]*)\}", r"\1", text)
    text = re.sub(r"\\[a-zA-Z]+(?:\[[^\]]*\])?(?:\{[^}]*\})?", " ", text)
    text = text.replace(r"\&", "&").replace(r"\%", "%").replace(r"\_", "_").replace(r"\#", "#").replace(r"\$", "$")
    text = text.replace(r"\\", "\n")
    return _clean_text(text)


def _plain_text_pdf_base64(text: str) -> str:
    lines = []
    for raw_line in _split_lines(text):
        line = raw_line[:96]
        if line:
            lines.append(line)
        if len(lines) >= 48:
            break
    if not lines:
        lines = ["RecruitAssistant generated document"]

    content_parts = ["BT", "/F1 10 Tf", "50 790 Td", "14 TL"]
    for line in lines:
        encoded = ("FEFF".encode("ascii") + line.encode("utf-16-be")).hex().upper()
        content_parts.append(f"<{encoded}> Tj")
        content_parts.append("T*")
    content_parts.append("ET")
    stream = "\n".join(content_parts).encode("ascii")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]

    pdf = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index, obj in enumerate(objects, start=1):
        offsets.append(len(pdf))
        pdf.extend(f"{index} 0 obj\n".encode("ascii"))
        pdf.extend(obj)
        pdf.extend(b"\nendobj\n")
    xref_offset = len(pdf)
    pdf.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    pdf.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        pdf.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    pdf.extend(
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    return base64.b64encode(bytes(pdf)).decode("ascii")
