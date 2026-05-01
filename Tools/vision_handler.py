"""
JARVIS Vision Handler
Handles image analysis, face recognition, OCR, and visual memory
"""

import os
import base64
import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
import google.generativeai as genai
from PIL import Image
import io

# Configure Gemini
genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))

class VisionHandler:
    """
    JARVIS AI Eyes - Vision and Image Analysis System
    
    Capabilities:
    - Image analysis and scene understanding
    - Face detection and recognition
    - OCR (text extraction from images)
    - Object and landmark identification
    - Visual memory and comparison
    """
    
    def __init__(self, storage_path: str = "jarvis_visual_memory"):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(exist_ok=True)
        
        # Initialize Gemini Vision model
        self.vision_model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Visual memory database (simple JSON for now)
        self.memory_db_path = self.storage_path / "visual_memory.json"
        self._load_memory_db()
        
    def _load_memory_db(self):
        """Load visual memory database"""
        if self.memory_db_path.exists():
            with open(self.memory_db_path, 'r', encoding='utf-8') as f:
                self.memory_db = json.load(f)
        else:
            self.memory_db = {
                "images": [],
                "faces": [],
                "important_moments": []
            }
            self._save_memory_db()
    
    def _save_memory_db(self):
        """Save visual memory database"""
        with open(self.memory_db_path, 'w', encoding='utf-8') as f:
            json.dump(self.memory_db, f, indent=2, ensure_ascii=False)
    
    async def analyze_image(
        self,
        image_path: str,
        analysis_type: str = "general",
        user_query: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze an image using Gemini Vision
        
        Args:
            image_path: Path to image file or base64 encoded image
            analysis_type: Type of analysis (general, face, ocr, object, scene)
            user_query: Optional specific question about the image
            
        Returns:
            Analysis results with description, detected objects, text, etc.
        """
        try:
            # Load image
            if image_path.startswith("data:image"):
                # Base64 encoded image
                image_data = image_path.split(",")[1]
                image_bytes = base64.b64decode(image_data)
                image = Image.open(io.BytesIO(image_bytes))
            else:
                # File path
                image = Image.open(image_path)
            
            # Prepare prompt based on analysis type
            prompts = {
                "general": """Analyze this image in detail. Provide:
1. Main subject/scene description
2. Notable objects and their positions
3. Colors and lighting
4. Any text visible in the image
5. Overall context and setting
Be concise but comprehensive.""",

                "face": """Analyze faces in this image. For each face detected:
1. Approximate age and gender
2. Facial expression and emotion
3. Notable features
4. Position in image
If you recognize a famous public figure, identify them with confidence level.
NEVER guess unknown identities - clearly state if unknown.""",

                "ocr": """Extract ALL visible text from this image.
Provide:
1. Complete text transcription
2. Text layout and structure
3. Language detected
4. Text quality and readability
Format the output clearly.""",

                "object": """Identify and list all objects in this image.
For each object provide:
1. Object name
2. Position/location in image
3. Size (relative)
4. Confidence level
Be thorough and precise.""",

                "scene": """Analyze the scene in this image.
Provide:
1. Location type (indoor/outdoor, specific place if identifiable)
2. Time of day (if determinable)
3. Weather conditions (if visible)
4. Activity or event happening
5. Overall atmosphere and mood"""
            }
            
            # Use custom query if provided, otherwise use preset prompt
            prompt = user_query if user_query else prompts.get(analysis_type, prompts["general"])
            
            # Generate analysis
            response = self.vision_model.generate_content([prompt, image])
            
            result = {
                "success": True,
                "analysis_type": analysis_type,
                "description": response.text,
                "timestamp": datetime.now().isoformat(),
                "image_path": str(image_path) if not image_path.startswith("data:") else "base64_image"
            }
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "analysis_type": analysis_type
            }
    
    async def save_visual_memory(
        self,
        image_path: str,
        description: str,
        memory_type: str = "general",
        metadata: Optional[Dict] = None
    ) -> Dict[str, Any]:
        """
        Save an image to visual memory with description
        
        Args:
            image_path: Path to image
            description: Description or context
            memory_type: Type (general, face, important, event)
            metadata: Additional metadata
            
        Returns:
            Save confirmation with memory ID
        """
        try:
            # Generate unique ID
            memory_id = f"visual_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            
            # Copy image to storage
            image = Image.open(image_path)
            saved_path = self.storage_path / f"{memory_id}.png"
            image.save(saved_path)
            
            # Create memory entry
            memory_entry = {
                "id": memory_id,
                "image_path": str(saved_path),
                "description": description,
                "type": memory_type,
                "timestamp": datetime.now().isoformat(),
                "metadata": metadata or {}
            }
            
            # Add to appropriate category
            if memory_type == "face":
                self.memory_db["faces"].append(memory_entry)
            elif memory_type == "important":
                self.memory_db["important_moments"].append(memory_entry)
            else:
                self.memory_db["images"].append(memory_entry)
            
            self._save_memory_db()
            
            return {
                "success": True,
                "memory_id": memory_id,
                "saved_path": str(saved_path),
                "message": f"Visual memory saved: {memory_id}"
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def compare_images(
        self,
        image1_path: str,
        image2_path: str,
        comparison_type: str = "similarity"
    ) -> Dict[str, Any]:
        """
        Compare two images
        
        Args:
            image1_path: First image
            image2_path: Second image
            comparison_type: Type of comparison (similarity, difference, face_match)
            
        Returns:
            Comparison results
        """
        try:
            image1 = Image.open(image1_path)
            image2 = Image.open(image2_path)
            
            prompts = {
                "similarity": "Compare these two images. Are they similar? What are the similarities and differences?",
                "difference": "Identify all differences between these two images. Be specific and detailed.",
                "face_match": "Do these images contain the same person? Analyze facial features and provide confidence level."
            }
            
            prompt = prompts.get(comparison_type, prompts["similarity"])
            
            response = self.vision_model.generate_content([
                prompt,
                image1,
                "Image 1 above. Image 2 below:",
                image2
            ])
            
            return {
                "success": True,
                "comparison_type": comparison_type,
                "result": response.text,
                "timestamp": datetime.now().isoformat()
            }
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    async def search_visual_memory(
        self,
        query: str,
        memory_type: Optional[str] = None,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Search visual memory using text query
        
        Args:
            query: Search query
            memory_type: Filter by type (face, important, general)
            limit: Maximum results
            
        Returns:
            List of matching memories
        """
        # Get all memories of specified type
        if memory_type == "face":
            memories = self.memory_db["faces"]
        elif memory_type == "important":
            memories = self.memory_db["important_moments"]
        else:
            memories = self.memory_db["images"]
        
        # Simple text matching (can be enhanced with embeddings)
        query_lower = query.lower()
        matches = []
        
        for memory in memories:
            description = memory.get("description", "").lower()
            if query_lower in description:
                matches.append(memory)
        
        return matches[:limit]
    
    async def identify_person(
        self,
        image_path: str,
        check_memory: bool = True
    ) -> Dict[str, Any]:
        """
        Identify a person in an image
        
        Args:
            image_path: Path to image
            check_memory: Whether to check against saved faces
            
        Returns:
            Identification results
        """
        try:
            # First, analyze the face
            analysis = await self.analyze_image(image_path, analysis_type="face")
            
            if not analysis["success"]:
                return analysis
            
            result = {
                "success": True,
                "analysis": analysis["description"],
                "matched_memory": None
            }
            
            # Check against saved faces if requested
            if check_memory:
                for face_memory in self.memory_db["faces"]:
                    # Compare with saved face
                    comparison = await self.compare_images(
                        image_path,
                        face_memory["image_path"],
                        comparison_type="face_match"
                    )
                    
                    # Simple matching logic (can be enhanced)
                    if "same person" in comparison["result"].lower() or "match" in comparison["result"].lower():
                        result["matched_memory"] = face_memory
                        break
            
            return result
            
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    
    def get_memory_stats(self) -> Dict[str, int]:
        """Get visual memory statistics"""
        return {
            "total_images": len(self.memory_db["images"]),
            "total_faces": len(self.memory_db["faces"]),
            "important_moments": len(self.memory_db["important_moments"]),
            "storage_path": str(self.storage_path)
        }


# Global instance
_vision_handler = None

def get_vision_handler() -> VisionHandler:
    """Get or create global vision handler instance"""
    global _vision_handler
    if _vision_handler is None:
        _vision_handler = VisionHandler()
    return _vision_handler
