"""Gemini-powered structured resume extractor with strict validation and zero-hallucination rules."""

import json
import logging
from typing import Any

from pydantic import ValidationError

from backend.core.config import get_settings
from backend.ingestion.schemas import StructuredResumeExtraction

logger = logging.getLogger("job_intelligence.extractor")


class ResumeExtractionError(Exception):
    """Raised when structured resume extraction fails."""

    pass


EXTRACTION_SYSTEM_INSTRUCTION = """
You are an expert, deterministic resume parsing engine for an automated Job Intelligence Platform.
Your ONLY responsibility is to extract explicit, verifiable information from the candidate's resume text.

STRICT CONTRACT RULES:
1. NEVER INVENT, ASSUME, OR HALLUCINATE.
2. Only include skills, tools, companies, degrees, or certifications that are EXPLICITLY written in the text.
3. If a field or category is not mentioned (e.g. no Cloud tools, no Internships, no Certifications), you MUST return an empty list [] or null.
4. Normalize skill names to standard capitalization (e.g. "Python", "FastAPI", "PostgreSQL", "Docker").
5. Seniority must be classified strictly based on stated graduation date and years of full-time experience (e.g. "Entry-Level (0-2 years)", "Intern", "Mid-Level (3-5 years)").
6. Output MUST strictly adhere to the provided JSON schema. Do NOT include markdown code fences (```json) or conversational text.
"""

EXTRACTION_PROMPT_TEMPLATE = """
Parse the following resume text and return structured JSON matching the schema.

--- RESUME TEXT START ---
{resume_text}
--- RESUME TEXT END ---
"""


class GeminiResumeExtractor:
    """Extracts structured profiles from resume text using Google Gemini API."""

    def __init__(self, api_key: str | None = None, model_name: str = "gemini-1.5-flash") -> None:
        self.settings = get_settings()
        self.api_key = api_key or self.settings.GEMINI_API_KEY
        self.model_name = model_name

    def extract(self, cleaned_text: str) -> StructuredResumeExtraction:
        """Execute structured extraction on cleaned resume text.

        Args:
            cleaned_text: Cleaned text extracted from PDF or DOCX

        Returns:
            StructuredResumeExtraction validated Pydantic model

        Raises:
            ResumeExtractionError: If API call fails, output is unparseable, or schema validation fails
        """
        if not cleaned_text or not cleaned_text.strip():
            raise ResumeExtractionError("Cannot extract from empty resume text.")

        if not self.api_key or self.api_key == "your_gemini_api_key_here":
            logger.warning("GEMINI_API_KEY is not configured. Running deterministic rule-based extractor.")
            return self._fallback_deterministic_extract(cleaned_text)

        try:
            import google.generativeai as genai

            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel(
                model_name=self.model_name,
                system_instruction=EXTRACTION_SYSTEM_INSTRUCTION,
                generation_config={
                    "response_mime_type": "application/json",
                    "temperature": 0.0,
                },
            )

            prompt = EXTRACTION_PROMPT_TEMPLATE.format(resume_text=cleaned_text)
            response = model.generate_content(prompt)

            if not response or not response.text:
                raise ResumeExtractionError("Empty response received from Gemini API.")

            raw_json_str = response.text.strip()
            # Remove any stray code fences if model output them
            if raw_json_str.startswith("```"):
                raw_json_str = raw_json_str.strip("`")
                if raw_json_str.startswith("json"):
                    raw_json_str = raw_json_str[4:].strip()

            return self.validate_extraction_json(raw_json_str)

        except ResumeExtractionError:
            raise
        except Exception as e:
            logger.error("Gemini API extraction failed: %s", e)
            raise ResumeExtractionError(f"Gemini API extraction failed: {e}") from e

    @staticmethod
    def validate_extraction_json(json_str_or_dict: str | dict[str, Any]) -> StructuredResumeExtraction:
        """Validate JSON text or dict against the strict Pydantic schema."""
        try:
            if isinstance(json_str_or_dict, str):
                parsed = json.loads(json_str_or_dict)
            else:
                parsed = json_str_or_dict

            return StructuredResumeExtraction.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as e:
            raise ResumeExtractionError(f"Schema validation failed for extracted resume data: {e}") from e

    @staticmethod
    def _fallback_deterministic_extract(text: str) -> StructuredResumeExtraction:
        """Deterministic extractor used when Gemini API key is not provided (offline/dev)."""
        import re

        lower_text = text.lower()

        # Extract explicit programming languages if mentioned
        known_langs = ["python", "javascript", "typescript", "java", "c++", "c#", "go", "rust", "sql", "html", "css"]
        found_langs = [lang for lang in known_langs if re.search(rf"\b{re.escape(lang)}\b", lower_text)]

        # Extract frameworks
        known_frameworks = ["fastapi", "django", "flask", "react", "express", "spring boot", "next.js", "vue"]
        found_frameworks = [f for f in known_frameworks if re.search(rf"\b{re.escape(f)}\b", lower_text)]

        # Extract databases
        known_dbs = ["postgresql", "postgres", "mysql", "mongodb", "sqlite", "redis"]
        found_dbs = [db for db in known_dbs if re.search(rf"\b{re.escape(db)}\b", lower_text)]

        # Extract cloud/devops
        known_devops = ["docker", "kubernetes", "git", "github actions", "aws", "gcp", "azure", "linux"]
        found_devops = [tool for tool in known_devops if re.search(rf"\b{re.escape(tool)}\b", lower_text)]

        # Find degree if mentioned
        degree = None
        if "bachelor" in lower_text or "b.tech" in lower_text or "b.e." in lower_text or "bs" in lower_text:
            degree = "Bachelor of Technology / Science"
        elif "master" in lower_text or "m.tech" in lower_text or "ms" in lower_text:
            degree = "Master of Technology / Science"

        # Find graduation year if explicitly stated 2018-2028
        year_match = re.search(r"\b(20[12][0-9])\b", text)
        grad_year = int(year_match.group(1)) if year_match else None

        return StructuredResumeExtraction(
            degree=degree,
            graduation_year=grad_year,
            skills={
                "programming_languages": [lang.capitalize() for lang in found_langs],
                "frameworks": [f.capitalize() for f in found_frameworks],
                "libraries": [],

                "databases": [d.capitalize() for d in found_dbs],
                "cloud": [t.upper() for t in found_devops if t in ["aws", "gcp", "azure"]],
                "ai_ml": [],
                "genai_llm": [],
                "backend": [f.capitalize() for f in found_frameworks if f in ["fastapi", "django", "flask", "express"]],
                "frontend": [f.capitalize() for f in found_frameworks if f in ["react", "vue", "next.js"]],
                "devops": [t.capitalize() for t in found_devops if t in ["docker", "kubernetes", "linux", "git"]],
                "tools": ["Git"] if "git" in lower_text else [],
                "apis": ["REST"] if "rest" in lower_text or "api" in lower_text else [],
            },
            likely_target_roles=["Junior Backend Engineer", "Software Engineer (0-2 YOE)"],
            seniority="Entry-Level (0-2 years)",
        )
