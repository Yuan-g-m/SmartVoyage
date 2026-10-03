#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文件名: app.py
描述: SmartVoyage 旅行智能助手前端（Streamlit）。
      UI 层重构：轻量、干净的旅行科技风。
      业务逻辑（意图识别、A2A 路由、结果汇总）保持不变。
"""
import asyncio
import json
import os
import re
import sys
import time
import uuid
from datetime import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytz
import streamlit as st
from langchain_openai import ChatOpenAI
from python_a2a import A2AClient, Message, MessageRole, Task, TextContent

from SmartVoyage.config import Config
from SmartVoyage.create_logger import logger
from SmartVoyage.main_prompts import SmartVoyagePrompts


conf = Config()

st.set_page_config(
    page_title="SmartVoyage · A2A 旅行智能助手",
    layout="wide",
    page_icon="🧳",
    initial_sidebar_state="expanded",
)


# ---------------------------------------------------------------
# 静态信息
# ---------------------------------------------------------------
AGENTS_INFO = {
    "WeatherQueryAssistant": {
        "icon": "🌤️",
        "name": "天气查询助手",
        "desc": "查询城市天气、温度、风力与日出日落等气象信息。",
        "port": "5005",
        "accent": "weather",
    },
    "TicketQueryAssistant": {
        "icon": "🎫",
        "name": "票务查询助手",
        "desc": "查询火车票、机票、演唱会余票与票价。",
        "port": "5006",
        "accent": "ticket",
    },
    "TicketOrderAssistant": {
        "icon": "🛒",
        "name": "票务预订助手",
        "desc": "根据查询结果完成车票、机票、演出票预订。",
        "port": "5007",
        "accent": "order",
    },
}

AGENT_URLS = {
    "WeatherQueryAssistant": "http://127.0.0.1:5005",
    "TicketQueryAssistant": "http://127.0.0.1:5006",
    "TicketOrderAssistant": "http://127.0.0.1:5007",
}

QUICK_EXAMPLES = [
    ("🌤️", "查北京天气", "北京今天天气怎么样"),
    ("✈️", "查京沪机票", "查一下 2025-10-28 从北京到上海的机票"),
    ("🎫", "订京沪火车票", "预订一张北京到上海的火车票"),
    ("🏞️", "推荐北京景点", "推荐北京必去的景点"),
]


# ---------------------------------------------------------------
# 自定义样式
# ---------------------------------------------------------------
CSS = """
<style>
:root {
    --brand: #2563eb;
    --brand-2: #0ea5e9;
    --brand-3: #06b6d4;
    --ink: #0f172a;
    --muted: #64748b;
    --line: #e2e8f0;
    --soft: #f6f9fd;
    --card: #ffffff;
}

html, body, [class*="st-"] {
    font-family: "Inter", "Segoe UI", "PingFang SC", "Microsoft YaHei", sans-serif;
}

.stApp {
    background:
        radial-gradient(1100px 420px at 8% -8%, rgba(37, 99, 235, 0.10), transparent 60%),
        radial-gradient(900px 420px at 100% 0%, rgba(14, 165, 233, 0.10), transparent 55%),
        #f6f9fd;
}

[data-testid="stHeader"] { background: transparent; }
[data-testid="stToolbar"] { visibility: hidden; }
#MainMenu, footer { visibility: hidden; }

.block-container {
    max-width: 1450px;
    padding-top: 1.15rem;
    padding-bottom: 1.5rem;
}

