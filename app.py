import streamlit as st
import pandas as pd
import json, time, requests

import pulsar
from astrapy import DataAPIClient

from openai import OpenAI
import instructor
from pydantic import BaseModel, Field

import folium
from streamlit_folium import st_folium

# Main app
st.set_page_config(page_title="Wikipedia - What's up in the world", page_icon="🌎")
col1, col2 = st.columns([0.8, 0.2])
with col1:
    st.title("What's up in the world")
with col2:
    st.image("https://upload.wikimedia.org/wikipedia/commons/6/63/Wikipedia-logo.png", use_column_width=True)
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(["Real-time updates", "Political news", "Celebrities", "Stock", "Search the world", "Chat with the world"])

#
# We use PyDantic and Instructor in combination with a LLM to find attributes and turn them into structured data.
# Attributes relative to source code
class Metadata(BaseModel):
    """Metadata of the content"""
    country: str = Field(..., description = "What is the country relevant to this content")
    city: str = Field(..., description = "What is the city relevant to this content")
    latitude: float = Field(..., description = "What is the latitude, ideally based on the city, otherwise the country")
    longitude: float = Field(..., description = "What is the longitude, ideally based on the city, otherwise the country")
    category: str = Field(..., description = "What news category does this content fall into, for instance Political, Sport, Celebrities, etc")
    sentiment: str = Field(..., description = "What is the sentiment of this content, on a scale of 0 to 100, 0 being negative and 100 being positive")

# Initialize the session state
if "stream" not in st.session_state:
    st.session_state.stream = []
if "langflow_endpoint" not in st.session_state:
    st.session_state.langflow_endpoint = ""
if "chat_thread" not in st.session_state:
    st.session_state.chat_thread = []

# Cache the Pulsar client and consumer
@st.cache_resource(show_spinner='Connecting to Pulsar')
def init_pulsar():
    client = pulsar.Client(st.secrets["PULSAR_SERVICE"], authentication=pulsar.AuthenticationToken(st.secrets["PULSAR_TOKEN"]))
    consumer = client.subscribe(st.secrets["PULSAR_TOPIC"], subscription_name='my-subscription-1')
    return client, consumer
client, consumer = init_pulsar()

# Cache the Astra DB Vector Store and collection
@st.cache_resource(show_spinner='Connecting to Astra')
def load_vector_store_collection():
    # Connect to the Vector Store
    client = DataAPIClient(st.secrets['ASTRA_DB_APPLICATION_TOKEN'])
    db = client.get_database_by_api_endpoint(st.secrets['ASTRA_DB_API_ENDPOINT'])
    # Get a collection
    collection = db.get_collection(st.secrets['ASTRA_COLLECTION'])
    return collection
collection = load_vector_store_collection()

# Construct and show a wiki update
def show_wiki_update(stream, placeholder):
    data = stream[-10:][::-1]
    content = ""
    for item in data:
        content += f"**[{item['title']}]({item['source']})**\\\n📅&nbsp;&nbsp;{item['date']}&nbsp;&nbsp;&nbsp;🕑&nbsp;{item['timestamp'].split('T')[1].split('.')[0]}&nbsp;&nbsp;&nbsp;#️⃣&nbsp;&nbsp;{item['count']}\n\n *{item['content'][0:400]}*...\n\n"
    placeholder.markdown(content)

# Get the wiki updates from the pulsar stream
# We keep on trying to get the updates until we get them all or the timeout is reached
def show_wiki_updates(placeholder):
    try:
        while True:
            msg = consumer.receive(timeout_millis=1000)  # Set a timeout to avoid blocking indefinitely
            if msg:
                data = json.loads(msg.data())
                data["count"] = len(st.session_state.stream) + 1
                st.session_state.stream.append(data)
                consumer.acknowledge(msg)
                show_wiki_update(st.session_state.stream, placeholder)
            else:
                break  # Exit the loop if no message is received within the timeout
    except pulsar.Timeout:
        pass  # Handle timeout exception if no messages are available
    
