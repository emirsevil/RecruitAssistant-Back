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
from typing import Optional, Generator

from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────
# OpenAI client
# ──────────────────────────────────────────────
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

MODEL = "gpt-4o"  # Best quality for complex LaTeX generation


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

### STRICT OUTPUT RULES
- NO MARKDOWN: Do NOT wrap in ```latex ... ``` blocks or add conversational text. Start exactly with `\documentclass` and end with `\end{document}`.
- IF YOU START WITH ```latex OR ANY MARKDOWN, YOU HAVE FAILED. 
- NO HALLUCINATIONS: If the candidate didn't provide a PhD, they don't have one.
- ESCAPE CHARACTERS: Ensure `# $ % & _ { } ~ ^ \` are escaped.
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

### STRICT OUTPUT RULES
- NO MARKDOWN: Do NOT wrap in ```latex ... ``` blocks or add conversational text. No backticks. Start exactly with `\documentclass` and end with `\end{document}`.
- NO CONVIVIAL FILLER: Do not say "Certainly, here is your letter."
- Return ONLY the final LaTeX source code. No conversational filler or markdown fences.
"""


# ══════════════════════════════════════════════
#  LLM GENERATION (STREAMING)
# ══════════════════════════════════════════════

def _build_user_message(candidate_profile: dict, job_description: str) -> str:
    """Format the user data into a structured prompt for the LLM."""
    return (
        "=== CANDIDATE PROFILE (JSON) ===\n"
        f"{json.dumps(candidate_profile, indent=2, ensure_ascii=False)}\n\n"
        "=== JOB DESCRIPTION ===\n"
        f"{job_description}"
    )


def generate_cv_latex_stream(candidate_profile: dict, job_description: str) -> Generator[str, None, None]:
    """Stream OpenAI generated CV LaTeX using a generator."""
    logger.info("Streaming CV LaTeX via OpenAI (%s)", MODEL)

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.3,
        messages=[
            {"role": "system", "content": CV_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(candidate_profile, job_description)},
        ],
        stream=True,
    )

    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def generate_cover_letter_latex_stream(candidate_profile: dict, job_description: str) -> Generator[str, None, None]:
    """Stream OpenAI generated Cover Letter LaTeX using a generator."""
    logger.info("Streaming Cover Letter LaTeX via OpenAI (%s)", MODEL)

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.5,
        messages=[
            {"role": "system", "content": COVER_LETTER_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(candidate_profile, job_description)},
        ],
        stream=True,
    )

    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


# ══════════════════════════════════════════════
#  LATEX → PDF COMPILATION
# ══════════════════════════════════════════════

def _find_pdflatex() -> Optional[str]:
    """Locate the pdflatex binary. Checks common install paths on macOS."""
    path = shutil.which("pdflatex")
    if path:
        return path
    common_paths = [
        "/Library/TeX/texbin/pdflatex",
        "/usr/texbin/pdflatex",
        "/usr/local/texlive/2024/bin/universal-darwin/pdflatex",
        "/usr/local/texlive/2025/bin/universal-darwin/pdflatex",
        "/usr/local/texlive/2026/bin/universal-darwin/pdflatex",
    ]
    for p in common_paths:
        if os.path.isfile(p):
            return p
    return None


def compile_latex_to_pdf(latex_content: str) -> Optional[str]:
    """
    Compile a LaTeX string to PDF using pdflatex.

    Returns the PDF as a base64-encoded string, or None if compilation fails.
    All temporary files (.tex, .aux, .log, .pdf) are cleaned up after use.
    """
    pdflatex_bin = _find_pdflatex()
    if not pdflatex_bin:
        logger.warning(
            "pdflatex not found on this system. "
            "Install TeX Live (e.g. `brew install --cask mactex-no-gui`) "
            "or use the provided Dockerfile for deployment."
        )
        return None

    tmp_dir = tempfile.mkdtemp(prefix="recruitassistant_latex_")
    tex_filename = f"{uuid.uuid4().hex}.tex"
    tex_path = os.path.join(tmp_dir, tex_filename)
    pdf_path = tex_path.replace(".tex", ".pdf")

    # Sanitize: Strip any markdown fences if present
    content = latex_content.strip()
    if content.startswith("```"):
        # Find the end of the first line (e.g., ```latex)
        first_newline = content.find("\n")
        if first_newline != -1:
            content = content[first_newline:].strip()
        
        # Strip the trailing fences
        if content.endswith("```"):
            content = content[:-3].strip()
    
    try:
        with open(tex_path, "w", encoding="utf-8") as f:
            f.write(content)

        for pass_num in range(2):
            result = subprocess.run(
                [
                    pdflatex_bin,
                    "-interaction=nonstopmode",
                    "-halt-on-error",
                    "-output-directory", tmp_dir,
                    tex_path,
                ],
                capture_output=True,
                text=True,
                timeout=60,
                cwd=tmp_dir,
            )

            if result.returncode != 0 and pass_num == 0:
                logger.error(
                    "pdflatex failed (pass %d):\nSTDOUT: %s\nSTDERR: %s",
                    pass_num + 1,
                    result.stdout[-2000:] if result.stdout else "",
                    result.stderr[-2000:] if result.stderr else "",
                )
                return None

        if not os.path.isfile(pdf_path):
            logger.error("PDF file was not generated at %s", pdf_path)
            return None

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        return base64.b64encode(pdf_bytes).decode("utf-8")

    except subprocess.TimeoutExpired:
        logger.error("pdflatex timed out after 60 seconds")
        return None
    except Exception as e:
        logger.error("LaTeX compilation error: %s", str(e))
        return None
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
