@echo off
cd /d C:\responder_intact_stability_tool
call venv/Scripts/activate
streamlit run app.py
pause