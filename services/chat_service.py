"""Question answering that is limited to the engagement's numbered facts."""
from agents.qa_checks import ID_RE, check_output, numbers_in
from services.knowledge_base import search_knowledge
from services.llm_service import LLMError, LLMService

SECTIONS = ["data_quality", "statements", "ratios", "planning", "exceptions", "controls"]

RULES = (
    "You are the AI Audit Assistant for an audit team in Pakistan. Answer the question using ONLY the facts "
    "and knowledge-base passages below.\n"
    "1. Never calculate, estimate, convert or round numbers. Copy numbers exactly as written. If the question "
    "needs a figure that is not in the facts, say the app does not have that figure.\n"
    "2. Cite the fact IDs you used in square brackets, like [RT-2] or [EX-001].\n"
    "3. If the facts do not contain the answer, say so plainly. Do not guess and do not use outside knowledge.\n"
    "4. An exception is something to investigate, never proof of fraud.\n"
    "5. Keep answers short and in plain words (under 150 words) unless asked for more.\n"
    "6. You support a qualified auditor and do not replace one."
)


def answer_question(pack, question: str, history: list) -> dict:
    facts = pack.text(SECTIONS)
    if not facts.strip():
        raise LLMError("There is no saved data for this engagement yet.")

    chunks = search_knowledge(question, k=3)
    kb_text = "\n".join(
        f"KB-{i}: [{c.source} > {c.location}] {' '.join(c.text.split())[:600]}"
        for i, c in enumerate(chunks, start=1)
    ) or "No matching passages were found in the knowledge base."

    system = f"{RULES}\n\nFACTS:\n{facts}\n\nKNOWLEDGE BASE PASSAGES:\n{kb_text}"
    messages = [{"role": "system", "content": system}]
    for turn in history[-4:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": question})

    answer = LLMService().chat(messages, temperature=0.1).strip()
    if not answer:
        raise LLMError("The AI returned an empty answer. Please try again.")

    known_ids = set(ID_RE.findall(facts + "\n" + kb_text))
    cited = sorted(set(ID_RE.findall(answer)))
    issues = check_output("AI Audit Assistant", {"answer": answer, "sources_used": cited},
                          numbers_in(facts + "\n" + kb_text), known_ids)
    issues = [i for i in issues if i["type"] != "No sources"]
    return {"answer": answer, "issues": issues}