# Chat with the world
# Ask a question and get a full response
def show_chat_qa(question, date, answer_placeholder, sources_placeholder):
    # First find relevant information from the Vector Database
    filter = {}
    if date:
        filter = {
            "metadata.date": str(date)
        }
    results = collection.find(
        filter,
        sort={
            "$vectorize": question
        },
        limit=10,
        projection={
            "content",
            "metadata.title", 
            "metadata.source", 
            "metadata.date"
        },
        include_similarity=True
    )

    # Construct the context
    context = ""
    sources = ""
    for result in results:
        context += f"{result['metadata']['title']}\n{result['content']}\n\n"
        sources += f"**[{result['metadata']['title']}]({result['metadata']['source']})**&nbsp;&nbsp;&nbsp;📅&nbsp;&nbsp;{result['metadata']['date'] if result['metadata'].get('date') else 'Not provided'}&nbsp;&nbsp;&nbsp;📈&nbsp;{round(result['$similarity'] * 100, 1)}%\\\n"

    # Now pass the context to the Chat Completion
    client = OpenAI(api_key=st.secrets['OPENAI_API_KEY'])
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": "You're an expert in world news and you specialize in summarizing information from the news."},
            {"role": "system", "content": "Only use the information provided in the context to answer the question. When there is no relevant information, just say so."},
            {"role": "system", "content": "When helpful, make use of captions or titles to better understand the content. Also you can make use of numbered lists to better structure the information."},
            {"role": "user", "content": f"Context: {context}"},
            {"role": "user", "content": f"Question: {question}"}
        ],
        stream=True
    )

    streaming_content = ""
    for chunk in response:
        chunk_content = chunk.choices[0].delta.content
        if chunk_content is not None:
            streaming_content += chunk_content
            answer_placeholder.markdown(f"{streaming_content}▌")

    answer_placeholder.markdown(f"{streaming_content[:-1]}")
    sources_placeholder.markdown(f"#### Sources used\n{sources[:-2]}")

# Get the content locations from the results using a structured parser (instructor) and a structured LLM
def get_metadata(title, content):
    article = f"Title: {title}\nContent: {content}"
    client = instructor.from_openai(OpenAI(api_key=st.secrets['OPENAI_API_KEY']))
    results = client.chat.completions.create(
        model="gpt-4o",
        response_model=Metadata,
        messages=[
            {"role": "system", "content": "You're an expert in location data and you specialize in understanding where things are located based on the content"},
            {"role": "system", "content": "You'also specialize in understaning what news category the content falls into, and what the sentiment of the content is."},
            {"role": "user", "content": f"Only use the following content, when relevant augmented with public knowledge: {article}"},
            {"role": "user", "content": "Extract the requested metadata from the provided content into a JSON format"}
        ]
    )
    json_result = results.model_dump()
    json_result["title"] = title
    json_result["content"] = content
    return json_result

def show_search_results(results, placeholder):
    all_metadata = []

    with placeholder:
        for result in results:
            metadata = get_metadata(result['metadata']['title'], result['content'])
            all_metadata.append(metadata)
            sentiment_emoji = "😊" if int(metadata['sentiment']) > 55 else "😞" if int(metadata['sentiment']) < 45 else "😐"
            st.markdown(f"""**[{result['metadata']['title']}]({result['metadata']['source']})**\\
📅&nbsp;&nbsp;{result['metadata']['date'] if result['metadata'].get('date') else 'Not provided'}&nbsp;&nbsp;&nbsp;
📈&nbsp;{round(result['$similarity'] * 100, 1)}%&nbsp;&nbsp;&nbsp;
📍&nbsp;{metadata['country']}&nbsp;&nbsp;&nbsp;
🗂️&nbsp;{metadata['category']}&nbsp;&nbsp;&nbsp;
{sentiment_emoji}&nbsp;{metadata['sentiment']}\n\n
*{result['content'][0:400]}*...\n\n"""
            )

        st.subheader("Where did it happen?")
        center = [0, 0]
        if all_metadata:
            avg_latitude = sum(loc["latitude"] for loc in all_metadata) / len(all_metadata)
            avg_longitude = sum(loc["longitude"] for loc in all_metadata) / len(all_metadata)
            center = [avg_latitude, avg_longitude]

        m = folium.Map(location=center, zoom_start=2)
        
        for loc in all_metadata:
            folium.Marker(
                location=[loc["latitude"], loc["longitude"]],
                icon=folium.Icon(color="red", icon="info-sign"),
                tooltip=f"{loc["title"]}",
                popup=f"{loc["content"][0:50]}..."
            ).add_to(m)
        
        m.fit_bounds([[loc["latitude"], loc["longitude"]] for loc in all_metadata])
    
        st_folium(m, width=700, height=500, returned_objects=[])

# Real-time stream
with tab1:
    subscribed = st.toggle("Subscribe to real-time updates", value=False)
    placeholder = st.empty()
    if subscribed:
        while True:
            show_wiki_updates(placeholder)
            time.sleep(1)

