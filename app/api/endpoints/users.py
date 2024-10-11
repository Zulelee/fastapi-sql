from fastapi import APIRouter, status, HTTPException, Request
from app.api import notion
import logging
import time
from datetime import datetime, timedelta
import json
from app.api.agents import IdeationFlow, ResearchFlow, ScriptingFlow, modify_script
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from app.core.config import get_settings

# Set up logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("uvicorn")

router = APIRouter()

# MongoDB connection setup
client = AsyncIOMotorClient(get_settings().MONGODB_URL)
db = client.DoctorAI


@router.post("/upsert", description="Upsert Notion DB/Page into Qdrant")
async def upsert(request: dict):
    logger.info(f"Upsert function started")
    start_time = time.time()
    try:
        notion_id = request.get('notion_id')
        doc_type = request.get('doc_type')
        cleanup_mode = request.get('cleanup_mode')
        last_update_time = request.get('last_update_time', "")

        response = await notion.process_notion_data(notion_id, doc_type, cleanup_mode)

        total_time = time.time() - start_time
        return {
            "success": True,
            "total_vectors": response["total_vectors"],
            "total_embedding_cost": response["Embedding_cost"],
            "upsert_details": response["Qdrant_result"],
            "cleanup_mode": cleanup_mode,
            "last_update_time": last_update_time,
            "total_process_time": total_time
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400,
                            detail="Invalid JSON in request body")
    except Exception as error:
        logger.error(f"Error in upsert: {str(error)}")
        raise HTTPException(status_code=500, detail=str(error))

@router.post("/execute_agent_teams", description="The team of agents performs a thorough research and returns high-quality, scientifically accurate scripts ready for teleprompter use")
async def agent_team(
        request: dict, 
        # session: AsyncSession = Depends(get_async_session)
    ):
    logger.info(f"Research started")
    start_time = time.time()
    try:
        initial_input = request.get('initial_input')
        chat_id = ObjectId(request.get('chat_id'))
        collection = db.Ideation
        
        ideation = IdeationFlow(timeout=300, verbose=True)

        ideation_result = await ideation.run(input=initial_input)

        research = ResearchFlow(timeout=300, verbose=True)

        research_result = await research.run(input=initial_input, ideation=ideation_result)

        total_time = time.time() - start_time

        document = {
            "initial_input": initial_input,
            "ideation_result": ideation_result,
            "research_result": research_result,
            "process_time": total_time,
            "chat_id": chat_id,
            "timestamp": time.time()
        }

        # Insert document into MongoDB
        ideation_insert_result = await collection.insert_one(document)

        return {
            "success": True,
            "ideation_result": ideation_result,
            "research_result": research_result,
            "total_process_time": total_time,
            "ideation_id": str(ideation_insert_result.inserted_id)
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400,
                            detail="Invalid JSON in request body")
    except Exception as error:
        logger.error(f"Error in upsert: {str(error)}")
        raise HTTPException(status_code=500, detail=str(error))

@router.post("/generate_script")
async def generate_script(request: dict):
    logger.info(f"Research started")
    start_time = time.time()
    try:
        ideation_result = request.get('ideation_result')
        research_result = request.get('research_result')
        ideation_id = ObjectId(request.get("ideation_id"))
        chat_id = ObjectId(request.get('chat_id'))
        collection = db.Scripts

        scripting = ScriptingFlow(timeout=300, verbose=True)

        response = await scripting.run(ideation=ideation_result, research=research_result)

        total_time = time.time() - start_time

        document = {
            "ideation_id": ideation_id,
            "initial_input": ideation_result,
            "script": response["Final_Script"],
            "mr_beast_score": response["MR_BEAST_SCORE"],
            "george_blackman_score": response["GEORGE_BLACKMAN_SCORE"],
            "chat_id": chat_id,
            "process_time": total_time,
            "timestamp": time.time()
        }

        # Insert document into MongoDB
        await collection.insert_one(document)

        return {
            "success": True,
            "script": response["Final_Script"],
            "mr_beast_score": response["MR_BEAST_SCORE"],
            "george_blackman_score": response["GEORGE_BLACKMAN_SCORE"],
            "total_process_time": total_time
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400,
                            detail="Invalid JSON in request body")
    except Exception as error:
        logger.error(f"Error in upsert: {str(error)}")
        raise HTTPException(status_code=500, detail=str(error))

