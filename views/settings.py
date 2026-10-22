"""Settings page: change how much each Layer 2 dimension counts toward the score."""

import streamlit as st

from scoring.tier import load_rubric, reset_weights, save_weights

st.title("⚙️ Rubric weights")
st.caption(
    "How much each teaching-quality dimension counts toward the Layer 2 score. "
    "Weights must add up to 100. Layer 1 must-haves and the tier caps are not affected."
)

rubric = load_rubric()
defaults = {d["id"]: d["weight"] for d in load_rubric(custom_weights=False)["dimensions"]}

# Bumping the version gives the inputs new keys, so "Reset" redraws them with the defaults.
version = st.session_state.setdefault("weights_version", 0)
weights = {}
for dim in rubric["dimensions"]:
    name_col, input_col = st.columns([3, 1])
    with name_col:
        st.markdown(f"**{dim['name']}**")
        st.caption(f"5 = {dim['anchors'][5]}")
    weights[dim["id"]] = input_col.number_input(
        dim["name"], min_value=0, max_value=100, step=1,
        value=dim["weight"], key=f"w_{dim['id']}_{version}", label_visibility="collapsed",
        help=f"Default: {defaults[dim['id']]}",
    )

total = sum(weights.values())
if total == 100:
    st.success("Total: 100")
else:
    st.error(f"Total: {total} (must be 100, {'remove' if total > 100 else 'add'} {abs(total - 100)})")

save_col, reset_col, _ = st.columns([1, 1, 3])
if save_col.button("Save weights", type="primary", disabled=total != 100):
    save_weights(weights)
    st.toast("Weights saved. New scores will use them.")
if reset_col.button("Reset to defaults", disabled=weights == defaults):
    reset_weights()
    st.session_state.weights_version += 1
    st.rerun()

