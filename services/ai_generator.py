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
from typing import Optional, Generator

from dotenv import load_dotenv

from utils.ai_client import get_ai_client, get_model_name

load_dotenv()

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════
#  SYSTEM PROMPTS (ATS OPTIMIZED & HARVARD FORMAT)
# ══════════════════════════════════════════════

CV_SYSTEM_PROMPT = r"""You are a senior technical resume editor and Harvard resume formatting specialist.
Your task is to generate a polished, accurate, targeted, one-page resume in LaTeX format that strictly follows the Harvard Resume Format.

### PHASE 1: ROLE TARGETING
1. Extract the target company, target role title, seniority, core domain, required tools, and business problems from the Job Description.
2. Reorder and rewrite the candidate's existing facts to emphasize fit for that exact role and company.
3. If the Job Description does not identify a company or role, stay factual and specific, but do not pretend the resume is company-specific.

### PHASE 2: CONTENT EDITING
1. Truth only: Never add roles, dates, tools, metrics, degrees, certifications, products, or outcomes not explicitly present in the profile or job description.
2. Use the candidate's provided metrics when available. Do not invent percentages, users, latency, revenue, scale, or awards.
3. Rewrite each bullet as: strong verb + concrete engineering/business task + tools/systems + outcome or scope if provided.
4. Avoid filler verbs and vague claims such as "responsible for", "worked on", "helped with", "leveraged", "impactful", "robust", "cutting-edge", "passionate", and "keen interest".
5. Keep bullets ATS-friendly, compact, and readable. Each experience bullet should be one line when possible and under 25 words.
6. Prefer precise verbs such as Built, Developed, Implemented, Optimized, Integrated, Automated, Designed, Refactored, Evaluated, Maintained, and Analyzed.
7. If a project named RecruitAssistant or RecruitAssistant.net appears, describe it as an end-to-end career preparation platform, not merely an interview assistant. Include only supported modules from the profile/docs/job context: job-specific CV and cover-letter generation, mock interviews, quizzes, speech-to-text transcription, evaluation, personalized feedback, analytics/progress tracking, React frontend, FastAPI backend, AI/ML modules, and PostgreSQL. Do not include unsupported modules.

### PHASE 3: RESUME STRATEGY
1. Summary: Write 2 compact lines focused on hiring value for the target technical role. Keep Bilkent, rank, scholarship, GPA, or honors only if present, but do not frame the summary around master's applications or graduate-school goals.
2. Experience: Prioritize the strongest technical signals for Data Engineering, AI/ML Engineering, and Software Engineering roles. When present, Jotform, ASELSAN, and RecruitAssistant should usually be more prominent than weaker or less relevant items.
3. Dates and titles: Normalize all dates to a clean style such as `Aug 2025 -- Present`, `Jun 2024 -- Aug 2024`, or `2024`. Never merge company, role, and date into one malformed line.
4. Experience layout must be consistent: company/location on line 1, role/dates on line 2, then bullets.
5. Projects: Use 1-3 bullets per project. Emphasize personal ownership, architecture, data/AI systems, backend/frontend integration, and measurable outcomes only when provided.
6. Skills: Keep only skills supported by the profile. Group into focused technical categories. Remove soft skills and inflated keyword dumps.

### PHASE 4: STRICT HARVARD RESUME FORMAT
- Use a classic serif resume style throughout. The final PDF must look like a Harvard career-services resume: compact, formal, black text on white paper.
- NO colors, icons, progress bars, sidebars, text boxes, graphics, columns, or decorative elements.
- NO gray text. Everything must render black on white.
- NO multi-column resume layout. Only normal document flow with left/right alignment where specified.

### LATEX ARCHITECTURE
- Preamble: Strictly start EXACTLY with:
  \documentclass[11pt,a4paper]{article}
  \usepackage{fontspec}
  \setmainfont{texgyretermes-regular.otf}[
    BoldFont=texgyretermes-bold.otf,
    ItalicFont=texgyretermes-italic.otf,
    BoldItalicFont=texgyretermes-bolditalic.otf
  ]
  \usepackage[english, turkish]{babel}
  \usepackage[margin=1.45cm]{geometry}
  \usepackage{enumitem}
  \usepackage[hidelinks]{hyperref}
  \pagestyle{empty}
  \setlength{\parindent}{0pt}
  \setlist[itemize]{leftmargin=1.2em, itemsep=1pt, topsep=2pt, parsep=0pt}
- The document body must be written with simple LaTeX primitives only: \begin{center}, \textbf{}, \textit{}, \hfill, \section*{}, \vspace{}, \hrule, \begin{itemize}.
- Contact Info: Do NOT use custom commands like `\email{}`. Use standard text.
- Header:
  1. Full name centered, uppercase, large, bold.
  2. Contact line centered directly below the name.
  3. Separate email, phone, location, LinkedIn, and GitHub/portfolio URL with ` | ` on one line.
  4. Include LinkedIn and GitHub/portfolio only when provided in the JSON profile.
- Section Headings:
  1. Left-aligned, bold, uppercase.
  2. The solid black horizontal rule must feel attached to the heading, not the body content.
  3. Use this exact pattern for every section heading:
     \section*{SECTION NAME}\vspace{-0.65em}
     \hrule
     \vspace{0.45em}
  4. Do not place body text immediately after \hrule without the larger post-rule gap.
- Education and Experience Item Structure:
  1. Line 1: left side organization/company in bold; right side location in normal text using \hfill.
  2. Line 2: left side degree/job title in italics; right side dates in normal text using \hfill.
  3. No extra vertical space between line 1 and line 2.
  4. Use exactly two tight lines before any bullets; do not introduce line breaks or vertical margins between those two lines.
- Bullet Points:
  1. Use standard itemize bullet lists.
  2. Keep bullets compact with snug leading.
  3. No icons, custom bullets, tables, or colored bullets.
- Projects:
  1. Project name bold on the left and project date right-aligned on the same line using \hfill.
  2. If a project date is not provided, omit the right-aligned date cleanly.
  3. Tech stack may appear in italics on the next line.
  4. Descriptions must be normal bullet points.
- Skills:
  1. Do NOT use chips, tags, boxes, columns, or tables.
  2. Display as a clean comma-separated text line, e.g. `Technical Skills: React, Node.js, TypeScript`.
  3. Do NOT create a Soft Skills category or Soft Skills bullets.
  4. If categorization is useful, use technical categories only, such as `Languages: ...`, `Frameworks: ...`, `Databases: ...`, `Cloud/Tools: ...`.
- Do not include a headline under the name unless explicitly present in the input.
- ESCAPE CHARACTERS: Ensure `# $ % & _ { } ~ ^ \` are escaped.
- ABSOLUTE PRIORITY: USER'S CUSTOM INSTRUCTIONS take precedence.
- NO HALLUCINATIONS: If the candidate didn't provide a PhD, they don't have one.
- Return ONLY raw LaTeX source. No conversational preamble. No preamble text.
"""

