import json
import os
from datetime import datetime
from pathlib import Path
import httpx
import ollama

DATA_FILE = Path(__file__).resolve().with_name("data.json")


# ============================================================
# BASIC HELPERS
# ============================================================

def get_current_timestamp() -> str:
    timestamp = datetime.now().isoformat()
    print("[Timestamp]", timestamp)
    return timestamp

# Loads the entire data.json file
def load_all_data() -> dict:

    print("\n[DATA] Loading data...")

    if os.path.exists(DATA_FILE):

        print(f"[DATA] Found {DATA_FILE}")

        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            print(
                f"[DATA] Loaded successfully. "
                f"Number of users: {len(data)}"
            )

            return data

        except Exception as e:

            print("[DATA ERROR] Could not load data.json")
            print("[DATA ERROR TYPE]:", type(e).__name__)
            print("[DATA ERROR]:", e)

    else:
        print(f"[DATA] {DATA_FILE} does not exist. Starting with empty data.")

    return {}

# Saves the data to data.json file (chat logs, food logs...)
def save_all_data(data: dict):

    print("\n[DATA] Saving data...")

    try:

        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(
                data,
                f,
                indent=2,
                ensure_ascii=False
            )

        print("[DATA] Saved successfully.")

    except Exception as e:

        print("[DATA ERROR] Could not save data.json")
        print("[DATA ERROR TYPE]:", type(e).__name__)
        print("[DATA ERROR]:", e)


# ============================================================
# USER
# ============================================================

# If user already there, return it, Else create a new user with default profile and return it
def get_or_create_user(phone_number: str, data: dict) -> dict:

    print("\n[USER] Looking for user:", phone_number)

    if phone_number not in data:

        print("[USER] User does not exist.")
        print("[USER] Creating new user...")

        data[phone_number] = {
            "profile": {
                "name": "Random",
                "age": 22,
                "activity_level": "moderate"
            },

            "wearables": {
                "2026-09-28T23:59:59": {
                    "steps_today": 8420,
                    "sleep_hours_last_night": 7.2,
                    "avg_heart_rate_bpm": 71,
                }
            },

            "food_log": [],
            "chat_logs": [],
            "pending_food_confirmation": None,
        }

        print("[USER] New user created.")

    else:

        print("[USER] Existing user found.")

        if "chat_logs" not in data[phone_number]:
            print("[USER] Adding missing chat_logs.")
            data[phone_number]["chat_logs"] = []

        if "food_log" not in data[phone_number]:
            print("[USER] Adding missing food_log.")
            data[phone_number]["food_log"] = []

        if "pending_food_confirmation" not in data[phone_number]:
            print("[USER] Adding missing pending_food_confirmation.")
            data[phone_number]["pending_food_confirmation"] = None

    return data[phone_number]


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

# Downloads image bytes from Twilio media URL using Twilio creds.
def download_image_bytes(image_url: str) -> bytes | None:

    print("\n========== IMAGE DOWNLOAD ==========")

    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")

    print(
        "[Image] Twilio SID:",
        "Loaded" if account_sid else "MISSING"
    )

    print(
        "[Image] Twilio Auth Token:",
        "Loaded" if auth_token else "MISSING"
    )

    try:

        print("[Image] Sending GET request to Twilio...")

        auth = (
            (account_sid, auth_token)
            if account_sid and auth_token
            else None
        )

        response = httpx.get(
            image_url,
            auth=auth,
            follow_redirects=True,
            timeout=30.0
        )

        print("[Image] HTTP status:", response.status_code)
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if not content_type.startswith("image/"):
            raise ValueError(
                f"Twilio media endpoint returned non-image content: {content_type or 'unknown'}"
            )

        print("[Image] Download successful:", len(response.content), "bytes")
        return response.content

    except Exception as e:

        print("[Image ERROR] Exception while downloading image.")
        print("[Image ERROR TYPE]:", type(e).__name__)
        print("[Image ERROR]:", e)

    return None


# ============================================================
# MAIN HEALTH RESPONSE
# ============================================================

