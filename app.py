"""Entry point: `streamlit run app.py`. Defines the sidebar navigation; each page lives in its own file."""
import streamlit as st

st.set_page_config(page_title="Ops Control Tower", layout="wide")

pages = [
    st.Page("home.py", title="Home", icon=":material/home:", default=True),
    st.Page("pages/1_Board_Readiness.py", title="Board Readiness", icon=":material/gavel:",
            url_path="board-readiness"),
    st.Page("pages/2_CEO_Week.py", title="CEO Week", icon=":material/calendar_month:", url_path="ceo-week"),
    st.Page("pages/3_Office_and_Events.py", title="Office & Events", icon=":material/apartment:",
            url_path="office-and-events"),
    st.Page("pages/4_Automation_Backlog.py", title="Automation Backlog", icon=":material/bolt:",
            url_path="automation-backlog"),
    st.Page("pages/5_About.py", title="About this demo", icon=":material/info:", url_path="about"),
]
st.navigation(pages).run()
