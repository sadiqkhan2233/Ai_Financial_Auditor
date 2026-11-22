import streamlit as st

from agents.facts import build_fact_pack
from services.chat_service import answer_question
from services.llm_service import LLMError
from ui.agent_state import current_answers

SUGGESTIONS = [
    "What are the biggest risks in this engagement?",
    "Which exceptions should be investigated first, and why?",
    "How is the company's liquidity?",
    "Which accounting guidance is relevant to inventory?",
]


def _show(message):
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
        for issue in message.get("issues", []):
            st.warning(f"Automatic check ({issue['type']}): {issue['detail']}")


def _read_question(engagement_id):
    try:
        return st.chat_input("Ask a question about this engagement", key=f"chat_{engagement_id}")
    except Exception:  # fallback for older Streamlit versions
        text = st.text_input("Your question", key=f"chat_text_{engagement_id}")
        return text if st.button("Ask", key=f"chat_ask_{engagement_id}") and text else None


def show_chat_panel(engagement_id):
    history = st.session_state.setdefault("chat_history", {}).setdefault(engagement_id, [])

    st.write("Ask questions about this engagement. Answers use only the numbered facts the app calculated and "
             "the knowledge-base notes. The app checks each answer for numbers or sources that do not exist.")
    clicked = None
    columns = st.columns(2)
    for index, text in enumerate(SUGGESTIONS):
        if columns[index % 2].button(text, key=f"suggest_{engagement_id}_{index}"):
            clicked = text
    if history and st.button("Clear conversation", key=f"clear_{engagement_id}"):
        st.session_state["chat_history"][engagement_id] = []
        st.rerun()

    for message in history:
        _show(message)

    question = _read_question(engagement_id) or clicked
    if not question:
        return

    user_message = {"role": "user", "content": question}
    _show(user_message)
    with st.chat_message("assistant"):
        with st.spinner("Looking at the facts..."):
            try:
                pack = build_fact_pack(engagement_id, current_answers(engagement_id))
                result = answer_question(pack, question, history)
            except LLMError as err:
                st.error(str(err))
                return
            except Exception as err:
                st.error(f"Something went wrong: {err}")
                return
        st.markdown(result["answer"])
        for issue in result["issues"]:
            st.warning(f"Automatic check ({issue['type']}): {issue['detail']}")
    history.append(user_message)
    history.append({"role": "assistant", "content": result["answer"], "issues": result["issues"]})
