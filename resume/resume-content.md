# ABIRAMI B
7708872650 | abiramib20.ai@gmail.com | linkedin.com/in/abirami-b-15a042213

## Professional Summary

Generative AI Developer with 1.10 years of experience building production-grade AI systems, specializing in RAG-based chatbots, LLM orchestration, and AI-driven analytics platforms. Proficient in Python, FastAPI, LangChain, vector databases, and scalable backend architectures. Experienced in translating business requirements into robust AI solutions using modern LLMs and production-grade AI workflows.

## Technical Skills

- **Programming:** Python
- **Machine Learning:** Supervised & Unsupervised Learning, Predictive Modeling, Classification, Clustering
- **Generative AI & NLP:** Large Language Models (LLMs), Retrieval-Augmented Generation (RAG), Prompt Engineering, LLM Fine-tuning, Transformers, Named Entity Recognition (NER), Text Summarization
- **AI Frameworks & Libraries:** LangChain, LangGraph, LangSmith, Hugging Face Transformers, PyTorch, TensorFlow, Scikit-learn
- **Data Processing & Analysis:** NumPy, Pandas, Data Preprocessing, Synthetic Data Generation, Model Evaluation
- **Databases & Vector Stores:** PostgreSQL, MongoDB, Azure CosmosDB, FAISS, ChromaDB, Vector Database Design
- **Backend & System Design:** FastAPI, Flask, RESTful APIs, Microservices Architecture, Asynchronous Processing
- **RAG & Agentic Architectures:** Vector-based RAG Architecture, Multi-Agent Systems, Agentic Workflows, ReAct, MCP and A2A Protocols
- **ETL & Data Engineering:** ETL Design Patterns, Data Pipelines, API-Based Data Ingestion
- **DevOps & MLOps:** Microsoft Azure, Docker, Git, Containerization
- **Data Visualization:** Matplotlib, Seaborn, Plotly

## Experience

### Generative AI Developer @ KGISL | October 2025 – Present

#### QA-Bot — AI-Assisted QA Issue Intake Platform

- Designed and deployed an AI-assisted QA intake platform that transforms unstructured tester bug reports into structured, Jira-ready issue summaries with mandatory validation and timestamp enforcement.
- Built a multi-stage issue lifecycle system (draft → approval → archive) with session tracking, attachment handling, and backend-driven Jira integration for issue creation, comments, and file uploads.
- Implemented zero-inference summarization workflows using Claude models to ensure generated reports only contain tester-provided information, improving reliability and reducing developer clarification cycles.
- Developed multi-issue parsing, natural-language time extraction, and per-client environment mapping supporting 8+ enterprise brokerage environments and workflows.
- Integrated read-only Git source grounding to map Jira stories/tasks with related branches and commits, enabling code-aware reproduction context for developers.
- Architected and deployed the platform as a long-running production service using FastAPI, Uvicorn, and systemd with journald logging, auto-restart, and local archival of issue evidence and attachments.

**Tech:** Python, FastAPI, PostgreSQL, Claude AI, Jira REST, Systemd

#### Dolphin Dashboard — AI-Driven Development & QA Automation Platform

- Architected and developed an AI-driven development and QA automation platform centered around a dynamically extensible library of 110 composable AI workflow skills spanning development orchestration, deployment automation, UI testing, settlement-cycle QA, debugging, and operational tooling.
- Built a filesystem-driven skill orchestration framework where Markdown-defined AI workflows are auto-discovered, categorized, synchronized, and executed at runtime without rebuilds, static manifests, or redeployment.
- Designed the DevFlow orchestration system automating the complete software development lifecycle including Jira analysis, planning, implementation, code review, testing, deployment, merge-request workflows, approval gates, and resumable execution state management.
- Developed multi-agent QA orchestration pipelines for autonomous UI testing, settlement-cycle validation, equity reconciliation, mismatch diagnosis, contract workflows, browser automation, and environment-aware test execution across enterprise brokerage systems.
- Implemented layered orchestration architectures where thin top-level orchestrators coordinate specialized AI sub-agents through gated execution phases with persistent state.json checkpointing and crash-resume recovery.
- Built a web-based operational dashboard integrating live workflow execution, AI skill launching, SSH/tmux terminal management, structured logs, request tracing, cycle-state monitoring, and real-time orchestration visibility into a unified keyboard-driven control surface.
- Integrated Playwright MCP, Dolphin UI MCP, PostgreSQL tooling, Kubernetes deployment workflows, and distributed environment automation supporting local, VDI K3s/Kubernetes, and multi-tenant QA infrastructure.
- Enabled autonomous development and QA operations across multiple enterprise brokerage tenants including UBS, Fyers, Jio, Morgan Stanley, and Opera/MOAP, significantly reducing manual coordination effort through reusable AI-driven automation workflows.

**Tech:** TypeScript, Node.js, Express, Socket.IO, Kubernetes, Playwright, Claude AI

