import hashlib, io, re

SKILLS = ["Python", "FastAPI", "Django", "Flask", "PostgreSQL", "SQL", "MySQL", "MongoDB", "Docker",
          "Kubernetes", "AWS", "GCP", "Azure", "TensorFlow", "PyTorch", "Machine Learning", "Deep Learning",
          "NLP", "React", "TypeScript", "JavaScript", "Java", "C++", "Git", "Pandas", "NumPy", "scikit-learn",
          "REST", "Redis", "Linux"]
ROLES = {"AI Engineer": ["machine learning", "deep learning", "nlp", "tensorflow", "pytorch"],
         "Backend Developer": ["fastapi", "django", "flask", "rest", "postgresql"],
         "Python Developer": ["python"]}


def sha256(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def extract_text(filename: str, data: bytes) -> str:
    name = filename.lower()
    if name.endswith(".pdf"):
        from pypdf import PdfReader
        return "\n".join(p.extract_text() or "" for p in PdfReader(io.BytesIO(data)).pages)
    if name.endswith(".docx"):
        from docx import Document
        return "\n".join(p.text for p in Document(io.BytesIO(data)).paragraphs)
    raise ValueError("Unsupported file type")


def build_profile(text: str) -> dict:
    """Deterministic extraction only: a skill is reported only if literally present in the resume."""
    low = text.lower()
    skills = [s for s in SKILLS if re.search(r"(?<![\w+])" + re.escape(s.lower()) + r"(?![\w])", low)]
    roles = [r for r, kw in ROLES.items() if any(k in low for k in kw)]
    return {"target_roles": roles, "skills": skills, "seniority": "unknown",
            "projects": [], "education": [], "experience": [], "extraction": "deterministic"}
