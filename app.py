import os
import requests
import time
import traceback
import json
import base64
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
from io import BytesIO

load_dotenv()

SLACK_BOT_TOKEN= os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN= os.getenv("SLACK_APP_TOKEN")
AI_KEY = os.getenv("AI_KEY")
SEARCH_API_URL= os.getenv("SEARCH_API_URL")
SEARCH_API_KEY= os.getenv("SEARCH_API_KEY")
AI_BASE_URL = os.getenv("AI_BASE_URL")
IMGGEN_MODEL = os.getenv("IMGGEN_MODEL")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL")
SUPABASE_URL= os.getenv("SUPABASE_URL")
SUPABASE_KEY= os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


default_client = OpenAI(
    api_key=AI_KEY,
   base_url=AI_BASE_URL
)

app=App(token=SLACK_BOT_TOKEN)

tools = [
    {
        "type": "function",
        "function" : {
            "name": "web_search",
            "description": "Search the world wide web for information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                            "description": "The search query.",
                },
            },
            "required": ["query"],
           }
        },
    },
    {
        "type": "function",
        "function": {
            "name": "image_generate",
            "description": "Generates an image with Nano Banana based on a detailed text description.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "A prompt for the image.",
                    },
                },
                "required": ["prompt"],
            }
        },
    }
]


def search_the_web(query):
    print(f"currently searching for {query} :3")
    try: 
        response = requests.get(
         f"{SEARCH_API_URL}?q={query}",
         headers={'Authorization': f'Bearer {SEARCH_API_KEY}'}
        )

        response.raise_for_status()
        
        return response.text
    except Exception as e:
        print(f"*cries* unable to search for {query}. {e}")
        return f"Unable to search."

def generate_img(prompt):
    print(f"calling nano banana to generate {prompt} :3")
    try:
        image_response = default_client.chat.completions.create(
            model=IMGGEN_MODEL,
            messages=[{"role": "user", "content": prompt}],
            extra_body={
                "modalities": ["image"],
                "response_format": "b64_json" 
            },
            timeout=60
        )


        print(f"RAW AI RESPONSE: {image_response}")

        content = image_response.choices[0].message.content

        print(f"Message object: {image_response.choices[0].message}")
        print(f"Message attributes: {dir(image_response.choices[0].message)}")

        if not content:
            print("content is empty!")
            return None
        
        if "base64," in content:
            content = content.split("base64,")[1]

            content = content.strip().strip('"').strip("'")


        # TRY THE DECODE.......................hurr
        try:
            return base64.b64decode(content)
        except Exception as decode_err:
            print(f"cannot decode the code directly :( trying the json method... {decode_err}")

            try:
                json_data = json.loads(content)
                if "b64_json" in json_data:
                    return base64.b64decode(json_data["b64_json"])
            except:
                print("failed to do the json method")

        print("unable to decode IMG")
        return None


    
        
    except Exception as e:
        print(f"waahhh! cannot generate image! {e}")
        traceback.print_exc()
        return None


@app.event("message")
def handle_msg_event(body, logger):
    logger.info(body)


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
    user_id = event['user']

    try:
        user_info = client.users_info(user=user_id)
        profile = user_info['user']['profile']
        user_name = profile.get('display_name') or profile.get('real_name')
    except Exception as e:
        print(f"Cannot fetch user info. {e}")
        user_name = "User"

    user_message=event['text']
    thread_ts=event.get("thread_ts", event["ts"])
    channel_id=event["channel"]
    msg_ts=event["ts"]
    
    ack()

    supabase.table("chat_mem").insert({
        "channel_id": channel_id,
        "thread_ts": thread_ts,
        "user_name": user_name,
        "role": "user",
        "content": user_message
    }).execute()


    mem_get = supabase.table("chat_mem") \
     .select("role, content") \
     .eq("thread_ts", thread_ts) \
     .order("created_at", desc=False) \
     .limit(10) \
     .execute()
    
    msgs = [{"role": "system", "content": f"The assistant is named Symphony. You are a helpful, harmless assistant. You are currently talking to {user_name}."}]
    for row in mem_get.data:
        msgs.append({"role": row["role"], "content": row ["content"]})

    try:
        client.reactions_add(
            name="typingresponse",
            channel=channel_id,
            timestamp=msg_ts
        )
    except Exception as e:
        print(f"Unable to add reaction. {e}")
    
    try:
        response=default_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=msgs,
            tools=tools,
            tool_choice="auto"
        )
        ai_rspnd = response.choices[0].message
        tool_caller = ai_rspnd.tool_calls

        if tool_caller:
            msgs.append(ai_rspnd)

            for tool_call in tool_caller:
                function_name = tool_call.function.name
                arguments = json.loads(tool_call.function.arguments)
                if function_name == "web_search":
                    the_result = search_the_web(arguments.get("query"))
                elif function_name == "image_generate":
                    prompt = arguments.get("prompt")
                    image_bytes = generate_img(prompt)

                    if image_bytes:
                        try:

                            file_obj = BytesIO(image_bytes)

                            client.files_upload_v2(
                                channel=channel_id,
                                thread_ts=thread_ts,
                                title=prompt,
                                file=file_obj,
                                filename="GenAIGeneratedIMG.png"
                            )
                            the_result = "Image generated and uploaded to Slack."
                        except Exception as e:
                            print(f"Failed to upload image. {e}")
                            the_result = f"Image genereated but failed to upload to Slack. {e}"
                    else:
                                the_result = "Failed to generate image!"

                msgs.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": the_result
                })

            final_ai_rspnd = default_client.chat.completions.create(
                model=DEFAULT_MODEL,
                messages=msgs,
            )
            ai_rspnd = final_ai_rspnd.choices[0].message.content
        else:
            ai_rspnd = ai_rspnd.content

        supabase.table("chat_mem").insert({
            "channel_id": channel_id,
        "thread_ts": thread_ts,
        "role": "assistant",
        "content": ai_rspnd
        }).execute()

        say(text=ai_rspnd, thread_ts=thread_ts)

        client.reactions_remove(
            name="typingresponse",
            channel=channel_id,
            timestamp=msg_ts
        )
    except Exception as e:
        print(f"failed to get response {e}")
        say(text=f"Unable to call AI service. : {e}", thread_ts=thread_ts)














































if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()