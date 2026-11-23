import streamlit as st


def choose(label, labels_by_id: dict, key=None, index=0):
    """A dropdown that shows text and returns the matching ID number."""
    ids = list(labels_by_id)
    seen, texts = {}, []
    for item_id in ids:
        text = str(labels_by_id[item_id])
        seen[text] = seen.get(text, 0) + 1
        texts.append(text if seen[text] == 1 else f"{text} ({seen[text]})")
    pick = st.selectbox(label, texts, index=min(index, len(texts) - 1), key=key)
    return ids[texts.index(pick)]
