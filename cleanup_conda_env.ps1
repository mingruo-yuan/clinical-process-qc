# === 专病库系统 conda 环境瘦身脚本 ===
# 移除项目未使用的重型包, 预计释放 ~1GB 磁盘空间
# 用法: 在激活 qilu 环境后运行此脚本

conda activate qilu

# --- 必须移除的重型包 ---
pip uninstall -y torch transformers sentence-transformers

# --- langchain 全家桶 ---
pip uninstall -y langchain langchain-classic langchain-community langchain-core langchain-openai langchain-huggingface langchain-text-splitters langchain-protocol langsmith langgraph langgraph-checkpoint langgraph-prebuilt langgraph-sdk langgraph-prebuilt

# --- 向量/ML ---
pip uninstall -y faiss-cpu opencv-python scikit-learn scipy

# --- huggingface 生态 (sentence-transformers 依赖) ---
pip uninstall -y huggingface-hub safetensors tokenizers

# --- 清理 pip 缓存 ---
pip cache purge

# --- 清理 conda 缓存 ---
conda clean --all -y

echo "=== 清理完成 ==="
echo "建议运行: pip list | wc -l  查看剩余包数量"