COVER_LETTER_SYSTEM_PROMPT = r"""You are a senior technical cover-letter editor.
Your task is to write a concise, credible, role-targeted cover letter in LaTeX that connects the candidate's real experience to the employer's specific role.

### STRATEGY: THE AIDA MODEL
1. **Attention (The Hook):** Open directly with the exact role and company when available. State a concrete fit in the first sentence.
2. **Interest (Proof of Value):** Select 2-3 facts from the candidate profile that map to the required qualifications.
3. **Desire (The Why):** Explain fit through systems, tools, product context, or data/AI problems from the job description. Do not use generic motivation.
4. **Action (The Close):** Close professionally and briefly.

### CONTENT RULES
1. Truth only: Never invent company facts, candidate achievements, metrics, tools, awards, seniority, dates, or project scope.
2. Company and role targeting is mandatory when the job description provides them. Use the company name and role title naturally in the opening paragraph.
3. If the company cannot be identified, omit the company-name recipient line and avoid pretending to know the employer. If the role cannot be identified, infer the narrowest role family from the job description.
4. The candidate should sound like a strong final-year or new-grad technical candidate with hands-on experience, not a generic template.
5. Ban generic phrasing, including: "challenging opportunities", "keen interest", "robust technical foundations", "impactful projects", "drive innovation", "forward-thinking team", "proven track record", "unique ability", "cutting-edge technologies", "valuable asset", "thrive in collaborative environments", and "contribute effectively from day one".
6. Use plain, specific language. Prefer concrete verbs such as built, optimized, implemented, integrated, automated, evaluated, maintained, and shipped.
7. Keep the letter to 3-4 short paragraphs and roughly 250-340 words.
8. Do not repeat the resume. Pick the most relevant evidence for the target role.
9. If RecruitAssistant or RecruitAssistant.net is mentioned, describe it concretely as an end-to-end career preparation platform with only supported facts from the profile/docs/job context: job-specific CV and cover-letter generation, mock interviews, quizzes, speech-to-text transcription, evaluation, personalized feedback, analytics/progress tracking, React frontend, FastAPI backend, AI/ML modules, and PostgreSQL. Do not call it only an "AI-powered interview assistant".
10. Avoid exaggerated claims. Do not call a student/final-year project production-scale unless the profile explicitly supports that.

### LATEX ARCHITECTURE (PREMIUM)
1. **Document Class:** `\documentclass[11pt,a4paper]{article}`.
2. **Preamble:** 
   \usepackage{fontspec}
   \setmainfont{texgyreheros-regular.otf}[
     BoldFont=texgyreheros-bold.otf,
     ItalicFont=texgyreheros-italic.otf,
     BoldItalicFont=texgyreheros-bolditalic.otf
   ]
   \usepackage[english, turkish]{babel}
   \usepackage{parskip}
   \usepackage[hidelinks]{hyperref}
3. **Geometry:** `\usepackage[left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm]{geometry}`.
6. **Header:** Match the professional header style of the CV (Name, Email, etc.).
7. **Structure:** Include the exact date provided in the user's custom instructions, recipient info, salutation, body paragraphs, professional closing, and candidate name.
8. **Recipient Info:** Use only two recipient lines: the localized hiring-manager label and the actual target company name. Do not include a company address, address placeholder, street, city/state/ZIP placeholder, or `[Company Address]`.

### STRICT OUTPUT RULES
- NO MARKDOWN: Start exactly with `\documentclass` and end with `\end{document}`. No backticks.
- DATE RULE: Never output `[Date]`. Use the exact formatted date supplied in the user's custom instructions, for example `April 12, 2026`.
- COMPANY NAME RULE: You MUST extract the name of the company from the Target Job Description. NEVER output generic placeholders like `[Company Name]` or `Company Name`. Insert the actual target company's name in the recipient header. If the company cannot be identified, omit the company-name line entirely instead of using a placeholder.
- COMPANY ADDRESS RULE: Never output `[Company Address]` and never render any containing line/element for company address. The recipient block must contain only the localized hiring-manager label and the actual company name if known.
- ZERO PLACEHOLDER RULE: The final letter must be ready to submit. Never output bracket placeholders or generic template words such as `[Recipient]`, `[Hiring Manager]`, `[Company Name]`, `[Company Address]`, `[Date]`, or `Company Name`.
- BRACKET SAFETY: NEVER use `\\` followed immediately by a bracket `[` on the next line. This causes compilation errors. Use `\\[0pt]` or simply start a new paragraph.
- ESCAPE CHARACTERS: Ensure `# $ % & _ { } ~ ^ \` are escaped.
- Return ONLY the final LaTeX source code. No conversational preamble.
"""

