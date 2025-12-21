import os
import requests
import time
import json
from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler
from openai import OpenAI
from dotenv import load_dotenv
from supabase import create_client, Client

load_dotenv()

SLACK_BOT_TOKEN= os.getenv("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN= os.getenv("SLACK_APP_TOKEN")
AI_KEY = os.getenv("AI_KEY")
SEARCH_API_URL= os.getenv("SEARCH_API_URL")
SEARCH_API_KEY= os.getenv("SEARCH_API_KEY")
AI_BASE_URL = os.getenv("AI_BASE_URL")
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL")
SUPABASE_URL= os.getenv("SUPABASE_URL")
SUPABASE_KEY= os.getenv("SUPABASE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


def_client = OpenAI(
    api_key=AI_KEY,
   base_url=AI_BASE_URL
)

app=App(token=SLACK_BOT_TOKEN)

tools = [
    {
        "type": "function",
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
        },
    },
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
        response=def_client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=msgs,
            tools=tools,
            tool_choice="auto"
        )
        ai_rspnd = response.choices[0].message.content
        tool_caller = ai_rspnd.tool_calls

        if tool_caller:
            msgs.append(ai_rspnd)

            for tool_call in tool_caller:
                function_name = tool_call.function.name
                if function_name == "web_search":
                    arguments = json.loads(tool_call.function.arguments)
                    the_result = search_the_web(arguments.get("query"))

                msgs.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": function_name,
                    "content": the_result
                })

            final_ai_rspnd = def_client.chat.completions.create(
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
        say(text=f"Unable to call OpenAI {e}", thread_ts=thread_ts)














































if __name__ == "__main__":
    SocketModeHandler(app, os.environ["SLACK_APP_TOKEN"]).start()