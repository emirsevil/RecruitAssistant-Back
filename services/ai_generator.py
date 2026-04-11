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
2. **Action Verbs:** Use powerful verbs (e.g., Orchestrated, Spearheaded, Engineered, Optimized).
3. **Truth Only:** Never add roles, dates, or skills not explicitly given in the JSON profile.

- Preamble: Strictly start EXACTLY with:
  \documentclass[11pt,a4paper]{article}
  \usepackage{fontspec}
  \setmainfont{texgyreheros-regular.otf}[
    BoldFont=texgyreheros-bold.otf,
    ItalicFont=texgyreheros-italic.otf,
    BoldItalicFont=texgyreheros-bolditalic.otf
  ]
  \usepackage[english, turkish]{babel}
  \usepackage[margin=1.25cm]{geometry}
- Contact Info: Do NOT use custom commands like `\email{}`. Use standard text.
- ESCAPE CHARACTERS: Ensure `# $ % & _ { } ~ ^ \` are escaped.
- ABSOLUTE PRIORITY: USER'S CUSTOM INSTRUCTIONS take precedence.
- NO HALLUCINATIONS: If the candidate didn't provide a PhD, they don't have one.
- Return ONLY raw LaTeX source. No conversational preamble. No preamble text.
"""

COVER_LETTER_SYSTEM_PROMPT = r"""You are a High-Stakes Career Coach and Persuasive Writer. 
Your task is to write a compelling, tailored Cover Letter in LaTeX that bridge the gap between the Candidate's profile and the Employer's needs.

### STRATEGY: THE AIDA MODEL
1. **Attention (The Hook):** Open with a strong, personalized statement about why the candidate is excited about this specific company and role.
2. **Interest (Proof of Value):** Select 1-2 key achievements from the candidate's profile that directly map to the "Required Qualifications".
3. **Desire (The Why):** Explain why the candidate is the solution to the company's specific pain points.
4. **Action (The Close):** A professional call to action, expressing readiness for an interview.

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
3. **Geometry:** `\usepackage[left=2.5cm,right=2.5cm,top=2.5cm,bottom=2.5cm]{geometry}`.
6. **Header:** Match the professional header style of the CV (Name, Email, etc.).
7. **Structure:** Include [Date], [Recipient/Company Info], [Salutation], [Body Paragraphs], [Professional Closing], and [Candidate Name].

### STRICT OUTPUT RULES
- NO MARKDOWN: Start exactly with `\documentclass` and end with `\end{document}`. No backticks.
- BRACKET SAFETY: NEVER use `\\` followed immediately by a bracket `[` on the next line (e.g., `\\ \n [Date]`). This causes compilation errors. Use `\\[0pt]` or simply start a new paragraph.
- ESCAPE CHARACTERS: Ensure `# $ % & _ { } ~ ^ \` are escaped.
- Return ONLY the final LaTeX source code. No conversational preamble.
"""

# ══════════════════════════════════════════════
#  LLM GENERATION (STREAMING)
# ══════════════════════════════════════════════

def _build_user_message(candidate_profile: dict, job_description: str, special_instructions: Optional[str] = None, prioritize: bool = False) -> str:
    """Format the user data into a structured prompt for the LLM."""
    parts = []
    
    if special_instructions:
        header = "=== ABSOLUTE PRIORITY: USER'S CUSTOM INSTRUCTIONS ===" if prioritize else "=== USER'S CUSTOM INSTRUCTIONS ==="
        parts.append(f"{header}\n{special_instructions}")
    
    parts.append("=== CANDIDATE PROFILE (JSON) ===\n" + json.dumps(candidate_profile, indent=2, ensure_ascii=False))
    parts.append(f"=== JOB DESCRIPTION ===\n{job_description}")
    
    return "\n\n".join(parts)


def generate_cv_latex_stream(candidate_profile: dict, job_description: str, special_instructions: Optional[str] = None) -> Generator[str, None, None]:
    """Stream OpenAI generated CV LaTeX using a generator."""
    logger.info("Streaming CV LaTeX via OpenAI (%s)", MODEL)

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.3,
        messages=[
            {"role": "system", "content": CV_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(candidate_profile, job_description, special_instructions, prioritize=True)},
        ],
        stream=True,
    )

    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def generate_cover_letter_latex_stream(candidate_profile: dict, job_description: str, special_instructions: Optional[str] = None) -> Generator[str, None, None]:
    """Stream OpenAI generated Cover Letter LaTeX using a generator."""
    logger.info("Streaming Cover Letter LaTeX via OpenAI (%s)", MODEL)

    response = client.chat.completions.create(
        model=MODEL,
        temperature=0.5,
        messages=[
            {"role": "system", "content": COVER_LETTER_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(candidate_profile, job_description, special_instructions)},
        ],
        stream=True,
    )

    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


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

    # Robust Extraction: Use regex to capture strictly between \documentclass and \end{document}
    import re
    match = re.search(r"(\\documentclass.*\\end\{document\})", latex_content, re.DOTALL)
    if match:
        content = match.group(1).strip()
    else:
        # Fallback to stripping markdown fences if regex fails
        content = latex_content.strip()
        if content.startswith("```"):
            first_newline = content.find("\n")
            if first_newline != -1:
                content = content[first_newline:].strip()
            if content.endswith("```"):
                content = content[:-3].strip()

    # Character Scrubber: Escape problematic characters that often fail compilation
    # 1. Escape basic characters if not already escaped
    content = re.sub(r"(?<!\\)_", r"\_", content)
    content = re.sub(r"(?<!\\)&", r"\&", content)
    content = re.sub(r"(?<!\\)%", r"\%", content)
    
    # 2. Strip common hallucinated commands that cause "Undefined control sequence"
    content = re.sub(r"\\email\{", r" ", content)
    content = re.sub(r"\\phone\{", r" ", content)
    content = re.sub(r"\\linkedin\{", r" ", content)
    content = re.sub(r"\\location\{", r" ", content)
    content = re.sub(r"\\github\{", r" ", content)
    content = re.sub(r"\\address\{", r" ", content)
    
    # 3. Fix potential "Missing number" issues in common spacing commands
    content = re.sub(r"\\vspace\{[a-zA-Z\s]+\}", r"\\vspace{1em}", content)
    
    # 4. FIX: Brackets after \\ are misinterpreted as spacing arguments
    # (e.g. \\ \n [Date] -> LaTeX thinks [Date] is a dimension)
    content = re.sub(r"\\\\\s*\n\s*\[", r"\\\\[0pt]\n[", content)
    
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
