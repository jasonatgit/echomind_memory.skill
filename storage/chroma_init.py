# echomind_memory.skill/storage/chroma_init.py

import chromadb
import os


def init_chroma():
    """
    初始化 ChromaDB 向量库，创建知识库集合
    若数据库目录不存在，则自动创建
    """
    chroma_path = os.getenv("CHROMA_PATH", "./echomind_chroma")
    client = chromadb.PersistentClient(path=chroma_path)

    # 创建知识集合，使用 cosine 距离
    collection = client.get_or_create_collection(
        name="knowledge_base", metadata={"hnsw:space": "cosine"}
    )

    print(f"✅ ChromaDB initialized at: {chroma_path}")
    print(f"✅ Collection 'knowledge_base' ready for embeddings.")
    return client, collection


if __name__ == "__main__":
    init_chroma()