# Politics
with tab2:
    col1, col2, col3 = st.columns(3, vertical_alignment="bottom")
    selected_date = col1.date_input("Select a date", value=pd.to_datetime("today"), key="politics")
    article_count = col2.number_input("Number of articles", value=5, key="politics_article_count")
    update_button = col3.button("Show me!", key="update_politics", use_container_width=True)
    placeholder = st.container()

    if selected_date and update_button:
        results = collection.find(
            {
                "metadata.date": str(selected_date)
            },
            sort={
                "$vectorize": "content that contains political information"
            },
            projection={
                "content",
                "metadata.title", 
                "metadata.source", 
                "metadata.date"
            },
            include_similarity=True,
            limit=article_count
        )

        show_search_results(results, placeholder)

# Celebrities
with tab3:
    col1, col2, col3 = st.columns(3, vertical_alignment="bottom")
    selected_date = col1.date_input("Select a date", value=pd.to_datetime("today"), key="celebrities")
    article_count = col2.number_input("Number of articles", value=5, key="celebrities_article_count")
    update_button = col3.button("Show me!", key="update_celebrities", use_container_width=True)
    placeholder = st.container()

    if selected_date and update_button:
        results = collection.find(
            {
                "metadata.date": str(selected_date)
            },
            sort={
                "$vectorize": "content about celebrities"
            },
            projection={
                "content",
                "metadata.title", 
                "metadata.source", 
                "metadata.date"
            },
            include_similarity=True,
            limit=article_count
        )

        show_search_results(results, placeholder)

with tab4:
    col1, col2, col3 = st.columns(3, vertical_alignment="bottom")
    selected_date = col1.date_input("Select a date", value=pd.to_datetime("today"), key="stock")
    article_count = col2.number_input("Number of articles", value=5, key="stock_article_count")
    update_button = col3.button("Show me!", key="update_stock", use_container_width=True)
    placeholder = st.container()

    if selected_date and update_button:
        results = collection.find(
            {
                "metadata.date": str(selected_date)
            },
            sort={
                "$vectorize": "content that has an impact on stock prices"
            },
            projection={
                "content",
                "metadata.title", 
                "metadata.source", 
                "metadata.date"
            },
            include_similarity=True,
            limit=article_count
        )

        show_search_results(results, placeholder)

# Search the world
with tab5:
    question = st.selectbox("Select a question", options=["What's up in the world?", "Construct a news bulletin about positive information", "Where is the next big earthquake?", "What's the latest news on AI?", "Anything happening in Europe?", "Ask your own question..."])
    custom_question = st.text_input("Ask the world a question", disabled=question != "Ask your own question...")
    col1, col2, col3 = st.columns([0.3, 0.3, 0.4], vertical_alignment="bottom")
    date_toggle = col1.toggle("Filter by date", value=False)
    date = col2.date_input("Select a date", value=pd.to_datetime("today"), key="chat", disabled=not date_toggle)
    update_button = col3.button("Show me!", key="update_chat", use_container_width=True)
    answer_placeholder = st.empty()
    sources_placeholder = st.empty()

    question = custom_question if question == "Ask your own question..." else question
    if update_button:
        show_chat_qa(question, date if date_toggle else None, answer_placeholder, sources_placeholder)

# Chat with the world
with tab6:
    langflow_endpoint = st.text_input("Langflow REST endpoint", key="langflow_endpoint")
    if langflow_endpoint and langflow_endpoint.startswith("http"):
        messages = st.container(height=600)

        if question := st.chat_input("Say something"):

            for item in st.session_state.chat_thread:
                messages.chat_message(item['role']).write(item['content'])

            st.session_state.chat_thread.append({
                'role': 'user',
                'content': question
            })
            messages.chat_message('user').write(question)

            # Call Langflow REST API
            payload = {
                "input_value": question,
                "output_type": "chat",
                "input_type": "chat"
            }
            response = requests.post(st.session_state.langflow_endpoint, headers={"Authorization": f"Bearer {st.secrets['ASTRA_DB_APPLICATION_TOKEN']}"}, json=payload)
            result = response.json()
            print(result)
            result = result['outputs'][0]['outputs'][0]['outputs']['message']['message']['text']

            st.session_state.chat_thread.append({
                'role': 'assistant',
                'content': result
            })
            messages.chat_message('assistant').write(result)