#### SCQA-Cycle — Autonomous Settlement Cycle QA Orchestrator

- Designed and implemented an autonomous QA orchestration system that executes the complete DolphinV2 settlement-cycle workflow end-to-end from a single trading-date input, eliminating manual operator intervention during multi-hour QA runs.
- Built a sequential stateful execution engine coordinating 25 ordered settlement actions including BOD uploads, trade processing, mismatch resolution, allocation workflows, checker approvals, and contract generation across brokerage QA environments.
- Architected a spec-driven orchestration framework where all workflow behavior is dynamically loaded from Markdown-based event/action specifications, enabling runtime extensibility without modifying orchestrator logic.
- Developed resilient checkpoint-based execution pipelines with crash recovery, resumable workflows (--resume), context-pressure handling, and idempotent action replay to support long-running autonomous QA operations.
- Implemented adaptive QA operating modes including fully autonomous execution, human-in-the-loop review, guided recovery flows, and patch-bypass execution for controlled troubleshooting and defect validation.
- Built a self-improving execution model using cycle-local patch generation, global spec promotion, and automated learning-feedback loops that continuously refine orchestration behavior from real settlement-cycle failures.
- Integrated Dolphin UI MCP automation, inline PostgreSQL validation, audit logging, screenshot capture, metrics tracking, and structured evidence generation into a fully traceable QA execution pipeline.
- Enabled reusable settlement-cycle preparation workflows consumed by QA-Agent, QA-UI-Pilot, and Devbox Testing, forming the foundational orchestration layer for enterprise brokerage QA automation.

**Tech:** Claude AI, PostgreSQL, Dolphin UI MCP, Markdown Spec Engine, Stateful Workflow Orchestration

#### SCQA-File-Simulate — Settlement Cycle Test Data Simulation Platform

- Designed and implemented a write-capable settlement-cycle test-data simulation platform that generates, uploads, and validates realistic trade, allocation, contract, and BOD datasets across enterprise brokerage QA environments.
- Built a guided human-in-the-loop orchestration workflow enabling operators to dynamically generate custom settlement-cycle records, restamp production templates, execute dry-run impact reviews, and selectively perform DB inserts or API uploads.
- Architected a safety-first transactional execution model with explicit approval gates, INSERT-only database mutations, pre-generated rollback scripts, impact verification, and deterministic environment teardown to prevent accidental corruption of live QA environments.
- Developed a config-driven simulation engine supporting all 10 settlement-cycle upload cards, including seedable trade/allocation/contract workflows and automated edge-case scenario generation for mismatch validation and settlement defect testing.
- Implemented resumable stateful execution pipelines with per-run journals, crash recovery, deterministic replay, and workflow continuation support using --resume and --list execution flags.
- Integrated Dolphin API MCP uploads, Dolphin UI MCP browser automation, inline PostgreSQL validation, multipart upload execution, and authoritative API-audit verification into a unified arrange-act-assert testing workflow.
- Enabled on-demand generation of code-grounded clean baselines and targeted negative settlement scenarios across multiple brokerage tenants, reducing manual test-data preparation effort for settlement-cycle QA automation.

**Tech:** Python, PostgreSQL, Dolphin API MCP, Dolphin UI MCP, Stateful Workflow Automation

#### AI-Powered Conversational Platform for API Discovery and Market Intelligence

- Developed an AI-powered conversational interface to interact with REST APIs and deliver intelligent, context-aware responses using Gemini.
- Implemented natural language query understanding and routing using YAML-based GET/POST endpoint definitions.
- Built a Retrieval-Augmented Generation (RAG) system to semantically discover and select relevant API endpoints from natural language queries.
- Designed an orchestrator to manage end-to-end workflows including Swagger/OpenAPI ingestion, synchronization, indexing, and semantic search.
- Generated vector embeddings for API endpoints and stored them in Pinecone with rich metadata for accurate filtering and retrieval.
- Integrated real-time stock market intelligence for NIFTY 50 and individual stocks using yfinance.
- Implemented smart query processing to automatically extract parameters from endpoint-related and market-related user queries.
- Enabled voice-driven interactions through audio and speech processing using FFmpeg.

**Tech:** Python, FastAPI, Gemini, Pinecone, RAG, Swagger/OpenAPI, REST APIs, YAML, yfinance, FFmpeg, NLP

#### AI-Powered Financial Analytics and Portfolio Intelligence Platform