# ══════════════════════════════════════════════
#  LLM GENERATION (STREAMING)
# ══════════════════════════════════════════════

def _normalise_output_language(output_language: Optional[str]) -> str:
    """Map UI/API language labels to the language names used in prompts."""
    language = (output_language or "English").strip().lower()
    if language in {"tr", "turkish", "turkce", "türkçe"} or language.startswith(("turk", "türk")):
        return "Turkish"
    return "English"


def _build_output_language_instruction(output_language: Optional[str], document_type: str) -> str:
    """Create explicit language instructions for user-facing generated content."""
    language = _normalise_output_language(output_language)
    babel_language = "turkish" if language == "Turkish" else "english"
    document_name = "cover letter" if document_type == "cover_letter" else "CV"

    common_rules = [
        f"Requested output language: {language}.",
        f"Write every user-facing part of the {document_name} in {language}.",
        "Do not translate names, company names, product names, URLs, email addresses, or programming/technology terms unless there is a standard localized form.",
        f"Add \\selectlanguage{{{babel_language}}} immediately after \\begin{{document}} so the LaTeX document uses the requested language.",
        "Keep LaTeX commands, package names, and environments in valid LaTeX syntax.",
    ]

    if language == "Turkish":
        if document_type == "cover_letter":
            language_rules = [
                "Use natural professional Turkish throughout the letter.",
                "Use `İşe Alım Yetkilisi` as the recipient/hiring-manager label. Never output `Hiring Manager` in Turkish output.",
                "Use Turkish greeting and closing text, for example `Sayın İşe Alım Yetkilisi,` and `Saygılarımla,` unless a more specific recipient is provided.",
                "Localize every address, location, recipient, salutation, and closing label into Turkish. Omit unknown address lines instead of using English labels or placeholders.",
                "Use the exact date supplied in the user's custom instructions; if it is supplied in Turkish, keep it in Turkish.",
            ]
        else:
            language_rules = [
                "Use Turkish section headings where those sections appear: ÖZET, YETENEKLER, DENEYİM, PROJELER, EĞİTİM.",
                "Use natural Turkish for summaries, bullets, dates, and section content while preserving factual details from the profile.",
            ]
    else:
        if document_type == "cover_letter":
            language_rules = [
                "Use natural professional English throughout the letter.",
                "Use `Hiring Manager` as the recipient/hiring-manager label.",
                "Use English greeting and closing text, for example `Dear Hiring Manager,` and `Sincerely,` unless a more specific recipient is provided.",
            ]
        else:
            language_rules = [
                "Use English section headings where those sections appear: SUMMARY, SKILLS, EXPERIENCE, PROJECTS, EDUCATION.",
                "Use natural English for summaries, bullets, dates, and section content while preserving factual details from the profile.",
            ]

    return "=== OUTPUT LANGUAGE (ABSOLUTE PRIORITY) ===\n" + "\n".join(common_rules + language_rules)


