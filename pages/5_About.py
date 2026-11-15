import streamlit as st

from utils import ui

# Replace these with your real links
LINKEDIN_URL = "https://www.linkedin.com/in/your-profile"
CV_URL = "https://example.com/your-cv.pdf"

ui.setup("About this demo")
ui.header("About this demo", "Why this exists and how it was built")

st.markdown(
    """<div class="hero">
         <div class="meta">Built by</div>
         <div class="hero-value" style="font-size:clamp(1.8rem, 5vw, 2.6rem)">Hariharan "Jay" Jayaprakasam</div>
         <div class="hero-sub">A working prototype of the control tower a Business Operations Coordinator
         would run for a CEO's office: Board readiness, the CEO's week, office &amp; events, and the
         automation backlog in one place.</div>
       </div>""",
    unsafe_allow_html=True,
)
with st.container(horizontal=True):
    st.link_button("LinkedIn", LINKEDIN_URL, icon=":material/person:", type="primary")
    st.link_button("Download CV", CV_URL, icon=":material/description:")

st.header("30 / 60 / 90-day plan")
plan = [
    ("First 30 days", "Learn", ["Learn how the CEO's office, ExCo and Board processes really run",
                                "Stand up the trackers: Board pack, actions, diary, office and events"]),
    ("By day 60", "Automate", ["Pick the top 3 manual processes by hours spent",
                               "Automate them and pilot with the people who do them today"]),
    ("By day 90", "Prove", ["Report hours saved against the baseline",
                            "Refine what's working, retire what isn't, and set the next backlog"]),
]
cols = st.columns(3)
for col, (when, theme, points) in zip(cols, plan):
    with col, st.container(border=True):
        st.markdown(f"<span class='meta'>{when}</span><p class='item-title'>{theme}</p>"
                    + "".join(f"<p class='item-detail'>• {p}</p>" for p in points),
                    unsafe_allow_html=True)

st.header("Tech stack")
st.write("Python, Streamlit, Groq-hosted LLM; designed to sit on Microsoft 365.")
st.write("AI features run on an open-source LLM via Groq for this demo; in production they would use "
         "Napier's approved AI tools (e.g. Claude, Copilot) so data stays within approved systems.")
st.caption("Demo · illustrative data only. All organisations, suppliers and figures are fictional.")
