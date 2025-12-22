import os
import requests
import time
import traceback
import re
import json
import base64
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client
from io import BytesIO

load_dotenv()

# --------- SLACK ENVS ------------
SLACK_BOT_TOKEN= os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN= os.getenv("SLACK_APP_TOKEN")
# --------- AI CONFIG ------------
AI_KEY = os.getenv("AI_KEY")
AI_BASE_URL = os.getenv("AI_BASE_URL")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL")
# ---------- MODERATION CONFIG ----------
MODERATION_URL = os.getenv("MODERATION_URL")
MODERATION_KEY = os.getenv("MODERATION_KEY")
# --------- TOOLS ------------
SEARCH_API_URL= os.getenv("SEARCH_API_URL")
SEARCH_API_KEY= os.getenv("SEARCH_API_KEY")
IMGGEN_MODEL = os.getenv("IMGGEN_MODEL")
# --------- MEMORY CONFIG ---------
SUPABASE_URL= os.getenv("SUPABASE_URL")
SUPABASE_KEY= os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


default_client = OpenAI(
    api_key=AI_KEY,
   base_url=AI_BASE_URL
)

moderation_client = OpenAI(
    api_key=MODERATION_KEY,
    base_url=MODERATION_URL
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

        msg_obj = image_response.choices[0].message
        content_text = ""
        
        if msg_obj.content:
            content_text = str(msg_obj.content)

        if len(content_text) < 10: 
            try:
                content_text = str(msg_obj.model_dump())
            except:
                content_text = str(msg_obj)

        b64_pattern = r'(data:image\/[^;]+;base64,[a-zA-Z0-9+/=]+)'
        b64_match = re.search(b64_pattern, content_text)

        if b64_match:
            print("Found Base64 string via Regex!")
            full_b64_url = b64_match.group(1)
            b64_string = full_b64_url.split('base64,')[1]
            try:
                return base64.b64decode(b64_string)
            except Exception as e:
                print(f"Regex found base64 but failed to decode: {e}")
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

    try:
        moderation = moderation_client.moderations.create(input=user_message)
        result = moderation.results[0]

        if result.flagged:
             categories = result.categories

             if categories.self_harm or categories.self_harm_instructions or categories.self_harm_intent:
              say(
                  text=f"I am unable to fufill your request. It looks like you're going through a hard time. Please check out this resource. https://hackclub.enterprise.slack.com/docs/T0266FRGM/F08HU1DD1AP. Remember, you are not alone. :ohneheart:",
                  thread_ts=thread_ts
              )
              return
        if result.flagged:     
            say(
                text=f"I cannot fulfill this request because it violates my content moderation policies.",
                thread_ts=thread_ts
            )
            return
    
    except Exception as e:
                    print("unable to call moderation API")

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
    
    msgs = [{"role": "system", 
    "content": f"""The assistant is named Symphony. You are a helpful, harmless assistant. 
You are currently talking to {user_name}.

You have access to the following tools:
- web_search: Use this to search for current information, news, facts, or anything you don't have knowledge about
- image_generate: Use this to create images based on user requests

Tool Usage Guidelines:
- Always use web_search when users ask about current events, recent information, or anything that requires up-to-date data
- Use image_generate when users ask you to create, generate, or make images

Image Generation Guidelines:
When using image_generate, ALWAYS optimize the prompt for best results:
- If the user's request is vague or short (e.g., "make a cat"), expand it into a detailed, high-quality prompt
- Include specific details about: style, lighting, composition, colors, mood, and artistic qualities
- Add descriptive adjectives and specify the medium (e.g., "digital art", "oil painting", "3D render", "photorealistic")
- Example transformation: "a cat" → "a majestic orange tabby cat with bright green eyes, sitting on a windowsill bathed in warm golden hour sunlight, highly detailed digital art, soft focus background, cozy atmosphere"
- For simple requests, enhance them; for already detailed requests, use them as-is."""
}]
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
                    status_msg = client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text=f"I am currently searching the web for your query. Please wait!"
                    )
                    the_result = search_the_web(arguments.get("query"))

                    client.chat_delete(channel=channel_id, ts=status_msg["ts"])

                elif function_name == "image_generate":
                    status_msg = client.chat_postMessage(
                        channel=channel_id,
                        thread_ts=thread_ts,
                        text=f"I am currently using {IMGGEN_MODEL} to generate your image. Please wait!"
                    )
                    prompt = arguments.get("prompt")
                    image_bytes = generate_img(prompt)

                    client.chat_delete(channel=channel_id, ts=status_msg["ts"])

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