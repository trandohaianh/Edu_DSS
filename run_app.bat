@echo off
cd /d %~dp0
streamlit run run_dss.py --server.port 8502
