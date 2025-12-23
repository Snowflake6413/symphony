import os
import time
import requests
import time
import datetime
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
ALLOWED_MODELS = ["qwen/qwen3-32b", "moonshotai/kimi-k2-instruct-0905", "openai/gpt-oss-120b", "meta-llama/llama-4-scout-17b-16e-instruct", "meta-llama/llama-4-maverick-17b-128e-instruct" ]
# ---------- MODERATION CONFIG ----------
MODERATION_URL = os.getenv("MODERATION_URL")
MODERATION_KEY = os.getenv("MODERATION_KEY")
# --------- TOOLS ------------
SEARCH_API_URL= os.getenv("SEARCH_API_URL")
SEARCH_API_KEY= os.getenv("SEARCH_API_KEY")
IMGGEN_MODEL = os.getenv("IMGGEN_MODEL")
LINKUP_API_KEY = os.getenv("LINKUP_API_KEY")
# --------- MEMORY CONFIG ---------
SUPABASE_URL= os.getenv("SUPABASE_URL")
SUPABASE_KEY= os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
# ----------- MISC ----------
ALLOWED_CHANNEL_ID = os.getenv("ALLOWED_CHANNEL_ID")


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
    },
    {
        "type": "function",
        "function": {
            "name": "deep_research",
            "description": "Perform a deep, comprehensive research on a topic. Use this for complex queries, report generation, or when a simple web search is insufficient.",
            "parameters": {
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "A query to search deeply.",
                    },
                },
                "required": ["prompt"],
            }
            
        },
    },
    {
        "type": "function",
        "function": {
            "name": "url_scrape",
            "description": "Scrape content from a specific URL using Linkup. Use this when a user provides a specific link they want you to read.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to scrape.",
                    }
                },
                "required": ["url"],
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

def download_slack_img(file_url, token):
    try: 
        res = requests.get(file_url, headers={"Authorization": f"Bearer {token}"})
        if res.status_code == 200:
            return base64.b64encode(res.content).decode('utf-8')
        return None
    except Exception as e:
        print("Failed to download IMG")
        return None

def do_deep_research(query):
    print (f"deeply researching {query} via linkup :3")
    try:
        response = requests.post(
            f"https://api.linkup.so/v1/fetch",
            headers={
                'Authorization': f'Bearer {LINKUP_API_KEY}',
                'Content-Type': 'application/json',
            },
            json ={
                "q": query,
                "depth": 'deep',
                "includeInlineCitations": 'true',
                "includeSources": 'true',
            },
            )

        response.raise_for_status()
        data = response.json()

        return data.get("markdown", "No content")
    except Exception as e:
        print(f"*waah* unable to deep search. {e}")
        return(f"Unable to deep research {query}")

def scrape_url_with_linkup(url):
    print (f"scraping {url} via linkup :3")
    try:
        response = requests.post(
            f"https://api.linkup.so/v1/fetch",
            headers={
                'Authorization': f'Bearer {LINKUP_API_KEY}',
                'Content-Type': 'application/json',
            },
            json ={
                "url": url,
                "renderJs": True,
            },
            )

        response.raise_for_status()
        data = response.json()

        return data.get("markdown", "No content")
    except Exception as e:
        print(f"*waah* unable scrape URL. {e}")
        return(f"Unable to scrape {url}")






@app.event("member_joined_channel")
def channel_join_handler(event, say, logger, ack, context, client):
    user_id = event["user"]
    channel_id = event["channel"]
    bot_user_id = context.get("bot_user_id")

    if user_id == bot_user_id:
             if channel_id != ALLOWED_CHANNEL_ID:
                 try:
                    say(f"Hi, it looks like you added me to a channel. I am only authorized to do tasks in <#{ALLOWED_CHANNEL_ID}. I will be leaving this channel now, goodbye!")
                    client.conversations_leave(channel=channel_id)
                 except Exception as e:
                     print(f"Unable to leave channel {e}")


     

@app.event("message")
def handle_msg_event(body, logger):
    logger.info(body)

@app.command("/model")
def switch_model(ack, body, respond, logger, command):
    ack()
    logger.info(body)
    requested_model = command["text"].strip()
    channel_id = command["channel_id"]

    if not requested_model:
        respond(f"Current available models: {', '.join(ALLOWED_MODELS)}\nUsage: `/model moonshotai/kimi-k2-0905`")
        return

    if requested_model not in ALLOWED_MODELS:
        respond(f"Invalid model {requested_model}. Please choose from: {', '.join(ALLOWED_MODELS)}")
        return

    try:
        supabase.table("bot_settings").upsert({
            "channel_id": channel_id,
            "selected_model": requested_model
        }).execute()
        respond(f"Success! I have switched the model to {requested_model} for this channel.")
    except Exception as e:
        print(f"Unable to switch model! {e}")
        respond(f"Failed to switch to model. {e}")