/* 侧边栏 */
[data-testid="stSidebar"] {
    background: rgba(255, 255, 255, 0.88);
    border-right: 1px solid var(--line);
    backdrop-filter: blur(14px);
    min-width: 292px;
    max-width: 320px;
}
[data-testid="stSidebarCollapseButton"] {
    display: none;
}
[data-testid="stSidebar"] * { color: #334155; }
[data-testid="stSidebar"] .stButton > button {
    background: #ffffff;
    border: 1px solid var(--line);
    border-radius: 12px;
    color: #334155;
    text-align: left;
    white-space: normal;
    height: auto;
    min-height: 2.8rem;
    padding: 0.65rem 0.8rem;
}
[data-testid="stSidebar"] .stButton > button:hover {
    border-color: #93c5fd;
    background: #f8fbff;
    color: var(--brand);
    transform: translateX(2px);
}

.brand {
    display: flex;
    align-items: center;
    gap: 0.7rem;
    padding: 0.4rem 0 1rem 0;
}
.brand-mark {
    width: 42px;
    height: 42px;
    border-radius: 13px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 22px;
    background: linear-gradient(135deg, #2563eb, #06b6d4);
    color: #ffffff;
    box-shadow: 0 12px 24px rgba(37, 99, 235, 0.20);
}
.brand-title { color: #0f172a; font-weight: 700; font-size: 1.05rem; line-height: 1.1; }
.brand-sub { color: #64748b; font-size: 0.72rem; margin-top: 0.12rem; }

.side-title {
    color: #94a3b8;
    font-size: 0.72rem;
    font-weight: 700;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin: 1rem 0 0.45rem 0;
}
.side-note {
    margin-top: 1rem;
    padding: 0.8rem 0.85rem;
    border-radius: 14px;
    background: #f8fbff;
    border: 1px solid #e2e8f0;
    color: #64748b;
    font-size: 0.78rem;
    line-height: 1.6;
}
.side-note code {
    background: #e8f1ff;
    color: #2563eb;
    padding: 0.05rem 0.3rem;
    border-radius: 6px;
    font-size: 0.74rem;
}

/* Hero 头部 */
.hero {
    position: relative;
    overflow: hidden;
    padding: 1.25rem 1.5rem;
    border-radius: 22px;
    background: linear-gradient(120deg, #1d4ed8 0%, #2563eb 34%, #0ea5e9 68%, #06b6d4 100%);
    color: #ffffff;
    box-shadow: 0 20px 44px rgba(37, 99, 235, 0.18);
    margin-bottom: 0.85rem;
}
.hero::after {
    content: "";
    position: absolute;
    right: -60px;
    top: -80px;
    width: 240px;
    height: 240px;
    border-radius: 50%;
    background: rgba(255, 255, 255, 0.12);
}
.hero-kicker {
    display: inline-block;
    padding: 0.22rem 0.55rem;
    border-radius: 999px;
    background: rgba(255, 255, 255, 0.16);
    border: 1px solid rgba(255, 255, 255, 0.22);
    font-size: 0.72rem;
    letter-spacing: 0.04em;
    margin-bottom: 0.6rem;
}
.hero h1 { color: #ffffff; font-size: 1.65rem; margin: 0 0 0.3rem 0; }
.hero p { color: rgba(255, 255, 255, 0.88); margin: 0; max-width: 880px; }

/* 顶部 Agent 状态 */
.agent-pill {
    height: 100%;
    display: flex;
    align-items: center;
    gap: 0.7rem;
    background: #ffffff;
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 0.72rem 0.8rem;
    box-shadow: 0 8px 22px rgba(15, 23, 42, 0.04);
    transition: transform 0.18s ease, box-shadow 0.18s ease;
}
.agent-pill:hover {
    transform: translateY(-2px);
    box-shadow: 0 14px 28px rgba(15, 23, 42, 0.07);
}
.agent-pill .icon {
    width: 38px;
    height: 38px;
    min-width: 38px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 19px;
}
.agent-pill.weather .icon { background: #e8f4ff; }
.agent-pill.ticket .icon { background: #eef6ff; }
.agent-pill.order .icon { background: #f1f7ff; }
.agent-pill .meta { min-width: 0; }
.agent-pill .meta b { display: block; color: #0f172a; font-size: 0.94rem; }
.agent-pill .meta span { color: #64748b; font-size: 0.74rem; }
.agent-pill .status {
    margin-left: auto;
    white-space: nowrap;
    color: #16a34a;
    font-size: 0.72rem;
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
    border-radius: 999px;
    padding: 0.22rem 0.5rem;
}

/* 欢迎语 */
.welcome {
    padding: 1rem 1.1rem;
    border-radius: 16px;
    border: 1px dashed #bfdbfe;
    background: #ffffff;
    color: #64748b;
    margin-bottom: 0.85rem;
    box-shadow: 0 8px 22px rgba(15, 23, 42, 0.03);
}

/* 聊天气泡 */
div[data-testid="stChatMessage"] {
    border-radius: 16px;
    padding: 0.75rem 0.9rem;
    margin: 0.42rem 0;
    border: 1px solid var(--line);
    background: #ffffff;
    box-shadow: 0 8px 22px rgba(15, 23, 42, 0.035);
}
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) {
    background: linear-gradient(135deg, #2563eb, #0ea5e9);
    border: none;
}
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) [data-testid="stMarkdownContainer"] {
    color: #ffffff;
}
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) [data-testid="stCaptionContainer"] {
    color: rgba(255, 255, 255, 0.72);
}
div[data-testid="stChatMessage"] [data-testid="stMarkdownContainer"] { color: #1e293b; }
div[data-testid="stChatMessage"] [data-testid="stCaptionContainer"] {
    color: #475569;
    font-size: 0.74rem;
    font-weight: 600;
    letter-spacing: 0.01em;
}
div[data-testid="stChatMessage"]:has(div[data-testid="stChatMessageAvatarUser"]) [data-testid="stCaptionContainer"] {
    color: rgba(255, 255, 255, 0.90);
}

/* 路由标签 */
.route-tag {
    margin-top: 0.35rem;
    color: #2563eb;
    font-size: 0.78rem;
}
.agent-chip {
    display: inline-block;
    padding: 0.05rem 0.5rem;
    border-radius: 999px;
    background: #e8f1ff;
    color: #2563eb;
    border: 1px solid #bfdbfe;
    font-size: 0.72rem;
    margin-right: 0.22rem;
}

/* 右侧能力卡片 */
.panel-title {
    color: #0f172a;
    font-weight: 700;
    font-size: 0.98rem;
    margin: 0.2rem 0 0.55rem 0;
}
.agent-card {
    position: relative;
    background: #ffffff;
    border: 1px solid var(--line);
    border-radius: 18px;
    padding: 0.9rem 0.95rem;
    margin-bottom: 0.75rem;
    box-shadow: 0 8px 22px rgba(15, 23, 42, 0.04);
}
.agent-card-head {
    display: flex;
    align-items: center;
    gap: 0.65rem;
    margin-bottom: 0.5rem;
}
.agent-card .icon {
    width: 38px;
    height: 38px;
    border-radius: 12px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 19px;
}
.agent-card.weather .icon { background: #e8f4ff; }
.agent-card.ticket .icon { background: #eef6ff; }
.agent-card.order .icon { background: #f1f7ff; }
.agent-card-name { color: #0f172a; font-weight: 700; }
.agent-card-ver {
    margin-left: auto;
    font-size: 0.68rem;
    color: #94a3b8;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    padding: 0.1rem 0.4rem;
    border-radius: 999px;
}
.agent-card-desc { color: #64748b; font-size: 0.82rem; line-height: 1.55; }

.tip-card {
    background: #f8fbff;
    border: 1px solid #e2e8f0;
    border-radius: 18px;
    padding: 0.85rem 0.95rem;
    color: #475569;
    font-size: 0.82rem;
    line-height: 1.75;
}
.tip-card code {
    background: #e8f1ff;
    color: #2563eb;
    padding: 0.05rem 0.3rem;
    border-radius: 6px;
    font-size: 0.78rem;
}

/* 输入框：与浅色主题融为一体 */
[data-testid="stChatInput"] {
    background: #ffffff;
    border: 1px solid #dbe3ef;
    border-radius: 18px;
    padding: 0.32rem 0.55rem;
    box-shadow: 0 12px 28px rgba(15, 23, 42, 0.07);
    transition: border-color 0.18s ease, box-shadow 0.18s ease;
}
[data-testid="stChatInput"] > div,
[data-testid="stChatInput"] [data-baseweb="base-input"],
[data-testid="stChatInput"] [data-baseweb="textarea"] {
    background: #ffffff !important;
    border: none !important;
    box-shadow: none !important;
    color: #0f172a !important;
}
[data-testid="stChatInput"]:focus-within {
    border-color: #93c5fd;
    box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.08), 0 14px 30px rgba(15, 23, 42, 0.08);
}
[data-testid="stChatInput"] textarea {
    min-height: 56px;
    border: none;
    background: transparent !important;
    color: #0f172a !important;
    caret-color: #2563eb !important;
    font-weight: 500;
    box-shadow: none;
}
[data-testid="stChatInput"] textarea::placeholder {
    color: #475569 !important;
    opacity: 1 !important;
    font-weight: 400;
}
[data-testid="stChatInput"] button {
    color: #2563eb;
    background: transparent;
}
.stButton > button {
    border-radius: 12px;
    border: 1px solid var(--line);
    background: #ffffff;
    color: #334155;
}
.stButton > button:hover {
    border-color: #93c5fd;
    color: var(--brand);
    background: #f8fbff;
}

/* 页脚 */
.footer {
    text-align: center;
    color: #94a3b8;
    font-size: 0.78rem;
    padding: 0.9rem 0 0.1rem 0;
}
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------
# 会话状态初始化（懒加载 Agent，避免首屏请求 Agent Card）
# ---------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pending_prompt" not in st.session_state:
    st.session_state.pending_prompt = None
if "pending_processing" not in st.session_state:
    st.session_state.pending_processing = None
if "agent_urls" not in st.session_state:
    st.session_state.agent_urls = AGENT_URLS
if "a2a_clients" not in st.session_state:
    st.session_state.a2a_clients = {}
if "llm" not in st.session_state:
    st.session_state.llm = ChatOpenAI(
        model=conf.model_name,
        api_key=conf.api_key,
        base_url=conf.base_url,
        temperature=conf.temperature,
    )
if "conversation_history" not in st.session_state:
    st.session_state.conversation_history = ""


# ---------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------
def intent_agent(user_input):
    chain = SmartVoyagePrompts.intent_prompt() | st.session_state.llm
    current_date = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%Y-%m-%d")
    intent_response = chain.invoke(
        {
            "conversation_history": "\n".join(st.session_state.conversation_history.split("\n")[-6:]),
            "query": user_input,
            "current_date": current_date,
        }
    ).content.strip()
    logger.info(f"意图识别原始响应: {intent_response}")

    intent_response = re.sub(r"^```json\s*|\s*```$", "", intent_response).strip()
    logger.info(f"清理后响应: {intent_response}")
    intent_output = json.loads(intent_response)
    intents = intent_output.get("intents", [])
    user_queries = intent_output.get("user_queries", {})
    follow_up_message = intent_output.get("follow_up_message", "")
    logger.info(f"intents: {intents}||user_queries: {user_queries}||follow_up_message: {follow_up_message}")
    return intents, user_queries, follow_up_message


def agent_display_name(agent_name):
    return AGENTS_INFO.get(agent_name, {}).get("name", agent_name)


def agent_for_intent(intent):
    if intent == "weather":
        return "WeatherQueryAssistant"
    if intent in ["flight", "train", "concert"]:
        return "TicketQueryAssistant"
    if intent == "order":
        return "TicketOrderAssistant"
    return None


def get_agent_client(agent_name):
    if agent_name not in st.session_state.a2a_clients:
        url = st.session_state.agent_urls[agent_name]
        st.session_state.a2a_clients[agent_name] = A2AClient(url)
    return st.session_state.a2a_clients[agent_name]


def extract_agent_result(raw_response):
    if raw_response.status.state == "completed":
        return raw_response.artifacts[0]["parts"][0]["text"]
    return raw_response.status.message["content"]["text"]


def summarize_agent_result(agent_name, query_str, agent_result):
    llm = st.session_state.llm
    if agent_name == "WeatherQueryAssistant":
        chain = SmartVoyagePrompts.summarize_weather_prompt() | llm
        return chain.invoke({"query": query_str, "raw_response": agent_result}).content.strip()
    if agent_name == "TicketQueryAssistant":
        chain = SmartVoyagePrompts.summarize_ticket_prompt() | llm
        return chain.invoke({"query": query_str, "raw_response": agent_result}).content.strip()
    return agent_result


async def run_agent_tasks(jobs):
    async def send_one(job):
        client = get_agent_client(job["agent_name"])
        return await client.send_task_async(job["task"])

    return await asyncio.gather(*(send_one(job) for job in jobs))


def agent_pill_html(name, info):
    return f"""
    <div class="agent-pill {info['accent']}">
      <div class="icon">{info['icon']}</div>
      <div class="meta"><b>{info['name']}</b><span>:{info['port']}</span></div>
      <span class="status">就绪</span>
    </div>
    """


def agent_card_html(name, info):
    return f"""
    <div class="agent-card {info['accent']}">
      <div class="agent-card-head">
        <div class="icon">{info['icon']}</div>
        <div class="agent-card-name">{info['name']}</div>
        <span class="agent-card-ver">v1.0</span>
      </div>
      <div class="agent-card-desc">{info['desc']}</div>
    </div>
    """


# ---------------------------------------------------------------
# 处理一轮对话
# ---------------------------------------------------------------
def generate_response(prompt):
    llm = st.session_state.llm
    response = ""
    routed_agents = []

    try:
        intents, user_queries, follow_up_message = intent_agent(prompt)

        if "out_of_scope" in intents:
            response = follow_up_message
            st.session_state.conversation_history += f"\nAssistant: {response}"
        elif follow_up_message:
            response = follow_up_message
            st.session_state.conversation_history += f"\nAssistant: {response}"
        else:
            # 先构建非订票任务；订票任务延后执行，以便注入天气/票务前置结果。
            base_jobs = {}
            non_order_indices = []
            order_indices = []
            for index, intent in enumerate(intents):
                agent_name = agent_for_intent(intent)
                if intent == "attraction" or not agent_name:
                    continue

                query_str = user_queries.get(intent) or prompt
                logger.info(f"{agent_name} 查询：{query_str}")
                chat_history = (
                    "\n".join(st.session_state.conversation_history.split("\n")[-7:-1])
                    + f"\nUser: {query_str}"
                )
                message = Message(content=TextContent(text=chat_history), role=MessageRole.USER)
                task = Task(id="task-" + str(uuid.uuid4()), message=message.to_dict())
                job = {
                    "index": index,
                    "intent": intent,
                    "agent_name": agent_name,
                    "query_str": query_str,
                    "task": task,
                }
                base_jobs[index] = job
                if intent == "order":
                    order_indices.append(index)
                else:
                    non_order_indices.append(index)

            for job in base_jobs.values():
                get_agent_client(job["agent_name"])

            results_by_index = {}
            final_by_index = {}
            prior_summaries = []

            # 1）并行执行非订票意图。
            non_order_jobs = [base_jobs[index] for index in non_order_indices]
            raw_results = asyncio.run(run_agent_tasks(non_order_jobs)) if non_order_jobs else []
            for job, raw_result in zip(non_order_jobs, raw_results):
                results_by_index[job["index"]] = raw_result
                agent_result = extract_agent_result(raw_result)
                final_response = summarize_agent_result(job["agent_name"], job["query_str"], agent_result)
                final_by_index[job["index"]] = final_response
                prior_summaries.append({"intent": job["intent"], "text": final_response})

            # 2）执行订票意图，并把前置结果注入到订票请求中。
            order_jobs = []
            for index in order_indices:
                job = base_jobs[index]
                enriched_query = job["query_str"]
                if prior_summaries:
                    context_lines = [f"- {item['intent']}：{item['text']}" for item in prior_summaries]
                    enriched_query = f"{enriched_query}\n已知前置信息：\n" + "\n".join(context_lines)

                chat_history = (
                    "\n".join(st.session_state.conversation_history.split("\n")[-7:-1])
                    + f"\nUser: {enriched_query}"
                )
                message = Message(content=TextContent(text=chat_history), role=MessageRole.USER)
                task = Task(id="task-" + str(uuid.uuid4()), message=message.to_dict())
                order_jobs.append(
                    {
                        "index": index,
                        "intent": job["intent"],
                        "agent_name": job["agent_name"],
                        "query_str": enriched_query,
                        "task": task,
                    }
                )

            raw_order_results = asyncio.run(run_agent_tasks(order_jobs)) if order_jobs else []
            for job, raw_result in zip(order_jobs, raw_order_results):
                results_by_index[job["index"]] = raw_result
                agent_result = extract_agent_result(raw_result)
                final_by_index[job["index"]] = summarize_agent_result(
                    job["agent_name"], job["query_str"], agent_result
                )

            responses = []
            for index, intent in enumerate(intents):
                if intent == "attraction":
                    chain = SmartVoyagePrompts.attraction_prompt() | llm
                    responses.append(chain.invoke({"query": prompt}).content.strip())
                    continue

                agent_name = agent_for_intent(intent)
                if not agent_name:
                    responses.append("暂不支持此意图。")
                    continue

                final_response = final_by_index.get(index)
                if final_response is None:
                    responses.append("该服务暂未返回结果，请稍后重试。")
                    continue

                responses.append(final_response)
                routed_agents.append(agent_name)

            response = "\n\n".join(responses)
            if routed_agents:
                logger.info(f"路由到代理：{routed_agents}")
            st.session_state.conversation_history += f"\nAssistant: {response}"

    except json.JSONDecodeError as json_err:
        logger.error(f"意图识别JSON解析失败")
        response = f"意图识别JSON解析失败：{str(json_err)}。请重试。"
        st.session_state.conversation_history += f"\nAssistant: {response}"
    except Exception as e:
        logger.error(f"处理异常: {str(e)}")
        response = f"处理失败：{str(e)}。请重试。"
        st.session_state.conversation_history += f"\nAssistant: {response}"

    return response, routed_agents


def process_input(prompt):
    """生成完整回复并写入会话消息，供需要一次性处理的场景复用。"""
    response, routed_agents = generate_response(prompt)
    now = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%H:%M:%S")
    st.session_state.messages.append(
        {"role": "assistant", "content": response, "time": now, "agents": routed_agents}
    )


def chunk_text(text, chunk_size=8):
    """按小块切分文本，用于前端渐进式流式渲染。"""
    text = text or ""
    for index in range(0, len(text), chunk_size):
        yield text[index:index + chunk_size]
        time.sleep(0.015)


def stream_pipeline(prompt, holder):
    """执行完整业务链路，并流式产出状态提示和最终回复。"""
    yield "正在分析意图并调用 Agent，请稍候…\n\n"
    response, routed_agents = generate_response(prompt)
    holder["response"] = response
    holder["agents"] = routed_agents
    yield from chunk_text(response)


# ---------------------------------------------------------------
# 侧边栏
# ---------------------------------------------------------------
with st.sidebar:
    st.markdown(
        """
        <div class="brand">
          <div class="brand-mark">🧳</div>
          <div>
            <div class="brand-title">SmartVoyage</div>
            <div class="brand-sub">A2A Travel Copilot</div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if st.button("🗑️ 清空对话", use_container_width=True):
        st.session_state.messages = []
        st.session_state.conversation_history = ""
        st.rerun()

    st.markdown('<div class="side-title">快捷体验</div>', unsafe_allow_html=True)
    for emoji, label, example in QUICK_EXAMPLES:
        if st.button(f"{emoji}  {label}", use_container_width=True, key=f"example_{label}"):
            st.session_state.pending_prompt = example

    st.markdown(
        """
        <div class="side-note">
          <b>使用提示</b><br>
          天气：<code>北京今天天气怎么样</code><br>
          查询：<code>查 2025-10-28 北京到上海的机票</code><br>
          预订：<code>预订一张北京到上海的火车票</code><br>
          推荐：<code>推荐北京必去的景点</code>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------
# 主界面
# ---------------------------------------------------------------
st.markdown(
    """
    <div class="hero">
      <div class="hero-kicker">A2A · MULTI-AGENT TRAVEL</div>
      <h1>SmartVoyage 旅行智能助手</h1>
      <p>主控 Agent 精准识别意图，协同天气、票务查询与票务预订三个专家代理，一站式规划您的旅程。</p>
    </div>
    """,
    unsafe_allow_html=True,
)

status_cols = st.columns(3)
for col, (name, info) in zip(status_cols, AGENTS_INFO.items()):
    with col:
        st.markdown(agent_pill_html(name, info), unsafe_allow_html=True)

chat_col = st.container()

with chat_col:
    if not st.session_state.messages:
        st.markdown(
            '<div class="welcome">👋 您好！我可以帮您查天气、查火车票 / 机票 / 演出票、订票，还可以推荐景点。'
            '试试左侧栏的快捷示例～</div>',
            unsafe_allow_html=True,
        )

    for message in st.session_state.messages:
        role = message["role"]
        with st.chat_message(role, avatar="🧑" if role == "user" else "🤖"):
            st.markdown(message["content"])
            if role == "assistant" and message.get("agents"):
                chips = " ".join(
                    f'<span class="agent-chip">{agent_display_name(name)}</span>' for name in message["agents"]
                )
                st.markdown(f'<div class="route-tag">本次调度：{chips}</div>', unsafe_allow_html=True)
            st.caption(f"🕒 {message.get('time', '')}")

    if st.session_state.pending_processing:
        prompt = st.session_state.pending_processing
        st.session_state.pending_processing = None
        holder = {}
        with st.chat_message("assistant", avatar="🤖"):
            st.write_stream(stream_pipeline(prompt, holder))
            routed_agents = holder.get("agents", [])
            if routed_agents:
                chips = " ".join(
                    f'<span class="agent-chip">{agent_display_name(name)}</span>' for name in routed_agents
                )
                st.markdown(f'<div class="route-tag">本次调度：{chips}</div>', unsafe_allow_html=True)
            now = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%H:%M:%S")
            st.caption(f"🕒 {now}")

        st.session_state.messages.append(
            {
                "role": "assistant",
                "content": holder.get("response", ""),
                "time": now,
                "agents": routed_agents,
            }
        )
        st.rerun()

    prompt = None
    user_input = st.chat_input("请输入旅行需求，例如「北京到上海的机票」…")
    if st.session_state.pending_prompt:
        prompt = st.session_state.pending_prompt
        st.session_state.pending_prompt = None
    elif user_input:
        prompt = user_input

    if prompt:
        now = datetime.now(pytz.timezone("Asia/Shanghai")).strftime("%H:%M:%S")
        st.session_state.messages.append({"role": "user", "content": prompt, "time": now})
        st.session_state.conversation_history += f"\nUser: {prompt}"
        st.session_state.pending_processing = prompt
        st.rerun()