def _build_user_message(candidate_profile: dict, job_description: str, special_instructions: Optional[str] = None, prioritize: bool = False) -> str:
    """Format the user data into a structured prompt for the LLM."""
    parts = []
    
    if special_instructions:
        header = "=== ABSOLUTE PRIORITY: USER'S CUSTOM INSTRUCTIONS ===" if prioritize else "=== USER'S CUSTOM INSTRUCTIONS ==="
        parts.append(f"{header}\n{special_instructions}")
    
    parts.append("=== CANDIDATE PROFILE (JSON) ===\n" + json.dumps(candidate_profile, indent=2, ensure_ascii=False))
    parts.append(f"=== JOB DESCRIPTION ===\n{job_description}")
    
    return "\n\n".join(parts)


def _extract_company_name(job_description: str) -> Optional[str]:
    """Best-effort extraction of the target company from a job description."""
    if not job_description:
        return None

    patterns = [
        r"(?:Company|Employer|Organization|Organisation)\s*[:\-]\s*([A-Z][A-Za-z0-9&.,'’\- ]{1,80})",
        r"(?:About|Join|at|with|for)\s+([A-Z][A-Za-z0-9&.'’\-]+(?:\s+[A-Z][A-Za-z0-9&.'’\-]+){0,4})\b",
        r"\b([A-Z][A-Za-z0-9&.'’\-]+(?:\s+[A-Z][A-Za-z0-9&.'’\-]+){0,4})\s+(?:is hiring|is seeking|seeks|is looking for)\b",
    ]
    blocked = {
        "About", "Apply", "Company", "Employer", "Hiring Manager", "Job Description",
        "Location", "Organization", "Organisation", "Role", "Team", "The Company",
        "We", "Work", "Your"
    }

    for pattern in patterns:
        match = re.search(pattern, job_description)
        if not match:
            continue
        company = match.group(1).strip()
        company = re.split(r"[.;]\s+", company)[0].strip()
        company = re.split(r"\s+(?:is|are|seeks|seeking|looking|hiring|for|with)\b", company)[0].strip()
        company = re.sub(r"[\s,.;:|/\\]+$", "", company)
        if company and company not in blocked and len(company) <= 80:
            return company

    return None


def _strip_cover_letter_placeholders(latex_content: str, company_name: Optional[str]) -> str:
    """Remove unresolved cover-letter placeholders from generated LaTeX."""
    content = latex_content
    if company_name:
        content = re.sub(r"\[Company Name\]|\bCompany Name\b", company_name, content)
    else:
        content = re.sub(r"(?m)^.*(?:\[Company Name\]|\bCompany Name\b).*(?:\n|$)", "", content)

    placeholder_line_patterns = [
        r"\[Company Address\]",
        r"\bCompany Address\b",
        r"\[Date\]",
        r"\[Recipient(?: Name)?\]",
        r"\[Hiring Manager\]",
    ]
    for placeholder in placeholder_line_patterns:
        content = re.sub(rf"(?m)^.*{placeholder}.*(?:\n|$)", "", content)

    content = re.sub(r"\n{3,}", "\n\n", content)
    return content


