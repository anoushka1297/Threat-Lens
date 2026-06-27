import requests
import base64
from datetime import datetime

# =========================
# KEYS
# =========================

OPENAI_API_KEY = "insert-key"

TELEGRAM_BOT_TOKEN = "insert-key"

# =========================
# TELEGRAM CHAT IDs
# =========================

CHAT_IDS = [
    
]

CAMERA_LOCATION = "Main Entrance — Block 2"


def describe_threat(image_path):
    try:
        with open(image_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        prompt = (
            "You are assisting a security alert system. "
            "Look at this image carefully. It may contain a person holding a weapon. "
            "Return a short factual emergency description in plain text only.\n\n"
            "Format exactly like this:\n"
            "Weapon: <weapon type or unclear>\n"
            "Person: <visible clothing colours, approximate build, posture, and other visible features>\n"
            "Summary: <one short sentence suitable for a Telegram security alert>\n\n"
            "Rules:\n"
            "- Only describe what is clearly visible in the image.\n"
            "- Do not identify the person by name.\n"
            "- Do not guess race, nationality, religion, or exact age.\n"
            "- If the weapon is a gun, say gun.\n"
            "- If the weapon is unclear, say unclear weapon.\n"
            "- Keep the whole answer under 3 lines."
        )

        response = requests.post(
            "https://api.openai.com/v1/responses",
            headers={
                "Authorization": f"Bearer {OPENAI_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-4.1-mini",
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "input_text",
                                "text": prompt,
                            },
                            {
                                "type": "input_image",
                                "image_url": f"data:image/jpeg;base64,{image_b64}",
                            },
                        ],
                    }
                ],
                "max_output_tokens": 150,
            },
            timeout=20,
        )

        data = response.json()
        print("RAW RESPONSE:", data) 
        if response.status_code != 200:
            print("OpenAI API error:", data)
            return ""

        description = ""
        try:
          description = data["output"][0]["content"][0]["text"].strip()
        except (KeyError, IndexError) as e:
          print("Could not parse response:", e)
          description = ""
        lines = [line.strip() for line in description.splitlines() if line.strip()]
        return "\n".join(lines[:3])

    except Exception as e:
        print("OpenAI API error:", e)
        return ""


def extract_weapon_type(description):
    for line in description.splitlines():
        if line.lower().startswith("weapon:"):
            weapon = line.split(":", 1)[1].strip()
            if weapon:
                return weapon
    return "weapon"


def send_weapon_alert(image_path):
    time_now = datetime.now().strftime("%d %b %Y, %I:%M:%S %p")

    description = describe_threat(image_path)
    weapon_type = extract_weapon_type(description)

    caption = (
        f"🚨🚨 WEAPON DETECTED 🚨🚨\n\n"
        f"⚠️ A {weapon_type} was detected on camera.\n"
        f"📍 Location: {CAMERA_LOCATION}\n"
        f"🕒 Time: {time_now}\n"
    )

    if description:
        caption += f"\n🔍 AI Details:\n{description}\n"
    else:
        caption += "\n🔍 AI Details: Could not generate description.\n"

    caption += "\n❗ Take cover and contact security/police immediately."

    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"

    results = []

    for chat_id in CHAT_IDS:
        try:
            with open(image_path, "rb") as photo:
                response = requests.post(
                    url,
                    data={
                        "chat_id": chat_id,
                        "caption": caption,
                    },
                    files={
                        "photo": photo,
                    },
                    timeout=15,
                )

            result = response.json()
            results.append({
                "chat_id": chat_id,
                "result": result
            })

            if result.get("ok"):
                print(f"Sent alert to {chat_id}")
            else:
                print(f"Failed to send to {chat_id}:", result)

        except Exception as e:
            print(f"Error sending to {chat_id}:", e)
            results.append({
                "chat_id": chat_id,
                "error": str(e)
            })

    return results


if __name__ == "__main__":
    print("Analysing test.jpg with OpenAI Vision...")
    print(send_weapon_alert("test.jpg"))
