# Enterprise-grade real-time RAG pipeline on Wikipedia
This project is part of the following Github projects:
- [Wikipedia - What's up in the world? (Back-end)](https://github.com/michelderu/wikipedia-pulsar-astra)
- [Wikipedia - What's up in the world? (Front-end)](https://github.com/michelderu/wikipedia-streamlit) **(THIS PROJECT)**

## Introduction
Wikipedia is an amazing source of information 🧠. With all the real-time additions and updates of articles, it's a valuable source of information about what's happening in the world 🌍. Perhaps even faster than the news 📰. And that's what this project is all about: Accessing the most relevant articles from Wikipedia to answer your questions.

Additionally, this project is a good example of how to build a rock-solid, scalable, and performant enterprise architecture 🚀. It makes use of the following technologies:
- [Astra Streaming](https://www.datastax.com/products/datastax-astra-streaming): A fully managed Pulsar as a service that provides a real-time pub-sub messaging platform.
- [Astra DB](https://www.datastax.com/products/datastax-astra-db): A fully managed Cassandra DB as a service.
- [Streamlit](https://streamlit.io/): A Python library for prototyping web apps.

🤩 Notable concepts used in this project are:
- Back-end ⏪
    - Publishing Wikipedia updates in real-time to a Pulsar Topic - Fire and forget with delivery guarantees.
    - [Pulsar Functions](https://pulsar.apache.org/docs/functions-overview/): Enriching the data and JSON structure of the Wikipedia articles.
    - Using a Pulsar Sink (function) to store the data in Astra DB using the Data API.
- Front-end ⏩
    - Using -just- Vector Search to classify data into news topics in real-time with no lag.
    - Using [Instructor](https://github.com/jxnl/instructor) + an LLM to enrich the data further including Sentiment Analysis.
    - Subscribing to the Pulsar Topic showing real-time Wikipedia updates flowing in.
    - [Astra Vector DB](https://docs.datastax.com/en/astra-db-serverless/get-started/concepts.html): A [Forrester Wave Leader](https://www.datastax.com/blog/forrester-wave-names-datastax-leader-vector-databases) in the Vector Database category.
    - [Astra Vectorize](https://docs.datastax.com/en/astra-db-serverless/databases/embedding-generation.html): Auto-generate embeddings with vectorize.
    - Providing a Chat with Wikipedia using an LLM.

## Why is real-time streaming so important?
A lot of people are struggling to make the leap from RAG prototyping to production hardened RAG pipelines. Streaming solves that.
> Streaming provides a no-more-sleepness-nights fire-and-forget way of updating your data.

It provides guarantees for delivery with just 2 lines of code. Additionally, it fully decouples apps and backbones which still keep working if one or the other is temporarily unavailable.

## Screenshots
![Application Interface](./assets/app-screenshot-1.png)
![Application Interface](./assets/app-screenshot-2.png)
![Application Interface](./assets/app-screenshot-3.png)

## The architecture
This application is the back-end for the Wikipedia - What's up in the world? project. It consists of two parts:
1. A [Pulsar Streaming project](https://github.com/michelderu/wikipedia-pulsar-astra) that consists of the following components:
    - A Pulsar producer that produces the Wikipedia articles to a Pulsar topic.
    - A Pulsar function that enriches the Wikipedia articles with and OpenAI LLM.
    - A Pulsar sink that stores the enriched Wikipedia articles in an Astra DB collection.
2. A [Streamlit application](https://github.com/michelderu/wikipedia-streamlit) **(THIS PROJECT)** that allows you to search the Wikipedia articles and chat with the articles.

![Architecture](./assets/architecture.png)

## How to run the application

### Create a virtual environment
```bash
python -m venv .venv
source .venv/bin/activate
```
Or use your favorite IDE's built-in function to create a virtual environment.

### Install the dependencies
```bash
pip install -r requirements.txt
```

### Run the application
Be sure to have the back-end producing some articles before running the front-end.
```bash
streamlit run app.py
```