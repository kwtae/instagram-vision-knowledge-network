import os
import logging
import chromadb
from typing import List, Dict

logger = logging.getLogger("mcp_vision_server.db_manager")

class VectorDBManager:
    def __init__(self, db_path: str = "./chroma_db"):
        self.db_path = db_path
        # PersistentClient를 사용하여 로컬에 데이터 저장
        self.client = chromadb.PersistentClient(path=db_path)
        
        # 레퍼런스(텍스트/태그 결합) 저장을 위한 컬렉션 생성 (존재하면 가져오기)
        self.collection = self.client.get_or_create_collection(
            name="references",
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"ChromaDB 초기화 완료: {db_path}")

    def add_reference(self, file_id: str, text: str, tags: List[str], metadata: Dict = None):
        """파일의 텍스트와 태그를 벡터 DB에 추가합니다."""
        if metadata is None:
            metadata = {}
        
        metadata["tags"] = ",".join(tags)
        metadata["filepath"] = file_id
        
        # 검색용 코퍼스는 텍스트와 태그의 결합
        document = f"Tags: {', '.join(tags)}\nContent: {text}"
        
        try:
            self.collection.add(
                documents=[document],
                metadatas=[metadata],
                ids=[file_id]
            )
            logger.info(f"DB에 레퍼런스 추가 완료: {file_id}")
        except Exception as e:
            logger.error(f"DB 추가 중 오류 발생 {file_id}: {e}")

    def search_similar(self, query: str, n_results: int = 5) -> List[Dict]:
        """쿼리와 가장 유사한 레퍼런스를 검색합니다."""
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=n_results
            )
            
            # ChromaDB 결과 포맷 변환
            matched_items = []
            if results["ids"] and len(results["ids"]) > 0:
                for idx in range(len(results["ids"][0])):
                    item = {
                        "id": results["ids"][0][idx],
                        "document": results["documents"][0][idx],
                        "metadata": results["metadatas"][0][idx],
                        "distance": results["distances"][0][idx]
                    }
                    matched_items.append(item)
            return matched_items
        except Exception as e:
            logger.error(f"DB 검색 중 오류 발생 '{query}': {e}")
            return []

    def update_tags(self, file_id: str, new_tags: str) -> bool:
        """기존 문서의 태그를 변경하고 DB를 업데이트합니다. 양방향 수정을 지원합니다."""
        try:
            result = self.collection.get(ids=[file_id], include=["documents", "metadatas"])
            if not result or not result["ids"]:
                logger.warning(f"수정하려는 ID를 찾을 수 없습니다: {file_id}")
                return False
                
            doc = result["documents"][0]
            meta = result["metadatas"][0]
            
            # 메타데이터 업데이트
            meta["tags"] = new_tags
            
            # 본문 내 Tags 헤더도 업데이트
            if "\nContent: " in doc:
                content_part = doc.split("\nContent: ", 1)[-1]
                new_doc = f"Tags: {new_tags}\nContent: {content_part}"
            else:
                new_doc = f"Tags: {new_tags}\n{doc}"
                
            self.collection.update(
                ids=[file_id],
                documents=[new_doc],
                metadatas=[meta]
            )
            logger.info(f"DB 태그 수정(Write-back) 완료: {file_id} -> {new_tags}")
            return True
        except Exception as e:
            logger.error(f"DB 태그 수정 오류 {file_id}: {e}")
            return False

    def get_file_network(self, file_id: str, max_siblings: int = 5) -> List[Dict]:
        """특정 파일과 유사한(공유된 속성/태그를 가진) 파일 네트워크를 반환합니다."""
        try:
            # 먼저 대상 파일의 정보를 가져옵니다.
            result = self.collection.get(ids=[file_id], include=["documents", "metadatas"])
            if not result["ids"]:
                return []
                
            document = result["documents"][0]
            
            # 해당 문서 내용으로 유사도 검색을 수행 (자기 자신 제외하기 위해 n_results + 1)
            similar_results = self.search_similar(query=document, n_results=max_siblings + 1)
            
            # 본인 제외
            network = [res for res in similar_results if res["id"] != file_id]
            return network[:max_siblings]
            
        except Exception as e:
            logger.error(f"네트워크 검색 중 오류 발생 '{file_id}': {e}")
            return []

# 싱글톤 인스턴스 생성
db = VectorDBManager()