@router.post("/modify_script")
async def generate_script(request: dict):
    logger.info(f"Research started")
    start_time = time.time()
    try:
        # ideation_id = ObjectId(request.get("script_id"))
        script = str(request.get("script"))
        modification_prompt = str(request.get("modification_prompt"))

        # collection = db.Scripts

        response = await modify_script(script, modification_prompt)

        total_time = time.time() - start_time

        return {
            "success": True,
            "script": response,
            "total_process_time": total_time
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=400,
                            detail="Invalid JSON in request body")
    except Exception as error:
        logger.error(f"Error in upsert: {str(error)}")
        raise HTTPException(status_code=500, detail=str(error))

@router.post("/test_mongodb")
async def test_mongodb():
    try:
        collection = db.Ideation
        document = {
            "initial_input": "Testing",
            "timestamp": time.time()
        }

        # Insert document into MongoDB
        response = await collection.insert_one(document)

        return {
            "success":True,
            "id":str(response.inserted_id)
        }
    except Exception as error:
        logger.error(f"Error in upsert: {str(error)}")
        raise HTTPException(status_code=500, detail=str(error))

@router.get("/get_ideation/{chat_id}")
async def get_recent_ideation(chat_id: str):
    try:
        # Reference the Ideation collection
        collection = db.Ideation
        object_id = ObjectId(chat_id)

        # Retrieve the most recent document from the collection for the given chat_id
        recent_document_cursor = collection.find({"chat_id": object_id}).sort("created_at", -1).limit(1)
        recent_document = None

        # Iterate over the cursor and convert ObjectId to string
        async for document in recent_document_cursor:
            document["_id"] = str(document["_id"])  # Convert ObjectId to string
            document["chat_id"] = str(document["chat_id"])
            recent_document = document

        # Return the recent document
        return {
            "success": True,
            "data": recent_document
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }

@router.get("/get_scripts_by_ideation/{ideation_id}&&{chat_id}")
async def get_scripts_by_ideation(ideation_id: str, chat_id: str):
    try:
        # Convert the ideation_id and chat_id to ObjectId to match MongoDB's _id type
        object_ideation_id = ObjectId(ideation_id)
        object_chat_id = ObjectId(chat_id)

        # Reference the Scripts collection
        collection = db.Scripts

        # Query the Scripts collection for documents with the matching ideation_id and chat_id
        documents_cursor = collection.find({"ideation_id": object_ideation_id, "chat_id": object_chat_id})
        scripts = []

        # Iterate over the cursor and convert ObjectId to string
        async for script in documents_cursor:
            script["_id"] = str(script["_id"])  # Convert ObjectId to string
            script["ideation_id"] = str(script["ideation_id"])  # Convert ideation_id to string
            script["chat_id"] = str(script["chat_id"])  # Convert chat_id to string
            scripts.append(script)

        # Return the list of scripts
        if scripts:
            return {
                "success": True,
                "data": scripts
            }
        else:
            raise HTTPException(status_code=404, detail="No scripts found for the given ideation_id and chat_id")

    except Exception as error:
        logger.error(f"Error retrieving scripts: {str(error)}")
        raise HTTPException(status_code=500, detail="Error retrieving scripts")

@router.post("/save_message")
async def save_message(request: dict):
    logger.info("Save message function started")
    try:
        # Extract the required fields from the request
        message = request.get("message")
        message_type = request.get("message_type") #agent1, agent2, user
        timestamp = request.get("timestamp")
        category = request.get("category") #script, set or text
        chat_id = ObjectId(request.get("chat_id"))

        # Validate the request data
        if not message or not message_type or not timestamp or not chat_id or not category:
            raise HTTPException(status_code=400, detail="Missing required fields")

        # Prepare the document for MongoDB
        document = {
            "message": message,
            "message_type": message_type,
            "category": category, 
            "timestamp": timestamp,
            "chat_id": chat_id
        }

        # Insert the document into the Messages collection
        collection = db.Message  # Ensure that this collection exists in your MongoDB
        insert_result = await collection.insert_one(document)

        return {
            "success": True,
            "id": str(insert_result.inserted_id)
        }

    except Exception as error:
        logger.error(f"Error saving message: {str(error)}")
        raise HTTPException(status_code=500, detail="Error saving message")

