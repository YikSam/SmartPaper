import streamlit as st
import requests
import os
import time
import json
from io import StringIO
import tempfile
import base64
import re

# 设置页面配置
st.set_page_config(
    page_title="SmartPaper - 论文智能分析",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# 定义API基础URL
API_BASE_URL = "http://localhost:900"

# 自定义CSS样式
st.markdown(
    """
<style>
    .main-header {
        font-size: 2.5rem !important;
        text-align: center;
        color: #1E88E5;
    }
    .sub-header {
        font-size: 1.5rem !important;
        color: #0D47A1;
    }
    .output-container {
        background-color: #f0f2f6;
        border-radius: 10px;
        padding: 20px;
        margin: 10px 0;
    }
    .stButton>button {
        width: 100%;
    }
    .info-box {
        background-color: #e3f2fd;
        border-left: 5px solid #1E88E5;
        padding: 10px;
        border-radius: 5px;
    }
</style>
""",
    unsafe_allow_html=True,
)

# 初始化会话状态变量
if "response_text" not in st.session_state:
    st.session_state.response_text = ""
if "uploaded_file_path" not in st.session_state:
    st.session_state.uploaded_file_path = None
if "processing" not in st.session_state:
    st.session_state.processing = False


# 获取可用任务类型和描述
@st.cache_data(ttl=600)
def get_task_descriptions():
    try:
        response = requests.get(f"{API_BASE_URL}/api/v1/prompts/task_descriptions")
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return data.get("descriptions", {})
        return {
            "coolpapaers": "复刻 papers.cool",
            "yuanbao": "类似混元元宝总结",
            "methodology": "研究方法论分析",
        }
    except Exception as e:
        st.error(f"获取任务类型描述失败: {str(e)}")
        return {
            "coolpapaers": "复刻 papers.cool",
            "yuanbao": "类似混元元宝总结",
            "methodology": "研究方法论分析",
        }


# 获取可用模型列表
@st.cache_data(ttl=600)
def get_available_models():
    try:
        response = requests.get(f"{API_BASE_URL}/models")
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return (
                    data.get("models", []),
                    data.get("default_provider"),
                    data.get("default_model"),
                )
        return [], None, None
    except Exception as e:
        st.error(f"获取模型列表失败: {str(e)}")
        return [], None, None


# 获取已上传的文件列表
@st.cache_data(ttl=60)
def get_uploaded_files():
    try:
        response = requests.get(f"{API_BASE_URL}/list_uploaded_papers")
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return data.get("files", [])
        return []
    except Exception as e:
        st.error(f"获取上传文件列表失败: {str(e)}")
        return []


# 上传PDF文件
def upload_pdf(file):
    try:
        files = {"file": file}
        response = requests.post(f"{API_BASE_URL}/upload_paper", files=files)
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                return data.get("file_path")
            else:
                st.error(f"上传文件失败: {data.get('error')}")
        else:
            st.error(f"上传文件失败: HTTP状态码 {response.status_code}")
        return None
    except Exception as e:
        st.error(f"上传文件出错: {str(e)}")
        return None


# 处理来自SSE的流式响应
def process_stream_response(response):
    buffer = StringIO()
    for line in response.iter_lines():
        if line:
            # 移除 "data: " 前缀
            line_text = line.decode("utf-8")
            if line_text.startswith("data: "):
                content = line_text[6:]
                if content == "[DONE]":
                    break
                try:
                    # 尝试解析JSON
                    data = json.loads(content)
                    if "content" in data:
                        buffer.write(data["content"])
                        # 更新会话状态以展示流式文本
                        st.session_state.response_text = buffer.getvalue()
                        # 使用st.empty().markdown来更新UI，添加unsafe_allow_html=True以渲染HTML标签
                        st.session_state.response_container.markdown(
                            st.session_state.response_text, unsafe_allow_html=True
                        )
                except Exception as e:
                    # 如果不是JSON格式，直接添加内容
                    buffer.write(content)
                    st.session_state.response_text = buffer.getvalue()
                    st.session_state.response_container.markdown(
                        st.session_state.response_text, unsafe_allow_html=True
                    )
    return buffer.getvalue()


# 与arXiv论文进行流式对话
def chat_with_arxiv_stream(paper_id, task_type, provider=None, model=None, image_text_mode=False):
    payload = {
        "paper_id": paper_id,
        "task_type": task_type,
        "stream": True,
        "image_text_mode": image_text_mode,
        "use_cache": True,
        "force_download": False,  # 添加force_download参数
    }
    if provider:
        payload["provider"] = provider
    if model:
        payload["model"] = model

    try:
        response = requests.post(
            f"{API_BASE_URL}/chat_with_arxiv_stream", json=payload, stream=True
        )
        if response.status_code == 200:
            return process_stream_response(response)
        else:
            st.error(f"请求失败: HTTP状态码 {response.status_code}")
            try:
                error_data = response.json()
                st.error(f"错误信息: {error_data.get('error', '未知错误')}")
            except:
                st.error(f"无法解析错误响应: {response.text}")
            return None
    except Exception as e:
        st.error(f"请求出错: {str(e)}")
        return None


# 与本地PDF文件进行流式对话
def chat_with_local_stream(pdf_path, task_type, provider=None, model=None, image_text_mode=False):
    payload = {
        "pdf_path": pdf_path,
        "task_type": task_type,
        "stream": True,
        "image_text_mode": image_text_mode,
        "use_cache": True,
    }
    if provider:
        payload["provider"] = provider
    if model:
        payload["model"] = model

    try:
        response = requests.post(
            f"{API_BASE_URL}/chat_with_local_stream", json=payload, stream=True
        )
        if response.status_code == 200:
            return process_stream_response(response)
        else:
            st.error(f"请求失败: HTTP状态码 {response.status_code}")
            try:
                error_data = response.json()
                st.error(f"错误信息: {error_data.get('error', '未知错误')}")
            except:
                st.error(f"无法解析错误响应: {response.text}")
            return None
    except Exception as e:
        st.error(f"请求出错: {str(e)}")
        return None


# 主应用
def main():
    st.markdown('<h1 class="main-header">SmartPaper 论文智能分析</h1>', unsafe_allow_html=True)

    # 侧边栏配置
    st.sidebar.markdown('<h2 class="sub-header">配置选项</h2>', unsafe_allow_html=True)

    # 获取任务类型描述
    task_descriptions = get_task_descriptions()
    task_types = list(task_descriptions.keys())

    # 获取模型列表
    models, default_provider, default_model = get_available_models()
    providers = set(model["provider"] for model in models) if models else []

    # 任务类型选择
    selected_task = st.sidebar.selectbox(
        "选择解释模式",
        options=task_types,
        format_func=lambda x: f"{x} - {task_descriptions.get(x, '')}",
    )

    # LLM提供商选择
    selected_provider = st.sidebar.selectbox(
        "选择LLM提供商",
        options=list(providers) or ["openai"],
        index=0 if default_provider not in providers else list(providers).index(default_provider),
    )

    # 模型选择（根据所选提供商过滤）
    provider_models = [model["name"] for model in models if model["provider"] == selected_provider]
    selected_model = st.sidebar.selectbox(
        "选择模型",
        options=provider_models or ["gpt-3.5-turbo"],
        index=0 if default_model not in provider_models else provider_models.index(default_model),
    )

    # 图文模式选择
    image_text_mode = st.sidebar.checkbox("启用图文模式（提取论文图片）", value=True)

    # 添加强制下载选项
    force_download = st.sidebar.checkbox("强制重新下载论文（不使用缓存）", value=False)

    # 创建选项卡
    tab1, tab2 = st.tabs(["arXiv论文", "上传PDF"])

    # arXiv论文选项卡
    with tab1:
        st.markdown('<h2 class="sub-header">通过arXiv ID分析论文</h2>', unsafe_allow_html=True)
        st.markdown(
            '<div class="info-box">输入arXiv论文ID，例如: 2303.08774</div>', unsafe_allow_html=True
        )

        paper_id = st.text_input("arXiv论文ID")

        if st.button("分析arXiv论文", key="analyze_arxiv"):
            if not paper_id:
                st.warning("请输入有效的arXiv论文ID")
            else:
                # 使用strip()去除ID中的空格，避免识别问题
                paper_id = paper_id.strip()
                # 验证arXiv ID格式
                if not re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", paper_id) and not re.match(
                    r"^\d{7}(v\d+)?$", paper_id
                ):
                    st.warning("请输入有效的arXiv论文ID格式，例如: 2303.08774 或 2303.08774v1")
                else:
                    st.session_state.processing = True
                    st.session_state.response_text = ""
                    st.session_state.response_container = st.empty()

                    with st.spinner(f"正在使用 {selected_task} 模式分析论文..."):
                        # 更新请求参数，添加force_download参数
                        payload = {
                            "paper_id": paper_id,
                            "task_type": selected_task,
                            "provider": selected_provider,
                            "model": selected_model,
                            "image_text_mode": image_text_mode,
                            "force_download": force_download,  # 添加强制下载参数
                            "stream": True,
                            "use_cache": True,
                        }

                        try:
                            response = requests.post(
                                f"{API_BASE_URL}/chat_with_arxiv_stream", json=payload, stream=True
                            )
                            if response.status_code == 200:
                                process_stream_response(response)
                            else:
                                st.error(f"请求失败: HTTP状态码 {response.status_code}")
                                try:
                                    error_data = response.json()
                                    st.error(f"错误信息: {error_data.get('error', '未知错误')}")
                                except:
                                    st.error(f"无法解析错误响应: {response.text}")
                        except Exception as e:
                            st.error(f"请求出错: {str(e)}")

                    st.session_state.processing = False

    # 上传PDF选项卡
    with tab2:
        st.markdown('<h2 class="sub-header">上传并分析PDF论文</h2>', unsafe_allow_html=True)

        col1, col2 = st.columns([2, 1])

        with col1:
            uploaded_file = st.file_uploader("上传PDF论文", type=["pdf"])

            if uploaded_file is not None and not st.session_state.processing:
                # 上传文件并获取路径
                with st.spinner("正在上传文件..."):
                    pdf_path = upload_pdf(uploaded_file)

                if pdf_path:
                    st.session_state.uploaded_file_path = pdf_path
                    st.success(f"文件上传成功！文件路径: {pdf_path}")

        with col2:
            st.markdown("#### 或选择已上传的文件")
            # 获取已上传的文件
            uploaded_files = get_uploaded_files()
            if uploaded_files:
                file_options = ["请选择..."] + [file["file_name"] for file in uploaded_files]
                file_paths = {file["file_name"]: file["file_path"] for file in uploaded_files}

                selected_file = st.selectbox("已上传的文件", options=file_options)

                if selected_file != "请选择...":
                    st.session_state.uploaded_file_path = file_paths[selected_file]

        if st.session_state.uploaded_file_path and st.button(
            "分析上传的论文", key="analyze_uploaded"
        ):
            st.session_state.processing = True
            st.session_state.response_text = ""
            st.session_state.response_container = st.empty()

            with st.spinner(f"正在使用 {selected_task} 模式分析论文..."):
                chat_with_local_stream(
                    pdf_path=st.session_state.uploaded_file_path,
                    task_type=selected_task,
                    provider=selected_provider,
                    model=selected_model,
                    image_text_mode=image_text_mode,
                )

            st.session_state.processing = False


if __name__ == "__main__":
    main()
