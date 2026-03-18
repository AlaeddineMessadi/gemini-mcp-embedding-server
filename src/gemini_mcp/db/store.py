import os
import chromadb
from typing import List, Dict, Any, Optional

# default to user's home directory for DB persistence
DEFAULT_DB_PATH = os.path.expanduser("~/.gemini_mcp_db")
COLLECTION_NAME = "documents"

class ChromaStore:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        # PersistentClient writes data to disk automatically
        self.client = chromadb.PersistentClient(path=self.db_path)
        self.collection = self.client.get_or_create_collection(name=COLLECTION_NAME)
        
    def add_chunks(self, chunks: List[Dict[str, Any]], embeddings: List[List[float]]):
        """
        Adds text chunks and their corresponding embeddings to ChromaDB.
        `chunks` should be a list of dicts: {"text": str, "metadata": dict}
        """
        if not chunks or not embeddings:
            return
            
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks must match number of embeddings.")
            
        ids = []
        documents = []
        metadatas = []
        
        for chunk in chunks:
            # Create a unique ID combining source and chunk_index
            source = chunk["metadata"]["source"]
            chunk_idx = chunk["metadata"]["chunk_index"]
            doc_id = f"{source}::{chunk_idx}"
            
            ids.append(doc_id)
            # Add a fallback text for images so they don't break chromadb requirements
            documents.append(chunk.get("text", f"[{chunk['metadata'].get('type', 'document')}] {source}"))
            metadatas.append(chunk["metadata"])
            
        # We use upsert so we overwrite if it already exists (updating)
        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

    def delete_directory(self, directory_path: str) -> int:
        """
        Deletes all chunks that originated from within a specific directory.
        Returns the number of deleted vectors.
        """
        # We have to fetch all sources, find matching ones, and delete by ID since Chroma
        # metadata filtering on string startswith is limited.
        data = self.collection.get(include=["metadatas"])
        if not data or not data["metadatas"]:
            return 0
            
        ids_to_delete = []
        for doc_id, meta in zip(data["ids"], data["metadatas"]):
            if meta and "source" in meta and meta["source"].startswith(directory_path):
                ids_to_delete.append(doc_id)
                
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)
            
        return len(ids_to_delete)
        
    def delete_file(self, file_path: str) -> int:
        """
        Deletes all chunks exactly matching a specific source file path.
        """
        data = self.collection.get(include=["metadatas"])
        if not data or not data["metadatas"]:
            return 0
            
        ids_to_delete = []
        for doc_id, meta in zip(data["ids"], data["metadatas"]):
            if meta and meta.get("source") == file_path:
                ids_to_delete.append(doc_id)
                
        if ids_to_delete:
            self.collection.delete(ids=ids_to_delete)
            
        return len(ids_to_delete)
        
    def query(self, query_embedding: List[float], n_results: int = 5) -> List[Dict[str, Any]]:
        """
        Queries ChromaDB using the query vector and returns the top matches.
        """
        if not query_embedding:
            return []
            
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results
        )
        
        matches = []
        # chromadb returns lists of lists because of batch querying
        if results and results["documents"] and results["documents"][0]:
            docs = results["documents"][0]
            metas = results["metadatas"][0]
            distances = results["distances"][0] if "distances" in results and results["distances"] else [0] * len(docs)
            
            for doc, meta, dist in zip(docs, metas, distances):
                matches.append({
                    "text": doc,
                    "metadata": meta,
                    "distance": dist
                })
                
        return matches

    def list_indexed_sources(self) -> List[str]:
        """Returns a list of unique 'source' files indexed in the database."""
        # This gets expensive for huge databases, but for local docs it's fine.
        data = self.collection.get(include=["metadatas"])
        if not data or not data["metadatas"]:
            return []
            
        sources = set()
        for meta in data["metadatas"]:
            if meta and "source" in meta:
                sources.add(meta["source"])
                
        return sorted(list(sources))