@router.get("/get_messages_by_chat/{chat_id}")
async def get_messages_by_chat(chat_id: str):
    logger.info("Get messages by chat ID function started")
    try:
        # Convert the chat_id to ObjectId to match MongoDB's _id type
        object_id = ObjectId(chat_id)

        # Reference the Messages collection
        collection = db.Message  # Ensure this collection exists in your MongoDB

        # Query the Messages collection for documents with the matching chat_id
        documents_cursor = collection.find({"chat_id": object_id})  # Assuming there is a field named "chat_id"
        messages = []

        # Iterate over the cursor and convert ObjectId to string
        async for document in documents_cursor:
            # Convert ObjectId to string for serialization
            document["_id"] = str(document["_id"])  # Convert message ID to string
            document["chat_id"] = str(document["chat_id"])  # Convert chat_id to string if it's in the message
            messages.append(document)

        # Return the list of messages
        if messages:
            return {
                "success": True,
                "data": messages
            }
        else:
            raise HTTPException(status_code=404, detail="No messages found for the given chat ID")

    except Exception as error:
        logger.error(f"Error retrieving messages for chat ID {chat_id}: {str(error)}")
        raise HTTPException(status_code=500, detail="Error retrieving messages")

@router.post("/create_chat")
async def create_chat(request: Request):
    logger.info("Create chat function started")
    try:
        # Parse JSON body from the request
        body = await request.json()

        # Extract the timestamp from the request body and convert it if necessary
        timestamp = body.get("timestamp")
        if not timestamp:
            raise HTTPException(status_code=400, detail="Missing 'timestamp' field in the request")

        # Prepare the document for MongoDB
        document = {
            "timestamp": timestamp  # Use the provided timestamp
        }

        # Reference the Chat collection
        collection = db.Chat  # Ensure this collection exists in your MongoDB

        # Insert the document into the Chat collection
        insert_result = await collection.insert_one(document)

        return {
            "success": True,
            "id": str(insert_result.inserted_id)  # Return the ID of the newly created document
        }

    except Exception as error:
        logger.error(f"Error creating chat: {str(error)}")
        raise HTTPException(status_code=500, detail="Error creating chat")

@router.put("/update_chat/{chat_id}")
async def update_chat(chat_id: str, request: dict):
    logger.info("Update chat function started")
    try:
        # Convert the chat_id to ObjectId to match MongoDB's _id type
        object_id = ObjectId(chat_id)
        
        # Prepare the update data
        update_data = {
            "$set": {
                "initial_message": request.get("initial_message", "")  # Add initial_message to the document
            }
        }

        # Reference the Chat collection
        collection = db.Chat  # Ensure this collection exists in your MongoDB

        # Update the chat document
        result = await collection.update_one({"_id": object_id}, update_data)

        if result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Chat not found")

        return {
            "success": True,
            "message": "Chat updated successfully"
        }

    except Exception as error:
        logger.error(f"Error updating chat: {str(error)}")
        raise HTTPException(status_code=500, detail="Error updating chat")

@router.get("/get_all_chats")
async def get_all_chats():
    logger.info("Get all chats function started")
    try:
        # Reference the Chat collection
        collection = db.Chat  # Ensure this collection exists in your MongoDB

        # Retrieve all documents from the collection
        documents_cursor = collection.find()
        chats = []

        # Iterate over the cursor and convert ObjectId to string
        async for document in documents_cursor:
            document["_id"] = str(document["_id"])  # Convert ObjectId to string
            chats.append(document)

        # Return the list of chats
        return {
            "success": True,
            "data": chats
        }

    except Exception as error:
        logger.error(f"Error retrieving chats: {str(error)}")
        raise HTTPException(status_code=500, detail="Error retrieving chats")

@router.post("/sessions")
async def create_session():
    try:
        login_datetime = datetime.now()
        expiry_datetime = login_datetime + timedelta(hours=24)
        
        collection = db.Session
        
        session_data = {
            "login": login_datetime,
            "expiry": expiry_datetime,
        }
        
        result = await collection.insert_one(session_data)
        
        return {
            "success": True
        }

    except Exception as error:
        logger.error(f"Error retrieving chats: {str(error)}")
        raise HTTPException(status_code=500, detail="Error retrieving chats")
        
@router.get("/sessions/latest")
async def get_latest_session():
    try:
        collection = db.Session
        latest_session = await collection.find_one(
            sort=[("login_datetime", -1)]
        )
        
        if latest_session is None:
            return {"success": True, "expiry": None}
        
        return {
            "success": True,
            "expiry": latest_session["expiry"]
        }
        
    except Exception as error:
        logger.error(f"Error retrieving chats: {str(error)}")
        raise HTTPException(status_code=500, detail="Error retrieving chats")