def generate_health_response(
    user_query: str,
    phone_number: str,
    image_url: str = None
) -> str:

    print("\n")
    print("================================================")
    print("       generate_health_response() STARTED")
    print("================================================")

    print("[Input] User query:", user_query)
    print("[Input] Phone number:", phone_number)
    print("[Input] Image URL:", image_url)

    # --------------------------------------------------------
    # LOAD DATA
    # --------------------------------------------------------

    data = load_all_data()

    # --------------------------------------------------------
    # USER
    # --------------------------------------------------------

    user_record = get_or_create_user(
        phone_number,
        data
    )

    print("[User] Name:", user_record["profile"]["name"])
    print("[User] Age:", user_record["profile"]["age"])
    print("[User] Activity:", user_record["profile"]["activity_level"])

    user_input = user_query.strip() if user_query else ""

    print("[Input] Cleaned user input:", user_input)

    timestamp = get_current_timestamp()

    # ========================================================
    # PENDING FOOD CONFIRMATION
    # ========================================================

    pending = user_record.get(
        "pending_food_confirmation"
    )

    print("\n[Food Confirmation]")
    print(
        "[Food Confirmation] Pending:",
        bool(pending)
    )

    if pending and not image_url:

        print("[Food Confirmation] Checking user response...")

        affirmative_keywords = [
            "yes",
            "yeah",
            "yep",
            "confirm",
            "correct",
            "ok",
            "sure"
        ]

        if any(
            kw in user_input.lower()
            for kw in affirmative_keywords
        ):

            print("[Food Confirmation] User confirmed food.")

            user_record["food_log"].append(pending)

            user_record["pending_food_confirmation"] = None

            reply = (
                f"✅ Got it! Logged "
                f"{pending['quantity']} of "
                f"{pending['food_item']} "
                f"({pending['meal_type']}) "
                f"into your food log."
            )

            print("[Food Confirmation] Reply:", reply)

            user_record["chat_logs"].append({
                "timestamp": timestamp,
                "user_query": user_input,
                "assistant_response": reply,
            })

            save_all_data(data)

            print("[Food Confirmation] Returning response.")

            return reply

        else:

            print(
                "[Food Confirmation] "
                "User did not confirm. Clearing pending food."
            )

            user_record[
                "pending_food_confirmation"
            ] = None

            save_all_data(data)

    # ========================================================
    # IMAGE / VISION PROCESSING
    # ========================================================

    if image_url:

        print("\n========== VISION FLOW ==========")

        print("[Vision] Image URL received.")

        image_bytes = download_image_bytes(
            image_url
        )

        if not image_bytes:

            print("[Vision ERROR] No image bytes received.")

            return (
                "⚠️ I received an image URL, but was "
                "unable to download it for analysis. "
                "Please check your credentials."
            )

        print(
            "[Vision] Image bytes received:",
            len(image_bytes),
            "bytes"
        )

        vision_prompt = (
            "Analyze this food image. Identify the visible "
            "food item(s), estimate the portion size, and "
            "state the probable meal type "
            "(breakfast, lunch, dinner, snack). "
            "Formulate your response by explicitly asking "
            "the user to confirm these details before logging."
        )

        print("[Vision] Prompt prepared.")
        print("[Vision] Calling Ollama vision model...")

        try:

            res = ollama.chat(
                model="gemma4",
                messages=[
                    {
                        "role": "user",
                        "content": vision_prompt,
                        "images": [image_bytes],
                    }
                ],
                options={
                    "temperature": 0.2
                },
            )

            print("[Vision] Ollama response received.")

            ai_response = (
                res["message"]["content"]
                .strip()
            )

            print("[Vision] AI response:")
            print(ai_response)

            user_record[
                "pending_food_confirmation"
            ] = {
                "timestamp": timestamp,
                "food_item": "Identified Image Meal",
                "quantity": "1 serving (estimated)",
                "meal_type": "Snack/Meal",
                "image_url": image_url,
                "ai_summary": ai_response,
            }

            print(
                "[Vision] Pending food confirmation saved."
            )

            user_record["chat_logs"].append({
                "timestamp": timestamp,
                "user_query": "[Image Uploaded]",
                "assistant_response": ai_response,
                "image_url": image_url,
            })

            save_all_data(data)

            print("[Vision] Returning vision response.")

            return ai_response

        except Exception as e:

            print("\n[Vision ERROR]")
            print("[Vision ERROR TYPE]:", type(e).__name__)
            print("[Vision ERROR]:", e)

            return (
                "I'm having trouble analyzing this image "
                "right now. Please verify that the "
                "`gemma4` model is loaded in Ollama."
            )

    # ========================================================
    # TEXT PROCESSING
    # ========================================================

    print("\n========== TEXT FLOW ==========")

    recent_chat = user_record["chat_logs"][-5:]

    print(
        "[Text] Number of previous messages used:",
        len(recent_chat)
    )

    system_instruction = f"""
    You are a friendly, WhatsApp-based Health Info & Vision Assistant.

    STRICT SAFETY & BOUNDARY RULES:
    1. Strictly INFORMATIONAL. You MUST NOT diagnose, prescribe, or provide medical advice.
    2. Ground your responses strictly in the provided User Profile, Wearable Data, and Food Log.
    3. If the user asks about steps, sleep, heart rate, or food logs, refer to the provided context below.
    4. If a query is completely out of scope, unclear, or unsupported, respond with a polite fallback offering assistance with steps, sleep, heart rate, or food logging.
    5. Keep responses structured and concise for WhatsApp readability.

    USER PROFILE & WEARABLES CONTEXT:
    - Name: {user_record['profile']['name']}
    - Age: {user_record['profile']['age']}
    - Activity Level: {user_record['profile']['activity_level']}
    - Latest Wearables: {json.dumps(user_record['wearables'], indent=2)}
    - Food Log History: {json.dumps(user_record['food_log'], indent=2)}
    """

    # Building conv. history for LLM with system instr. , rcent chats and current user input
    messages = [
        {
            "role": "system",
            "content": system_instruction
        }
    ]

    for chat in recent_chat:

        messages.append({
            "role": "user",
            "content": chat.get(
                "user_query",
                ""
            )
        })

        messages.append({
            "role": "assistant",
            "content": chat.get(
                "assistant_response",
                ""
            )
        })

    messages.append({
        "role": "user",
        "content": user_input
    })

    print(
        "[Text] Total messages being sent to LLM:",
        len(messages)
    )

    # ========================================================
    # CALL OLLAMA
    # ========================================================

    print("[Text] Calling Ollama text model...")

    try:

        response = ollama.chat(
            model="llama3.2",
            messages=messages,
            options={
                "temperature": 0.2
            },
        )

        print("[Text] Ollama response received.")

        ai_response = (
            response["message"]["content"]
            .strip()
        )

        print("[Text] AI response:")
        print(ai_response)

    except Exception as e:

        print("\n[Text ERROR]")
        print("[Text ERROR TYPE]:", type(e).__name__)
        print("[Text ERROR]:", e)

        ai_response = (
            "I am unable to process your query right now. "
            "Please check your local Ollama instance."
        )

    # ========================================================
    # FOOD DETECTION
    # ========================================================

    is_food = any(
        kw in user_input.lower()
        for kw in [
            "ate",
            "eat",
            "food",
            "lunch",
            "dinner",
            "breakfast",
            "log",
            "snack"
        ]
    )

    print("[Food Detection] Is food query:", is_food)

    if is_food and not any(
        kw in user_input.lower()
        for kw in [
            "what",
            "show",
            "view",
            "list"
        ]
    ):

        print("[Food Detection] Adding food entry.")

        user_record["food_log"].append({
            "timestamp": timestamp,
            "entry": user_input,
            "ai_summary": ai_response,
        })

    # ========================================================
    # CHAT LOG
    # ========================================================

    print("[Chat Log] Saving conversation.")

    user_record["chat_logs"].append({
        "timestamp": timestamp,
        "user_query": user_input,
        "assistant_response": ai_response,
    })

    # ========================================================
    # SAVE
    # ========================================================

    save_all_data(data)

    print(
        "================================================"
    )
    print(
        "       generate_health_response() FINISHED"
    )
    print(
        "================================================\n"
    )

    return ai_response