def _localize_cover_letter_static_text(latex_content: str, output_language: Optional[str]) -> str:
    """Localize common static labels that the model may leave in English."""
    if _normalise_output_language(output_language) != "Turkish":
        return latex_content

    content = latex_content
    replacements = {
        r"\bDear Hiring Manager\b": "Sayın İşe Alım Yetkilisi",
        r"\bHiring Manager\b": "İşe Alım Yetkilisi",
        r"\bSincerely\b": "Saygılarımla",
        r"\bBest regards\b": "Saygılarımla",
        r"\bKind regards\b": "Saygılarımla",
        r"\bCompany Address\b": "Şirket Adresi",
        r"\bAddress\b": "Adres",
        r"\bLocation\b": "Konum",
        r"\bTurkey\b": "Türkiye",
        r"\bIstanbul\b": "İstanbul",
    }
    for pattern, replacement in replacements.items():
        content = re.sub(pattern, replacement, content)

    return content


def _sanitize_cover_letter_latex(latex_content: str) -> str:
    """Clean cover-letter-only LaTeX issues that commonly break compilation."""
    content = latex_content.strip()

    if content.startswith("```"):
        first_newline = content.find("\n")
        if first_newline != -1:
            content = content[first_newline:].strip()
        if content.endswith("```"):
            content = content[:-3].strip()

    match = re.search(r"(\\documentclass.*\\end\{document\})", content, re.DOTALL)
    if match:
        content = match.group(1).strip()

    cleaned_lines = []
    for line in content.splitlines():
        if re.match(r"^\s*\\?%", line):
            continue
        cleaned_lines.append(re.sub(r"(?<!\\)%.*$", "", line).rstrip())

    content = "\n".join(cleaned_lines)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()


def _normalize_resume_section_dividers(latex_content: str) -> str:
    """Keep resume divider rules visually attached to their section headings."""
    section_heading_pattern = re.compile(
        r"(\\section\*\{[^{}]+\})\s*"
        r"(?:\\vspace\{[^{}]+\}\s*)?"
        r"\\hrule\s*"
        r"(?:\\vspace\{[^{}]+\}\s*)?"
    )
    return section_heading_pattern.sub(
        lambda match: f"{match.group(1)}\\vspace{{-0.65em}}\n\\hrule\n\\vspace{{0.45em}}\n",
        latex_content,
    )


def generate_cv_latex_stream(
    candidate_profile: dict,
    job_description: str,
    special_instructions: Optional[str] = None,
    output_language: Optional[str] = None,
) -> Generator[str, None, None]:
    """Stream AI-generated CV LaTeX using a generator."""
    client = get_ai_client(provider="openai")
    model = get_model_name(tier="default", provider="openai")
    logger.info("Streaming CV LaTeX via %s", model)
    generation_instructions = "\n\n".join(
        part for part in [
            special_instructions,
            _build_output_language_instruction(output_language, "cv"),
        ] if part
    )
    
    response = client.chat.completions.create(
        model=model,
        temperature=0.3,
        messages=[
            {"role": "system", "content": CV_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(candidate_profile, job_description, generation_instructions, prioritize=True)},
        ],
        stream=True,
    )

    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def generate_cover_letter_latex_stream(
    candidate_profile: dict,
    job_description: str,
    special_instructions: Optional[str] = None,
    output_language: Optional[str] = None,
) -> Generator[str, None, None]:
    """Stream AI-generated Cover Letter LaTeX using a generator."""
    client = get_ai_client(provider="openai")
    model = get_model_name(tier="default", provider="openai")
    logger.info("Streaming Cover Letter LaTeX via %s", model)
    company_name = _extract_company_name(job_description)
    company_instruction = (
        f"=== TARGET COMPANY NAME ===\n{company_name}\nUse this exact company name in the recipient header."
        if company_name
        else "=== TARGET COMPANY NAME ===\nUNKNOWN\nOmit the company-name line in the recipient header. Never output Company Name."
    )
    
    cover_letter_instructions = "\n\n".join(
        part for part in [
            company_instruction,
            special_instructions,
            _build_output_language_instruction(output_language, "cover_letter"),
        ] if part
    )

    response = client.chat.completions.create(
        model=model,
        temperature=0.5,
        messages=[
            {"role": "system", "content": COVER_LETTER_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(candidate_profile, job_description, cover_letter_instructions, prioritize=True)},
        ],
        stream=True,
    )

    generated_latex = ""
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            generated_latex += delta

    sanitized_latex = _strip_cover_letter_placeholders(generated_latex, company_name)
    sanitized_latex = _localize_cover_letter_static_text(sanitized_latex, output_language)
    sanitized_latex = _sanitize_cover_letter_latex(sanitized_latex)
    yield sanitized_latex


