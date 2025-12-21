import os
import time
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

SLACK_BOT_TOKEN= os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN= os.getenv("SLACK_APP_TOKEN")
AI_KEY = os.getenv("AI_KEY")
AI_BASE_URL = os.getenv("AI_BASE_URL")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL")

def_client = OpenAI(
    api_key=AI_KEY,
   base_url=AI_BASE_URL
)

app=App(token=SLACK_BOT_TOKEN)


@app.message("Ping")
def hello_back(ack, say, client, body, event):
    channel_id = event["channel"]
    message_ts = event["ts"]
    ack()
    say("Pong!")
    client.reactions_add(
        name="agahi",
        channel=channel_id,
        timestamp=message_ts
    )


@app.event("app_mention")
def ai_msg(event, say, body, client, ack, respond):
    user_message=event['text']
    thread_ts=event.get("thread_ts", event["ts"])
    channel_id=event["channel"]
    msg_ts=event["ts"]
    
    ack()

    try:
        client.reactions_add(
            name="typingresponse",
            channel=channel_id,
            timestamp=msg_ts
        )
    except Exception as e:
        print(f"Unable to add reaction. {e}")
    
    try:
        response=def_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": "The assistant is named Symphony. You are a helpful, harmless assistant."},
                {"role" : "user", "content": user_message}
            ]
        )
        ai_rspnd = response.choices[0].message.content

        say(text=ai_rspnd, thread_ts=thread_ts)

        client.reactions_remove(
            name="typingresponse",
            channel=channel_id,
            timestamp=msg_ts
        )
    except Exception as e:
        print(f"failed to get response {e}")
        say(text=f"Unable to call OpenAI {e}", thread_ts=thread_ts)














































if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()