@app.command("/symphony-help")
def help_msg(ack, respond, logger, body):
    ack()
    logger.info(body)

    blocks = [
		{
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": "Hi! My name is Symphony! Here is some things I can assist you with! :agahi:",
				"emoji": True
			}
		},
		{
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": "1. Chat: Just mention me to talk.",
				"emoji": True
			}
		},
		{
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": "2. Search and Deep Research: I can search the web and do deep research for more information",
				"emoji": True
			}
		},
		{
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": "3. Generate Images: I can generate images you request with ",
				"emoji": True
			}
		},
        {
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": "4. URL Scraping: I can search specific URLs for more information. ",
				"emoji": True
			}
		},
		{
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": "5. Vision: I can see images. Upload an image and ask me about it.",
				"emoji": True
			}
		}
	]
    respond(blocks=blocks)

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
@app.event("message")
def ai_msg(event, say, body, client, ack, respond):

    if event.get("type") == "message" and event.get("channel_type") != "im":
        return
    

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
    files = event.get("files", [])
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
    

    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    msgs = [{"role": "system", 
    "content": f"""The assistant is named Symphony. You are a helpful, harmless assistant. 
You are currently talking to {user_name}.

The current time is {current_time}

You have access to the following tools:
- web_search: Use this to search for current information, news, facts, or anything you don't have knowledge about.
- deep_research: Use this for complex topics, comprehensive reports, market analysis, or when the user specifically asks for "research" or a "deep dive".
- image_generate: Use this to create images based on user requests.
- url_scrape: Use this to extract content from a specific URL provided by the user.

Tool Usage Guidelines:
- Always use web_search when users ask about current events, recent information, or anything that requires up-to-date data.
- If the query is too complex, use deep_research to throughly research the query.
- Use url_scrape when the user provides a specific link/URL and asks you to read, summarize, or analyze its contents.
- Use image_generate when users ask you to create, generate, or make images.
- If using deep_resarch, make sure the output is less than 3001 characters.

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

        current_img_data = None
        if files:
            for file in files:
                if file.get("mimetype", "").startswith("image/"):
                    print(f"Got img :3 {file.get('name')}")
                    prv_url = file.get("url_private")
                    if prv_url:
                        b64_img = download_slack_img(prv_url, SLACK_BOT_TOKEN)
                        if b64_img:
                            current_img_data = b64_img
                            break
        if current_img_data:
            last_msg = msgs[-1]
            text_content = last_msg["content"]

            vision_content = [
                {"type": "text", "text": text_content},
                {
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/jpeg;base64,{current_img_data}"
                }
            }
            ]
            msgs[-1]["content"] = vision_content
        

    try:
        client.reactions_add(
            name="typingresponse",
            channel=channel_id,
            timestamp=msg_ts
        )
    except Exception as e:
        print(f"Unable to add reaction. {e}")

    target_model = DEFAULT_MODEL
    try:
        settings_res = supabase.table("bot_settings") \
            .select("selected_model") \
            .eq("channel_id", channel_id) \
            .execute()
        if settings_res.data and len(settings_res.data) > 0:
            target_model = settings_res.data[0]["selected_model"]
    except Exception as e:
        print(f"Failed to fetch custom model, defaulting: {e}")

    start_time = time.time()
    
    try:
        response=default_client.chat.completions.create(
            model=target_model,
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
                
                elif function_name == "url_scrape":
                 status_msg = client.chat_postMessage(
                     channel=channel_id,
                     thread_ts=thread_ts,
                     text=f"I'm currently scraping and searching the URL."
                 )
                 url = arguments.get("url")
                 the_result = scrape_url_with_linkup(url)
                 client.chat_delete(channel=channel_id, ts=status_msg["ts"])

                
                elif function_name == "deep_research":
                 status_msg = client.chat_postMessage(
                     channel=channel_id,
                     thread_ts=thread_ts,
                     text=f"I'm currenly deep researching on the top you requested. This might take a few minutes."
                 )
                 query = arguments.get("query")
                 the_result = do_deep_research(query)
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

        end_time = time.time()
        latency = round(end_time - start_time, 2)

        blocks = [
		{
			"type": "section",
			"text": {
				"type": "mrkdwn",
				"text": f"{ai_rspnd}"
			}
		},
		{
			"type": "divider"
		},
		{
			"type": "section",
			"text": {
				"type": "plain_text",
				"text": f"Model: {target_model} | Latency: {latency}",
				"emoji": True
			}
		}
	]


        say(blocks=blocks, thread_ts=thread_ts)

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