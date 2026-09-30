import json
import os
from dotenv import load_dotenv
from fastapi import FastAPI, Request, Response, BackgroundTasks
from twilio.rest import Client
# TwiML is Twilio Markup Language
from twilio.twiml.messaging_response import MessagingResponse
from gemini import generate_health_response

# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

print("\n========== STARTING HEALTH AGENT ==========")

load_dotenv()

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER")
TWILIO_CONTENT_SID = os.getenv("TWILIO_CONTENT_SID")

print("[ENV] TWILIO_ACCOUNT_SID:", "Loaded" if TWILIO_ACCOUNT_SID else "MISSING")
print("[ENV] TWILIO_AUTH_TOKEN:", "Loaded" if TWILIO_AUTH_TOKEN else "MISSING")
print("[ENV] TWILIO_PHONE_NUMBER:", "Loaded" if TWILIO_PHONE_NUMBER else "MISSING")
print("[ENV] TWILIO_CONTENT_SID:", "Loaded" if TWILIO_CONTENT_SID else "Not configured")

if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER]):
    raise ValueError("Twilio credentials are missing from environment variables!")

print("[Twilio] Credentials loaded successfully.")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

app = FastAPI()

print("[FastAPI] Application initialized.")
print("============================================\n")


# ============================================================
# BACKGROUND MESSAGE PROCESSING
# ============================================================

def process_and_send_whatsapp(
    message: str,
    clean_sender: str,
    image_url: str | None = None,
):
    print("\n========== BACKGROUND MESSAGE TASK STARTED ==========")

    try:
        reply_text = generate_health_response(
            user_query=message,
            phone_number=clean_sender,
            image_url=image_url
        )
    except Exception as e:
        print("[Background] Message processing failed:", type(e).__name__, e)
        reply_text = "Sorry, I couldn't process that message right now. Please try again."

    try:
        message_params = {
            "from_": f"whatsapp:{TWILIO_PHONE_NUMBER}",
            "to": f"whatsapp:{clean_sender}"
        }
        if TWILIO_CONTENT_SID:
            message_params["content_sid"] = TWILIO_CONTENT_SID
            message_params["content_variables"] = json.dumps({"1": reply_text})
        else:
            message_params["body"] = reply_text

        message_response = twilio_client.messages.create(**message_params)
        print("[Background] WhatsApp reply sent. SID:", message_response.sid)
    except Exception as e:
        error_code = getattr(e, "code", None)
        if str(error_code) == "21654":
            print(
                "[Background] Twilio rejected the WhatsApp reply with error "
                "21654. This process "
                + (
                    "sent a Content Template; verify TWILIO_CONTENT_SID is a "
                    "WhatsApp-approved template with a {{1}} variable."
                    if TWILIO_CONTENT_SID
                    else
                    "sent a body-only message; no ContentSid or ContentVariables "
                    "were configured. The Twilio account/sender requires a "
                    "WhatsApp-approved Content Template. Create/approve one "
                    "after enabling Content Templates for the account, then "
                    "set TWILIO_CONTENT_SID to its HX SID and restart the app."
                )
            )
        else:
            print(
                "[Background] WhatsApp reply failed:",
                type(e).__name__,
                "Twilio code:",
                error_code or "unavailable"
            )

    print("========== BACKGROUND MESSAGE TASK ENDED ==========\n")


# ============================================================
# HOME
# ============================================================

@app.get("/")
def home():
    print("[GET /] Health check received.")

    return {
        "status": "Health Agent with Vision is running smoothly"
    }


# ============================================================
# WHATSAPP WEBHOOK
# ============================================================

@app.api_route("/whatsapp", methods=["GET", "POST"])
async def whatsapp(
    request: Request,
    background_tasks: BackgroundTasks
):

    print("\n================================================")
    print("           WHATSAPP WEBHOOK HIT")
    print("================================================")

    print("[Request] Method:", request.method)
    try:

        # ----------------------------------------------------
        # READ TWILIO DATA
        # ----------------------------------------------------

        if request.method == "POST":
            print("[Request] Reading POST form data...")
            data = await request.form()
            print("[Request] Form data received:", data)
        else:
            print("[Request] Reading GET query parameters...")
            data = request.query_params

        print("[Request] Form fields received:", ", ".join(data.keys()))

        # ----------------------------------------------------
        # EXTRACT MESSAGE
        # ----------------------------------------------------

        message = data.get("Body", "")
        sender = data.get("From", "")
        image_url = data.get("MediaUrl0", None)

        print("\n[WhatsApp Data]")
        print("Message received:", bool(message))
        print("Sender received:", bool(sender))
        print("Image received:", bool(image_url))

        # Someone might send a message without a sender (e.g., if the request is malformed). Handle that case gracefully.
        if not sender:
            return Response(
                content="Missing WhatsApp sender",
                status_code=400
            )

        # ----------------------------------------------------
        # CLEAN PHONE NUMBER
        # ----------------------------------------------------

        clean_sender = sender.removeprefix("whatsapp:").strip()

        # ----------------------------------------------------
        # CHECK MESSAGE TYPE
        # ----------------------------------------------------

        if image_url:
            print("\n[Message Type] IMAGE + TEXT/IMAGE MESSAGE")

        else:
            print("\n[Message Type] TEXT MESSAGE")

        # ----------------------------------------------------
        # PROCESS MESSAGE
        # ----------------------------------------------------

        # Ensure to check for both empty text or image URL, as a user might send empty msg wt. an image or vice versa.
        if not message.strip() and not image_url:
            return Response(
                content="No text or supported image was received",
                status_code=400
            )

        twilio_resp = MessagingResponse()
        # If there is an image, process it in background and send an ack. that process has started.
        if image_url:
            background_tasks.add_task(
                process_and_send_whatsapp,
                message,
                clean_sender,
                image_url
            )
            acknowledgement = "📸 Analyzing your image. I'll message you with the results shortly."
            twilio_resp.message(acknowledgement)
        else:
            try:
                reply_text = generate_health_response(
                    user_query=message,
                    phone_number=clean_sender,
                    image_url=None
                )
                print("[Webhook] Reply generated:", reply_text)
            except Exception as e:
                print("[Webhook] Message processing failed:", type(e).__name__, e)
                reply_text = "Sorry, I couldn't process that message right now. Please try again."
            twilio_resp.message(reply_text)

        return Response(
            content=str(twilio_resp),
            media_type="application/xml"
        )

    except Exception as e:

        print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
        print("[WEBHOOK ERROR]")
        print("[ERROR TYPE]:", type(e).__name__)
        print("[ERROR]:", e)
        print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!\n")

        return Response(
            content="Internal server error",
            status_code=500
        )