# ══════════════════════════════════════════════
#  LATEX → PDF COMPILATION (TECTONIC)
# ══════════════════════════════════════════════

def _find_tectonic() -> Optional[str]:
    """Locate the tectonic binary. Checks common install paths on macOS."""
    # Check absolute paths first for reliability
    common_paths = [
        "/usr/local/bin/tectonic",
        "/opt/homebrew/bin/tectonic",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
            
    # Fallback to PATH
    return shutil.which("tectonic")


def _latex_uses_package(content: str, package_name: str) -> bool:
    return re.search(rf"\\usepackage(?:\[[^\]]*\])?\{{{re.escape(package_name)}\}}", content) is not None


def _ensure_latex_package(content: str, package_name: str) -> str:
    if _latex_uses_package(content, package_name):
        return content

    begin_document = r"\begin{document}"
    if begin_document not in content:
        return content

    return content.replace(begin_document, f"\\usepackage{{{package_name}}}\n{begin_document}", 1)


def _prepare_latex_for_compilation(latex_content: str) -> str:
    """Extract and clean model-generated LaTeX before handing it to Tectonic."""
    match = re.search(r"(\\documentclass.*\\end\{document\})", latex_content, re.DOTALL)
    if match:
        content = match.group(1).strip()
    else:
        content = latex_content.strip()
        if content.startswith("```"):
            first_newline = content.find("\n")
            if first_newline != -1:
                content = content[first_newline:].strip()
            if content.endswith("```"):
                content = content[:-3].strip()

    # Escape common unescaped special characters from prose and links.
    content = re.sub(r"(?<!\\)_", r"\_", content)
    content = re.sub(r"(?<!\\)&", r"\&", content)
    content = re.sub(r"(?<!\\)%", r"\%", content)

    # Preserve the value of hallucinated contact commands instead of leaving
    # behind unbalanced braces.
    content = re.sub(
        r"\\(?:email|phone|linkedin|location|github|address)\{([^{}]*)\}",
        r"\1",
        content,
    )
    content = re.sub(r"\\(?:email|phone|linkedin|location|github|address)\{?", " ", content)

    # Models sometimes emit the wrong capitalization for ragged2e's command.
    content = content.replace(r"\Justifying", r"\justifying")
    if r"\justifying" in content:
        content = _ensure_latex_package(content, "ragged2e")
    if re.search(r"\\(?:href|url)\{", content):
        content = _ensure_latex_package(content, "hyperref")

    # Fix potential "Missing number" issues in common spacing commands.
    content = re.sub(r"\\vspace\{[a-zA-Z\s]+\}", r"\\vspace{1em}", content)

    # Brackets after \\ are interpreted as optional spacing arguments.
    content = re.sub(r"\\\\\s*\n\s*\[", r"\\\\[0pt]\n[", content)
    content = _normalize_resume_section_dividers(content)

    return content


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
        return None

    tmp_dir = tempfile.mkdtemp(prefix="recruitassistant_latex_")
    tex_filename = f"{uuid.uuid4().hex}.tex"
    tex_path = os.path.join(tmp_dir, tex_filename)
    pdf_path = tex_path.replace(".tex", ".pdf")

    content = _prepare_latex_for_compilation(latex_content)
    
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
            # Log the content that failed for debugging
            fail_log_path = os.path.join(os.getcwd(), "last_failed_latex.tex")
            try:
                with open(fail_log_path, "w", encoding="utf-8") as f:
                    f.write(content)
                logger.info("Saved failing LaTeX to %s", fail_log_path)
            except:
                pass
            return None

        if not os.path.isfile(pdf_path):
            logger.error("PDF file was not generated at %s", pdf_path)
            # Try to find any PDF in the directory as fallback
            generated_pdfs = [f for f in os.listdir(tmp_dir) if f.endswith(".pdf")]
            if generated_pdfs:
                pdf_path = os.path.join(tmp_dir, generated_pdfs[0])
            else:
                return None

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        return base64.b64encode(pdf_bytes).decode("utf-8")

    except subprocess.TimeoutExpired:
        logger.error("Tectonic timed out after 120 seconds")
        return None
    except Exception as e:
        logger.error("LaTeX compilation error: %s", str(e))
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