- Developed a backend platform integrating portfolio management, market analysis, and news intelligence using Python, FastAPI, and Flask.
- Implemented a SWOT news filter with two modes: Fast keyword-based filtering for instant results and LLM-powered semantic analysis using Google Gemini (gemini-2.5-flash) to categorize news into Strengths, Weaknesses, Opportunities, and Threats.
- Built a Dynamic Data Generator within the backend using Google Gemini LLM and Faker to generate realistic, context-aware synthetic data for PostgreSQL databases, supporting primitive, complex, and user-defined data types.
- Implemented Portfolio Analysis APIs enabling users to analyze investment portfolios with detailed performance metrics, risk assessment, and AI-generated alerts based on historical returns, volatility, and news sentiment. Users can retrieve: Overview, Holdings Analytics Heatmap, and AI-driven Alerts.
- Developed a Holdings API to provide detailed information on individual positions, including quantity, purchase price, current value, P&L, and risk metrics.
- Implemented a Strategy Builder module for options strategies, allowing users to create and analyze strategies programmatically with interactive payoff diagrams generated server-side based on option parameters.
- Exposed RESTful APIs for portfolio retrieval, stock screening, historical and real-time stock data, SWOT news analysis, portfolio impact calculations, and strategy evaluation.
- Integrated real Nifty 50 stock data via yfinance, including historical investment date selection, accurate P&L calculation, and live market price updates.
- Optimized AI integration with batch processing, confidence scoring, exponential backoff, and rate-limit handling for scalable LLM usage.
- Generated structured JSON outputs for portfolio analytics, holdings, strategy evaluation, SWOT news, and synthetic data to facilitate downstream analysis and reporting.
- Designed a modular, maintainable backend architecture with comprehensive logging, environment configuration, and error handling for robust production deployment.
- Supported future enhancements including predictive modeling, portfolio benchmarking, advanced risk metrics, and expanded AI-driven alerts for proactive investment decisions.

**Tech:** Python, FastAPI, Flask, Google Gemini LLM, Faker, yfinance, PostgreSQL, REST APIs, NLP, JSON, Batch Processing, Portfolio Analysis, Options Strategy Evaluation

#### Dynamic Document Intelligence and JSON Mapping Engine

- Architected and developed a dynamic document intelligence engine to extract and map data from Word and Excel templates using configurable metadata.
- Implemented query-driven value extraction to dynamically identify and capture relevant fields based on user inputs and document context.
- Designed a flexible JSON mapping layer to normalize extracted data into standardized schemas for downstream processing.
- Enabled configuration-based workflows to support multiple document formats, reducing manual effort and improving automation at scale.

**Tech:** Python, python-docx, OpenPyXL, JSON, Python Scripting, VS Code, PyCharm

### Generative AI Developer @ Yectra Technologies | April 2024 – September 2025

#### AI Analytics Platform - Conversational Data Interface

- Developed production RAG chatbot enabling natural language queries across multiple datasets.
- Implemented hybrid retrieval system using FAISS vector database, achieving 85% answer relevance score in user testing with 200+ queries.
- Designed multi-turn conversation handling with LangChain, supporting context retention across 5+ conversation turns.

**Tech:** Python, FastAPI, LangChain, FAISS, OpenAI GPT-4, sentence-transformers

#### Natural Language to MongoDB Query Engine

- Built NL-to-MongoDB converter enabling non-technical users to extract insights independently, reducing data team tickets by 40+ requests per week.
- Achieved 75% query accuracy through systematic prompt engineering and validation pipeline testing with 500+ query variations.
- Implemented automatic schema analysis and query optimization for collections with 100K+ documents.

**Tech:** LangChain, OpenAI API, MongoDB, Python, JSON Schema Validation

#### Predictive Analytics Integration

- Integrated Facebook Prophet forecasting model with conversational interface, enabling stakeholders to generate predictions through natural language.
- Delivered sales forecasting with 88% accuracy on historical data, supporting business planning.

**Tech:** Facebook Prophet, Pandas, NumPy, FastAPI, Python

#### Dynamic Visualization System (Multi-Agent Architecture)

- Developed LangGraph-based agent system for automatic chart generation from natural language requests, supporting 10+ chart types.
- Implemented iterative refinement capability allowing users to modify visualizations through conversation, improving user adoption by 60%.
- Created reusable visualization templates reducing custom chart development time from 2 hours to 10 minutes.

**Tech:** LangGraph, OpenAI API, Plotly, Python, Multi-agent Systems

#### Cross-Dataset Analytics Engine

- Built asynchronous processing pipeline for correlation analysis across multiple data sources, processing 10M+ records efficiently.
- Developed pattern recognition algorithms identifying key business relationships, uncovering 3+ actionable insights for stakeholders.
- Created automated data ingestion system supporting CSV, JSON, and database connections with schema auto-mapping.

**Tech:** Python, FastAPI, Pandas, NumPy, Asyncio, Background Tasks

#### Domain-Specific Chatbot (ROOS - Cloud Kitchen Assistant)

- Fine-tuned open-source LLM using LoRA for cloud kitchen domain.
- Optimized model training pipeline reducing GPU training time from 6 hours to 3 hours using QLoRA techniques.
- Deployed production-ready chatbot handling 200+ daily queries with sub-2-second response time.

**Tech:** Hugging Face Transformers, LoRA/QLoRA, CUDA, FastAPI, Model Deployment

## Education

### B.Tech in Information Technology @ Dr. N.G.P Institute of Technology | 2020 – 2024

- CGPA: 8.74