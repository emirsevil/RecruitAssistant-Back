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

CV_SYSTEM_PROMPT = r"""You are an elite Career Strategy Expert, ATS Optimizer, and Harvard resume formatting specialist.
Your task is to generate a world-class, single-page (extend to two pages ONLY if experience >10 years) resume in LaTeX format that strictly follows the Harvard Resume Format.

### PHASE 1: STRATEGIC AUDIT
1. **Keyword Analysis:** Identify the 'Must-Have' technologies and interpersonal skill signals in the Job Description.
2. **Mirroring:** Rephrase the Candidate's existing accomplishments to use the EXACT terminology found in the JD (without fabricating facts).
3. **Hierarchy:** Prioritize the 'Skills' and 'Experience' that most directly solve the problems mentioned in the JD.

### PHASE 2: CONTENT ENGINEERING
1. **The Google XYZ Formula:** Every bullet point must follow: "Accomplished [X] as measured by [Y], by doing [Z]". 
2. **Action Verbs:** Use powerful verbs (e.g., Orchestrated, Spearheaded, Engineered, Optimized).
3. **Truth Only:** Never add roles, dates, or skills not explicitly given in the JSON profile.

### PHASE 3: STRICT HARVARD RESUME FORMAT
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
- The document body must be written with simple LaTeX primitives only: \begin{center}, \textbf{}, \textit{}, \hfill, \section*{}, \hrule, \begin{itemize}.
- Contact Info: Do NOT use custom commands like `\email{}`. Use standard text.
- Header:
  1. Full name centered, uppercase, large, bold.
  2. Contact line centered directly below the name.
  3. Separate email, phone, location, LinkedIn, and GitHub/portfolio URL with ` | ` on one line.
  4. Include LinkedIn and GitHub/portfolio only when provided in the JSON profile.
- Section Headings:
  1. Left-aligned, bold, uppercase.
  2. Immediately followed by a solid black horizontal rule.
  3. Use compact spacing before and after each section.
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
7. **Structure:** Include the exact date provided in the user's custom instructions, recipient info, salutation, body paragraphs, professional closing, and candidate name.
8. **Recipient Info:** Use only two recipient lines: `Hiring Manager` and the actual target company name. Do not include a company address, address placeholder, street, city/state/ZIP placeholder, or `[Company Address]`.

### STRICT OUTPUT RULES
- NO MARKDOWN: Start exactly with `\documentclass` and end with `\end{document}`. No backticks.
- DATE RULE: Never output `[Date]`. Use the exact formatted date supplied in the user's custom instructions, for example `April 12, 2026`.
- COMPANY NAME RULE: You MUST extract the name of the company from the Target Job Description. NEVER output generic placeholders like `[Company Name]` or `Company Name`. Insert the actual target company's name in the recipient header. If the company cannot be identified, omit the company-name line entirely instead of using a placeholder.
- COMPANY ADDRESS RULE: Never output `[Company Address]` and never render any containing line/element for company address. The recipient block must contain only `Hiring Manager` and the actual company name if known.
- ZERO PLACEHOLDER RULE: The final letter must be ready to submit. Never output bracket placeholders or generic template words such as `[Recipient]`, `[Hiring Manager]`, `[Company Name]`, `[Company Address]`, `[Date]`, or `Company Name`.
- BRACKET SAFETY: NEVER use `\\` followed immediately by a bracket `[` on the next line. This causes compilation errors. Use `\\[0pt]` or simply start a new paragraph.
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
        r"\[Date\]",
        r"\[Recipient(?: Name)?\]",
        r"\[Hiring Manager\]",
    ]
    for placeholder in placeholder_line_patterns:
        content = re.sub(rf"(?m)^.*{placeholder}.*(?:\n|$)", "", content)

    content = re.sub(r"\n{3,}", "\n\n", content)
    return content


def generate_cv_latex_stream(candidate_profile: dict, job_description: str, special_instructions: Optional[str] = None, language: str = "en") -> Generator[str, None, None]:
    """Stream AI-generated CV LaTeX using a generator."""
    client = get_ai_client()
    model = get_model_name(tier="default")
    logger.info("Streaming CV LaTeX via %s", model)

    lang_instruction = f"Output Language: {language.upper()}. Ensure the entire CV is written strictly in {language.upper()}."
    
    response = client.chat.completions.create(
        model=model,
        temperature=0.3,
        messages=[
            {"role": "system", "content": CV_SYSTEM_PROMPT + "\n\n" + lang_instruction},
            {"role": "user", "content": _build_user_message(candidate_profile, job_description, special_instructions, prioritize=True)},
        ],
        stream=True,
    )

    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            yield delta


def generate_cover_letter_latex_stream(candidate_profile: dict, job_description: str, special_instructions: Optional[str] = None, language: str = "en") -> Generator[str, None, None]:
    """Stream AI-generated Cover Letter LaTeX using a generator."""
    client = get_ai_client()
    model = get_model_name(tier="default")
    logger.info("Streaming Cover Letter LaTeX via %s", model)
    company_name = _extract_company_name(job_description)
    company_instruction = (
        f"=== TARGET COMPANY NAME ===\n{company_name}\nUse this exact company name in the recipient header."
        if company_name
        else "=== TARGET COMPANY NAME ===\nUNKNOWN\nOmit the company-name line in the recipient header. Never output Company Name."
    )
    
    lang_instruction = f"Output Language: {language.upper()}. Ensure the entire cover letter is written strictly in {language.upper()}."
    
    cover_letter_instructions = "\n\n".join(
        part for part in [company_instruction, lang_instruction, special_instructions] if part
    )

    response = client.chat.completions.create(
        model=model,
        temperature=0.5,
        messages=[
            {"role": "system", "content": COVER_LETTER_SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_message(candidate_profile, job_description, cover_letter_instructions)},
        ],
        stream=True,
    )

    generated_latex = ""
    for chunk in response:
        delta = chunk.choices[0].delta.content
        if delta:
            generated_latex += delta

    sanitized_latex = _strip_cover_letter_placeholders(generated_latex, company_name)
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
