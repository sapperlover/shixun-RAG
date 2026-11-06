"""创建 Neo4j 约束与索引：python -m scripts.init_neo4j"""

from app.storage import neo4j_client

if __name__ == "__main__":
    n = neo4j_client.apply_constraints()
    print(f"Neo4j 约束/索引已应用 {n} 条")
    neo4j_client.close()
